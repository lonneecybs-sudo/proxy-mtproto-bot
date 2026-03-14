#!/usr/bin/env python3
"""
"""
import asyncio
import logging
import sys
import os
import random
from datetime import datetime
from pathlib import Path
from aiohttp import web
import json

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import Database
from anonymizer import Anonymizer
from parser import ProxyParser
from payments import PaymentHandler
from proxy_checker import ProxyChecker
from bot import BotHandler, BroadcastStates

# Настройка логирования
def setup_logging():
    """Настройка системы логирования"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Создаем директорию для логов если её нет
    config.LOG_DIR.mkdir(exist_ok=True)
    
    # Имя лог файла с датой
    log_file = config.LOG_DIR / f'bot_{datetime.now().strftime("%Y%m%d")}.log'
    
    # Настройка обработчиков
    handlers = [
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
    
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=log_format,
        handlers=handlers
    )
    
    # Скрываем реальные IP в логах
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logging()

class ProxyBot:
    """Основной класс приложения с веб-сервером"""
    
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db = None
        self.anonymizer = None
        self.parser = None
        self.payment_handler = None
        self.proxy_checker = None
        self.bot_handler = None
        self.running = True
        self.web_app = None
        self.web_runner = None
        
    async def initialize(self):
        """Инициализация всех компонентов"""
        logger.info("Инициализация бота...")
        
        # Проверяем наличие токена
        if not config.BOT_TOKEN or config.BOT_TOKEN == 'ВАШ_НОВЫЙ_ТОКЕН_ОТ_BOTFATHER':
            logger.error("Токен бота не установлен! Отредактируйте файл .env")
            sys.exit(1)
        
        # Инициализация бота
        self.bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Инициализация базы данных
        logger.info("Подключение к базе данных...")
        self.db = Database(config.DATABASE_PATH)
        await self.db.init_db()
        
        # Инициализация анонимайзера
        logger.info("Инициализация анонимайзера...")
        self.anonymizer = Anonymizer(config)
        
        # Инициализация парсера
        logger.info("Инициализация парсера...")
        self.parser = ProxyParser(config, self.db, self.anonymizer)
        
        # Инициализация платежей
        logger.info("Инициализация платежной системы...")
        self.payment_handler = PaymentHandler(self.bot, self.db)
        
        # Инициализация проверщика прокси
        logger.info("Инициализация проверщика прокси...")
        self.proxy_checker = ProxyChecker(self.db)
        
        # Инициализация обработчика бота
        logger.info("Инициализация обработчика команд...")
        self.bot_handler = BotHandler(
            self.bot, self.dp, self.db,
            self.payment_handler, self.parser
        )
        
        # Регистрируем дополнительные обработчики для FSM
        self.dp.message.register(
        )
        self.dp.callback_query.register(
            self.bot_handler.broadcast_confirm,
            lambda c: c.data == 'broadcast_confirm'
        )
        self.dp.callback_query.register(
            self.bot_handler.broadcast_cancel,
            lambda c: c.data == 'broadcast_cancel'
        )
        
        logger.info("Инициализация завершена успешно")
    
    async def handle_index(self, request):
        """Обработчик главной страницы"""
        user_id = request.query.get('user_id')
        chat_id = request.query.get('chat_id')
        
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            html = f.read()
        
        return web.Response(text=html, content_type='text/html')
    
    async def handle_check_access(self, request):
        """API для проверки доступа"""
        user_id = request.query.get('user_id')
        if not user_id:
            return web.json_response({'error': 'no_user_id'}, status=400)
        
        try:
            user_id = int(user_id)
            has_access = await self.db.check_subscription(user_id)
            trial_available = await self.db.check_trial_available(user_id)
            
            return web.json_response({
                'has_access': has_access,
                'trial_available': trial_available
            })
        except Exception as e:
            logger.error(f"Error checking access: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def handle_get_proxies(self, request):
        """API для получения прокси"""
        user_id = request.query.get('user_id')
        if not user_id:
            return web.json_response({'error': 'no_user_id'}, status=400)
        
        try:
            user_id = int(user_id)
            has_access = await self.db.check_subscription(user_id)
            
            if not has_access:
                return web.json_response({
                    'error': 'no_access',
                    'proxies': []
                })
            
            proxies = await self.db.get_working_proxies(limit=10)
            
            # Обновляем счетчик
            await self.db.execute(
                "UPDATE users SET proxies_received = proxies_received + 1 WHERE user_id = ?",
                (user_id,)
            )
            
            return web.json_response({
                'success': True,
                'proxies': [{'proxy_link': p['proxy_link']} for p in proxies]
            })
        except Exception as e:
            logger.error(f"Error getting proxies: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def handle_create_invoice(self, request):
        """API для создания инвойса"""
        try:
            data = await request.json()
            user_id = data.get('user_id')
            chat_id = data.get('chat_id')
            tariff = data.get('tariff')
            
            if not all([user_id, chat_id, tariff]):
                return web.json_response({'error': 'missing_data'}, status=400)
            
            # Создаем инвойс в Telegram
            await self.payment_handler.create_invoice(user_id, tariff)
            
            return web.json_response({'success': True})
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def handle_activate_trial(self, request):
        """API для активации пробного периода"""
        try:
            data = await request.json()
            user_id = data.get('user_id')
            
            if not user_id:
                return web.json_response({'error': 'no_user_id'}, status=400)
            
            # Проверяем доступность пробного периода
            trial_available = await self.db.check_trial_available(user_id)
            
            if not trial_available:
                return web.json_response({
                    'success': False,
                    'message': 'Пробный период уже использован'
                })
            
            # Активируем пробный период
            success = await self.db.activate_trial(user_id)
            
            if success:
                return web.json_response({
                    'success': True,
                    'message': 'Пробный период активирован'
                })
            else:
                return web.json_response({
                    'success': False,
                    'message': 'Ошибка активации'
                })
        except Exception as e:
            logger.error(f"Error activating trial: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def start_web_server(self):
        """Запуск веб-сервера"""
        self.web_app = web.Application()
        
        # Маршруты
        self.web_app.router.add_get('/', self.handle_index)
        self.web_app.router.add_get('/api/check_access', self.handle_check_access)
        self.web_app.router.add_get('/api/get_proxies', self.handle_get_proxies)
        self.web_app.router.add_post('/api/create_invoice', self.handle_create_invoice)
        self.web_app.router.add_post('/api/activate_trial', self.handle_activate_trial)
        
        # Статические файлы (если нужны)
        self.web_app.router.add_static('/static/', path='static/', name='static')
        
        # Получаем порт из переменных окружения (Railway)
        port = int(os.getenv('PORT', 8080))
        
        self.web_runner = web.AppRunner(self.web_app)
        await self.web_runner.setup()
        site = web.TCPSite(self.web_runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    
    async def parser_task(self):
        """Фоновая задача для парсинга прокси"""
        logger.info("Запуск задачи парсера")
        
        while self.running:
            try:
                # Случайная задержка перед началом
                delay = random.uniform(5, 15)
                await asyncio.sleep(delay)
                
                if not self.running:
                    break
                
                # Запускаем парсинг
                logger.info("Запуск парсинга...")
                count = await self.parser.parse_and_save()
                
                if count > 0:
                    logger.info(f"✅ Парсер нашел {count} новых прокси")
                    
                    # Проверяем новые прокси
                    await self.proxy_checker.check_all_proxies(limit=20)
                else:
                    logger.info("Новых прокси не найдено")
                
                # Случайный интервал до следующего парсинга
                interval = random.uniform(
                    config.PARSE_INTERVAL_MIN * 60,
                    config.PARSE_INTERVAL_MAX * 60
                )
                
                logger.info(f"Следующий парсинг через {interval/60:.1f} минут")
                
                # Постепенный сон с проверкой флага остановки
                for _ in range(int(interval / 10)):
                    if not self.running:
                        break
                    await asyncio.sleep(10)
                    
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче парсера: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def checker_task(self):
        """Фоновая задача для проверки прокси"""
        logger.info("Запуск задачи проверки прокси")
        
        while self.running:
            try:
                # Проверяем прокси каждый час
                await asyncio.sleep(3600)
                
                if not self.running:
                    break
                
                logger.info("Запуск плановой проверки прокси")
                checked, working = await self.proxy_checker.check_all_proxies()
                logger.info(f"Проверка завершена: {working} рабочих из {checked}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче проверки: {e}")
                await asyncio.sleep(60)
    
    async def cleanup_task(self):
        """Фоновая задача для очистки старых логов и бэкапов"""
        logger.info("Запуск задачи очистки")
        
        while self.running:
            try:
                # Очистка раз в день
                await asyncio.sleep(86400)
                
                if not self.running:
                    break
                
                # Очистка старых логов
                await self.cleanup_old_logs()
                
                # Создание бэкапа БД
                await self.create_backup()
                
            except Exception as e:
                logger.error(f"❌ Ошибка в задаче очистки: {e}")
    
    async def cleanup_old_logs(self):
        """Очищает логи старше 7 дней"""
        try:
            import time
            now = time.time()
            cutoff = now - (config.LOG_RETENTION_DAYS * 86400)
            
            deleted = 0
            for log_file in config.LOG_DIR.glob('*.log'):
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    deleted += 1
            
            if deleted > 0:
                logger.info(f"Удалено старых логов: {deleted}")
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке логов: {e}")
    
    async def create_backup(self):
        """Создает бэкап базы данных"""
        try:
            # Создаем директорию для бэкапов
            config.BACKUP_DIR.mkdir(exist_ok=True)
            
            # Имя файла бэкапа
            backup_file = config.BACKUP_DIR / f'bot_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
            
            # Копируем файл БД
            import shutil
            if os.path.exists(config.DATABASE_PATH):
                shutil.copy2(config.DATABASE_PATH, backup_file)
                
                # Сжимаем
                import gzip
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(f'{backup_file}.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Удаляем несжатый файл
                backup_file.unlink()
                
                logger.info(f"✅ Создан бэкап: {backup_file.name}.gz")
                
                # Удаляем старые бэкапы (старше 7 дней)
                await self.cleanup_old_backups()
                
        except Exception as e:
            logger.error(f"Ошибка при создании бэкапа: {e}")
    
    async def cleanup_old_backups(self):
        """Удаляет бэкапы старше 7 дней"""
        try:
            import time
            now = time.time()
            cutoff = now - (7 * 86400)
            
            deleted = 0
            for backup_file in config.BACKUP_DIR.glob('*.gz'):
                if backup_file.stat().st_mtime < cutoff:
                    backup_file.unlink()
                    deleted += 1
            
            if deleted > 0:
                logger.info(f"Удалено старых бэкапов: {deleted}")
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке бэкапов: {e}")
    
    async def start_polling(self):
        """Запуск поллинга бота"""
        logger.info("Запуск поллинга...")
        
        try:
            # Удаляем webhook если был
            await self.bot.delete_webhook(drop_pending_updates=True)
            
            # Запускаем поллинг
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types()
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при поллинге: {e}")
            raise
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Завершение работы бота...")
        
        self.running = False
        
        # Останавливаем веб-сервер
        if self.web_runner:
            await self.web_runner.cleanup()
        
        # Закрываем браузер если был открыт
        if self.parser:
            await self.parser.close_browser()
        
        # Закрываем сессию бота
        if self.bot:
            await self.bot.session.close()
        
        logger.info("✅ Бот остановлен")
    
    async def run(self):
        """Основной метод запуска"""
        try:
            # Инициализация
            await self.initialize()
            
            # Запуск веб-сервера
            await self.start_web_server()
            
            # Запуск фоновых задач
            tasks = [
                asyncio.create_task(self.parser_task(), name="parser"),
                asyncio.create_task(self.checker_task(), name="checker"),
                asyncio.create_task(self.cleanup_task(), name="cleanup"),
                asyncio.create_task(self.start_polling(), name="polling")
            ]
            
            # Ожидаем завершения
            await asyncio.gather(*tasks)
            
        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        finally:
            await self.shutdown()

def main():
    """Точка входа"""
    print("""
    ╔════════════════════════════════════╗
    ║        BProxy Bot v2.0             ║
    ║     с веб-интерфейсом              ║
    ╚════════════════════════════════════╝
    """)
    
    bot = ProxyBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
