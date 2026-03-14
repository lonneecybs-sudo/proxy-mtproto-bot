"""
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).parent

BOT_TOKEN = os.getenv('BOT_TOKEN', '8212559417:AAHXgKaeOBcvp69h-3dSO9YyB02cKi8MHwU')
ADMIN_ID = int(os.getenv('ADMIN_ID', '8259326703'))

DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'data' / 'bot.db'))
LOG_DIR = BASE_DIR / 'logs'
BACKUP_DIR = BASE_DIR / 'backups'

# Настройки парсера
PROXY_POOL_ENABLED = os.getenv('PROXY_POOL_ENABLED', 'True').lower() == 'true'
USE_TOR = os.getenv('USE_TOR', 'False').lower() == 'true'
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))

MIN_DELAY = 5
MAX_DELAY = 15
MAX_RETRIES = 3
ROTATE_PROXY_EVERY = 3

PARSE_INTERVAL_MIN = 15
PARSE_INTERVAL_MAX = 30

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_RETENTION_DAYS = 7

# Цены в BP (1 BP = 1 звезда)
PRICES = {
    '1day': 5,
    '7days': 30,
    '30days': 100,
    'forever': 500
}

PARSE_URL = 'https://t.me/s/ProxyMTProto'

# Создаем директории
for dir_path in [LOG_DIR, BACKUP_DIR, BASE_DIR / 'data']:
    dir_path.mkdir(parents=True, exist_ok=True)
