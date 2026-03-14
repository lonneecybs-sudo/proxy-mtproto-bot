"""
"""
import logging
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message

from database import Database
from config import PRICES

logger = logging.getLogger(__name__)

class PaymentHandler:
    
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        
        self.tariffs = {
            'buy_1day': {'days': 1, 'price': PRICES['1day'], 'title': '1 день'},
            'buy_7days': {'days': 7, 'price': PRICES['7days'], 'title': '7 дней'},
            'buy_30days': {'days': 30, 'price': PRICES['30days'], 'title': '30 дней'},
            'buy_forever': {'days': None, 'price': PRICES['forever'], 'title': 'Навсегда'}
        }
    
    async def create_invoice(self, user_id: int, tariff_key: str) -> str:
        tariff = self.tariffs.get(tariff_key)
        if not tariff:
            raise ValueError(f"Неизвестный тариф: {tariff_key}")
        
        payment_id = f"stars_{user_id}_{datetime.now().timestamp()}"
        
        prices = [LabeledPrice(label=f"Доступ {tariff['title']}", amount=tariff['price'])]
        
        await self.bot.send_invoice(
            chat_id=user_id,
            title=f"⭐ Пополнение BP",
            description=f"Покупка {tariff['price']} BP для доступа к прокси",
            payload=payment_id,
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="proxy_subscription"
        )
        
        return payment_id
    
    async def process_successful_payment(self, message: Message):
        payment = message.successful_payment
        user_id = message.from_user.id
        amount = payment.total_amount
        
        # Конвертируем звезды в BP (1:1)
        await self.db.add_bp(user_id, amount, f"Конвертация {amount} звезд")
        
        await message.answer(
            f"✅ **Оплата прошла успешно!**\n\n"
            f"💰 Вам начислено **{amount} BP**\n"
            f"Теперь вы можете купить подписку за BP\n\n"
            f"👉 Нажмите /buy чтобы выбрать тариф",
            parse_mode="Markdown"
        )
        
        logger.info(f"Пользователь {user_id} пополнил BP на {amount} ⭐")
    
    async def pre_checkout_handler(self, pre_checkout_query: PreCheckoutQuery):
        await self.bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=True
        )
