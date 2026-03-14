"""
Модуль для проверки работоспособности прокси
"""
import asyncio
import logging
import socket
from typing import List, Dict, Tuple
from datetime import datetime
import random

logger = logging.getLogger(__name__)

class ProxyChecker:
    """
    Проверяет MTProto прокси на работоспособность
    """
    
    def __init__(self, db):
        self.db = db
        self.timeout = 10  # таймаут подключения в секундах
    
    async def check_proxy(self, server: str, port: int, secret: str) -> Tuple[bool, float]:
        """
        Проверяет один прокси
        Возвращает (работоспособность, время отклика)
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Здесь должна быть реальная проверка MTProto протокола
            # Для демо используем TCP подключение
            conn = asyncio.open_connection(server, port)
            try:
                reader, writer = await asyncio.wait_for(conn, timeout=self.timeout)
                writer.close()
                await writer.wait_closed()
                
                response_time = asyncio.get_event_loop().time() - start_time
                return True, response_time
                
            except asyncio.TimeoutError:
                logger.debug(f"Таймаут подключения к {server}:{port}")
                return False, 0
            except Exception as e:
                logger.debug(f"Ошибка подключения к {server}:{port}: {e}")
                return False, 0
                
        except Exception as e:
            logger.error(f"Ошибка при проверке прокси {server}:{port}: {e}")
            return False, 0
    
    async def check_all_proxies(self, limit: int = None) -> Tuple[int, int]:
        """
        Проверяет все прокси в базе
        Возвращает (проверено, рабочие)
        """
        # Получаем прокси для проверки
        query = "SELECT id, server, port, secret FROM proxies WHERE is_working = 1 OR last_check IS NULL"
        if limit:
            query += f" LIMIT {limit}"
        
        proxies = await self.db.fetch_all(query)
        
        if not proxies:
            logger.info("Нет прокси для проверки")
            return 0, 0
        
        logger.info(f"Начинаю проверку {len(proxies)} прокси")
        
        working_count = 0
        checked_count = 0
        
        # Проверяем с ограничением параллельности
        semaphore = asyncio.Semaphore(10)
        
        async def check_with_semaphore(proxy):
            nonlocal working_count, checked_count
            
            async with semaphore:
                is_working, response_time = await self.check_proxy(
                    proxy['server'], 
                    proxy['port'], 
                    proxy['secret']
                )
                
                await self.db.mark_proxy_checked(proxy['id'], is_working)
                
                checked_count += 1
                if is_working:
                    working_count += 1
                
                if checked_count % 10 == 0:
                    logger.info(f"Проверено {checked_count}/{len(proxies)} прокси")
        
        # Запускаем проверку
        tasks = [check_with_semaphore(proxy) for proxy in proxies]
        await asyncio.gather(*tasks)
        
        logger.info(f"Проверка завершена. Рабочих: {working_count} из {checked_count}")
        
        return checked_count, working_count
    
    async def continuous_check(self, interval_minutes: int = 60):
        """
        Непрерывная проверка прокси с заданным интервалом
        """
        while True:
            try:
                await self.check_all_proxies()
                logger.info(f"Следующая проверка через {interval_minutes} минут")
                await asyncio.sleep(interval_minutes * 60)
            except Exception as e:
                logger.error(f"Ошибка в continuous_check: {e}")
                await asyncio.sleep(60)
