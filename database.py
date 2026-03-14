"""
Модуль для работы с базой данных SQLite
Асинхронный пул соединений с автоматическим управлением
"""
import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import json

logger = logging.getLogger(__name__)

class Database:
    """
    Асинхронный менеджер базы данных с пулом соединений
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.pool_size = 10
        self._connection_pool = []
        self._in_use = set()
        
    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        async with self._get_connection() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    subscription_end TIMESTAMP,
                    is_forever BOOLEAN DEFAULT 0,
                    proxies_received INTEGER DEFAULT 0,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_paid INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'ru',
                    is_blocked BOOLEAN DEFAULT 0
                )
            ''')
            
            # Таблица прокси
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_link TEXT UNIQUE,
                    server TEXT,
                    port INTEGER,
                    secret TEXT,
                    is_working BOOLEAN DEFAULT 1,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check TIMESTAMP,
                    source TEXT,
                    check_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    country TEXT
                )
            ''')
            
            # Таблица платежей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount_stars INTEGER,
                    period_days INTEGER,
                    payment_id TEXT UNIQUE,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'completed',
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица прокси-пула для анонимности
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS proxy_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_address TEXT UNIQUE,
                    type TEXT,
                    last_used TIMESTAMP,
                    is_working BOOLEAN DEFAULT 1,
                    fail_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    country TEXT,
                    speed REAL
                )
            ''')
            
            # Таблица статистики
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE,
                    new_users INTEGER DEFAULT 0,
                    payments_count INTEGER DEFAULT 0,
                    payments_sum INTEGER DEFAULT 0,
                    proxies_found INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0
                )
            ''')
            
            # Индексы для ускорения
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription_end)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_proxies_working ON proxies(is_working)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(date)')
            
            await conn.commit()
            
        logger.info("База данных инициализирована")
    
    @asynccontextmanager
    async def _get_connection(self):
        """Контекстный менеджер для получения соединения из пула"""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()
    
    async def execute(self, query: str, params: tuple = ()) -> Optional[int]:
        """Выполняет SQL запрос"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.lastrowid
    
    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Получает одну запись"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        """Получает все записи"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Методы для работы с пользователями
    
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
    async def activate_trial(self, user_id: int):
        """Активирует пробный период для пользователя"""
    async def activate_trial(self, user_id: int):
        """Активирует пробный период для пользователя"""
        user = await self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        
        if user and user.get("trial_used"):
            return False
        
        from datetime import datetime, timedelta
        trial_end = datetime.now() + timedelta(days=2)
        
        await self.execute(
            "UPDATE users SET subscription_end = ?, trial_used = 1 WHERE user_id = ?",
            (trial_end, user_id)
        )
        return True

    async def check_trial_available(self, user_id: int) -> bool:
        """Проверяет, доступен ли пробный период"""
        user = await self.fetch_one("SELECT trial_used FROM users WHERE user_id = ?", (user_id,))
        return not (user and user.get("trial_used"))

        """Получает пользователя или создает нового"""
        user = await self.fetch_one(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )
        
        if not user:
            await self.execute(
                """INSERT INTO users (user_id, username, first_name) 
                   VALUES (?, ?, ?)""",
                (user_id, username, first_name)
            )
            user = await self.fetch_one(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            
            # Обновляем статистику
            await self.update_daily_stats('new_users')
        
        return user
    
    async def update_user_subscription(self, user_id: int, days: int, forever: bool = False):
        """Обновляет подписку пользователя"""
        if forever:
            await self.execute(
                "UPDATE users SET is_forever = 1 WHERE user_id = ?",
                (user_id,)
            )
        else:
            subscription_end = datetime.now() + timedelta(days=days)
            await self.execute(
                """UPDATE users SET subscription_end = ? 
                   WHERE user_id = ?""",
                (subscription_end, user_id)
            )
    
    async def check_subscription(self, user_id: int) -> bool:
        """Проверяет активна ли подписка у пользователя"""
        user = await self.fetch_one(
            "SELECT subscription_end, is_forever FROM users WHERE user_id = ?",
            (user_id,)
        )
        
        if not user:
            return False
        
        if user['is_forever']:
            return True
        
        if user['subscription_end']:
            end_date = datetime.fromisoformat(user['subscription_end'])
            return end_date > datetime.now()
        
        return False
    
    # Методы для работы с прокси
    
    async def add_proxy(self, proxy_link: str, server: str, port: int, secret: str, source: str) -> bool:
        """Добавляет новый прокси"""
        try:
            await self.execute(
                """INSERT INTO proxies (proxy_link, server, port, secret, source) 
                   VALUES (?, ?, ?, ?, ?)""",
                (proxy_link, server, port, secret, source)
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления прокси: {e}")
            return False
    
    async def get_working_proxies(self, limit: int = 10) -> List[Dict]:
        """Получает список рабочих прокси"""
        return await self.fetch_all(
            """SELECT * FROM proxies 
               WHERE is_working = 1 
               ORDER BY last_check DESC 
               LIMIT ?""",
            (limit,)
        )
    
    async def mark_proxy_checked(self, proxy_id: int, is_working: bool):
        """Обновляет статус проверки прокси"""
        await self.execute(
            """UPDATE proxies 
               SET last_check = CURRENT_TIMESTAMP, 
                   is_working = ?,
                   check_count = check_count + 1,
                   fail_count = CASE WHEN ? = 0 THEN fail_count + 1 ELSE fail_count END
               WHERE id = ?""",
            (is_working, is_working, proxy_id)
        )
    
    # Методы для статистики
    
    async def update_daily_stats(self, field: str, value: int = 1):
        """Обновляет дневную статистику"""
        today = datetime.now().date()
        
        # Проверяем есть ли запись за сегодня
        stats = await self.fetch_one(
            "SELECT * FROM stats WHERE date = ?",
            (today,)
        )
        
        if stats:
            await self.execute(
                f"UPDATE stats SET {field} = {field} + ? WHERE date = ?",
                (value, today)
            )
        else:
            await self.execute(
                f"INSERT INTO stats (date, {field}) VALUES (?, ?)",
                (today, value)
            )
    
    async def get_stats(self, days: int = 30) -> Dict:
        """Получает статистику за последние N дней"""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Общая статистика
        total_users = await self.fetch_one("SELECT COUNT(*) as count FROM users")
        active_subs = await self.fetch_one(
            "SELECT COUNT(*) as count FROM users WHERE is_forever = 1 OR subscription_end > CURRENT_TIMESTAMP"
        )
        total_payments = await self.fetch_one("SELECT SUM(amount_stars) as sum FROM payments")
        total_proxies = await self.fetch_one("SELECT COUNT(*) as count FROM proxies WHERE is_working = 1")
        
        # Статистика за период
        period_stats = await self.fetch_all(
            """SELECT date, new_users, payments_count, payments_sum, proxies_found 
               FROM stats WHERE date >= ? ORDER BY date""",
            (start_date,)
        )
        
        return {
            'total_users': dict(total_users)['count'] if total_users else 0,
            'active_subs': dict(active_subs)['count'] if active_subs else 0,
            'total_payments': dict(total_payments)['sum'] if total_payments else 0,
            'total_proxies': dict(total_proxies)['count'] if total_proxies else 0,
            'period_stats': period_stats
        }
    
    # Методы для администрирования
    
    async def get_all_users(self) -> List[Dict]:
        """Получает всех пользователей (для рассылки)"""
        return await self.fetch_all(
            "SELECT user_id, username, first_name, language FROM users WHERE is_blocked = 0"
        )
    
    async def cleanup_inactive_proxies(self, days: int = 7) -> int:
        """Очищает нерабочие прокси старше N дней"""
        result = await self.execute(
            """DELETE FROM proxies 
               WHERE is_working = 0 
               AND last_check < datetime('now', ?)""",
            (f'-{days} days',)
        )
        return result or 0
