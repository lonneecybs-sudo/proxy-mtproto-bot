"""
Модуль анонимизации запросов
Управление прокси-пулом, ротация User-Agent, имитация поведения
"""
import random
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime
import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class Anonymizer:
    """
    Класс для анонимизации запросов
    Управляет пулом прокси, ротацией User-Agent и заголовков
    """
    
    def __init__(self, config):
        self.config = config
        self.proxy_pool = []
        self.current_proxy_index = 0
        self.request_count = 0
        self.ua = UserAgent()
        self._load_proxy_pool()
        
    def _load_proxy_pool(self):
        """Загружает пул прокси из файла или генерирует начальный список"""
        proxy_file = Path(__file__).parent / 'data' / 'proxy_pool.json'
        
        if proxy_file.exists():
            try:
                with open(proxy_file, 'r') as f:
                    self.proxy_pool = json.load(f)
                logger.info(f"Загружено {len(self.proxy_pool)} прокси из файла")
            except:
                self._generate_initial_proxy_pool()
        else:
            self._generate_initial_proxy_pool()
    
    def _generate_initial_proxy_pool(self):
        """Генерирует начальный список бесплатных прокси"""
        # Здесь можно добавить парсинг бесплатных прокси из открытых источников
        # Для примера добавляем несколько тестовых
        self.proxy_pool = [
            {'address': 'socks5://127.0.0.1:9050', 'type': 'socks5', 'is_working': True},  # Tor
            {'address': 'http://proxy1.example.com:8080', 'type': 'http', 'is_working': True},
        ]
        logger.warning("Используется тестовый пул прокси. Рекомендуется добавить реальные прокси.")
    
    async def get_random_proxy(self) -> Optional[Dict]:
        """Возвращает случайный рабочий прокси из пула"""
        working_proxies = [p for p in self.proxy_pool if p.get('is_working', False)]
        
        if not working_proxies:
            # Если нет рабочих прокси, используем Tor если разрешено
            if self.config.USE_TOR:
                return {'address': 'socks5://127.0.0.1:9050', 'type': 'socks5'}
            return None
        
        return random.choice(working_proxies)
    
    async def rotate_proxy(self):
        """Ротация прокси после определенного количества запросов"""
        self.request_count += 1
        
        if self.request_count >= self.config.ROTATE_PROXY_EVERY:
            self.request_count = 0
            # Меняем индекс текущего прокси
            self.current_proxy_index = (self.current_proxy_index + 1) % max(1, len(self.proxy_pool))
            logger.debug("Произведена ротация прокси")
    
    def get_random_headers(self) -> Dict[str, str]:
        """Генерирует случайные заголовки для запроса"""
        # Список популярных Accept-Language
        accept_languages = [
            'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'en-US,en;q=0.9,ru;q=0.8',
            'ru,en;q=0.9,en-US;q=0.8',
            'en-GB,en;q=0.9,ru;q=0.8',
        ]
        
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': random.choice(accept_languages),
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Добавляем случайные Sec-Ch-UA заголовки если User-Agent от Chrome
        if 'Chrome' in headers['User-Agent']:
            headers.update({
                'Sec-Ch-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-UA-Mobile': '?0',
                'Sec-Ch-UA-Platform': random.choice(['"Windows"', '"macOS"', '"Linux"']),
            })
        
        return headers
    
    async def human_delay(self):
        """Имитация человеческой задержки между действиями"""
        delay = random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY)
        logger.debug(f"Задержка {delay:.2f} секунд")
        await asyncio.sleep(delay)
    
    async def get_connector(self) -> Optional[ProxyConnector]:
        """Создает connector с прокси для aiohttp"""
        proxy = await self.get_random_proxy()
        
        if proxy:
            try:
                if proxy['type'] == 'socks5':
                    return ProxyConnector.from_url(proxy['address'])
                elif proxy['type'] == 'http':
                    return ProxyConnector.from_url(proxy['address'])
            except Exception as e:
                logger.error(f"Ошибка создания прокси-коннектора: {e}")
                # Помечаем прокси как нерабочий
                for p in self.proxy_pool:
                    if p['address'] == proxy['address']:
                        p['is_working'] = False
                        break
        
        return None
    
    async def mark_proxy_failed(self, proxy_address: str):
        """Помечает прокси как нерабочий"""
        for proxy in self.proxy_pool:
            if proxy['address'] == proxy_address:
                proxy['is_working'] = False
                proxy['fail_count'] = proxy.get('fail_count', 0) + 1
                logger.info(f"Прокси {proxy_address} помечен как нерабочий")
                break
    
    async def add_proxy(self, proxy_address: str, proxy_type: str = 'http'):
        """Добавляет новый прокси в пул"""
        new_proxy = {
            'address': proxy_address,
            'type': proxy_type,
            'is_working': True,
            'fail_count': 0,
            'added_date': datetime.now().isoformat()
        }
        
        # Проверяем, нет ли уже такого прокси
        if not any(p['address'] == proxy_address for p in self.proxy_pool):
            self.proxy_pool.append(new_proxy)
            logger.info(f"Добавлен новый прокси: {proxy_address}")
            
            # Сохраняем пул в файл
            await self._save_proxy_pool()
    
    async def _save_proxy_pool(self):
        """Сохраняет пул прокси в файл"""
        proxy_file = Path(__file__).parent / 'data' / 'proxy_pool.json'
        try:
            with open(proxy_file, 'w') as f:
                json.dump(self.proxy_pool, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка сохранения пула прокси: {e}")
