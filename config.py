"""
Конфигурационный файл бота
Все чувствительные данные загружаются из переменных окружения
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения
load_dotenv()

# Базовая директория проекта
BASE_DIR = Path(__file__).parent

# Токен бота (обязательно)
BOT_TOKEN = os.getenv('BOT_TOKEN', '8686343699:AAEvA6M3ol8jIEgnHpDyofPxR48vv5yeb7g')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '8259326703'))

# Пути к файлам
DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'data' / 'bot.db'))
LOG_DIR = BASE_DIR / 'logs'
BACKUP_DIR = BASE_DIR / 'backups'

# Настройки парсера
PROXY_POOL_ENABLED = os.getenv('PROXY_POOL_ENABLED', 'True').lower() == 'true'
USE_TOR = os.getenv('USE_TOR', 'False').lower() == 'true'
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))

# Настройки анонимности
MIN_DELAY = 5  # минимальная задержка между запросами (сек)
MAX_DELAY = 15  # максимальная задержка между запросами (сек)
MAX_RETRIES = 3  # количество попыток при ошибке
ROTATE_PROXY_EVERY = 3  # менять прокси каждые N запросов

# Настройки парсинга
PARSE_INTERVAL_MIN = 15  # минимальный интервал парсинга (минут)
PARSE_INTERVAL_MAX = 30  # максимальный интервал парсинга (минут)

# Настройки базы данных
DB_POOL_SIZE = 10
DB_MAX_OVERFLOW = 20
DB_POOL_TIMEOUT = 30

# Настройки логов
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_RETENTION_DAYS = 7
LOG_MAX_SIZE_MB = 100

# Тарифы (в Telegram Stars)
PRICES = {
    '1day': 5,
    '7days': 30,
    '30days': 100,
    'forever': 500
}

# URL для парсинга
PARSE_URL = 'https://t.me/s/ProxyMTProto'

# User-Agent список
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
]

# Создаем необходимые директории
for dir_path in [LOG_DIR, BACKUP_DIR, BASE_DIR / 'data']:
    dir_path.mkdir(parents=True, exist_ok=True)
