"""
"""
import logging
import asyncio
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from payments import PaymentHandler
from parser import ProxyParser
from config import PRICES, ADMIN_ID

logger = logging.getLogger(__name__)

# Состояния для FSM
class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirming = State()

class BotHandler:
    """
    Упрощенный класс с обработчиками бота
    """
    
    def __init__(self, bot: Bot, dp: Dispatcher, db: Database, 
                 payment_handler: PaymentHandler, parser: ProxyParser):
        self.bot = bot
        self.dp = dp
        self.db = db
        self.payment_handler = payment_handler
        self.parser = parser
        
        # Регистрируем обработчики
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрирует все обработчики команд и callback'ов"""
        
        # Команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command('help'))
        self.dp.message.register(self.cmd_web, Command('web'))
        self.dp.message.register(self.cmd_admin, Command('admin'))
        
        # Callback обработчики
        self.dp.callback_query.register(self.cb_buy_tariff, F.data.startswith('buy_'))
        
        # Обработчик успешной оплаты
        self.dp.message.register(
            self.payment_handler.process_successful_payment,
            F.successful_payment
        )
        
        # Pre-checkout handler
        self.dp.pre_checkout_query.register(
            self.payment_handler.pre_checkout_handler
        )
    
    async def get_web_url(self, user_id: int, chat_id: int) -> str:
        """Генерирует URL веб-интерфейса"""
        # Для Railway используем домен из переменных окружения
        base_url = os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost:8080')
        return f"https://{base_url}/?user_id={user_id}&chat_id={chat_id}"
    
    async def cmd_start(self, message: Message):
        """Обработчик команды /start"""
        user = message.from_user
        
        # Сохраняем пользователя в БД
        await self.db.get_or_create_user(
            user.id, 
            user.username, 
            user.first_name
        )
        
        # Генерируем ссылку на веб-интерфейс
        web_url = await self.get_web_url(user.id, message.chat.id)
        
        welcome_text = (
            "✨ **Добро пожаловать в BProxy!** ✨\n\n"
            "🎉 **Мы полностью обновили бота!**\n\n"
            "Теперь у нас есть **удобный веб-интерфейс**, где вы можете:\n"
            "• 🔥 Получать рабочие прокси\n"
            "• 💎 Покупать доступ за Stars\n"
            "• 🎁 Активировать пробный период\n"
            "• 📋 Копировать прокси одним кликом\n\n"
            "👇 **Нажмите кнопку ниже, чтобы открыть веб-версию:**"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🚀 ОТКРЫТЬ ВЕБ-ИНТЕРФЕЙС', url=web_url)],
            [InlineKeyboardButton(text='❓ Помощь', callback_data='help')]
        ])
        
        await message.answer(
            welcome_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def cmd_web(self, message: Message):
        """Команда для получения ссылки на веб-интерфейс"""
        user = message.from_user
        web_url = await self.get_web_url(user.id, message.chat.id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🌐 ОТКРЫТЬ ВЕБ-ИНТЕРФЕЙС', url=web_url)]
        ])
        
        await message.answer(
            "🌐 **Веб-интерфейс BProxy**\n\n"
            "Нажмите кнопку ниже, чтобы открыть удобный веб-интерфейс "
            "для управления прокси:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def cmd_help(self, message: Message):
        """Обработчик команды /help"""
        user = message.from_user
        web_url = await self.get_web_url(user.id, message.chat.id)
        
        help_text = (
            "❓ **Помощь по BProxy**\n\n"
            "**Как пользоваться ботом:**\n"
            "1️⃣ Нажмите /web чтобы открыть веб-интерфейс\n"
            "2️⃣ Там вы можете:\n"
            "   • 🎁 Активировать пробный период (2 дня)\n"
            "   • 💎 Купить доступ за Stars\n"
            "   • 📡 Получать рабочие прокси\n"
            "   • 📋 Копировать их в буфер обмена\n\n"
            "**Команды:**\n"
            "/start - Начать работу\n"
            "/web - Открыть веб-интерфейс\n"
            "/help - Эта справка\n\n"
            "**Тарифы:**\n"
            f"• 1 день — {PRICES['1day']} ⭐\n"
            f"• 7 дней — {PRICES['7days']} ⭐\n"
            f"• 30 дней — {PRICES['30days']} ⭐\n"
            f"• Навсегда — {PRICES['forever']} ⭐\n\n"
            "По всем вопросам: @admin"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🚀 ОТКРЫТЬ ВЕБ-ИНТЕРФЕЙС', url=web_url)]
        ])
        
        await message.answer(help_text, reply_markup=keyboard, parse_mode='Markdown')
    
    async def cmd_admin(self, message: Message):
        """Админская панель (упрощенная)"""
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещен")
            return
        
        stats = await self.db.get_stats(days=7)
        
        admin_text = (
            "👨‍💻 **АДМИН ПАНЕЛЬ**\n\n"
            f"👥 **Пользователей:** {stats['total_users']}\n"
            f"✨ **Активных:** {stats['active_subs']}\n"
            f"💰 **Заработано:** {stats['total_payments']} ⭐\n"
            f"🔌 **Прокси:** {stats['total_proxies']}\n\n"
            "📊 **Команды:**\n"
            "/admin - это меню\n"
            "/parser - запустить парсер\n"
            "/stats - статистика"
        )
        
        await message.answer(admin_text, parse_mode='Markdown')
    
    async def cb_buy_tariff(self, callback: CallbackQuery):
        """Обработчик покупки тарифа"""
        tariff = callback.data
        
        try:
            await self.payment_handler.create_invoice(callback.from_user.id, tariff)
            await callback.answer("✅ Счет создан! Проверьте чат.")
        except Exception as e:
            logger.error(f"Ошибка создания инвойса: {e}")
            await callback.answer("❌ Ошибка создания счета", show_alert=True)
    
    async def process_broadcast(self, message: Message, state: FSMContext):
        """Обработчик рассылки (для админа)"""
        if message.from_user.id != ADMIN_ID:
            return
        
        # Здесь можно реализовать рассылку при необходимости
        pass
