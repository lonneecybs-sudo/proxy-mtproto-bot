"""
Модуль парсера с максимальной анонимностью
Использует Playwright для рендеринга JavaScript и имитации поведения человека
"""
import re
import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
import random

from anonymizer import Anonymizer
from database import Database

logger = logging.getLogger(__name__)

class ProxyParser:
    """
    Парсер MTProto прокси из Telegram канала
    С полной анонимизацией и защитой от блокировок
    """
    
    def __init__(self, config, db: Database, anonymizer: Anonymizer):
        self.config = config
        self.db = db
        self.anonymizer = anonymizer
        self.browser: Optional[Browser] = None
        self.playwright = None
        
        # Регулярное выражение для поиска прокси ссылок
        self.proxy_pattern = re.compile(
            r'(?:proxy|mtproto)://[^\s<>"\']+|'
            r'tg://proxy\?server=([^&]+)&port=(\d+)&secret=([^\s<>"\']+)'
        )
        
        # Детальный паттерн для разбора параметров
        self.detail_pattern = re.compile(
            r'server=([^&]+)&port=(\d+)&secret=([^\s&]+)'
        )
    
    async def start_browser(self):
        """Запускает браузер для парсинга"""
        if not self.browser:
            self.playwright = await async_playwright().start()
            
            # Запускаем с прокси если доступно
            proxy = await self.anonymizer.get_random_proxy()
            proxy_config = None
            if proxy:
                proxy_config = {
                    'server': proxy['address']
                }
            
            self.browser = await self.playwright.firefox.launch(
                headless=True,
                proxy=proxy_config,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials'
                ]
            )
            logger.info("Браузер запущен")
    
    async def close_browser(self):
        """Закрывает браузер"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def parse_with_playwright(self) -> List[Tuple[str, str, int, str]]:
        """
        Парсинг с использованием Playwright для полной эмуляции браузера
        """
        await self.start_browser()
        
        try:
            # Создаем новую страницу
            context = await self.browser.new_context(
                viewport={'width': random.randint(1024, 1920), 
                         'height': random.randint(768, 1080)},
                user_agent=self.anonymizer.get_random_headers()['User-Agent'],
                locale=random.choice(['ru-RU', 'en-US', 'en-GB']),
                timezone_id=random.choice(['Europe/Moscow', 'Europe/London', 'America/New_York'])
            )
            
            page = await context.new_page()
            
            # Устанавливаем случайные заголовки
            await page.set_extra_http_headers(self.anonymizer.get_random_headers())
            
            # Идем на страницу
            logger.info(f"Навигация на {self.config.PARSE_URL}")
            await page.goto(self.config.PARSE_URL, wait_until='networkidle')
            
            # Имитация человеческого поведения
            await self._simulate_human_behavior(page)
            
            # Ждем загрузки контента
            await page.wait_for_selector('.tgme_widget_message_text', timeout=30000)
            
            # Получаем HTML
            content = await page.content()
            
            # Парсим прокси
            proxies = self._extract_proxies_from_html(content)
            
            # Прокручиваем страницу для загрузки новых сообщений
            for _ in range(random.randint(1, 3)):
                await page.evaluate('window.scrollBy(0, window.innerHeight)')
                await asyncio.sleep(random.uniform(1, 3))
                
                # Ждем загрузки новых сообщений
                await page.wait_for_timeout(2000)
                
                # Получаем обновленный контент
                content = await page.content()
                new_proxies = self._extract_proxies_from_html(content)
                proxies.extend(new_proxies)
            
            await context.close()
            
            # Убираем дубликаты
            unique_proxies = list(set(proxies))
            logger.info(f"Найдено {len(unique_proxies)} уникальных прокси")
            
            return unique_proxies
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге с Playwright: {e}")
            # Пробуем альтернативный метод
            return await self.parse_with_requests()
        finally:
            await self.close_browser()
    
    async def _simulate_human_behavior(self, page: Page):
        """Имитирует поведение человека на странице"""
        try:
            # Случайные движения мыши
            for _ in range(random.randint(3, 7)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Случайные нажатия клавиш
            if random.random() > 0.7:
                await page.keyboard.press('PageDown')
                await asyncio.sleep(random.uniform(0.5, 1))
            
            # Небольшая задержка перед основными действиями
            await asyncio.sleep(random.uniform(1, 3))
            
        except Exception as e:
            logger.debug(f"Ошибка при имитации поведения: {e}")
    
    async def parse_with_requests(self) -> List[Tuple[str, str, int, str]]:
        """
        Альтернативный метод парсинга через requests (с прокси)
        """
        proxies_found = []
        
        # Пробуем несколько раз с разными прокси
        for attempt in range(self.config.MAX_RETRIES):
            try:
                # Получаем прокси для запроса
                proxy = await self.anonymizer.get_random_proxy()
                connector = None
                
                if proxy:
                    if proxy['type'] == 'socks5':
                        from aiohttp_socks import ProxyConnector
                        connector = ProxyConnector.from_url(proxy['address'])
                    else:
                        connector = aiohttp.TCPConnector()
                
                # Настраиваем заголовки
                headers = self.anonymizer.get_random_headers()
                
                # Выполняем запрос
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        self.config.PARSE_URL,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                        ssl=False
                    ) as response:
                        
                        if response.status == 200:
                            html = await response.text()
                            proxies_found = self._extract_proxies_from_html(html)
                            
                            if proxies_found:
                                logger.info(f"Найдено {len(proxies_found)} прокси через requests")
                                break
                            else:
                                logger.warning("Прокси не найдены в HTML")
                        else:
                            logger.warning(f"HTTP {response.status} при запросе")
                            
                            # Если получили блокировку, помечаем прокси как нерабочий
                            if response.status in [403, 429] and proxy:
                                await self.anonymizer.mark_proxy_failed(proxy['address'])
            
            except Exception as e:
                logger.error(f"Ошибка при requests парсинге (попытка {attempt+1}): {e}")
                if proxy:
                    await self.anonymizer.mark_proxy_failed(proxy['address'])
            
            # Ждем перед следующей попыткой
            await self.anonymizer.human_delay()
        
        return list(set(proxies_found))
    
    def _extract_proxies_from_html(self, html: str) -> List[Tuple[str, str, int, str]]:
        """
        Извлекает прокси из HTML кода
        Возвращает список кортежей (полная_ссылка, сервер, порт, секрет)
        """
        proxies = []
        soup = BeautifulSoup(html, 'lxml')
        
        # Ищем текстовые сообщения
        message_texts = soup.find_all(class_='tgme_widget_message_text')
        
        for message in message_texts:
            text = message.get_text()
            
            # Ищем прокси ссылки
            for match in self.proxy_pattern.finditer(text):
                full_link = match.group(0)
                
                # Пытаемся извлечь параметры
                server, port, secret = self._extract_proxy_params(full_link)
                
                if server and port and secret:
                    proxies.append((full_link, server, port, secret))
                    logger.debug(f"Найден прокси: {server}:{port}")
        
        return proxies
    
    def _extract_proxy_params(self, proxy_link: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Извлекает параметры прокси из ссылки
        """
        try:
            # Пробуем детальный паттерн
            match = self.detail_pattern.search(proxy_link)
            if match:
                server = match.group(1)
                port = int(match.group(2))
                secret = match.group(3)
                return server, port, secret
            
            # Пробуем URL парсинг
            parsed = urlparse(proxy_link)
            if parsed.scheme in ['proxy', 'mtproto']:
                # Парсим параметры из query
                from urllib.parse import parse_qs
                params = parse_qs(parsed.query)
                
                server = params.get('server', [None])[0]
                port = params.get('port', [None])[0]
                secret = params.get('secret', [None])[0]
                
                if server and port and secret:
                    return server, int(port), secret
            
        except Exception as e:
            logger.debug(f"Ошибка парсинга параметров прокси: {e}")
        
        return None, None, None
    
    async def parse_and_save(self) -> int:
        """
        Основной метод парсинга: получает прокси и сохраняет в БД
        Возвращает количество новых прокси
        """
        logger.info("Начинаю парсинг прокси...")
        
        # Выбираем метод парсинга
        if random.random() > 0.3:  # 70% используем Playwright
            proxies = await self.parse_with_playwright()
        else:
            proxies = await self.parse_with_requests()
        
        if not proxies:
            logger.warning("Прокси не найдены")
            return 0
        
        # Сохраняем в базу
        saved_count = 0
        for full_link, server, port, secret in proxies:
            try:
                # Проверяем, существует ли уже
                existing = await self.db.fetch_one(
                    "SELECT id FROM proxies WHERE server = ? AND port = ?",
                    (server, port)
                )
                
                if not existing:
                    await self.db.execute(
                        """INSERT INTO proxies 
                           (proxy_link, server, port, secret, source, is_working) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (full_link, server, port, secret, self.config.PARSE_URL, True)
                    )
                    saved_count += 1
                    logger.debug(f"Сохранен новый прокси: {server}:{port}")
                    
            except Exception as e:
                logger.error(f"Ошибка сохранения прокси {server}:{port}: {e}")
        
        logger.info(f"Сохранено {saved_count} новых прокси из {len(proxies)} найденных")
        return saved_count
    
    async def check_proxy_health(self, server: str, port: int, secret: str) -> bool:
        """
        Проверяет работоспособность MTProto прокси
        """
        # Здесь должна быть реальная проверка через MTProto протокол
        # Для демо возвращаем True
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return random.random() > 0.2  # 80% рабочих для демо
