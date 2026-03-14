"""
"""
import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class Database:
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    async def init_db(self):
        """Инициализация базы данных"""
        async with self._get_connection() as conn:
            # Таблица пользователей с балансом BP
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
                    trial_used BOOLEAN DEFAULT 0,
                    bp_balance INTEGER DEFAULT 0
                )
            ''')
            
            # Таблица для истории транзакций BP
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bp_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    type TEXT,
                    description TEXT,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_id INTEGER
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
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.commit()
            logger.info("База данных инициализирована")
    
    @asynccontextmanager
    async def _get_connection(self):
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()
    
    async def execute(self, query: str, params: tuple = ()) -> Optional[int]:
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.lastrowid
    
    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # МЕТОДЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ
    
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
        user = await self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        
        if not user:
            await self.execute(
                """INSERT INTO users (user_id, username, first_name, bp_balance) 
                   VALUES (?, ?, ?, 0)""",
                (user_id, username, first_name)
            )
            user = await self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        
        return user
    
    async def update_user_subscription(self, user_id: int, days: int, forever: bool = False):
        if forever:
            await self.execute(
                "UPDATE users SET is_forever = 1 WHERE user_id = ?",
                (user_id,)
            )
        else:
            subscription_end = datetime.now() + timedelta(days=days)
            await self.execute(
                "UPDATE users SET subscription_end = ? WHERE user_id = ?",
                (subscription_end, user_id)
            )
    
    async def check_subscription(self, user_id: int) -> bool:
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
    
    # МЕТОДЫ ДЛЯ РАБОТЫ С ВАЛЮТОЙ BP
    
    async def get_bp_balance(self, user_id: int) -> int:
        """Получить баланс BP пользователя"""
        user = await self.fetch_one("SELECT bp_balance FROM users WHERE user_id = ?", (user_id,))
        return user['bp_balance'] if user else 0
    
    async def add_bp(self, user_id: int, amount: int, description: str = "", admin_id: int = None):
        """Добавить BP пользователю (выдача админом)"""
        await self.execute(
            "UPDATE users SET bp_balance = bp_balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        
        # Записываем транзакцию
        await self.execute(
            """INSERT INTO bp_transactions (user_id, amount, type, description, admin_id) 
               VALUES (?, ?, 'admin_add', ?, ?)""",
            (user_id, amount, description, admin_id)
        )
        
        new_balance = await self.get_bp_balance(user_id)
        return new_balance
    
    async def spend_bp(self, user_id: int, amount: int, description: str = "") -> bool:
        """Потратить BP (покупка подписки)"""
        balance = await self.get_bp_balance(user_id)
        
        if balance < amount:
            return False
        
        await self.execute(
            "UPDATE users SET bp_balance = bp_balance - ? WHERE user_id = ?",
            (amount, user_id)
        )
        
        # Записываем транзакцию
        await self.execute(
            """INSERT INTO bp_transactions (user_id, amount, type, description) 
               VALUES (?, ?, 'spend', ?)""",
            (user_id, -amount, description)
        )
        
        return True
    
    async def convert_stars_to_bp(self, user_id: int, stars_amount: int) -> bool:
        """Конвертация звезд в BP (1 звезда = 1 BP)"""
        # Здесь будет логика обработки платежа Stars
        # После успешной оплаты добавляем BP
        await self.add_bp(user_id, stars_amount, f"Конвертация {stars_amount} звезд")
        return True
    
    async def get_transaction_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю транзакций BP"""
        return await self.fetch_all(
            """SELECT * FROM bp_transactions 
               WHERE user_id = ? 
               ORDER BY date DESC 
               LIMIT ?""",
            (user_id, limit)
        )
    
    async def get_all_users_balance(self) -> List[Dict]:
        """Получить балансы всех пользователей (для админа)"""
        return await self.fetch_all(
            "SELECT user_id, username, first_name, bp_balance FROM users ORDER BY bp_balance DESC"
        )
    
    # МЕТОДЫ ДЛЯ ПРОБНОГО ПЕРИОДА
    
    async def activate_trial(self, user_id: int):
        user = await self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        
        if user and user.get("trial_used"):
            return False
        
        trial_end = datetime.now() + timedelta(days=2)
        
        await self.execute(
            "UPDATE users SET subscription_end = ?, trial_used = 1 WHERE user_id = ?",
            (trial_end, user_id)
        )
        return True

    async def check_trial_available(self, user_id: int) -> bool:
        user = await self.fetch_one("SELECT trial_used FROM users WHERE user_id = ?", (user_id,))
        return not (user and user.get("trial_used"))
    
    # МЕТОДЫ ДЛЯ ПРОКСИ
    
    async def add_proxy(self, proxy_link: str, server: str, port: int, secret: str, source: str) -> bool:
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
        return await self.fetch_all(
            "SELECT * FROM proxies WHERE is_working = 1 ORDER BY added_date DESC LIMIT ?",
            (limit,)
        )
    
    # МЕТОДЫ ДЛЯ АДМИНА
    
    async def get_stats(self) -> Dict:
        total_users = await self.fetch_one("SELECT COUNT(*) as count FROM users")
        active_subs = await self.fetch_one(
            "SELECT COUNT(*) as count FROM users WHERE is_forever = 1 OR subscription_end > CURRENT_TIMESTAMP"
        )
        total_bp = await self.fetch_one("SELECT SUM(bp_balance) as sum FROM users")
        total_proxies = await self.fetch_one("SELECT COUNT(*) as count FROM proxies WHERE is_working = 1")
        
        return {
            'total_users': dict(total_users)['count'] if total_users else 0,
            'active_subs': dict(active_subs)['count'] if active_subs else 0,
            'total_bp': dict(total_bp)['sum'] if total_bp else 0,
            'total_proxies': dict(total_proxies)['count'] if total_proxies else 0,
        }
    
    async def get_all_users(self) -> List[Dict]:
        return await self.fetch_all(
            "SELECT user_id, username, first_name, bp_balance FROM users"
        )
