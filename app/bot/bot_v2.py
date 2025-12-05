#!/usr/bin/env python3
"""
Smart Campus Telegram Bot v2
With secure login flow and AI integration
"""

import asyncio
import logging
import os
import re
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import Counter
from zoneinfo import ZoneInfo

# Load environment variables BEFORE importing other modules
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from app.core.calendar_service import CalendarService
from app.core.database import Database
from app.core.credentials import CredentialManager
from app.core.schedule_monitor import ScheduleMonitor
from app.ai.providers import AIManager, Message
from app.ai.intent_classifier import IntentClassifier

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    STATE_AWAITING_USERNAME,
    STATE_AWAITING_PASSWORD,
    STATE_AWAITING_GROUP,
    STATE_AWAITING_FEEDBACK,
    STATE_CONFIRM_LOGOUT,
    STATE_AWAITING_NOTE,
    STATE_AWAITING_DEADLINE,
    STATE_AWAITING_REMINDER,
) = range(8)

# Campus building info
CAMPUS_ROOMS = {
    "1": {"name": "Главный корпус", "floors": 5, "location": "Lomonosova 1"},
    "2": {"name": "Технический корпус", "floors": 3, "location": "Lomonosova 1/4"},
    "3": {"name": "Учебный корпус", "floors": 4, "location": "Lomonosova 1/5"},
}

# Motivational quotes for students
MOTIVATION_QUOTES = [
    "💪 Ты справишься! Каждая пара — шаг к успеху!",
    "🎯 Фокус на цели! Сессия не за горами!",
    "📚 Знания — это сила. Учись и покоряй!",
    "🚀 Сегодня учимся — завтра летаем!",
    "☕ Кофе + лекция = продуктивный день!",
    "🧠 Каждый день — новые нейронные связи!",
    "✨ Ты умнее, чем думаешь!",
    "🎓 Диплом уже ждёт тебя!",
]


def get_main_keyboard(is_logged_in: bool = False) -> ReplyKeyboardMarkup:
    """Get persistent keyboard with Menu button"""
    webapp_url = os.getenv('WEBAPP_URL')
    
    if is_logged_in:
        keyboard = [
            [KeyboardButton("📋 Menu"), KeyboardButton("📅 Сегодня"), KeyboardButton("📅 Завтра")],
        ]
    else:
        keyboard = [
            [KeyboardButton("📋 Menu"), KeyboardButton("📅 Сегодня"), KeyboardButton("📅 Завтра")],
            [KeyboardButton("🔐 Войти")],
        ]
    
    return ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True,  # Компактная клавиатура
        is_persistent=True     # Всегда видна
    )


class SmartCampusBotV2:
    """Enhanced Telegram Bot with login flow and AI"""
    
    def __init__(self, token: str):
        self.token = token
        
        # Initialize services
        self.db = Database()
        self.credentials = CredentialManager()
        self.ai_manager = AIManager()
        self.intent_classifier = IntentClassifier()
        
        # User calendar services (per-user)
        self._user_calendars: Dict[int, CalendarService] = {}
        
        # Conversation history for AI (per-user, limited)
        self._conversation_history: Dict[int, list] = {}
        
        # Start reminder checker
        self._reminder_task = None
        
        # Schedule monitor for cancellation notifications
        self.schedule_monitor = ScheduleMonitor(self.db, self.credentials)
        self._monitor_task = None
        
        # Build application
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _get_calendar_service(self, telegram_id: int) -> Optional[CalendarService]:
        """Get or create calendar service for user"""
        if telegram_id in self._user_calendars:
            service = self._user_calendars[telegram_id]
            if service.is_authenticated():
                return service
        
        # Try to login with stored credentials
        creds = self.credentials.get_credentials(telegram_id)
        if not creds:
            return None
        
        try:
            service = CalendarService(
                username=creds["username"],
                password=creds["password"]
            )
            if service.login():
                self._user_calendars[telegram_id] = service
                self.credentials.verify_credentials(telegram_id, True)
                return service
            else:
                self.credentials.record_failed_login(telegram_id)
                return None
        except Exception as e:
            logger.error(f"Login error for {telegram_id}: {e}")
            return None
    
    def _setup_handlers(self):
        """Setup all message handlers"""
        app = self.application
        
        # Login conversation handler - MUST BE FIRST with high priority (group 0)
        login_conv = ConversationHandler(
            entry_points=[
                CommandHandler("login", self.cmd_login),
                CallbackQueryHandler(self.cb_login_start, pattern="^login$"),
                MessageHandler(filters.Regex("^🔐 Войти$"), self.cmd_login)
            ],
            states={
                STATE_AWAITING_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_username)
                ],
                STATE_AWAITING_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_password)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cmd_cancel),
                CallbackQueryHandler(self.cb_cancel, pattern="^cancel$")
            ],
            conversation_timeout=300,  # 5 minutes timeout
            per_message=False,
            per_chat=True,
            per_user=True
        )
        app.add_handler(login_conv, group=0)
        
        # Command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("menu", self.cmd_menu))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("today", self.cmd_today))
        app.add_handler(CommandHandler("tomorrow", self.cmd_tomorrow))
        app.add_handler(CommandHandler("week", self.cmd_week))
        app.add_handler(CommandHandler("next", self.cmd_next))
        app.add_handler(CommandHandler("setgroup", self.cmd_setgroup))
        app.add_handler(CommandHandler("mygroup", self.cmd_mygroup))
        app.add_handler(CommandHandler("settings", self.cmd_settings))
        app.add_handler(CommandHandler("freerooms", self.cmd_freerooms))
        app.add_handler(CommandHandler("search", self.cmd_search))
        app.add_handler(CommandHandler("logout", self.cmd_logout))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("ai", self.cmd_ai_status))
        
        # New feature commands
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("exam", self.cmd_exams))
        app.add_handler(CommandHandler("exams", self.cmd_exams))
        app.add_handler(CommandHandler("where", self.cmd_where))
        app.add_handler(CommandHandler("weather", self.cmd_weather))
        app.add_handler(CommandHandler("motivation", self.cmd_motivation))
        app.add_handler(CommandHandler("note", self.cmd_note))
        app.add_handler(CommandHandler("notes", self.cmd_notes))
        app.add_handler(CommandHandler("deadline", self.cmd_deadline))
        app.add_handler(CommandHandler("deadlines", self.cmd_deadlines))
        app.add_handler(CommandHandler("export", self.cmd_export))
        app.add_handler(CommandHandler("remind", self.cmd_remind))
        app.add_handler(CommandHandler("reminders", self.cmd_reminders))
        
        # My TSI commands (student portal)
        app.add_handler(CommandHandler("grades", self.cmd_grades))
        app.add_handler(CommandHandler("gpa", self.cmd_gpa))
        app.add_handler(CommandHandler("bills", self.cmd_bills))
        app.add_handler(CommandHandler("profile", self.cmd_profile))
        app.add_handler(CommandHandler("attendance", self.cmd_attendance))
        
        # Callback query handler for inline buttons
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handler for natural language (AI) - LOWER PRIORITY (group 1)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ), group=1)
        
        # Error handler
        app.add_error_handler(self.error_handler)
    
    async def set_commands(self):
        """Set bot commands for the menu"""
        commands = [
            BotCommand("start", "🚀 Начать работу"),
            BotCommand("menu", "📋 Главное меню"),
            BotCommand("login", "🔐 Войти в аккаунт TSI"),
            BotCommand("today", "📅 Сегодня"),
            BotCommand("tomorrow", "📅 Завтра"),
            BotCommand("week", "📅 Неделя"),
            BotCommand("grades", "📊 Оценки"),
            BotCommand("gpa", "📈 Средний балл"),
            BotCommand("bills", "💰 Счета"),
            BotCommand("remind", "⏰ Напоминание"),
            BotCommand("notes", "📝 Заметки"),
            BotCommand("help", "❓ Справка"),
        ]
        await self.application.bot.set_my_commands(commands)
        
        # Set Menu button to open Mini App if URL is configured
        webapp_url = os.getenv('WEBAPP_URL')
        if webapp_url:
            try:
                await self.application.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="📱 Открыть",
                        web_app=WebAppInfo(url=webapp_url)
                    )
                )
                logger.info(f"Menu button set to WebApp: {webapp_url}")
            except Exception as e:
                logger.warning(f"Failed to set menu button: {e}")
    
    # ==================== Login Flow ====================
    
    async def cmd_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start login process"""
        telegram_id = update.effective_user.id
        
        # Check if already logged in
        if self.credentials.has_credentials(telegram_id):
            creds = self.credentials.get_credentials(telegram_id)
            if creds and creds.get("is_verified"):
                keyboard = [[
                    InlineKeyboardButton("🔄 Перелогиниться", callback_data="relogin"),
                    InlineKeyboardButton("🚪 Выйти", callback_data="logout")
                ]]
                await update.message.reply_text(
                    f"✅ Ты уже авторизован как **{creds['username']}**\n\n"
                    "Хочешь войти в другой аккаунт?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        
        # Mark that user is in login flow
        context.user_data["in_login_flow"] = True
        
        await update.message.reply_text(
            "🔐 **Авторизация в TSI**\n\n"
            "Введи свой студенческий логин (например: `st12345`):\n\n"
            "⚠️ _Твои данные будут зашифрованы и храниться безопасно._\n"
            "_Отправь /cancel для отмены._",
            parse_mode="Markdown"
        )
        return STATE_AWAITING_USERNAME
    
    async def cb_login_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start login from callback button"""
        query = update.callback_query
        await query.answer()
        
        # Mark that user is in login flow
        context.user_data["in_login_flow"] = True
        
        await query.edit_message_text(
            "🔐 **Авторизация в TSI**\n\n"
            "Введи свой студенческий логин (например: `st12345`):\n\n"
            "⚠️ _Твои данные будут зашифрованы._\n"
            "_Отправь /cancel для отмены._",
            parse_mode="Markdown"
        )
        return STATE_AWAITING_USERNAME
    
    async def handle_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle username input"""
        username = update.message.text.strip().lower()
        
        # Validate username format
        if not re.match(r'^st\d{5,6}$', username):
            await update.message.reply_text(
                "❌ Неверный формат логина.\n"
                "Логин должен быть в формате: `st12345`\n\n"
                "Попробуй ещё раз или /cancel для отмены.",
                parse_mode="Markdown"
            )
            return STATE_AWAITING_USERNAME
        
        # Store username temporarily
        context.user_data["tsi_username"] = username
        
        # Delete the message with username for security
        try:
            await update.message.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"👤 Логин: `{username}`\n\n"
            "Теперь введи пароль:\n\n"
            "🔒 _Сообщение с паролем будет удалено автоматически._",
            parse_mode="Markdown"
        )
        return STATE_AWAITING_PASSWORD
    
    async def handle_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password input and attempt login"""
        telegram_id = update.effective_user.id
        password = update.message.text
        username = context.user_data.get("tsi_username")
        
        # Delete the message with password immediately
        try:
            await update.message.delete()
        except:
            pass
        
        if not username:
            await update.message.reply_text(
                "❌ Сессия истекла. Начни заново: /login"
            )
            return ConversationHandler.END
        
        # Send "logging in" message
        status_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔄 Проверяю данные..."
        )
        
        # Try to login
        try:
            service = CalendarService(username=username, password=password)
            if service.login():
                # Store encrypted credentials
                self.credentials.store_credentials(telegram_id, username, password)
                self.credentials.verify_credentials(telegram_id, True)
                self._user_calendars[telegram_id] = service
                
                # Create user in database
                self.db.create_user(
                    telegram_id=telegram_id,
                    username=update.effective_user.username,
                    student_id=username
                )
                
                await status_msg.edit_text(
                    f"✅ **Авторизация успешна!**\n\n"
                    f"👤 Аккаунт: `{username}`\n\n"
                    f"Теперь установи свою группу:\n"
                    f"`/setgroup [код группы]`\n\n"
                    f"Например: `/setgroup 3401BNA`",
                    parse_mode="Markdown"
                )
                
                # Update keyboard to show logged-in buttons
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="🎉 Готово! Используй кнопки ниже:",
                    reply_markup=get_main_keyboard(is_logged_in=True)
                )
            else:
                self.credentials.record_failed_login(telegram_id)
                await status_msg.edit_text(
                    "❌ **Неверный логин или пароль**\n\n"
                    "Проверь данные и попробуй снова: /login"
                )
        except Exception as e:
            logger.error(f"Login error: {e}")
            await status_msg.edit_text(
                "❌ **Ошибка подключения к TSI**\n\n"
                "Попробуй позже: /login"
            )
        
        # Clear temporary data (including login flow flag)
        context.user_data.pop("tsi_username", None)
        context.user_data.pop("in_login_flow", None)
        return ConversationHandler.END
    
    async def cmd_logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Logout user"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("❌ Ты не авторизован.")
            return
        
        # Delete credentials and session
        self.credentials.delete_credentials(telegram_id)
        if telegram_id in self._user_calendars:
            self._user_calendars[telegram_id].close()
            del self._user_calendars[telegram_id]
        
        await update.message.reply_text(
            "✅ Ты успешно вышел из аккаунта.\n\n"
            "Для входа: /login",
            reply_markup=get_main_keyboard(is_logged_in=False)
        )
    
    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation"""
        context.user_data.clear()
        await update.message.reply_text("❌ Операция отменена.")
        return ConversationHandler.END
    
    async def cb_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel from callback"""
        query = update.callback_query
        await query.answer()
        context.user_data.clear()
        await query.edit_message_text("❌ Операция отменена.")
        return ConversationHandler.END
    
    # ==================== Command Handlers ====================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        telegram_id = user.id
        
        # Create user in database
        self.db.create_user(
            telegram_id=telegram_id,
            username=user.username
        )
        
        # Check login status
        is_logged_in = self.credentials.has_credentials(telegram_id)
        creds = self.credentials.get_credentials(telegram_id) if is_logged_in else None
        
        if is_logged_in and creds and creds.get("is_verified"):
            # User is logged in
            keyboard = [
                [
                    InlineKeyboardButton("📅 Сегодня", callback_data="schedule_today"),
                    InlineKeyboardButton("📅 Завтра", callback_data="schedule_tomorrow")
                ],
                [
                    InlineKeyboardButton("⏰ След. пара", callback_data="next_class"),
                    InlineKeyboardButton("📅 Неделя", callback_data="schedule_week")
                ],
                [
                    InlineKeyboardButton("📝 Заметки", callback_data="menu_notes"),
                    InlineKeyboardButton("⏰ Напоминания", callback_data="menu_reminders")
                ],
                [
                    InlineKeyboardButton("📊 Ещё", callback_data="menu_more"),
                    InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
                ]
            ]
            welcome_text = f"""
👋 **{user.first_name}**, добро пожаловать!

✅ Аккаунт: `{creds['username']}`
🤖 AI: активен

**Быстрые команды** — кнопки ниже
**Или просто напиши**, например:
_"Что сегодня?" / "Напомни через час..."_
            """
        else:
            # User not logged in
            keyboard = [
                [InlineKeyboardButton("🔐 Войти в TSI", callback_data="login")],
                [InlineKeyboardButton("❓ Что умеет бот?", callback_data="help")]
            ]
            welcome_text = f"""
👋 Привет, **{user.first_name}**!

Я **Smart Campus Assistant** 🎓
Твой помощник для TSI

🔐 Войди, чтобы видеть расписание
            """
        
        # Send with both inline keyboard and persistent reply keyboard
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(is_logged_in),
            parse_mode="Markdown"
        )
        
        # Also send inline menu
        await update.message.reply_text(
            "👇 **Быстрые действия:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu with buttons"""
        telegram_id = update.effective_user.id
        is_logged_in = self.credentials.has_credentials(telegram_id)
        
        if is_logged_in:
            keyboard = [
                [
                    InlineKeyboardButton("📅 Сегодня", callback_data="schedule_today"),
                    InlineKeyboardButton("📅 Завтра", callback_data="schedule_tomorrow")
                ],
                [
                    InlineKeyboardButton("⏰ След. пара", callback_data="next_class"),
                    InlineKeyboardButton("📅 Неделя", callback_data="schedule_week")
                ],
                [
                    InlineKeyboardButton("📝 Заметки", callback_data="menu_notes"),
                    InlineKeyboardButton("⏰ Напоминания", callback_data="menu_reminders")
                ],
                [
                    InlineKeyboardButton("🎯 Дедлайны", callback_data="menu_deadlines"),
                    InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")
                ],
                [
                    InlineKeyboardButton("🚪 Аудитории", callback_data="menu_rooms"),
                    InlineKeyboardButton("☀️ Погода", callback_data="menu_weather")
                ],
            ]
            # Add Mini App button if configured
            webapp_url = os.getenv('WEBAPP_URL')
            if webapp_url:
                keyboard.append([
                    InlineKeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(url=webapp_url))
                ])
            keyboard.append([
                    InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                    InlineKeyboardButton("❓ Помощь", callback_data="help")
            ])
            text = "📋 **Главное меню**\n\nВыбери действие:"
        else:
            keyboard = [
                [InlineKeyboardButton("🔐 Войти в TSI", callback_data="login")],
                [InlineKeyboardButton("❓ Помощь", callback_data="help")]
            ]
            text = "📋 **Меню**\n\n🔐 Войди для доступа к функциям"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # Also update persistent keyboard if needed
        await update.message.reply_text(
            "👇",
            reply_markup=get_main_keyboard(is_logged_in)
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        ai_status = "✅" if self.ai_manager.get_available_providers() else "❌"
        providers = ", ".join(self.ai_manager.get_available_providers()) or "нет"
        
        help_text = f"""
🤖 **Smart Campus Assistant - Справка**

**🔐 Аккаунт:**
• `/login` - войти в аккаунт TSI
• `/logout` - выйти из аккаунта
• `/status` - статус авторизации

**📅 Расписание:**
• `/today` - расписание на сегодня
• `/tomorrow` - расписание на завтра
• `/week` - расписание на неделю
• `/next` - следующая пара

**👥 Группа:**
• `/setgroup [код]` - установить группу
• `/mygroup` - показать группу

**🔍 Поиск:**
• `/search [запрос]` - поиск
• `/freerooms` - свободные аудитории

**🤖 AI Ассистент:** {ai_status}
Провайдеры: {providers}

💡 **Просто напиши вопрос!**
Примеры:
• "Что у меня сегодня?"
• "Когда экзамен по математике?"
• "Где проходит следующая пара?"
        """
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show login status"""
        telegram_id = update.effective_user.id
        
        if self.credentials.has_credentials(telegram_id):
            creds = self.credentials.get_credentials(telegram_id)
            if creds:
                user_db = self.db.get_user(telegram_id)
                group = user_db.get("group_code", "Не установлена") if user_db else "N/A"
                
                status = "✅ Подтверждён" if creds.get("is_verified") else "⚠️ Требует проверки"
                
                await update.message.reply_text(
                    f"📊 **Статус аккаунта**\n\n"
                    f"👤 Логин: `{creds['username']}`\n"
                    f"🔐 Статус: {status}\n"
                    f"👥 Группа: {group}\n",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "⚠️ Аккаунт заблокирован или данные повреждены.\n"
                    "Попробуй /logout и /login заново."
                )
        else:
            await update.message.reply_text(
                "❌ Ты не авторизован.\n\n"
                "Для входа: /login"
            )
    
    async def cmd_ai_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show AI status"""
        providers = self.ai_manager.get_available_providers()
        primary = self.ai_manager.primary_provider
        
        if providers:
            provider_list = "\n".join([
                f"  {'➡️' if p == primary else '  '} {p}" 
                for p in providers
            ])
            await update.message.reply_text(
                f"🤖 **AI Статус**\n\n"
                f"✅ AI доступен!\n\n"
                f"Провайдеры:\n{provider_list}\n\n"
                f"Просто напиши мне вопрос!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "🤖 **AI Статус**\n\n"
                "❌ AI провайдеры недоступны.\n\n"
                "Для активации добавь в .env:\n"
                "• `GROQ_API_KEY` - бесплатно на groq.com\n"
                "• `GEMINI_API_KEY` - бесплатно от Google\n"
                "• Или запусти Ollama локально",
                parse_mode="Markdown"
            )
    
    async def _check_auth(self, update: Update) -> bool:
        """Check if user is authenticated"""
        telegram_id = update.effective_user.id
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text(
                "🔐 Для этой команды нужно войти в аккаунт.\n\n"
                "Отправь /login для авторизации."
            )
            return False
        return True
    
    async def cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command"""
        if not await self._check_auth(update):
            return
        await self._send_schedule(update, context, "today")
    
    async def cmd_tomorrow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tomorrow command"""
        if not await self._check_auth(update):
            return
        await self._send_schedule(update, context, "tomorrow")
    
    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /week command"""
        if not await self._check_auth(update):
            return
        await self._send_schedule(update, context, "week")
    
    async def cmd_next(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /next command"""
        if not await self._check_auth(update):
            return
        
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: `/setgroup [код]`",
                parse_mode="Markdown"
            )
            return
        
        calendar = self._get_calendar_service(telegram_id)
        if not calendar:
            await update.message.reply_text(
                "❌ Ошибка авторизации. Попробуй /login заново."
            )
            return
        
        try:
            event = calendar.get_next_event(group=user['group_code'])
            if event:
                response = self._format_single_event(event)
                await update.message.reply_text(
                    f"⏰ **Следующая пара:**\n\n{response}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("✨ Ближайших занятий не найдено!")
        except Exception as e:
            logger.error(f"Error getting next class: {e}")
            await update.message.reply_text("❌ Ошибка получения данных")
    
    async def cmd_setgroup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setgroup command"""
        if not context.args:
            await update.message.reply_text(
                "📝 Укажи код группы:\n"
                "`/setgroup [код группы]`\n\n"
                "Примеры:\n"
                "• `/setgroup 3401BNA`\n"
                "• `/setgroup 4201-2BDA`",
                parse_mode="Markdown"
            )
            return
        
        group_code = context.args[0].upper()
        
        # Support formats: 3401BNA, 4201-2BDA, 5502DTL, etc.
        if not re.match(r'^[0-9]{4}(-[0-9])?[A-Z]{3}$', group_code):
            await update.message.reply_text(
                "❌ Неверный формат группы.\n"
                "Примеры: `3401BNA`, `4201-2BDA`",
                parse_mode="Markdown"
            )
            return
        
        self.db.update_user(
            telegram_id=update.effective_user.id,
            group_code=group_code
        )
        
        await update.message.reply_text(
            f"✅ Группа установлена: **{group_code}**",
            parse_mode="Markdown"
        )
    
    async def cmd_mygroup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mygroup command"""
        user = self.db.get_user(update.effective_user.id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "❌ Группа не установлена.\n"
                "Используй: `/setgroup [код]`",
                parse_mode="Markdown"
            )
            return
        
        await update.message.reply_text(
            f"👥 Твоя группа: **{user['group_code']}**",
            parse_mode="Markdown"
        )
    
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        creds = self.credentials.get_credentials(telegram_id)
        
        login_status = f"✅ {creds['username']}" if creds else "❌ Не авторизован"
        group = user.get('group_code', 'Не установлена') if user else "N/A"
        notifications = "✅ Вкл" if user and user.get('notifications_enabled') else "❌ Выкл"
        
        keyboard = [
            [InlineKeyboardButton("👥 Изменить группу", callback_data="set_group")],
            [InlineKeyboardButton(
                f"🔔 Уведомления: {notifications}",
                callback_data="toggle_notifications"
            )],
            [InlineKeyboardButton("🚪 Выйти из аккаунта", callback_data="logout")]
        ]
        
        await update.message.reply_text(
            f"⚙️ **Настройки**\n\n"
            f"🔐 Аккаунт: {login_status}\n"
            f"👥 Группа: {group}\n"
            f"🔔 Уведомления: {notifications}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def cmd_freerooms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /freerooms command"""
        if not await self._check_auth(update):
            return
        
        telegram_id = update.effective_user.id
        calendar = self._get_calendar_service(telegram_id)
        
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации. Попробуй /login")
            return
        
        try:
            rooms = calendar.get_free_rooms()
            if rooms:
                rooms_list = "\n".join([f"🚪 {room}" for room in rooms[:15]])
                now = datetime.now().strftime("%H:%M")
                await update.message.reply_text(
                    f"🚪 **Свободные аудитории** ({now})\n\n{rooms_list}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Информация недоступна")
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text("❌ Ошибка получения данных")
    
    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        if not await self._check_auth(update):
            return
        
        if not context.args:
            await update.message.reply_text(
                "🔍 Укажи что искать:\n`/search [запрос]`",
                parse_mode="Markdown"
            )
            return
        
        query = " ".join(context.args)
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        calendar = self._get_calendar_service(telegram_id)
        
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации")
            return
        
        try:
            events = calendar.search_events(
                query,
                group=user.get('group_code') if user else None,
                limit=5
            )
            
            if events:
                response = f"🔍 **Результаты:** '{query}'\n\n"
                response += self._format_events(events)
                await update.message.reply_text(response, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"🔍 По запросу '{query}' ничего не найдено")
        except Exception as e:
            logger.error(f"Search error: {e}")
            await update.message.reply_text("❌ Ошибка поиска")
    
    # ==================== New Feature Commands ====================
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show schedule statistics"""
        if not await self._check_auth(update):
            return
        
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: `/setgroup [код]`",
                parse_mode="Markdown"
            )
            return
        
        calendar = self._get_calendar_service(telegram_id)
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации")
            return
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Get week events
            events = calendar.get_week_events(group=user['group_code'])
            
            if not events:
                await update.message.reply_text("📊 Нет данных для статистики")
                return
            
            # Calculate statistics
            total_classes = len(events)
            
            # Count by subject
            subjects = Counter()
            lecturers = Counter()
            rooms = Counter()
            total_hours = 0
            
            for event in events:
                title = event.get('title', 'Unknown')
                subjects[title] += 1
                
                lecturer = event.get('lecturer', 'Unknown')
                if lecturer and lecturer != 'Unknown':
                    lecturers[lecturer] += 1
                
                room = event.get('room', 'Unknown')
                if room:
                    rooms[room] += 1
                
                # Calculate hours
                try:
                    start = datetime.strptime(event.get('start_time', '00:00'), '%H:%M')
                    end = datetime.strptime(event.get('end_time', '00:00'), '%H:%M')
                    hours = (end - start).seconds / 3600
                    total_hours += hours
                except:
                    total_hours += 1.5  # Default 1.5 hours per class
            
            # Format response
            top_subjects = subjects.most_common(3)
            top_rooms = rooms.most_common(3)
            
            subjects_str = "\n".join([f"  • {s}: {c} раз" for s, c in top_subjects])
            rooms_str = ", ".join([f"{r}" for r, c in top_rooms])
            
            response = f"""📊 **Статистика на эту неделю**

👥 Группа: {user['group_code']}

📚 **Всего пар:** {total_classes}
⏱️ **Часов:** {total_hours:.1f}ч

📖 **Топ предметов:**
{subjects_str}

🏫 **Частые аудитории:** {rooms_str}

💡 _Совет: планируй время между парами!_
"""
            await update.message.reply_text(response, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text("❌ Ошибка получения статистики")
    
    async def cmd_exams(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show upcoming exams"""
        if not await self._check_auth(update):
            return
        
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        calendar = self._get_calendar_service(telegram_id)
        
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации")
            return
        
        try:
            # Search for exams
            all_events = calendar.fetch_events(group=user.get('group_code'))
            
            exam_keywords = ['экзамен', 'exam', 'eksāmen', 'зачёт', 'зачет', 'test', 'pārbaud']
            exams = []
            
            for event in all_events:
                title = event.get('title', '').lower()
                event_type = event.get('event_type', '').lower()
                
                if any(kw in title or kw in event_type for kw in exam_keywords):
                    exams.append(event)
            
            if exams:
                # Sort by date
                exams.sort(key=lambda x: x.get('date', ''))
                
                response = "📝 **Экзамены и зачёты:**\n\n"
                for exam in exams[:10]:
                    date = exam.get('date', 'N/A')
                    title = exam.get('title', 'N/A')[:40]
                    time = exam.get('start_time', 'N/A')
                    room = exam.get('room', 'N/A')
                    
                    # Days until exam
                    try:
                        exam_date = datetime.strptime(date, '%Y-%m-%d')
                        days_left = (exam_date - datetime.now()).days
                        if days_left == 0:
                            days_str = "🔴 СЕГОДНЯ!"
                        elif days_left == 1:
                            days_str = "🟠 Завтра"
                        elif days_left < 0:
                            days_str = "✅ Прошёл"
                        else:
                            days_str = f"📅 через {days_left} дн."
                    except:
                        days_str = ""
                    
                    response += f"📌 **{title}**\n"
                    response += f"   {date} {time} | Ауд. {room}\n"
                    response += f"   {days_str}\n\n"
                
                await update.message.reply_text(response, parse_mode="Markdown")
            else:
                await update.message.reply_text(
                    "📝 Экзамены не найдены в расписании.\n\n"
                    "_Возможно, они ещё не добавлены._"
                , parse_mode="Markdown")
                
        except Exception as e:
            logger.error(f"Exams error: {e}")
            await update.message.reply_text("❌ Ошибка поиска экзаменов")
    
    async def cmd_where(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Find room location"""
        if not context.args:
            await update.message.reply_text(
                "📍 **Где аудитория?**\n\n"
                "Укажи номер: `/where 305`\n\n"
                "🏫 **Корпуса TSI:**\n"
                "• Корпус 1 (ауд. 1XX) - Lomonosova 1\n"
                "• Корпус 2 (ауд. 2XX) - Lomonosova 1/4\n"
                "• Корпус 3 (ауд. 3XX) - Lomonosova 1/5",
                parse_mode="Markdown"
            )
            return
        
        room = context.args[0].upper()
        
        # Parse room number
        room_clean = re.sub(r'[^0-9]', '', room)
        
        if not room_clean:
            await update.message.reply_text("❌ Укажи номер аудитории")
            return
        
        # Determine building and floor
        if len(room_clean) >= 3:
            building = room_clean[0]
            floor = room_clean[1]
        elif len(room_clean) == 2:
            building = "1"
            floor = room_clean[0]
        else:
            building = "1"
            floor = "1"
        
        building_info = CAMPUS_ROOMS.get(building, CAMPUS_ROOMS["1"])
        
        response = f"""📍 **Аудитория {room}**

🏫 **Корпус:** {building_info['name']}
📍 **Адрес:** {building_info['location']}
🔢 **Этаж:** {floor}

🚶 **Как найти:**
1. Найди корпус {building} по адресу
2. Поднимись на {floor} этаж
3. Ищи аудиторию {room}

💡 _Совет: приходи за 5-10 минут!_
"""
        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def cmd_weather(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show weather in Riga"""
        try:
            import requests
            
            # Free weather API
            url = "https://wttr.in/Riga?format=j1"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            current = data.get('current_condition', [{}])[0]
            
            temp = current.get('temp_C', 'N/A')
            feels_like = current.get('FeelsLikeC', 'N/A')
            desc = current.get('weatherDesc', [{}])[0].get('value', 'N/A')
            humidity = current.get('humidity', 'N/A')
            wind = current.get('windspeedKmph', 'N/A')
            
            # Weather emoji
            weather_emoji = "☀️"
            if 'rain' in desc.lower() or 'shower' in desc.lower():
                weather_emoji = "🌧️"
            elif 'cloud' in desc.lower():
                weather_emoji = "☁️"
            elif 'snow' in desc.lower():
                weather_emoji = "❄️"
            elif 'sun' in desc.lower() or 'clear' in desc.lower():
                weather_emoji = "☀️"
            
            # Clothing advice
            temp_int = int(temp) if temp != 'N/A' else 10
            if temp_int < 0:
                advice = "🧥 Тепло одевайся! Шапка и перчатки!"
            elif temp_int < 10:
                advice = "🧥 Возьми куртку!"
            elif temp_int < 18:
                advice = "👕 Лёгкая куртка или свитер"
            else:
                advice = "😎 Можно налегке!"
            
            weather_text = f"""{weather_emoji} **Погода в Риге**

🌡️ Температура: **{temp}°C**
🤔 Ощущается: {feels_like}°C
📝 {desc}
💧 Влажность: {humidity}%
💨 Ветер: {wind} км/ч

{advice}
"""
            await update.message.reply_text(weather_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Weather error: {e}")
            await update.message.reply_text("❌ Не удалось получить погоду")
    
    async def cmd_motivation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send motivational quote"""
        quote = random.choice(MOTIVATION_QUOTES)
        
        keyboard = [[
            InlineKeyboardButton("🔄 Ещё", callback_data="motivation_more")
        ]]
        
        await update.message.reply_text(
            f"✨ **Мотивация дня:**\n\n{quote}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def cmd_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a note"""
        if not context.args:
            await update.message.reply_text(
                "📝 **Добавить заметку:**\n\n"
                "`/note [текст заметки]`\n\n"
                "Пример: `/note Сдать лабу до пятницы!`",
                parse_mode="Markdown"
            )
            return
        
        telegram_id = update.effective_user.id
        note_text = " ".join(context.args)
        
        # Save note to database
        self.db.set_user_preference(
            telegram_id,
            f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            note_text
        )
        
        await update.message.reply_text(
            f"✅ Заметка сохранена!\n\n📝 {note_text}\n\n"
            "_Посмотреть все: /notes_",
            parse_mode="Markdown"
        )
    
    async def cmd_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all notes"""
        telegram_id = update.effective_user.id
        notes = self.db.get_user_preferences(telegram_id)
        
        # Filter only notes
        user_notes = [(k, v) for k, v in notes.items() if k.startswith('note_')]
        
        if not user_notes:
            await update.message.reply_text(
                "📝 У тебя пока нет заметок.\n\n"
                "Добавь: `/note [текст]`",
                parse_mode="Markdown"
            )
            return
        
        response = "📝 **Твои заметки:**\n\n"
        for i, (key, value) in enumerate(sorted(user_notes, reverse=True)[:10], 1):
            # Parse date from key
            try:
                date_str = key.replace('note_', '')
                date = datetime.strptime(date_str, '%Y%m%d_%H%M%S')
                date_formatted = date.strftime('%d.%m %H:%M')
            except:
                date_formatted = ""
            
            response += f"{i}. {value}\n   _({date_formatted})_\n\n"
        
        response += "_Добавить: /note [текст]_"
        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def cmd_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a deadline"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "🎯 **Добавить дедлайн:**\n\n"
                "`/deadline [дата] [описание]`\n\n"
                "Примеры:\n"
                "• `/deadline 2025-12-15 Сдать курсовую`\n"
                "• `/deadline 25.12 Защита проекта`",
                parse_mode="Markdown"
            )
            return
        
        telegram_id = update.effective_user.id
        date_str = context.args[0]
        description = " ".join(context.args[1:])
        
        # Parse date
        parsed_date = None
        for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d.%m', '%d/%m']:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                if fmt == '%d.%m' or fmt == '%d/%m':
                    parsed_date = parsed_date.replace(year=datetime.now().year)
                break
            except:
                continue
        
        if not parsed_date:
            await update.message.reply_text("❌ Неверный формат даты. Пример: 2025-12-15 или 15.12")
            return
        
        # Save deadline
        deadline_key = f"deadline_{parsed_date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}"
        self.db.set_user_preference(telegram_id, deadline_key, description)
        
        days_left = (parsed_date - datetime.now()).days
        if days_left < 0:
            days_str = "⚠️ Дата в прошлом!"
        elif days_left == 0:
            days_str = "🔴 Сегодня!"
        elif days_left == 1:
            days_str = "🟠 Завтра!"
        else:
            days_str = f"📅 Через {days_left} дней"
        
        await update.message.reply_text(
            f"✅ Дедлайн добавлен!\n\n"
            f"🎯 {description}\n"
            f"📆 {parsed_date.strftime('%d.%m.%Y')}\n"
            f"{days_str}\n\n"
            "_Все дедлайны: /deadlines_",
            parse_mode="Markdown"
        )
    
    async def cmd_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all deadlines"""
        telegram_id = update.effective_user.id
        prefs = self.db.get_user_preferences(telegram_id)
        
        # Filter deadlines
        deadlines = []
        for key, value in prefs.items():
            if key.startswith('deadline_'):
                try:
                    date_str = key.split('_')[1]
                    date = datetime.strptime(date_str, '%Y%m%d')
                    deadlines.append((date, value, key))
                except:
                    continue
        
        if not deadlines:
            await update.message.reply_text(
                "🎯 У тебя пока нет дедлайнов.\n\n"
                "Добавь: `/deadline [дата] [описание]`",
                parse_mode="Markdown"
            )
            return
        
        # Sort by date
        deadlines.sort(key=lambda x: x[0])
        
        response = "🎯 **Твои дедлайны:**\n\n"
        for date, desc, key in deadlines[:10]:
            days_left = (date - datetime.now()).days
            
            if days_left < 0:
                emoji = "✅"  # Past
                days_str = "прошёл"
            elif days_left == 0:
                emoji = "🔴"
                days_str = "СЕГОДНЯ!"
            elif days_left <= 3:
                emoji = "🟠"
                days_str = f"{days_left} дн."
            elif days_left <= 7:
                emoji = "🟡"
                days_str = f"{days_left} дн."
            else:
                emoji = "🟢"
                days_str = f"{days_left} дн."
            
            response += f"{emoji} **{date.strftime('%d.%m')}** - {desc} _{days_str}_\n"
        
        response += "\n_Добавить: /deadline [дата] [текст]_"
        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Export calendar to ICS"""
        if not await self._check_auth(update):
            return
        
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text("⚠️ Сначала установи группу")
            return
        
        calendar = self._get_calendar_service(telegram_id)
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации")
            return
        
        await update.message.reply_text(
            "📤 **Экспорт расписания**\n\n"
            "Экспорт в ICS формат скоро будет доступен!\n\n"
            "_Пока используй /week для просмотра расписания_",
            parse_mode="Markdown"
        )
    
    # ==================== Reminders ====================
    
    async def cmd_remind(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a reminder"""
        telegram_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "⏰ **Добавить напоминание**\n\n"
                "Формат: `/remind [когда] [время] [текст]`\n\n"
                "Примеры:\n"
                "• `/remind 14:30 Сдать лабу`\n"
                "• `/remind завтра 10:00 Зайти в деканат`\n"
                "• `/remind через 2 часа Позвонить`",
                parse_mode="Markdown"
            )
            return
        
        # Join all args into one string for easier parsing
        full_text = " ".join(context.args)
        
        try:
            reminder_time, reminder_text = self._parse_reminder_input(full_text)
            
            if not reminder_text:
                reminder_text = "Напоминание"
            
            # Save reminder
            reminder_id = self.db.add_text_reminder(telegram_id, reminder_text, reminder_time)
            
            if reminder_id:
                await update.message.reply_text(
                    f"✅ **Напоминание сохранено!**\n\n"
                    f"📝 {reminder_text}\n"
                    f"📅 {reminder_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"_Бот напомнит тебе в указанное время_ 🔔",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка сохранения напоминания")
                
        except Exception as e:
            logger.error(f"Remind error: {e}")
            await update.message.reply_text(
                "❌ Не удалось распознать время.\n\n"
                "Примеры:\n"
                "• `/remind 14:30 Сдать лабу`\n"
                "• `/remind завтра 10:00 Встреча`\n"
                "• `/remind через 1 час Позвонить`",
                parse_mode="Markdown"
            )
    
    def _parse_reminder_input(self, text: str) -> tuple:
        """Parse reminder input and return (datetime, text)"""
        import re
        from datetime import datetime, timedelta
        
        # Get timezone from env or default to Europe/Riga
        tz_name = os.getenv('TIMEZONE', 'Europe/Riga')
        try:
            tz = ZoneInfo(tz_name)
        except:
            tz = ZoneInfo('Europe/Riga')
        
        now = datetime.now(tz)
        reminder_time = None
        reminder_text = text
        
        text_lower = text.lower()
        
        # FIRST: Clean up command words from beginning
        # Remove "поставь напоминание", "напомни мне", etc.
        clean_patterns = [
            r'^(поставь|создай|добавь|установи)\s+(напоминани\w*|remind\w*|уведомлени\w*)\s*',
            r'^(напомни|remind|напомнить)\s*(мне|me)?\s*',
            r'^(напоминани\w*)\s*[:]\s*',
        ]
        for pattern in clean_patterns:
            reminder_text = re.sub(pattern, '', reminder_text, flags=re.IGNORECASE).strip()
        
        text_lower = reminder_text.lower()
        
        # Word to number mapping
        word_to_num = {
            'один': 1, 'одну': 1, 'одна': 1,
            'два': 2, 'две': 2, 'двух': 2,
            'три': 3, 'трёх': 3, 'трех': 3,
            'четыре': 4, 'четырёх': 4, 'четырех': 4,
            'пять': 5, 'пяти': 5,
            'шесть': 6, 'шести': 6,
            'семь': 7, 'семи': 7,
            'восемь': 8, 'восьми': 8,
            'девять': 9, 'девяти': 9,
            'десять': 10, 'десяти': 10,
            'пятнадцать': 15, 'двадцать': 20, 'тридцать': 30,
            'полчаса': 30, 'пол часа': 30,
        }
        
        # Helper function to extract number (digit or word)
        def extract_number(match_str):
            match_str = match_str.strip().lower()
            if match_str.isdigit():
                return int(match_str)
            return word_to_num.get(match_str, None)
        
        # Pattern: "через X часов/минут" (X can be digit or word)
        through_match = re.search(r'через\s+(\d+|один|одну|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|пятнадцать|двадцать|тридцать|полчаса)\s*(час|мин|hour|min)?\w*', text_lower)
        if through_match:
            amount = extract_number(through_match.group(1))
            unit = through_match.group(2) or ''
            
            if amount:
                # "полчаса" means 30 minutes
                if 'полчаса' in through_match.group(1) or 'пол часа' in through_match.group(1):
                    reminder_time = now + timedelta(minutes=30)
                elif 'час' in unit or 'hour' in unit:
                    reminder_time = now + timedelta(hours=amount)
                else:
                    # Default to minutes if unit not specified or is minutes
                    reminder_time = now + timedelta(minutes=amount)
                
                # Remove the time part from text
                reminder_text = re.sub(r'через\s+(\d+|один|одну|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|пятнадцать|двадцать|тридцать|полчаса|пол\s*часа)\s*(час|мин|hour|min)?\w*\s*', '', reminder_text, flags=re.IGNORECASE).strip()
        
        # Pattern: "через X дней"
        days_match = re.search(r'через\s+(\d+|один|одну|два|две|три|четыре|пять)\s*(день|дня|дней|day)\w*', text_lower)
        if days_match and not reminder_time:
            days = extract_number(days_match.group(1))
            if days:
                reminder_time = now + timedelta(days=days)
                reminder_text = re.sub(r'через\s+(\d+|один|одну|два|две|три|четыре|пять)\s*(день|дня|дней|day)\w*\s*', '', reminder_text, flags=re.IGNORECASE)
        
        # Pattern: "завтра/послезавтра/сегодня [время]" - with/without "на"
        if 'послезавтра' in text_lower:
            reminder_time = now + timedelta(days=2)
            reminder_text = re.sub(r'(на\s+)?послезавтра', '', reminder_text, flags=re.IGNORECASE).strip()
        elif 'завтра' in text_lower or 'tomorrow' in text_lower:
            reminder_time = now + timedelta(days=1)
            reminder_text = re.sub(r'(на\s+)?(завтра|tomorrow)', '', reminder_text, flags=re.IGNORECASE).strip()
        elif 'сегодня' in text_lower or 'today' in text_lower:
            reminder_time = now
            reminder_text = re.sub(r'(на\s+)?(сегодня|today)', '', reminder_text, flags=re.IGNORECASE).strip()
        
        # Look for time pattern HH:MM or HH.MM (with optional "в")
        time_match = re.search(r'(?:в\s+)?(\d{1,2})[:\.](\d{2})', reminder_text)
        if time_match:
            hour, minute = int(time_match.group(1)), int(time_match.group(2))
            if reminder_time is None:
                reminder_time = now
            reminder_time = reminder_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Remove time from text (including "в")
            reminder_text = re.sub(r'в\s+\d{1,2}[:\.]?\d{2}\s*', '', reminder_text).strip()
            reminder_text = re.sub(r'\d{1,2}[:\.]?\d{2}\s*', '', reminder_text).strip()
        elif reminder_time is not None and reminder_time.date() != now.date():
            # Default to 9:00 if date specified but no time
            reminder_time = reminder_time.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # If still no time, set for 1 hour from now
        if reminder_time is None:
            reminder_time = now + timedelta(hours=1)
            reminder_time = reminder_time.replace(second=0, microsecond=0)
        
        # If time is in the past today, move to tomorrow
        if reminder_time < now:
            reminder_time += timedelta(days=1)
        
        # Clean up reminder_text: remove "чтобы", "что", extra prepositions at start
        reminder_text = re.sub(r'^(чтобы|что|о том что|о том|про то что)\s+', '', reminder_text, flags=re.IGNORECASE).strip()
        
        # Remove leading prepositions
        reminder_text = re.sub(r'^(у меня|о|об|про)\s+', '', reminder_text, flags=re.IGNORECASE).strip()
        
        # Capitalize first letter
        if reminder_text:
            reminder_text = reminder_text[0].upper() + reminder_text[1:] if len(reminder_text) > 1 else reminder_text.upper()
        
        return reminder_time, reminder_text.strip()
    
    async def cmd_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all reminders"""
        telegram_id = update.effective_user.id
        
        reminders = self.db.get_user_reminders(telegram_id)
        
        if not reminders:
            await update.message.reply_text(
                "📭 У тебя нет активных напоминаний\n\n"
                "Добавь: `/remind 14:00 Текст`",
                parse_mode="Markdown"
            )
            return
        
        text = "⏰ **Твои напоминания:**\n\n"
        
        for r in reminders[:10]:
            r_time = datetime.fromisoformat(r['reminder_time']) if isinstance(r['reminder_time'], str) else r['reminder_time']
            r_text = r['reminder_text'] or r.get('event_id', 'Напоминание')
            text += f"• {r_time.strftime('%d.%m %H:%M')} - {r_text}\n"
            text += f"  _/del_remind_{r['id']}_\n"
        
        text += "\n_Для удаления нажми на команду_"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    # ==================== My TSI Commands ====================
    
    async def cmd_grades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show student grades from my.tsi.lv"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("🔐 Сначала войди: /login")
            return
        
        await update.message.reply_text("📚 Загружаю оценки...")
        
        try:
            from app.core.my_tsi_service import MyTSIService
            
            creds = self.credentials.get_credentials(telegram_id)
            service = MyTSIService()
            
            if service.login(creds['username'], creds['password']):
                grades = service.get_grades()
                service.close()
                
                if not grades:
                    await update.message.reply_text("📭 Оценки не найдены")
                    return
                
                # Group by semester
                semesters = {}
                for g in grades:
                    sem = g.get('semester', 'Без семестра')
                    if sem not in semesters:
                        semesters[sem] = []
                    semesters[sem].append(g)
                
                text = "📊 **Твои оценки:**\n"
                
                # Show last 2 semesters
                sem_keys = list(semesters.keys())[-2:]
                for sem in sem_keys:
                    text += f"\n**{sem}**\n"
                    for g in semesters[sem]:
                        grade = g.get('grade', '-')
                        subject = g.get('subject', 'Неизвестно')[:35]
                        credits = g.get('credits', '')
                        
                        # Add emoji based on grade
                        if grade.isdigit():
                            grade_int = int(grade)
                            if grade_int >= 9:
                                emoji = "🌟"
                            elif grade_int >= 7:
                                emoji = "✅"
                            elif grade_int >= 5:
                                emoji = "📝"
                            else:
                                emoji = "⚠️"
                        else:
                            emoji = "📝"
                        
                        text += f"{emoji} {grade} | {subject}"
                        if credits:
                            text += f" ({credits} кр.)"
                        text += "\n"
                
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка входа в my.tsi.lv")
                
        except Exception as e:
            logger.error(f"Grades error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_gpa(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show GPA (average grade)"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("🔐 Сначала войди: /login")
            return
        
        await update.message.reply_text("📊 Считаю средний балл...")
        
        try:
            from app.core.my_tsi_service import MyTSIService
            
            creds = self.credentials.get_credentials(telegram_id)
            service = MyTSIService()
            
            if service.login(creds['username'], creds['password']):
                gpa = service.get_gpa()
                grades = service.get_grades()
                service.close()
                
                total_credits = sum(int(g.get('credits', 0)) for g in grades if g.get('credits', '').isdigit())
                
                # Emoji based on GPA
                if gpa >= 9:
                    emoji = "🏆"
                    comment = "Отлично!"
                elif gpa >= 8:
                    emoji = "🌟"
                    comment = "Очень хорошо!"
                elif gpa >= 7:
                    emoji = "✅"
                    comment = "Хорошо"
                elif gpa >= 5:
                    emoji = "📝"
                    comment = "Нормально"
                else:
                    emoji = "📚"
                    comment = "Есть над чем поработать"
                
                text = f"""
{emoji} **Средний балл (GPA): {gpa}**

📚 Всего предметов: {len(grades)}
📊 Всего кредитов: {total_credits}

_{comment}_
"""
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка входа в my.tsi.lv")
                
        except Exception as e:
            logger.error(f"GPA error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_bills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bills and payments from my.tsi.lv"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("🔐 Сначала войди: /login")
            return
        
        await update.message.reply_text("💰 Загружаю счета...")
        
        try:
            from app.core.my_tsi_service import MyTSIService
            
            creds = self.credentials.get_credentials(telegram_id)
            service = MyTSIService()
            
            if service.login(creds['username'], creds['password']):
                bills_data = service.get_bills()
                service.close()
                
                if 'error' in bills_data:
                    await update.message.reply_text(f"❌ {bills_data['error']}")
                    return
                
                bills = bills_data.get('bills', [])
                
                text = "💰 **Счета и оплаты:**\n\n"
                text += f"📊 {bills_data.get('summary', 'Нет данных')}\n\n"
                
                # Show unpaid bills first
                unpaid = [b for b in bills if not b['paid'] and b['amount'] > 0]
                if unpaid:
                    text += "⏳ **К оплате:**\n"
                    for bill in unpaid[-5:]:
                        text += f"• {bill['date']}: {bill['service'][:30]}\n"
                        text += f"  💵 {bill['amount']:.2f} EUR\n"
                
                # Recent payments
                paid = [b for b in bills if b['paid']][-5:]
                if paid:
                    text += "\n✅ **Последние оплаты:**\n"
                    for bill in reversed(paid):
                        text += f"• {bill['payment_date'] or bill['date']}: {abs(bill['amount']):.2f} EUR\n"
                
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка входа в my.tsi.lv")
                
        except Exception as e:
            logger.error(f"Bills error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show student profile from my.tsi.lv"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("🔐 Сначала войди: /login")
            return
        
        await update.message.reply_text("👤 Загружаю профиль...")
        
        try:
            from app.core.my_tsi_service import MyTSIService
            
            creds = self.credentials.get_credentials(telegram_id)
            service = MyTSIService()
            
            if service.login(creds['username'], creds['password']):
                profile = service.get_profile()
                service.close()
                
                if 'error' in profile:
                    await update.message.reply_text(f"❌ {profile['error']}")
                    return
                
                text = f"""
👤 **Профиль студента**

📛 **{profile.get('name', 'Неизвестно')}**
🆔 Код: {profile.get('student_code', '-')}
📊 Статус: {profile.get('status', '-')}

🎓 **Обучение:**
• Факультет: {profile.get('faculty', '-')}
• Программа: {profile.get('programme', '-')}
• Специализация: {profile.get('specialization', '-')}
• Уровень: {profile.get('level', '-')}
• Курс: {profile.get('year', '-')}
• Группа: {profile.get('group', '-')}
• Форма: {profile.get('study_mode', '-')}
"""
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка входа в my.tsi.lv")
                
        except Exception as e:
            logger.error(f"Profile error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_attendance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show attendance from my.tsi.lv dashboard"""
        telegram_id = update.effective_user.id
        
        if not self.credentials.has_credentials(telegram_id):
            await update.message.reply_text("🔐 Сначала войди: /login")
            return
        
        await update.message.reply_text("📊 Загружаю посещаемость...")
        
        try:
            from app.core.my_tsi_service import MyTSIService
            
            creds = self.credentials.get_credentials(telegram_id)
            service = MyTSIService()
            
            if service.login(creds['username'], creds['password']):
                attendance = service.get_attendance()
                service.close()
                
                if 'error' in attendance:
                    await update.message.reply_text(f"❌ {attendance['error']}")
                    return
                
                overall = attendance.get('overall', 0)
                subjects = attendance.get('subjects', [])
                
                # Emoji based on overall attendance
                if overall >= 80:
                    emoji = "✅"
                    comment = "Отлично!"
                elif overall >= 60:
                    emoji = "📊"
                    comment = "Нормально"
                elif overall >= 40:
                    emoji = "⚠️"
                    comment = "Нужно больше ходить"
                else:
                    emoji = "🚨"
                    comment = "Критически низкая посещаемость!"
                
                text = f"""
{emoji} **Посещаемость: {overall}%**
_{comment}_

📚 **По предметам:**
"""
                for s in subjects:
                    subj_name = s['subject'][:35]
                    pct = s['percentage']
                    
                    if pct >= 80:
                        subj_emoji = "✅"
                    elif pct >= 50:
                        subj_emoji = "📊"
                    elif pct > 0:
                        subj_emoji = "⚠️"
                    else:
                        subj_emoji = "❌"
                    
                    text += f"{subj_emoji} {pct}% — {subj_name}\n"
                
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка входа в my.tsi.lv")
                
        except Exception as e:
            logger.error(f"Attendance error: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # ==================== AI Message Handler ====================
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages with AI"""
        text = update.message.text
        telegram_id = update.effective_user.id
        
        # SKIP if user is in login conversation (waiting for username/password)
        # This prevents AI from processing login credentials
        if context.user_data.get("in_login_flow") or text == "🔐 Войти":
            # User is in login flow or pressing login button - let ConversationHandler handle it
            return
        
        # Handle keyboard button presses
        if text == "📋 Menu":
            await self.cmd_menu(update, context)
            return
        elif text == "📅 Сегодня":
            await self.cmd_today(update, context)
            return
        elif text == "📅 Завтра":
            await self.cmd_tomorrow(update, context)
            return
        
        # Get user context
        user = self.db.get_user(telegram_id)
        if not user:
            self.db.create_user(telegram_id=telegram_id, username=update.effective_user.username)
            user = self.db.get_user(telegram_id)
        
        # PRIORITY CHECK: handle reminders and notes BEFORE AI
        # This ensures these requests are processed correctly
        intent, confidence, meta = self.intent_classifier.classify(text)
        logger.info(f"Intent classified: {intent} (confidence: {confidence})")
        
        if intent == "add_reminder" and confidence >= 0.5:
            await self._force_ai_reminder(update, context, text)
            return
        elif intent == "show_reminders" and confidence >= 0.5:
            await self.cmd_reminders(update, context)
            return
        elif intent == "add_note" and confidence >= 0.5:
            await self._force_ai_note(update, context, text)
            return
        elif intent == "show_notes" and confidence >= 0.5:
            await self._show_notes(update, context)
            return
        # My TSI portal intents
        elif intent == "show_grades" and confidence >= 0.5:
            await self.cmd_grades(update, context)
            return
        elif intent == "show_gpa" and confidence >= 0.5:
            await self.cmd_gpa(update, context)
            return
        elif intent == "show_attendance" and confidence >= 0.5:
            await self.cmd_attendance(update, context)
            return
        elif intent == "show_bills" and confidence >= 0.5:
            await self.cmd_bills(update, context)
            return
        elif intent == "show_profile" and confidence >= 0.5:
            await self.cmd_profile(update, context)
            return
        
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        # Get conversation history
        history = self._conversation_history.get(telegram_id, [])
        
        # Get user context for AI
        user_context = {
            "username": update.effective_user.first_name,
            "group_code": user.get('group_code') if user else None,
            "is_logged_in": self.credentials.has_credentials(telegram_id)
        }
        
        try:
            # Get AI response
            ai_response = self.ai_manager.chat(
                user_message=text,
                conversation_history=history,
                user_context=user_context
            )
            
            # Update conversation history
            history.append(Message(role="user", content=text))
            history.append(Message(role="assistant", content=ai_response))
            self._conversation_history[telegram_id] = history[-20:]  # Keep last 20
            
            # Process special commands in response
            final_response = await self._process_ai_commands(
                update, context, ai_response, telegram_id, user
            )
            
            await update.message.reply_text(final_response, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"AI error: {e}")
            # Fallback to basic response
            await self._handle_intent(update, context, intent, text)
    
    async def _force_ai_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Force process reminder request - parse directly without relying on AI"""
        telegram_id = update.effective_user.id
        
        try:
            # Parse directly using our parser
            reminder_time, reminder_text = self._parse_reminder_input(text)
            
            if not reminder_text or reminder_text.lower() in ['напомни', 'напомни мне', 'remind', 'remind me']:
                # AI didn't get proper text, ask for clarification
                await update.message.reply_text(
                    "📋 Что тебе напомнить?\n\n"
                    "Пример: `Напомни мне завтра в 10:00 сдать лабу`",
                    parse_mode="Markdown"
                )
                return
            
            # Save reminder
            reminder_id = self.db.add_text_reminder(telegram_id, reminder_text, reminder_time)
            
            if reminder_id:
                await update.message.reply_text(
                    f"✅ **Напоминание сохранено!**\n\n"
                    f"📝 {reminder_text}\n"
                    f"📅 {reminder_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"_Бот напомнит тебе в указанное время_ 🔔",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка сохранения напоминания")
                
        except Exception as e:
            logger.error(f"Reminder parse error: {e}")
            await update.message.reply_text(
                "❌ Не удалось распознать напоминание.\n\n"
                "Попробуй:\n"
                "• `Напомни завтра 10:00 текст`\n"
                "• `/remind 14:30 текст`",
                parse_mode="Markdown"
            )
    
    async def _force_ai_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Force AI to process note request"""
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        user_context = {
            "username": update.effective_user.first_name,
            "group_code": user.get('group_code') if user else None,
            "is_logged_in": self.credentials.has_credentials(telegram_id)
        }
        
        # Add explicit instruction for note
        note_prompt = f"Пользователь хочет сохранить заметку: '{text}'. Извлеки текст заметки и ответь командой [ADD_NOTE:текст заметки]"
        
        try:
            ai_response = self.ai_manager.chat(
                user_message=note_prompt,
                conversation_history=[],
                user_context=user_context
            )
            
            final_response = await self._process_ai_commands(
                update, context, ai_response, telegram_id, user
            )
            await update.message.reply_text(final_response, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Note AI error: {e}")
            await update.message.reply_text(
                "❌ Не удалось сохранить заметку.\n"
                "Попробуй: `Добавь заметку: текст`",
                parse_mode="Markdown"
            )
    
    async def _show_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all user notes"""
        telegram_id = update.effective_user.id
        notes = self.db.get_notes(telegram_id)
        
        if not notes:
            await update.message.reply_text(
                "📭 У тебя нет заметок\n\n"
                "Добавь: `Добавь заметку: текст`",
                parse_mode="Markdown"
            )
            return
        
        text = "📝 **Твои заметки:**\n\n"
        for n in notes[:20]:
            created = datetime.fromisoformat(n['created_at']) if isinstance(n['created_at'], str) else n['created_at']
            text += f"• {n['content'][:100]}\n"
            text += f"  _({created.strftime('%d.%m.%Y')})_ `/del_note_{n['id']}`\n\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _process_ai_commands(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        ai_response: str,
        telegram_id: int,
        user: Dict
    ) -> str:
        """Process special commands in AI response"""
        response = ai_response
        
        # Extract and process ALL commands (schedule + settings + reminders + notes)
        # Use greedy matching for commands with parameters
        all_commands = re.findall(
            r'\[(SCHEDULE_TODAY|SCHEDULE_TOMORROW|SCHEDULE_WEEK|NEXT_CLASS|FREE_ROOMS|'
            r'SEARCH:[^\]]+|SET_GROUP:[^\]]+|SET_LANGUAGE:[^\]]+|TOGGLE_NOTIFICATIONS|SHOW_SETTINGS|EXPORT_CALENDAR|'
            r'ADD_REMINDER:[^\]]+|SHOW_REMINDERS|ADD_NOTE:[^\]]+|SHOW_NOTES)\]',
            response
        )
        
        logger.info(f"AI Response commands found: {all_commands}")
        
        for cmd in all_commands:
            response = response.replace(f"[{cmd}]", "")
            
            # ==================== SETTINGS COMMANDS ====================
            if cmd.startswith("SET_GROUP:"):
                group_code = cmd.replace("SET_GROUP:", "").strip().upper()
                # Support formats: 3401BNA, 4201-2BDA
                if re.match(r'^[0-9]{4}(-[0-9])?[A-Z]{3}$', group_code):
                    self.db.update_user(telegram_id=telegram_id, group_code=group_code)
                    response += f"\n\n✅ Группа установлена: **{group_code}**"
                else:
                    response += f"\n\n⚠️ Неверный формат группы: {group_code}. Примеры: 3401BNA, 4201-2BDA"
                continue
            
            elif cmd.startswith("SET_LANGUAGE:"):
                lang = cmd.replace("SET_LANGUAGE:", "").strip().lower()
                if lang in ["ru", "en", "lv"]:
                    self.db.update_user(telegram_id=telegram_id, language=lang)
                    lang_names = {"ru": "Русский 🇷🇺", "en": "English 🇬🇧", "lv": "Latviešu 🇱🇻"}
                    response += f"\n\n✅ Язык установлен: **{lang_names.get(lang, lang)}**"
                else:
                    response += f"\n\n⚠️ Неверный язык. Доступны: ru, en, lv"
                continue
            
            elif cmd == "TOGGLE_NOTIFICATIONS":
                current_user = self.db.get_user(telegram_id)
                if current_user:
                    new_state = not current_user.get('notifications_enabled', True)
                    self.db.update_user(telegram_id=telegram_id, notifications_enabled=new_state)
                    status = "включены ✅" if new_state else "выключены ❌"
                    response += f"\n\n🔔 Уведомления {status}"
                continue
            
            elif cmd == "SHOW_SETTINGS":
                current_user = self.db.get_user(telegram_id)
                creds = self.credentials.get_credentials(telegram_id)
                
                if current_user:
                    group = current_user.get('group_code', 'Не установлена')
                    lang = current_user.get('language', 'ru')
                    notif = "✅ Вкл" if current_user.get('notifications_enabled', True) else "❌ Выкл"
                    login_status = f"✅ {creds['username']}" if creds else "❌ Не авторизован"
                    lang_names = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English", "lv": "🇱🇻 Latviešu"}
                    
                    response += f"""

⚙️ **Твои настройки:**
• 🔐 Аккаунт: {login_status}
• 👥 Группа: {group}
• 🌍 Язык: {lang_names.get(lang, lang)}
• 🔔 Уведомления: {notif}

_Скажи "измени группу на XXXX" или "выключи уведомления"_"""
                continue
            
            elif cmd == "EXPORT_CALENDAR":
                response += "\n\n📤 _Экспорт календаря пока в разработке. Скоро!_"
                continue
            
            # ==================== REMINDER & NOTES COMMANDS ====================
            elif cmd.startswith("ADD_REMINDER:"):
                params = cmd.replace("ADD_REMINDER:", "").strip()
                logger.info(f"Processing ADD_REMINDER with params: '{params}'")
                
                # Parse: datetime text (e.g., "завтра 12:00 пойти в магаз")
                try:
                    parts = params.split()
                    if len(parts) >= 1:
                        date_str = parts[0].lower()
                        
                        # Determine if first part is date or time
                        if date_str in ["сегодня", "today"]:
                            dt = datetime.now()
                            time_str = parts[1] if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else "09:00"
                            text_start = 2 if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else 1
                            text = " ".join(parts[text_start:]) if len(parts) > text_start else "Напоминание"
                        elif date_str in ["завтра", "tomorrow"]:
                            dt = datetime.now() + timedelta(days=1)
                            time_str = parts[1] if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else "09:00"
                            text_start = 2 if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else 1
                            text = " ".join(parts[text_start:]) if len(parts) > text_start else "Напоминание"
                        elif re.match(r'^\d{1,2}:\d{2}$', date_str):
                            # Time only - today
                            dt = datetime.now()
                            time_str = date_str
                            text = " ".join(parts[1:]) if len(parts) > 1 else "Напоминание"
                        elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                            # Full date
                            dt = datetime.strptime(date_str, "%Y-%m-%d")
                            time_str = parts[1] if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else "09:00"
                            text_start = 2 if len(parts) > 1 and re.match(r'^\d{1,2}:\d{2}$', parts[1]) else 1
                            text = " ".join(parts[text_start:]) if len(parts) > text_start else "Напоминание"
                        else:
                            # Assume it's all text, set for today at 09:00
                            dt = datetime.now()
                            time_str = "09:00"
                            text = params
                        
                        # Parse time
                        if re.match(r'^\d{1,2}:\d{2}$', time_str):
                            hour, minute = map(int, time_str.split(":"))
                            dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        
                        # Check if time is in past
                        if dt < datetime.now():
                            if dt.date() == datetime.now().date():
                                dt += timedelta(days=1)
                        
                        logger.info(f"Creating reminder: '{text}' at {dt}")
                        reminder_id = self.db.add_text_reminder(telegram_id, text, dt)
                        if reminder_id:
                            response += f"\n\n✅ Напоминание добавлено: **{text}** на {dt.strftime('%d.%m.%Y %H:%M')}"
                        else:
                            response += "\n\n❌ Не удалось добавить напоминание"
                    else:
                        response += "\n\n⚠️ Укажи время и текст (например: завтра 10:00 Сдать лабу)"
                except Exception as e:
                    logger.error(f"Add reminder error: {e}")
                    response += f"\n\n⚠️ Ошибка: {str(e)}"
                continue
            
            elif cmd == "SHOW_REMINDERS":
                reminders = self.db.get_user_reminders(telegram_id)
                if reminders:
                    response += "\n\n⏰ **Твои напоминания:**\n"
                    for r in reminders[:10]:
                        r_time = datetime.fromisoformat(r['reminder_time']) if isinstance(r['reminder_time'], str) else r['reminder_time']
                        r_text = r['reminder_text'] or 'Напоминание'
                        response += f"• {r_time.strftime('%d.%m %H:%M')} - {r_text}\n"
                else:
                    response += "\n\n📭 У тебя нет активных напоминаний"
                continue
            
            elif cmd.startswith("ADD_NOTE:"):
                note_text = cmd.replace("ADD_NOTE:", "").strip()
                if note_text:
                    note_id = self.db.add_note(telegram_id, "Заметка", note_text)
                    if note_id:
                        response += f"\n\n✅ Заметка сохранена!"
                    else:
                        response += "\n\n❌ Не удалось сохранить заметку"
                continue
            
            elif cmd == "SHOW_NOTES":
                notes = self.db.get_notes(telegram_id)
                if notes:
                    response += "\n\n📝 **Твои заметки:**\n"
                    for n in notes[:10]:
                        response += f"• {n['content'][:50]}{'...' if len(n['content']) > 50 else ''}\n"
                else:
                    response += "\n\n📭 У тебя нет заметок"
                continue
            
            # ==================== SCHEDULE COMMANDS ====================
            # Need auth for these
            if not self.credentials.has_credentials(telegram_id):
                response += "\n\n🔐 _Для просмотра расписания нужно войти: /login_"
                break
            
            calendar = self._get_calendar_service(telegram_id)
            if not calendar:
                response += "\n\n❌ _Ошибка авторизации. Попробуй /login_"
                break
            
            group = user.get('group_code') if user else None
            
            try:
                if cmd == "SCHEDULE_TODAY":
                    events = calendar.get_today_events(group=group)
                    if events:
                        response += f"\n\n📅 **Сегодня:**\n{self._format_events(events)}"
                    else:
                        response += "\n\n✨ Сегодня занятий нет!"
                
                elif cmd == "SCHEDULE_TOMORROW":
                    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    all_events = calendar.fetch_events(group=group)
                    events = [e for e in all_events if e.get('date') == tomorrow]
                    if events:
                        response += f"\n\n📅 **Завтра:**\n{self._format_events(events)}"
                    else:
                        response += "\n\n✨ Завтра занятий нет!"
                
                elif cmd == "SCHEDULE_WEEK":
                    all_events = calendar.fetch_events(group=group)
                    if all_events:
                        response += f"\n\n📅 **Расписание на неделю:**\n{self._format_events(all_events)}"
                    else:
                        response += "\n\n✨ На этой неделе занятий нет!"
                
                elif cmd == "NEXT_CLASS":
                    event = calendar.get_next_event(group=group)
                    if event:
                        response += f"\n\n⏰ **Следующая пара:**\n{self._format_single_event(event)}"
                
                elif cmd == "FREE_ROOMS":
                    rooms = calendar.get_free_rooms()
                    if rooms:
                        response += f"\n\n🚪 **Свободные аудитории:**\n" + ", ".join(rooms[:10])
                
                elif cmd.startswith("SEARCH:"):
                    query = cmd.replace("SEARCH:", "")
                    events = calendar.search_events(query, group=group, limit=3)
                    if events:
                        response += f"\n\n🔍 **Найдено:**\n{self._format_events(events)}"
            
            except Exception as e:
                logger.error(f"Command execution error: {e}")
        
        return response.strip()
    
    async def _handle_intent(self, update: Update, context: ContextTypes.DEFAULT_TYPE, intent: str, original_text: str = ""):
        """Handle intent when AI is not available"""
        if intent == "greeting":
            await update.message.reply_text("👋 Привет! Используй /help для справки.")
        elif intent == "help":
            await self.cmd_help(update, context)
        elif intent in ["schedule_today", "schedule_tomorrow", "schedule_week"]:
            if self.credentials.has_credentials(update.effective_user.id):
                period = intent.replace("schedule_", "")
                await self._send_schedule(update, context, period)
            else:
                await update.message.reply_text("🔐 Сначала войди: /login")
        elif intent == "add_reminder":
            # Передаём в AI для обработки напоминания
            await self._force_ai_reminder(update, context, original_text)
        elif intent == "show_reminders":
            await self.cmd_reminders(update, context)
        elif intent == "add_note":
            # Передаём в AI для обработки заметки
            await self._force_ai_note(update, context, original_text)
        elif intent == "show_notes":
            await self._show_notes(update, context)
        else:
            await update.message.reply_text("🤔 Не понял. Попробуй /help")
    
    # ==================== Callback Handler ====================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        telegram_id = update.effective_user.id
        
        if data == "login":
            await query.edit_message_text(
                "🔐 **Авторизация в TSI**\n\n"
                "Введи свой студенческий логин (например: `st12345`):\n\n"
                "_Отправь /cancel для отмены._",
                parse_mode="Markdown"
            )
            return STATE_AWAITING_USERNAME
        
        elif data == "logout":
            self.credentials.delete_credentials(telegram_id)
            if telegram_id in self._user_calendars:
                del self._user_calendars[telegram_id]
            await query.edit_message_text("✅ Ты вышел из аккаунта.")
        
        elif data == "schedule_today":
            await self._send_schedule_callback(query, telegram_id, "today")
        
        elif data == "schedule_tomorrow":
            await self._send_schedule_callback(query, telegram_id, "tomorrow")
        
        elif data == "schedule_week":
            await self._send_schedule_callback(query, telegram_id, "week")
        
        elif data == "next_class":
            user = self.db.get_user(telegram_id)
            calendar = self._get_calendar_service(telegram_id)
            keyboard = [[InlineKeyboardButton("◀️ Меню", callback_data="back_to_menu")]]
            if calendar and user and user.get('group_code'):
                event = calendar.get_next_event(group=user['group_code'])
                if event:
                    await query.edit_message_text(
                        f"⏰ **Следующая пара:**\n\n{self._format_single_event(event)}",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        "✨ Ближайших занятий нет!",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            else:
                await query.edit_message_text(
                    "⚠️ Установи группу: /setgroup",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        elif data == "help":
            keyboard = [[InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❓ **Справка**\n\n"
                "**📅 Расписание:**\n"
                "• Сегодня / Завтра / Неделя\n\n"
                "**🤖 AI-помощник:**\n"
                "Просто напиши вопрос!\n"
                "• _\"Что сегодня?\"_\n"
                "• _\"Напомни через час...\"_\n"
                "• _\"Добавь заметку...\"_\n\n"
                "**⏰ Напоминания:**\n"
                "• _\"Напомни завтра в 10:00...\"_\n\n"
                "**📝 Заметки:**\n"
                "• _\"Запиши: текст\"_\n\n"
                "/menu — главное меню",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "settings":
            user = self.db.get_user(telegram_id)
            notif_status = "🔔 Вкл" if user and user.get('notifications_enabled', True) else "🔕 Выкл"
            group = user.get('group_code', 'Не установлена') if user else 'Не установлена'
            
            keyboard = [
                [InlineKeyboardButton(f"🔔 Уведомления: {notif_status}", callback_data="toggle_notifications")],
                [InlineKeyboardButton(f"👥 Группа: {group}", callback_data="set_group")],
                [InlineKeyboardButton("🚪 Выйти из аккаунта", callback_data="logout")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                "⚙️ **Настройки**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "back_to_menu":
            # Show main menu
            is_logged_in = self.credentials.has_credentials(telegram_id)
            if is_logged_in:
                keyboard = [
                    [
                        InlineKeyboardButton("📅 Сегодня", callback_data="schedule_today"),
                        InlineKeyboardButton("📅 Завтра", callback_data="schedule_tomorrow")
                    ],
                    [
                        InlineKeyboardButton("⏰ След. пара", callback_data="next_class"),
                        InlineKeyboardButton("📅 Неделя", callback_data="schedule_week")
                    ],
                    [
                        InlineKeyboardButton("📝 Заметки", callback_data="menu_notes"),
                        InlineKeyboardButton("⏰ Напоминания", callback_data="menu_reminders")
                    ],
                    [
                        InlineKeyboardButton("📊 Ещё", callback_data="menu_more"),
                        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
                    ]
                ]
                await query.edit_message_text(
                    "📋 **Главное меню**",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                # Send keyboard reminder
                await query.message.reply_text(
                    "👇",
                    reply_markup=get_main_keyboard(is_logged_in)
                )
            else:
                keyboard = [[InlineKeyboardButton("🔐 Войти", callback_data="login")]]
                await query.edit_message_text(
                    "📋 **Меню**\n\n🔐 Войди для доступа",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                # Send keyboard reminder
                await query.message.reply_text(
                    "👇",
                    reply_markup=get_main_keyboard(False)
                )
        
        elif data == "menu_notes":
            notes = self.db.get_user_notes(telegram_id, limit=5)
            if notes:
                text = "📝 **Заметки:**\n\n"
                for i, (key, value, dt) in enumerate(notes[:5], 1):
                    text += f"{i}. {value[:50]}{'...' if len(value) > 50 else ''}\n"
            else:
                text = "📝 У тебя пока нет заметок"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить", callback_data="add_note_prompt")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                text + "\n\n_Напиши: \"Запиши: текст\"_",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_reminders":
            reminders = self.db.get_user_reminders(telegram_id)
            if reminders:
                text = "⏰ **Напоминания:**\n\n"
                for r in reminders[:5]:
                    r_text = r.get('reminder_text', 'Напоминание')[:40]
                    r_time = r.get('reminder_time', '')
                    if isinstance(r_time, str):
                        try:
                            dt = datetime.strptime(r_time, '%Y-%m-%d %H:%M:%S')
                            r_time = dt.strftime('%d.%m %H:%M')
                        except:
                            pass
                    text += f"• {r_text} — _{r_time}_\n"
            else:
                text = "⏰ Нет активных напоминаний"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить", callback_data="add_reminder_prompt")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                text + "\n\n_Напиши: \"Напомни через час...\"_",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_more":
            keyboard = [
                [
                    InlineKeyboardButton("🎯 Дедлайны", callback_data="menu_deadlines"),
                    InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")
                ],
                [
                    InlineKeyboardButton("🚪 Аудитории", callback_data="menu_rooms"),
                    InlineKeyboardButton("☀️ Погода", callback_data="menu_weather")
                ],
                [
                    InlineKeyboardButton("✨ Мотивация", callback_data="motivation_more"),
                    InlineKeyboardButton("📝 Экзамены", callback_data="menu_exams")
                ],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                "📊 **Дополнительно**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_deadlines":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_more")]]
            await query.edit_message_text(
                "🎯 **Дедлайны**\n\n"
                "Добавь: `/deadline 25.12 Сдать курсовую`\n"
                "Список: `/deadlines`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_stats":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_more")]]
            await query.edit_message_text(
                "📊 Статистика: /stats",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_rooms":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_more")]]
            await query.edit_message_text(
                "🚪 Свободные аудитории: /freerooms\n"
                "Где аудитория: /where [номер]",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_weather":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_more")]]
            await query.edit_message_text(
                "☀️ Погода: /weather",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "menu_exams":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_more")]]
            await query.edit_message_text(
                "📝 Экзамены: /exams",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "add_note_prompt":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_notes")]]
            await query.edit_message_text(
                "📝 **Добавить заметку**\n\n"
                "Напиши:\n"
                "`Запиши: твой текст`\n\n"
                "или\n"
                "`/note твой текст`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "add_reminder_prompt":
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="menu_reminders")]]
            await query.edit_message_text(
                "⏰ **Добавить напоминание**\n\n"
                "Напиши:\n"
                "• _Напомни через 2 часа..._\n"
                "• _Напомни завтра в 10:00..._\n\n"
                "или\n"
                "`/remind 14:30 текст`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        elif data == "toggle_notifications":
            user = self.db.get_user(telegram_id)
            if user:
                new_state = not user.get('notifications_enabled', True)
                self.db.update_user(telegram_id, notifications_enabled=new_state)
                status = "включены" if new_state else "выключены"
                await query.edit_message_text(f"🔔 Уведомления {status}")
        
        elif data == "set_group":
            await query.edit_message_text(
                "👥 Отправь команду:\n`/setgroup [код группы]`",
                parse_mode="Markdown"
            )
        
        elif data == "motivation_more":
            quote = random.choice(MOTIVATION_QUOTES)
            keyboard = [[
                InlineKeyboardButton("🔄 Ещё", callback_data="motivation_more")
            ]]
            await query.edit_message_text(
                f"✨ **Мотивация дня:**\n\n{quote}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        # Google Calendar callbacks
        elif data == "gcal_connect":
            auth_url = self.google_calendar.get_auth_url(telegram_id)
            if auth_url:
                await query.edit_message_text(
                    "🔗 **Подключение Google Calendar**\n\n"
                    "1️⃣ Перейди по ссылке\n"
                    "2️⃣ Войди в Google\n"
                    "3️⃣ Разреши доступ\n"
                    "4️⃣ Скопируй код\n"
                    "5️⃣ Отправь: `/gcal_code [код]`\n\n"
                    f"🔗 [Открыть Google]({auth_url})",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text("❌ Ошибка")
        
        elif data == "gcal_disconnect":
            self.google_calendar.disconnect(telegram_id)
            await query.edit_message_text("✅ Google Calendar отключен")
        
        elif data == "gcal_sync_week":
            await query.edit_message_text("🔄 Синхронизирую...\n\nОтправь /gcal_sync")
        
        elif data == "gcal_sync_deadlines":
            prefs = self.db.get_user_preferences(telegram_id)
            deadlines = [(k, v) for k, v in prefs.items() if k.startswith('deadline_')]
            
            if not deadlines:
                await query.edit_message_text("🎯 Нет дедлайнов для синхронизации")
                return
            
            added = 0
            for key, desc in deadlines:
                try:
                    date_str = key.split('_')[1]
                    date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                    if self.google_calendar.add_deadline(telegram_id, desc, date):
                        added += 1
                except:
                    continue
            
            await query.edit_message_text(
                f"✅ Синхронизировано {added} дедлайнов в Google Calendar!"
            )
        
        elif data == "gcal_events":
            events = self.google_calendar.get_upcoming_events(telegram_id, 5)
            if events:
                response = "📅 **Ближайшие события:**\n\n"
                for e in events:
                    response += f"• {e['summary']}\n  {e['start'][:16]}\n\n"
                await query.edit_message_text(response, parse_mode="Markdown")
            else:
                await query.edit_message_text("📅 Нет предстоящих событий")
        
        elif data == "export_gcal":
            if self.google_calendar.is_user_connected(telegram_id):
                await query.edit_message_text(
                    "📅 Для синхронизации используй:\n\n"
                    "`/gcal_sync` - расписание на неделю\n"
                    "`/gcal` - меню Google Calendar",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    "❌ Google Calendar не подключен.\n\n"
                    "Подключи: /gcal_connect"
                )
        
        elif data == "export_ics":
            await query.edit_message_text(
                "📄 **ICS экспорт**\n\n"
                "🔧 _Функция в разработке!_"
            )
    
    # ==================== Helper Methods ====================
    
    async def _send_schedule(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        period: str
    ):
        """Send schedule for a period"""
        telegram_id = update.effective_user.id
        user = self.db.get_user(telegram_id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: `/setgroup [код]`",
                parse_mode="Markdown"
            )
            return
        
        calendar = self._get_calendar_service(telegram_id)
        if not calendar:
            await update.message.reply_text("❌ Ошибка авторизации. Попробуй /login")
            return
        
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        try:
            group = user['group_code']
            
            if period == "today":
                events = calendar.get_today_events(group=group)
                title = "📅 **Расписание на сегодня:**"
            elif period == "tomorrow":
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                all_events = calendar.fetch_events(group=group)
                events = [e for e in all_events if e.get('date') == tomorrow]
                title = "📅 **Расписание на завтра:**"
            else:
                events = calendar.get_week_events(group=group)
                title = "📅 **Расписание на неделю:**"
            
            if events:
                response = f"{title}\n\n{self._format_events(events)}"
            else:
                response = f"{title}\n\n✨ Занятий не найдено!"
            
            await update.message.reply_text(response, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Schedule error: {e}")
            await update.message.reply_text("❌ Ошибка получения расписания")
    
    async def _send_schedule_callback(self, query, telegram_id: int, period: str):
        """Send schedule in response to callback"""
        user = self.db.get_user(telegram_id)
        calendar = self._get_calendar_service(telegram_id)
        
        if not calendar:
            await query.edit_message_text("❌ Требуется авторизация: /login")
            return
        
        if not user or not user.get('group_code'):
            await query.edit_message_text("⚠️ Установи группу: /setgroup")
            return
        
        try:
            group = user['group_code']
            
            if period == "today":
                events = calendar.get_today_events(group=group)
                title = "📅 **Сегодня:**"
            elif period == "tomorrow":
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                all_events = calendar.fetch_events(group=group)
                events = [e for e in all_events if e.get('date') == tomorrow]
                title = "📅 **Завтра:**"
            else:
                events = calendar.get_week_events(group=group)
                title = "📅 **Неделя:**"
            
            if events:
                response = f"{title}\n\n{self._format_events(events[:10])}"  # Limit for callback
            else:
                response = f"{title}\n\n✨ Занятий нет!"
            
            keyboard = [[InlineKeyboardButton("◀️ Меню", callback_data="back_to_menu")]]
            await query.edit_message_text(
                response, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Schedule callback error: {e}")
            await query.edit_message_text("❌ Ошибка")
    
    def _format_events(self, events: list) -> str:
        """Format list of events"""
        if not events:
            return "Нет событий"
        
        # Sort events by date and time
        def sort_key(e):
            date = e.get('date', '9999-99-99')
            time = e.get('start_time', '99:99')
            return (date, time)
        
        sorted_events = sorted(events, key=sort_key)
        
        lines = []
        current_date = None
        day_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        
        for event in sorted_events:
            event_date = event.get('date', '')
            
            if event_date != current_date:
                current_date = event_date
                try:
                    date_obj = datetime.strptime(event_date, "%Y-%m-%d")
                    day = day_names.get(date_obj.weekday(), "")
                    lines.append(f"\n📆 **{event_date}** ({day})")
                except:
                    lines.append(f"\n📆 **{event_date}**")
            
            time_str = f"{event.get('start_time', '?')}-{event.get('end_time', '?')}"
            title = event.get('title', 'N/A')[:35]
            room = event.get('room', '-')
            is_cancelled = event.get('is_cancelled', False)
            
            if is_cancelled:
                lines.append(f"⏰ {time_str} | ❌ ~~{title}~~ **ОТМЕНЕНО**")
            else:
                lines.append(f"⏰ {time_str} | 📚 {title}")
            lines.append(f"   🚪 Ауд. {room}")
        
        return "\n".join(lines)
    
    def _format_single_event(self, event: dict) -> str:
        """Format a single event"""
        date_str = event.get('date', 'N/A')
        day_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day = day_names.get(date_obj.weekday(), "")
            date_str = f"{date_str} ({day})"
        except:
            pass
        
        return (
            f"📆 {date_str}\n"
            f"⏰ {event.get('start_time', '?')} - {event.get('end_time', '?')}\n"
            f"📚 {event.get('title', 'N/A')}\n"
            f"🚪 Ауд. {event.get('room', 'N/A')}\n"
            f"👨‍🏫 {event.get('lecturer', 'N/A')}"
        )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуй ещё раз."
            )
    
    async def check_reminders(self, context: ContextTypes.DEFAULT_TYPE):
        """Background job to check and send reminders"""
        try:
            reminders = self.db.get_pending_reminders()
            
            if reminders:
                logger.info(f"Processing {len(reminders)} pending reminders")
            
            for reminder in reminders:
                telegram_id = reminder.get('telegram_id')
                if not telegram_id:
                    logger.warning(f"Reminder {reminder.get('id')} has no telegram_id!")
                    continue
                
                text = reminder.get('reminder_text') or reminder.get('event_id', 'Напоминание')
                
                logger.info(f"Sending reminder to {telegram_id}: {text}")
                
                try:
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=f"🔔 **Напоминание!**\n\n📝 {text}",
                        parse_mode="Markdown"
                    )
                    self.db.mark_reminder_sent(reminder['id'])
                    logger.info(f"✅ Sent reminder {reminder['id']} to {telegram_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to send reminder {reminder['id']}: {e}")
                except Exception as e:
                    logger.error(f"Failed to send reminder: {e}")
                    
        except Exception as e:
            logger.error(f"Check reminders error: {e}")
    
    def run(self):
        """Run the bot"""
        logger.info("Starting Smart Campus Bot v2...")
        
        # Set bot reference for schedule monitor
        self.schedule_monitor.bot = self.application.bot
        
        # Add background job for checking reminders every minute
        job_queue = self.application.job_queue
        if job_queue:
            job_queue.run_repeating(self.check_reminders, interval=60, first=10)
            logger.info("Reminder checker started")
            
            # Add schedule monitor job (check every 2 minutes for faster notifications)
            job_queue.run_repeating(self.check_schedule_changes, interval=120, first=30)
            logger.info("Schedule monitor started (every 2 minutes)")
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def check_schedule_changes(self, context: ContextTypes.DEFAULT_TYPE):
        """Background task to check for schedule changes"""
        try:
            # Get all unique groups from users
            groups = self.schedule_monitor.get_monitored_groups()
            logger.info(f"Checking schedule changes for {len(groups)} groups")
            
            for group in groups:
                try:
                    # Create a temporary calendar service for checking
                    # Try to use any logged-in user's credentials
                    users = self.db.get_users_by_group(group)
                    calendar_service = None
                    
                    for user in users:
                        telegram_id = user.get('telegram_id')
                        if telegram_id:
                            service = self._get_calendar_service(telegram_id)
                            if service:
                                calendar_service = service
                                break
                    
                    if calendar_service:
                        changes = await self.schedule_monitor.check_group(group, calendar_service)
                        
                        if changes.get('newly_cancelled'):
                            logger.info(f"Found {len(changes['newly_cancelled'])} cancelled classes for {group}")
                    else:
                        logger.debug(f"No authenticated user found for group {group}")
                        
                except Exception as e:
                    logger.error(f"Error checking group {group}: {e}")
                
                # Small delay between groups
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Schedule check error: {e}")


def main():
    """Main entry point for the bot"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        exit(1)
    bot = SmartCampusBotV2(token=token)
    bot.run()


if __name__ == "__main__":
    main()
