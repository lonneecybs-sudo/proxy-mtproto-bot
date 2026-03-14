"""
"""
import logging
import asyncio
import os
import re
from datetime import datetime, timedelta
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
    ИМБОВЫЙ КЛАСС С КРУТЫМИ ОБРАБОТЧИКАМИ
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
        self.dp.message.register(self.cmd_proxies, Command('proxies'))
        self.dp.message.register(self.cmd_profile, Command('profile'))
        self.dp.message.register(self.cmd_buy, Command('buy'))
        self.dp.message.register(self.cmd_stats, Command('stats'))
        self.dp.message.register(self.cmd_admin, Command('admin'))
        
        # Обработчики кнопок главного меню
        self.dp.message.register(self.menu_buy, F.text == '🛒 Купить прокси')
        self.dp.message.register(self.menu_proxies, F.text == '📡 Мои прокси')
        self.dp.message.register(self.menu_stats, F.text == '📊 Статистика')
        self.dp.message.register(self.menu_help, F.text == '❓ Помощь')
        self.dp.message.register(self.menu_profile, F.text == '👤 Профиль')
        self.dp.message.register(self.menu_balance, F.text == '⭐ Баланс Stars')
        
        # Callback обработчики
        self.dp.callback_query.register(self.cb_buy_access, F.data == 'buy_access')
        self.dp.callback_query.register(self.cb_get_proxies, F.data == 'get_proxies')
        self.dp.callback_query.register(self.cb_help, F.data == 'help')
        self.dp.callback_query.register(self.cb_my_subscriptions, F.data == 'my_subscriptions')
        self.dp.callback_query.register(self.cb_buy_tariff, F.data.startswith('buy_'))
        self.dp.callback_query.register(self.cb_refresh_proxies, F.data == 'refresh_proxies')
        self.dp.callback_query.register(self.cb_copy_all, F.data == 'copy_all')
        self.dp.callback_query.register(self.cb_refresh_profile, F.data == 'refresh_profile')
        self.dp.callback_query.register(self.cb_trial, F.data == 'trial')
        
        # Обработчик успешной оплаты
        self.dp.message.register(
            self.payment_handler.process_successful_payment,
            F.successful_payment
        )
        
        # Pre-checkout handler
        self.dp.pre_checkout_query.register(
            self.payment_handler.pre_checkout_handler
        )
    
    async def get_main_keyboard(self) -> ReplyKeyboardMarkup:
        """Создает главную клавиатуру"""
        keyboard = [
            [KeyboardButton(text='🛒 Купить прокси'), KeyboardButton(text='📡 Мои прокси')],
            [KeyboardButton(text='📊 Статистика'), KeyboardButton(text='❓ Помощь')],
            [KeyboardButton(text='👤 Профиль'), KeyboardButton(text='⭐ Баланс Stars')]
        ]
        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            input_field_placeholder="Выберите действие..."
        )
    
    async def cmd_start(self, message: Message):
        """Обработчик команды /start"""
        user = message.from_user
        
        # Сохраняем пользователя в БД
        await self.db.get_or_create_user(
            user.id, 
            user.username, 
            user.first_name
        )
        
        # Отправляем приветствие
        welcome_text = (
            "✨ **Добро пожаловать в BProxy!** ✨\n\n"
            "🔥 **Преимущества:**\n"
            "• ✅ Рабочие прокси 24/7\n"
            "• ⚡ Высокая скорость\n"
            "• 🔒 Безопасное подключение\n"
            "• 💫 Оплата звездами Telegram\n\n"
            "👇 **Выберите действие:**"
        )
        
        # Создаем инлайн клавиатуру
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='🛒 КУПИТЬ ДОСТУП', callback_data='buy_access'),
                InlineKeyboardButton(text='📡 ПОЛУЧИТЬ ПРОКСИ', callback_data='get_proxies')
            ],
            [
                InlineKeyboardButton(text='🎁 2 ДНЯ БЕСПЛАТНО', callback_data='trial'),
                InlineKeyboardButton(text='❓ ПОМОЩЬ', callback_data='help')
            ],
            [
                InlineKeyboardButton(text='💳 МОИ ПОДПИСКИ', callback_data='my_subscriptions')
            ]
        ])
        
        await message.answer(
            welcome_text,
            reply_markup=inline_keyboard,
            parse_mode='Markdown'
        )
        
        # Отправляем главное меню
        await message.answer(
            "📱 **Главное меню:**",
            reply_markup=await self.get_main_keyboard(),
            parse_mode='Markdown'
        )
    
    async def cmd_help(self, message: Message):
        """Обработчик команды /help"""
        help_text = (
            "❓ **Помощь по использованию**\n\n"
            "**Как это работает:**\n"
            "1️⃣ Купите доступ на нужный срок\n"
            "2️⃣ Получите рабочие прокси\n"
            "3️⃣ Используйте их в любом приложении\n\n"
            "**Команды:**\n"
            "/start - Начать работу\n"
            "/buy - Купить доступ\n"
            "/proxies - Получить прокси\n"
            "/profile - Мой профиль\n"
            "/help - Эта справка\n\n"
            "**Тарифы:**\n"
            f"• 1 день — {PRICES['1day']} ⭐\n"
            f"• 7 дней — {PRICES['7days']} ⭐\n"
            f"• 30 дней — {PRICES['30days']} ⭐\n"
            f"• Навсегда — {PRICES['forever']} ⭐\n\n"
            "По всем вопросам: @admin"
        )
        await message.answer(help_text, parse_mode='Markdown')
    
    async def cmd_proxies(self, message: Message):
        """Обработчик команды /proxies"""
        user_id = message.from_user.id
        
        # Проверяем подписку
        has_access = await self.db.check_subscription(user_id)
        
        if not has_access:
            await message.answer(
                "❌ **У вас нет активной подписки!**\n\n"
                "Купите доступ чтобы получить прокси 👇",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='🛒 КУПИТЬ ДОСТУП', callback_data='buy_access')]
                ]),
                parse_mode='Markdown'
            )
            return
        
        # Отправляем сообщение с поиском
        wait_msg = await message.answer("🔍 **ИЩУ РАБОЧИЕ ПРОКСИ...** ⏳")
        
        # Получаем прокси из базы
        proxies = await self.db.get_working_proxies(limit=10)
        
        if not proxies:
            await wait_msg.delete()
            await message.answer(
                "😕 **Временно нет прокси**\n\n"
                "Попробуйте позже или обновите список",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='🔄 ОБНОВИТЬ', callback_data='refresh_proxies')]
                ])
            )
            return
        
        # Формируем сообщение с прокси
        proxy_text = f"✅ **АКТУАЛЬНЫЕ ПРОКСИ НА {datetime.now().strftime('%d.%m.%Y %H:%M')}:**\n\n"
        
        for i, proxy in enumerate(proxies[:5], 1):
            proxy_text += f"{i}. 🔌 `{proxy['proxy_link']}`\n\n"
        
        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='🔄 ОБНОВИТЬ', callback_data='refresh_proxies'),
                InlineKeyboardButton(text='📋 КОПИРОВАТЬ ВСЕ', callback_data='copy_all')
            ],
            [InlineKeyboardButton(text='📤 ПОДЕЛИТЬСЯ', switch_inline_query='прокси')]
        ])
        
        await wait_msg.delete()
        await message.answer(proxy_text, reply_markup=keyboard, parse_mode='Markdown')
        
        # Обновляем счетчик полученных прокси
        await self.db.execute(
            "UPDATE users SET proxies_received = proxies_received + 1 WHERE user_id = ?",
            (user_id,)
        )
    
    async def cmd_profile(self, message: Message):
        """Обработчик команды /profile"""
        user = message.from_user
        user_data = await self.db.get_or_create_user(user.id, user.username, user.first_name)
        
        # Проверяем статус подписки
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
            f"👤 **ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ**\n\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"👤 **Имя:** {user.first_name}\n"
            f"📛 **Username:** @{user.username if user.username else 'не указан'}\n"
            f"⭐ **Статус:** {status}\n"
            f"📅 **Подписка до:** {expiry}\n"
            f"🎁 **Получено прокси:** {user_data['proxies_received']}\n"
            f"💰 **Всего потрачено:** {user_data['total_paid']} ⭐\n"
            f"📆 **Регистрация:** {user_data['joined_date'].split()[0] if user_data['joined_date'] else 'неизвестно'}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='⭐ КУПИТЬ ПРЕМИУМ', callback_data='buy_access'),
                InlineKeyboardButton(text='🔄 ОБНОВИТЬ', callback_data='refresh_profile')
            ]
        ])
        
        await message.answer(profile_text, reply_markup=keyboard, parse_mode='Markdown')
    
    async def cmd_buy(self, message: Message):
        """Обработчик команды /buy"""
        await self.show_tariffs(message)
    
    async def cmd_stats(self, message: Message):
        """Обработчик команды /stats (публичная статистика)"""
        stats = await self.db.get_stats(days=7)
        
        stats_text = (
            f"📊 **СТАТИСТИКА БОТА**\n\n"
            f"👥 **Всего пользователей:** {stats['total_users']}\n"
            f"✨ **Активных подписок:** {stats['active_subs']}\n"
            f"💰 **Всего заработано:** {stats['total_payments']} ⭐\n"
            f"🔌 **Рабочих прокси:** {stats['total_proxies']}\n\n"
            f"📈 **За последние 7 дней:**\n"
        )
        
        for day_stat in stats['period_stats'][-7:]:
            stats_text += f"  • {day_stat['date']}: +{day_stat['new_users']} 👤\n"
        
        await message.answer(stats_text, parse_mode='Markdown')
    
    async def cmd_admin(self, message: Message):
        """Админская панель"""
        if message.from_user.id != ADMIN_ID:
            await message.answer("⛔ Доступ запрещен")
            return
        
        admin_text = (
            "👨‍💻 **АДМИН ПАНЕЛЬ**\n\n"
            "Выберите действие:"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='📊 СТАТИСТИКА', callback_data='admin_stats'),
                InlineKeyboardButton(text='📢 РАССЫЛКА', callback_data='admin_broadcast')
            ],
            [
                InlineKeyboardButton(text='🔄 ПАРСЕР', callback_data='admin_parser'),
                InlineKeyboardButton(text='📋 ЛОГИ', callback_data='admin_logs')
            ],
            [
                InlineKeyboardButton(text='🧹 ОЧИСТКА', callback_data='admin_cleanup'),
                InlineKeyboardButton(text='📦 ПРОКСИ-ПУЛ', callback_data='admin_proxy_pool')
            ]
        ])
        
        await message.answer(admin_text, reply_markup=keyboard, parse_mode='Markdown')
    
    async def show_tariffs(self, message: Message):
        """Показывает тарифы для покупки"""
        tariffs_text = (
            "⚡ **ПРЕМИУМ ДОСТУП К ПРОКСИ** ⚡\n\n"
            "Выберите тариф:\n\n"
            f"🟢 **1 день** — {PRICES['1day']} ⭐\n"
            f"🔵 **7 дней** — {PRICES['7days']} ⭐\n"
            f"🟣 **30 дней** — {PRICES['30days']} ⭐\n"
            f"🟡 **НАВСЕГДА** — {PRICES['forever']} ⭐\n\n"
            "После оплаты вы получите доступ к рабочим прокси"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f'КУПИТЬ 1 ДЕНЬ ЗА {PRICES["1day"]} ⭐', callback_data='buy_1day')],
            [InlineKeyboardButton(text=f'КУПИТЬ 7 ДНЕЙ ЗА {PRICES["7days"]} ⭐', callback_data='buy_7days')],
            [InlineKeyboardButton(text=f'КУПИТЬ 30 ДНЕЙ ЗА {PRICES["30days"]} ⭐', callback_data='buy_30days')],
            [InlineKeyboardButton(text=f'КУПИТЬ НАВСЕГДА ЗА {PRICES["forever"]} ⭐', callback_data='buy_forever')]
        ])
        
        await message.answer(tariffs_text, reply_markup=keyboard, parse_mode='Markdown')
    
    # Обработчики кнопок меню
    
    async def menu_buy(self, message: Message):
        await self.show_tariffs(message)
    
    async def menu_proxies(self, message: Message):
        await self.cmd_proxies(message)
    
    async def menu_stats(self, message: Message):
        await self.cmd_stats(message)
    
    async def menu_help(self, message: Message):
        await self.cmd_help(message)
    
    async def menu_profile(self, message: Message):
        await self.cmd_profile(message)
    
    async def menu_balance(self, message: Message):
        await message.answer(
            "⭐ **Баланс Stars**\n\n"
            "Ваш баланс Telegram Stars можно посмотреть в настройках Telegram.\n\n"
            "Пополнить баланс можно через @PremiumBot или в Telegram Premium.",
            parse_mode='Markdown'
        )
    
    # Обработчики callback'ов
    
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
    
    async def cb_my_subscriptions(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.cmd_profile(callback.message)
        await callback.answer()
    
    async def cb_refresh_profile(self, callback: CallbackQuery):
        await callback.message.delete()
        await self.cmd_profile(callback.message)
        await callback.answer()
    
    async def cb_buy_tariff(self, callback: CallbackQuery):
        tariff = callback.data
        
        # Создаем инвойс
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
        # Получаем текст сообщения и извлекаем прокси
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
        """Обработчик пробного периода"""
        user_id = callback.from_user.id
        
        # Проверяем, использовал ли пользователь пробный период
        trial_available = await self.db.check_trial_available(user_id)
        
        if not trial_available:
            await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
            return
        
        # Активируем пробный период
        success = await self.db.activate_trial(user_id)
        
        if success:
            await callback.message.edit_text(
                "✅ **Пробный период активирован!**\n\n"
                "🎁 Вам начислено **2 дня** бесплатного доступа.\n"
                "Теперь вы можете получать прокси.\n\n"
                "Нажмите ПОЛУЧИТЬ ПРОКСИ чтобы начать!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='📡 ПОЛУЧИТЬ ПРОКСИ', callback_data='get_proxies')]
                ]),
                parse_mode='Markdown'
            )
        else:
            await callback.answer("❌ Ошибка активации пробного периода", show_alert=True)
        
        await callback.answer()
    
    # Админские callback'и
    async def cb_admin_stats(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("📊 Статистика")
    
    async def cb_admin_broadcast(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("📢 Рассылка")
    
    async def cb_admin_parser(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("🔄 Парсер")
    
    async def cb_admin_logs(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("📋 Логи")
    
    async def cb_admin_cleanup(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("🧹 Очистка")
    
    async def cb_admin_proxy_pool(self, callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.answer("📦 Прокси-пул")
    
    # Обработчик для рассылки
    async def process_broadcast(self, message: Message, state: FSMContext):
        """Обрабатывает сообщение для рассылки"""
        if message.from_user.id != ADMIN_ID:
            return
        await message.answer("✅ Ок")
        await state.clear()
    
    async def broadcast_confirm(self, callback: CallbackQuery, state: FSMContext):
        """Подтверждение и отправка рассылки"""
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.message.edit_text("✅ Рассылка выполнена")
        await state.clear()
        await callback.answer()
    
    async def broadcast_cancel(self, callback: CallbackQuery, state: FSMContext):
        """Отмена рассылки"""
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен", show_alert=True)
            return
        await callback.message.edit_text("❌ Рассылка отменена")
        await state.clear()
        await callback.answer()
