"""
Модуль обработки платежей Telegram Stars
"""
import logging
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message

from database import Database
from config import PRICES

logger = logging.getLogger(__name__)

class PaymentHandler:
    """
    Обработчик платежей в Telegram Stars
    """
    
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        
        # Маппинг callback данных на параметры тарифа
        self.tariffs = {
            'buy_1day': {'days': 1, 'price': PRICES['1day'], 'title': '1 день'},
            'buy_7days': {'days': 7, 'price': PRICES['7days'], 'title': '7 дней'},
            'buy_30days': {'days': 30, 'price': PRICES['30days'], 'title': '30 дней'},
            'buy_forever': {'days': None, 'price': PRICES['forever'], 'title': 'Навсегда'}
        }
    
    async def create_invoice(self, user_id: int, tariff_key: str) -> str:
        """
        Создает инвойс для оплаты Stars
        Возвращает ID платежа
        """
        tariff = self.tariffs.get(tariff_key)
        if not tariff:
            raise ValueError(f"Неизвестный тариф: {tariff_key}")
        
        # Создаем уникальный ID платежа
        payment_id = f"stars_{user_id}_{datetime.now().timestamp()}"
        
        # Создаем инвойс
        prices = [LabeledPrice(label=f"Доступ {tariff['title']}", amount=tariff['price'])]
        
        invoice = await self.bot.send_invoice(
            chat_id=user_id,
            title=f"⭐ Премиум доступ к прокси",
            description=f"Активация доступа на {tariff['title']} к быстрым MTProto прокси",
            payload=payment_id,
            provider_token="",  # Пустой токен для Stars
            currency="XTR",
            prices=prices,
            start_parameter="proxy_subscription",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
            disable_notification=False,
            protect_content=False,
            reply_to_message_id=None,
            allow_sending_without_reply=True,
            reply_markup=None,
            request_timeout=30
        )
        
        return payment_id
    
    async def process_successful_payment(self, message: Message):
        """
        Обрабатывает успешный платеж
        """
        payment = message.successful_payment
        user_id = message.from_user.id
        payment_id = payment.invoice_payload
        amount = payment.total_amount
        
        # Определяем тариф по сумме
        tariff = None
        for key, t in self.tariffs.items():
            if t['price'] == amount:
                tariff = t
                tariff_key = key
                break
        
        if not tariff:
            logger.error(f"Неизвестная сумма платежа: {amount} от user {user_id}")
            return
        
        # Сохраняем платеж в БД
        await self.db.execute(
            """INSERT INTO payments (user_id, amount_stars, period_days, payment_id) 
               VALUES (?, ?, ?, ?)""",
            (user_id, amount, tariff['days'] or 999999, payment_id)
        )
        
        # Обновляем подписку пользователя
        if tariff['days'] is None:  # Навсегда
            await self.db.update_user_subscription(user_id, 0, forever=True)
            expiry_text = "НАВСЕГДА"
        else:
            await self.db.update_user_subscription(user_id, tariff['days'], forever=False)
            user = await self.db.fetch_one("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
            expiry_text = f"до {user['subscription_end'].split()[0]}" if user else ""
        
        # Обновляем статистику
        await self.db.update_daily_stats('payments_count')
        await self.db.update_daily_stats('payments_sum', amount)
        
        # Отправляем подтверждение
        await message.answer(
            f"✅ **Оплата прошла успешно!**\n\n"
            f"✨ Вам активирован доступ на **{tariff['title']}** {expiry_text}\n\n"
            f"👉 Нажмите **/proxies** чтобы получить рабочие прокси",
            parse_mode="Markdown"
        )
        
        logger.info(f"Пользователь {user_id} купил доступ {tariff['title']} за {amount} ⭐")
    
    async def pre_checkout_handler(self, pre_checkout_query: PreCheckoutQuery):
        """
        Проверяет платеж перед проведением
        """
        # Всегда подтверждаем для Stars
        await self.bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=True
        )
