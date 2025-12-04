#!/usr/bin/env python3
"""
Smart Campus Telegram Bot
Main bot implementation with all handlers
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
from app.ai.assistant import AIAssistant
from app.ai.intent_classifier import IntentClassifier

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
AWAITING_GROUP = 0
AWAITING_CREDENTIALS = 1
AWAITING_FEEDBACK = 2


class SmartCampusBot:
    """Telegram Bot for Smart Campus Assistant"""
    
    def __init__(
        self,
        token: str,
        tsi_username: str = None,
        tsi_password: str = None
    ):
        self.token = token
        self.tsi_username = tsi_username
        self.tsi_password = tsi_password
        
        # Initialize services
        self.db = Database()
        self.calendar_service = None
        self.assistant = None
        self.intent_classifier = IntentClassifier()
        
        # Initialize calendar service if credentials provided
        if tsi_username and tsi_password:
            self._init_calendar_service()
        
        # Build application
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _init_calendar_service(self):
        """Initialize the calendar service"""
        try:
            self.calendar_service = CalendarService(
                username=self.tsi_username,
                password=self.tsi_password
            )
            if self.calendar_service.login():
                self.assistant = AIAssistant(
                    calendar_service=self.calendar_service,
                    database=self.db
                )
                logger.info("Calendar service initialized successfully")
            else:
                logger.error("Failed to login to TSI portal")
        except Exception as e:
            logger.error(f"Error initializing calendar service: {e}")
    
    def _setup_handlers(self):
        """Setup all message handlers"""
        app = self.application
        
        # Command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
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
        app.add_handler(CommandHandler("notify", self.cmd_notify))
        app.add_handler(CommandHandler("feedback", self.cmd_feedback))
        app.add_handler(CommandHandler("export", self.cmd_export))
        
        # Callback query handler for inline buttons
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handler for natural language
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        # Error handler
        app.add_error_handler(self.error_handler)
    
    async def set_commands(self):
        """Set bot commands for the menu"""
        commands = [
            BotCommand("start", "🚀 Начать работу"),
            BotCommand("help", "❓ Справка"),
            BotCommand("today", "📅 Расписание на сегодня"),
            BotCommand("tomorrow", "📅 Расписание на завтра"),
            BotCommand("week", "📅 Расписание на неделю"),
            BotCommand("next", "⏰ Следующая пара"),
            BotCommand("setgroup", "👥 Установить группу"),
            BotCommand("mygroup", "ℹ️ Моя группа"),
            BotCommand("freerooms", "🚪 Свободные аудитории"),
            BotCommand("search", "🔍 Поиск"),
            BotCommand("settings", "⚙️ Настройки"),
            BotCommand("notify", "🔔 Уведомления"),
            BotCommand("feedback", "💬 Обратная связь"),
        ]
        await self.application.bot.set_my_commands(commands)
    
    # ==================== Command Handlers ====================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        telegram_id = user.id
        
        # Create or update user in database
        self.db.create_user(
            telegram_id=telegram_id,
            username=user.username
        )
        
        # Welcome message with keyboard
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
                InlineKeyboardButton("👥 Установить группу", callback_data="set_group"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""
👋 Привет, {user.first_name}!

Я **Smart Campus Assistant** 🎓

Я помогу тебе с:
• 📅 Расписанием занятий
• 🚪 Поиском свободных аудиторий
• ⏰ Напоминаниями о парах
• 🔍 Поиском информации

Для начала установи свою группу командой:
/setgroup [код группы]

Например: `/setgroup 3401BNA`

Или просто напиши мне вопрос!
        """
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🤖 **Smart Campus Assistant - Справка**

**📅 Расписание:**
• `/today` - расписание на сегодня
• `/tomorrow` - расписание на завтра
• `/week` - расписание на неделю
• `/next` - следующая пара

**👥 Группа:**
• `/setgroup [код]` - установить группу
• `/mygroup` - показать мою группу

**🔍 Поиск:**
• `/search [запрос]` - поиск по расписанию
• `/freerooms` - свободные аудитории

**⚙️ Настройки:**
• `/settings` - настройки бота
• `/notify on/off` - уведомления

**💬 Обратная связь:**
• `/feedback` - оставить отзыв

**💡 Совет:** Ты можешь просто написать вопрос естественным языком!

Примеры:
• "Что сегодня?"
• "Когда следующая пара?"
• "Найди математику"
• "Свободные аудитории"
        """
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /today command"""
        await self._send_schedule(update, context, "today")
    
    async def cmd_tomorrow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tomorrow command"""
        await self._send_schedule(update, context, "tomorrow")
    
    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /week command"""
        await self._send_schedule(update, context, "week")
    
    async def cmd_next(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /next command"""
        user = self.db.get_user(update.effective_user.id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: /setgroup [код]\n"
                "Например: `/setgroup 3401BNA`",
                parse_mode="Markdown"
            )
            return
        
        if not self.assistant:
            await update.message.reply_text("⚠️ Сервис расписания временно недоступен")
            return
        
        response, _ = self.assistant.process_query(
            "следующая пара",
            user_context=user
        )
        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def cmd_setgroup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setgroup command"""
        if not context.args:
            await update.message.reply_text(
                "📝 Укажи код группы:\n"
                "`/setgroup [код группы]`\n\n"
                "Примеры:\n"
                "• `/setgroup 3401BNA`\n"
                "• `/setgroup 5502DTL`",
                parse_mode="Markdown"
            )
            return
        
        group_code = context.args[0].upper()
        
        # Validate group code format
        import re
        if not re.match(r'^[0-9]{4}[A-Z]{3}$', group_code):
            await update.message.reply_text(
                "❌ Неверный формат группы.\n"
                "Правильный формат: 4 цифры + 3 буквы\n"
                "Пример: `3401BNA`",
                parse_mode="Markdown"
            )
            return
        
        # Update user's group
        self.db.update_user(
            telegram_id=update.effective_user.id,
            group_code=group_code
        )
        
        await update.message.reply_text(
            f"✅ Группа установлена: **{group_code}**\n\n"
            f"Теперь можешь использовать:\n"
            f"• /today - расписание на сегодня\n"
            f"• /tomorrow - расписание на завтра\n"
            f"• /next - следующая пара",
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
            f"👥 Твоя группа: **{user['group_code']}**\n\n"
            f"Изменить: `/setgroup [новый код]`",
            parse_mode="Markdown"
        )
    
    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user = self.db.get_user(update.effective_user.id)
        
        if not user:
            await update.message.reply_text("❌ Пользователь не найден. Используй /start")
            return
        
        notifications = "✅ Вкл" if user.get('notifications_enabled') else "❌ Выкл"
        reminder = user.get('reminder_minutes', 15)
        group = user.get('group_code', 'Не установлена')
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🔔 Уведомления: {notifications}",
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    f"⏰ Напоминание: {reminder} мин",
                    callback_data="set_reminder"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Изменить группу",
                    callback_data="set_group"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        settings_text = f"""
⚙️ **Настройки**

👤 Пользователь: @{user.get('username', 'N/A')}
👥 Группа: {group}
🔔 Уведомления: {notifications}
⏰ Напоминание: за {reminder} мин
        """
        
        await update.message.reply_text(
            settings_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def cmd_freerooms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /freerooms command"""
        if not self.calendar_service:
            await update.message.reply_text("⚠️ Сервис расписания временно недоступен")
            return
        
        try:
            rooms = self.calendar_service.get_free_rooms()
            
            if not rooms:
                await update.message.reply_text("❌ Информация о свободных аудиториях недоступна")
                return
            
            rooms_list = "\n".join([f"🚪 {room}" for room in rooms[:15]])
            now = datetime.now().strftime("%H:%M")
            
            await update.message.reply_text(
                f"🚪 **Свободные аудитории** (на {now})\n\n{rooms_list}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error getting free rooms: {e}")
            await update.message.reply_text("❌ Ошибка получения данных")
    
    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        if not context.args:
            await update.message.reply_text(
                "🔍 Укажи что искать:\n"
                "`/search [запрос]`\n\n"
                "Примеры:\n"
                "• `/search математика`\n"
                "• `/search Gercevs`",
                parse_mode="Markdown"
            )
            return
        
        query = " ".join(context.args)
        user = self.db.get_user(update.effective_user.id)
        group = user.get('group_code') if user else None
        
        if not self.calendar_service:
            await update.message.reply_text("⚠️ Сервис расписания временно недоступен")
            return
        
        try:
            events = self.calendar_service.search_events(query, group=group, limit=5)
            
            if not events:
                await update.message.reply_text(f"🔍 По запросу '{query}' ничего не найдено")
                return
            
            response = f"🔍 **Результаты поиска:** '{query}'\n\n"
            for event in events:
                response += (
                    f"📅 {event.get('date', 'N/A')}\n"
                    f"⏰ {event.get('start_time', '?')}-{event.get('end_time', '?')}\n"
                    f"📚 {event.get('title', 'N/A')}\n"
                    f"🚪 Ауд. {event.get('room', 'N/A')}\n"
                    f"👨‍🏫 {event.get('lecturer', 'N/A')}\n\n"
                )
            
            await update.message.reply_text(response, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            await update.message.reply_text("❌ Ошибка поиска")
    
    async def cmd_notify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /notify command"""
        if not context.args:
            await update.message.reply_text(
                "🔔 Управление уведомлениями:\n"
                "• `/notify on` - включить\n"
                "• `/notify off` - выключить",
                parse_mode="Markdown"
            )
            return
        
        action = context.args[0].lower()
        enabled = action in ['on', 'yes', 'да', 'вкл', '1']
        
        self.db.update_user(
            telegram_id=update.effective_user.id,
            notifications_enabled=enabled
        )
        
        if enabled:
            await update.message.reply_text(
                "🔔 Уведомления включены!\n"
                "Ты будешь получать напоминания о занятиях."
            )
        else:
            await update.message.reply_text("🔕 Уведомления выключены.")
    
    async def cmd_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /feedback command"""
        keyboard = [
            [
                InlineKeyboardButton("⭐️", callback_data="feedback_1"),
                InlineKeyboardButton("⭐️⭐️", callback_data="feedback_2"),
                InlineKeyboardButton("⭐️⭐️⭐️", callback_data="feedback_3"),
            ],
            [
                InlineKeyboardButton("⭐️⭐️⭐️⭐️", callback_data="feedback_4"),
                InlineKeyboardButton("⭐️⭐️⭐️⭐️⭐️", callback_data="feedback_5"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💬 **Обратная связь**\n\n"
            "Оцени работу бота:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command - export schedule to ICS"""
        user = self.db.get_user(update.effective_user.id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: /setgroup [код]"
            )
            return
        
        await update.message.reply_text(
            "📤 Функция экспорта в разработке.\n"
            "Скоро ты сможешь экспортировать расписание в:\n"
            "• 📅 Google Calendar\n"
            "• 📱 Apple Calendar\n"
            "• 📄 ICS файл"
        )
    
    # ==================== Message Handlers ====================
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages"""
        text = update.message.text
        user = self.db.get_user(update.effective_user.id)
        
        if not user:
            self.db.create_user(
                telegram_id=update.effective_user.id,
                username=update.effective_user.username
            )
            user = self.db.get_user(update.effective_user.id)
        
        # Use AI assistant if available
        if self.assistant:
            response, intent = self.assistant.process_query(text, user_context=user)
            
            # Log the query
            self.db.log_query(
                telegram_id=update.effective_user.id,
                query=text,
                response=response[:500],  # Truncate for storage
                intent=intent
            )
            
            await update.message.reply_text(response, parse_mode="Markdown")
        else:
            # Basic intent classification without calendar service
            intent, confidence, _ = self.intent_classifier.classify(text)
            
            if intent == "greeting":
                await update.message.reply_text(
                    "👋 Привет! Я Smart Campus Assistant.\n"
                    "Используй /help для списка команд."
                )
            elif intent == "help":
                await self.cmd_help(update, context)
            elif intent in ["schedule_today", "schedule_tomorrow", "schedule_week"]:
                await update.message.reply_text(
                    "⚠️ Для просмотра расписания нужно настроить подключение к TSI.\n"
                    "Обратись к администратору бота."
                )
            else:
                await update.message.reply_text(
                    "🤔 Не совсем понял. Попробуй /help для справки."
                )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = self.db.get_user(update.effective_user.id)
        
        if data == "schedule_today":
            await self._send_schedule_callback(query, user, "today")
        
        elif data == "schedule_tomorrow":
            await self._send_schedule_callback(query, user, "tomorrow")
        
        elif data == "schedule_week":
            await self._send_schedule_callback(query, user, "week")
        
        elif data == "next_class":
            if self.assistant and user and user.get('group_code'):
                response, _ = self.assistant.process_query("следующая пара", user)
                await query.edit_message_text(response, parse_mode="Markdown")
            else:
                await query.edit_message_text("⚠️ Сначала установи группу: /setgroup")
        
        elif data == "set_group":
            await query.edit_message_text(
                "👥 Установка группы:\n\n"
                "Отправь команду:\n"
                "`/setgroup [код группы]`\n\n"
                "Пример: `/setgroup 3401BNA`",
                parse_mode="Markdown"
            )
        
        elif data == "help":
            await query.edit_message_text(
                "❓ Справка\n\n"
                "Отправь /help для полного списка команд.",
                parse_mode="Markdown"
            )
        
        elif data == "toggle_notifications":
            if user:
                new_state = not user.get('notifications_enabled', True)
                self.db.update_user(
                    telegram_id=update.effective_user.id,
                    notifications_enabled=new_state
                )
                status = "включены" if new_state else "выключены"
                await query.edit_message_text(f"🔔 Уведомления {status}")
        
        elif data.startswith("feedback_"):
            rating = int(data.split("_")[1])
            self.db.add_feedback(
                telegram_id=update.effective_user.id,
                query_id=0,  # Generic feedback
                rating=rating
            )
            stars = "⭐️" * rating
            await query.edit_message_text(
                f"✅ Спасибо за оценку! {stars}\n\n"
                "Твой отзыв помогает улучшить бота."
            )
    
    # ==================== Helper Methods ====================
    
    async def _send_schedule(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        period: str
    ):
        """Send schedule for a period"""
        user = self.db.get_user(update.effective_user.id)
        
        if not user or not user.get('group_code'):
            await update.message.reply_text(
                "⚠️ Сначала установи группу: /setgroup [код]\n"
                "Например: `/setgroup 3401BNA`",
                parse_mode="Markdown"
            )
            return
        
        if not self.assistant:
            await update.message.reply_text("⚠️ Сервис расписания временно недоступен")
            return
        
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        query = {
            "today": "расписание на сегодня",
            "tomorrow": "расписание на завтра",
            "week": "расписание на неделю"
        }.get(period, "расписание на сегодня")
        
        response, _ = self.assistant.process_query(query, user_context=user)
        await update.message.reply_text(response, parse_mode="Markdown")
    
    async def _send_schedule_callback(self, query, user, period: str):
        """Send schedule in response to callback"""
        if not user or not user.get('group_code'):
            await query.edit_message_text(
                "⚠️ Сначала установи группу: /setgroup [код]"
            )
            return
        
        if not self.assistant:
            await query.edit_message_text("⚠️ Сервис расписания временно недоступен")
            return
        
        query_text = {
            "today": "расписание на сегодня",
            "tomorrow": "расписание на завтра",
            "week": "расписание на неделю"
        }.get(period, "расписание на сегодня")
        
        response, _ = self.assistant.process_query(query_text, user_context=user)
        await query.edit_message_text(response, parse_mode="Markdown")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Error: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуй ещё раз."
            )
    
    # ==================== Bot Control ====================
    
    async def start(self):
        """Start the bot"""
        await self.set_commands()
        logger.info("Bot started")
    
    def run(self):
        """Run the bot (blocking)"""
        logger.info("Starting Smart Campus Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    async def stop(self):
        """Stop the bot"""
        if self.calendar_service:
            self.calendar_service.close()
        logger.info("Bot stopped")
