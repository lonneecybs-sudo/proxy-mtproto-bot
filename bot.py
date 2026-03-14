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

# Состояния для FSM (админские функции)
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_bp_amount = State()
    waiting_for_bp_reason = State()

class BotHandler:
    
    def __init__(self, bot: Bot, dp: Dispatcher, db: Database, 
                 payment_handler: PaymentHandler, parser: ProxyParser):
        self.bot = bot
        self.dp = dp
        self.db = db
        self.payment_handler = payment_handler
        self.parser = parser
        
        self._register_handlers()
    
    def _register_handlers(self):
        # Команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command('help'))
        self.dp.message.register(self.cmd_proxies, Command('proxies'))
        self.dp.message.register(self.cmd_profile, Command('profile'))
        self.dp.message.register(self.cmd_buy, Command('buy'))
        self.dp.message.register(self.cmd_balance, Command('balance'))
        self.dp.message.register(self.cmd_admin, Command('admin'))
        
        # Админские команды для BP
        self.dp.message.register(self.cmd_add_bp, Command('addbp'))
        self.dp.message.register(self.cmd_bp_list, Command('bplist'))
        
        # Обработчики кнопок меню
        self.dp.message.register(self.menu_buy, F.text == '🛒 Купить прокси')
        self.dp.message.register(self.menu_proxies, F.text == '📡 Мои прокси')
        self.dp.message.register(self.menu_profile, F.text == '👤 Профиль')
        self.dp.message.register(self.menu_balance, F.text == '💰 BP Баланс')
        self.dp.message.register(self.menu_help, F.text == '❓ Помощь')
        
        # Callback обработчики
        self.dp.callback_query.register(self.cb_buy_access, F.data == 'buy_access')
        self.dp.callback_query.register(self.cb_get_proxies, F.data == 'get_proxies')
        self.dp.callback_query.register(self.cb_help, F.data == 'help')
        self.dp.callback_query.register(self.cb_buy_tariff, F.data.startswith('buy_'))
        self.dp.callback_query.register(self.cb_refresh_proxies, F.data == 'refresh_proxies')
        self.dp.callback_query.register(self.cb_copy_all, F.data == 'copy_all')
        self.dp.callback_query.register(self.cb_trial, F.data == 'trial')
        
        # Обработчик успешной оплаты
        self.dp.message.register(
            self.payment_handler.process_successful_payment,
            F.successful_payment
        )
        
        self.dp.pre_checkout_query.register(
            self.payment_handler.pre_checkout_handler
        )
    
    async def get_main_keyboard(self) -> ReplyKeyboardMarkup:
        keyboard = [
            [KeyboardButton(text='🛒 Купить прокси'), KeyboardButton(text='📡 Мои прокси')],
            [KeyboardButton(text='👤 Профиль'), KeyboardButton(text='💰 BP Баланс')],
            [KeyboardButton(text='❓ Помощь')]
        ]
        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True
        )
    
    async def cmd_start(self, message: Message):
        user = message.from_user
        await self.db.get_or_create_user(user.id, user.username, user.first_name)
        
        welcome_text = (
            "✨ **Добро пожаловать в BProxy!** ✨\n\n"
            "💰 **Внутренняя валюта BP:**\n"
            "• 1 ⭐ = 1 BP\n"
            "• Покупай подписки за BP\n\n"
            "🔥 **Преимущества:**\n"
            "• ✅ Рабочие прокси 24/7\n"
            "• ⚡ Высокая скорость\n"
            "• 🔒 Безопасное подключение\n\n"
            "👇 **Выберите действие:**"
        )
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='🛒 КУПИТЬ ДОСТУП', callback_data='buy_access'),
                InlineKeyboardButton(text='📡 ПОЛУЧИТЬ ПРОКСИ', callback_data='get_proxies')
            ],
            [
                InlineKeyboardButton(text='🎁 2 ДНЯ БЕСПЛАТНО', callback_data='trial'),
                InlineKeyboardButton(text='❓ ПОМОЩЬ', callback_data='help')
            ]
        ])
        
        await message.answer(welcome_text, reply_markup=inline_keyboard, parse_mode='Markdown')
        await message.answer("📱 **Главное меню:**", reply_markup=await self.get_main_keyboard(), parse_mode='Markdown')
    
    async def cmd_balance(self, message: Message):
        """Показать баланс BP"""
        user_id = message.from_user.id
        balance = await self.db.get_bp_balance(user_id)
        
        text = (
            f"💰 **BP БАЛАНС**\n\n"
            f"У вас: **{balance} BP**\n\n"
            f"1 ⭐ = 1 BP\n"
            f"Купите звезды и конвертируйте в BP!"
        )
        
        await message.answer(text, parse_mode='Markdown')
    
    async def cmd_profile(self, message: Message):
        user = message.from_user
        user_data = await self.db.get_or_create_user(user.id, user.username, user.first_name)
        balance = await self.db.get_bp_balance(user.id)
        
        has_premium = await self.db.check_subscription(user.id)
        
        if has_premium:
            if user_data['is_forever']:
                status = "🔥 Премиум НАВСЕГДА"
                expiry = "бессрочно"
            else:
                status = "⭐ Премиум"
                expiry = user_data['subscription_end'].split()[0] if user_data['subscription_end'] else "неизвестно"
        else:
            status = "🆓 Бесплатный"
            expiry = "нет"
        
        profile_text = (
            f"👤 **ПРОФИЛЬ**\n\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"👤 **Имя:** {user.first_name}\n"
            f"💰 **BP:** {balance}\n"
            f"⭐ **Статус:** {status}\n"
            f"📅 **Подписка до:** {expiry}\n"
            f"🎁 **Получено прокси:** {user_data['proxies_received']}"
        )
        
        await message.answer(profile_text, parse_mode='Markdown')
    
    # АДМИНСКИЕ КОМАНДЫ ДЛЯ BP
    
    async def cmd_add_bp(self, message: Message):
        """Добавить BP пользователю (только админ)"""
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещен")
            return
        
        args = message.text.split()
        if len(args) != 3:
            await message.answer("❌ Использование: /addbp [user_id] [количество]")
            return
        
        try:
            user_id = int(args[1])
            amount = int(args[2])
            
            # Проверяем существует ли пользователь
            user = await self.db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
            if not user:
                await message.answer("❌ Пользователь не найден")
                return
            
            new_balance = await self.db.add_bp(user_id, amount, f"Выдано админом", message.from_user.id)
            
            await message.answer(
                f"✅ **BP добавлены!**\n\n"
                f"Пользователь: {user_id}\n"
                f"Добавлено: {amount} BP\n"
                f"Новый баланс: {new_balance} BP"
            )
            
            # Уведомляем пользователя
            try:
                await self.bot.send_message(
                    user_id,
                    f"💰 **Вам начислено {amount} BP!**\n"
                    f"Текущий баланс: {new_balance} BP"
                )
            except:
                pass
                
        except ValueError:
            await message.answer("❌ Неверный формат чисел")
    
    async def cmd_bp_list(self, message: Message):
        """Показать всех пользователей с BP (только админ)"""
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещен")
            return
        
        users = await self.db.get_all_users_balance()
        
        if not users:
            await message.answer("📭 Нет пользователей")
            return
        
        text = "💰 **BALANCE BP ВСЕХ ПОЛЬЗОВАТЕЛЕЙ**\n\n"
        for user in users[:20]:  # Показываем первых 20
            name = user['first_name'] or user['username'] or "No name"
            text += f"• {name} (ID: {user['user_id']}): **{user['bp_balance']} BP**\n"
        
        if len(users) > 20:
            text += f"\n... и еще {len(users) - 20} пользователей"
        
        await message.answer(text, parse_mode='Markdown')
    
    # ОСТАЛЬНЫЕ МЕТОДЫ (без изменений)
    
    async def cmd_help(self, message: Message):
        help_text = (
            "❓ **Помощь**\n\n"
            "**Команды:**\n"
            "/start - Начать работу\n"
            "/buy - Купить доступ\n"
            "/proxies - Получить прокси\n"
            "/profile - Мой профиль\n"
            "/balance - BP баланс\n"
            "/help - Эта справка\n\n"
            "**Тарифы в BP:**\n"
            f"• 1 день — {PRICES['1day']} BP\n"
            f"• 7 дней — {PRICES['7days']} BP\n"
            f"• 30 дней — {PRICES['30days']} BP\n"
            f"• Навсегда — {PRICES['forever']} BP\n\n"
            "1 ⭐ = 1 BP"
        )
        await message.answer(help_text, parse_mode='Markdown')
    
    async def menu_buy(self, message: Message):
        await self.show_tariffs(message)
    
    async def menu_proxies(self, message: Message):
        await self.cmd_proxies(message)
    
    async def menu_profile(self, message: Message):
        await self.cmd_profile(message)
    
    async def menu_balance(self, message: Message):
        await self.cmd_balance(message)
    
    async def menu_help(self, message: Message):
        await self.cmd_help(message)
    
    async def cmd_proxies(self, message: Message):
        user_id = message.from_user.id
        has_access = await self.db.check_subscription(user_id)
        
        if not has_access:
            await message.answer(
                "❌ **У вас нет активной подписки!**",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='🛒 КУПИТЬ ДОСТУП', callback_data='buy_access')]
                ]),
                parse_mode='Markdown'
            )
            return
        
        wait_msg = await message.answer("🔍 **ИЩУ РАБОЧИЕ ПРОКСИ...** ⏳")
        
        proxies = await self.db.get_working_proxies(limit=10)
        
        if not proxies:
            await wait_msg.delete()
            await message.answer(
                "😕 **Временно нет прокси**",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='🔄 ОБНОВИТЬ', callback_data='refresh_proxies')]
                ])
            )
            return
        
        proxy_text = f"✅ **АКТУАЛЬНЫЕ ПРОКСИ НА {datetime.now().strftime('%d.%m.%Y %H:%M')}:**\n\n"
        
        for i, proxy in enumerate(proxies[:5], 1):
            proxy_text += f"{i}. 🔌 `{proxy['proxy_link']}`\n\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='🔄 ОБНОВИТЬ', callback_data='refresh_proxies'),
                InlineKeyboardButton(text='📋 КОПИРОВАТЬ ВСЕ', callback_data='copy_all')
            ]
        ])
        
        await wait_msg.delete()
        await message.answer(proxy_text, reply_markup=keyboard, parse_mode='Markdown')
        
        await self.db.execute(
            "UPDATE users SET proxies_received = proxies_received + 1 WHERE user_id = ?",
            (user_id,)
        )
    
    async def show_tariffs(self, message: Message):
        tariffs_text = (
            "⚡ **ПРЕМИУМ ДОСТУП К ПРОКСИ** ⚡\n\n"
            "💰 **Цены в BP:**\n"
            f"🟢 **1 день** — {PRICES['1day']} BP\n"
            f"🔵 **7 дней** — {PRICES['7days']} BP\n"
            f"🟣 **30 дней** — {PRICES['30days']} BP\n"
            f"🟡 **НАВСЕГДА** — {PRICES['forever']} BP\n\n"
            "1 ⭐ = 1 BP\n"
            "Звезды автоматически конвертируются в BP при покупке"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f'КУПИТЬ 1 ДЕНЬ ЗА {PRICES["1day"]} ⭐', callback_data='buy_1day')],
            [InlineKeyboardButton(text=f'КУПИТЬ 7 ДНЕЙ ЗА {PRICES["7days"]} ⭐', callback_data='buy_7days')],
            [InlineKeyboardButton(text=f'КУПИТЬ 30 ДНЕЙ ЗА {PRICES["30days"]} ⭐', callback_data='buy_30days')],
            [InlineKeyboardButton(text=f'КУПИТЬ НАВСЕГДА ЗА {PRICES["forever"]} ⭐', callback_data='buy_forever')]
        ])
        
        await message.answer(tariffs_text, reply_markup=keyboard, parse_mode='Markdown')
    
    async def cb_buy_access(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.show_tariffs(callback.message)
        await callback.answer()
    
    async def cb_get_proxies(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.cmd_proxies(callback.message)
        await callback.answer()
    
    async def cb_help(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.cmd_help(callback.message)
        await callback.answer()
    
    async def cb_buy_tariff(self, callback: CallbackQuery):
        tariff = callback.data
        
        try:
            await self.payment_handler.create_invoice(callback.from_user.id, tariff)
            await callback.answer("✅ Счет создан! Проверьте чат с ботом.")
        except Exception as e:
            logger.error(f"Ошибка создания инвойса: {e}")
            await callback.answer("❌ Ошибка создания счета", show_alert=True)
    
    async def cb_refresh_proxies(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.cmd_proxies(callback.message)
        await callback.answer()
    
    async def cb_copy_all(self, callback: CallbackQuery):
        text = callback.message.text
        proxies = re.findall(r'🔌 `(proxy[^`]+)`', text)
        
        if proxies:
            all_proxies = '\n'.join(proxies)
            await callback.message.answer(
                f"📋 **Все прокси скопированы:**\n\n`{all_proxies}`",
                parse_mode='Markdown'
            )
        await callback.answer("✅ Скопировано!")
    
    async def cb_trial(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        trial_available = await self.db.check_trial_available(user_id)
        
        if not trial_available:
            await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
            return
        
        success = await self.db.activate_trial(user_id)
        
        if success:
            await callback.message.edit_text(
                "✅ **Пробный период активирован!**\n\n"
                "🎁 Вам начислено **2 дня** бесплатного доступа.\n"
                "Теперь вы можете получать прокси.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='📡 ПОЛУЧИТЬ ПРОКСИ', callback_data='get_proxies')]
                ]),
                parse_mode='Markdown'
            )
        else:
            await callback.answer("❌ Ошибка активации пробного периода", show_alert=True)
        
        await callback.answer()
    
    async def cmd_admin(self, message: Message):
        """Админская панель"""
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещен")
            return
        
        stats = await self.db.get_stats()
        
        admin_text = (
            "👨‍💻 **АДМИН ПАНЕЛЬ**\n\n"
            f"👥 **Пользователей:** {stats['total_users']}\n"
            f"✨ **Активных подписок:** {stats['active_subs']}\n"
            f"💰 **Всего BP:** {stats['total_bp']}\n"
            f"🔌 **Рабочих прокси:** {stats['total_proxies']}\n\n"
            "📝 **Команды:**\n"
            "/addbp [id] [количество] - выдать BP\n"
            "/bplist - список всех BP\n"
            "/admin - это меню"
        )
        
        await message.answer(admin_text, parse_mode='Markdown')
