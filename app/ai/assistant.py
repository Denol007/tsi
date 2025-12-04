#!/usr/bin/env python3
"""
AI Assistant for Smart Campus
Provides intelligent responses and schedule recommendations
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIAssistant:
    """
    AI-powered assistant for campus-related queries
    Uses pattern matching and NLP for intent recognition
    """
    
    def __init__(self, calendar_service=None, database=None):
        self.calendar_service = calendar_service
        self.database = database
        
        # Response templates
        self.templates = {
            "greeting": [
                "👋 Привет! Я Smart Campus Assistant. Чем могу помочь?",
                "🎓 Привет! Я готов помочь с расписанием и информацией о кампусе!",
                "Hi! I'm your Smart Campus Assistant. How can I help you today?"
            ],
            "schedule_today": "📅 Вот твоё расписание на сегодня:\n\n{events}",
            "schedule_tomorrow": "📅 Расписание на завтра:\n\n{events}",
            "schedule_week": "📅 Расписание на неделю:\n\n{events}",
            "next_class": "⏰ Следующая пара:\n\n{event}",
            "no_events": "✨ На этот период занятий не найдено!",
            "free_rooms": "🚪 Свободные аудитории:\n\n{rooms}",
            "search_results": "🔍 Результаты поиска:\n\n{results}",
            "help": """
🤖 **Smart Campus Assistant - Справка**

Вот что я умею:

📅 **Расписание:**
• "Расписание на сегодня" / "today"
• "Расписание на завтра" / "tomorrow"
• "Расписание на неделю" / "week"
• "Следующая пара" / "next class"

🔍 **Поиск:**
• "Найди [предмет/преподавателя]"
• "Когда [предмет]?"
• "Где занятие [предмет]?"

🚪 **Аудитории:**
• "Свободные аудитории"
• "Где находится [аудитория]?"

⚙️ **Настройки:**
• "Установить группу [код]"
• "Мои настройки"
• "Включить уведомления"

💡 Просто напиши свой вопрос, и я постараюсь помочь!
            """,
            "error": "❌ Произошла ошибка. Попробуй ещё раз или напиши /help",
            "unknown": "🤔 Не совсем понял запрос. Попробуй переформулировать или напиши /help для справки.",
            "group_set": "✅ Группа установлена: {group}",
            "notifications_on": "🔔 Уведомления включены!",
            "notifications_off": "🔕 Уведомления выключены.",
        }
        
        # Day translations
        self.day_names = {
            0: "Понедельник",
            1: "Вторник",
            2: "Среда",
            3: "Четверг",
            4: "Пятница",
            5: "Суббота",
            6: "Воскресенье"
        }
    
    def process_query(
        self,
        query: str,
        user_context: Dict[str, Any] = None
    ) -> Tuple[str, str]:
        """
        Process user query and return response
        
        Args:
            query: User's text query
            user_context: User information (group, preferences, etc.)
            
        Returns:
            Tuple of (response_text, detected_intent)
        """
        query_lower = query.lower().strip()
        user_context = user_context or {}
        
        # Intent detection
        intent = self._detect_intent(query_lower)
        
        try:
            response = self._generate_response(intent, query_lower, user_context)
            return response, intent
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return self.templates["error"], "error"
    
    def _detect_intent(self, query: str) -> str:
        """Detect the intent of the user's query"""
        
        # Greeting patterns
        if re.search(r'\b(привет|здравствуй|hello|hi|hey|start)\b', query):
            return "greeting"
        
        # Help patterns
        if re.search(r'\b(помощь|помоги|help|справка|что умеешь|команды)\b', query):
            return "help"
        
        # Schedule patterns
        if re.search(r'\b(сегодня|today|на сегодня)\b', query):
            return "schedule_today"
        
        if re.search(r'\b(завтра|tomorrow|на завтра)\b', query):
            return "schedule_tomorrow"
        
        if re.search(r'\b(неделя|week|на неделю|эта неделя)\b', query):
            return "schedule_week"
        
        if re.search(r'\b(следующ|next|ближайш|скоро)\b.*\b(пара|занятие|лекция|class|lesson)\b', query):
            return "next_class"
        
        if re.search(r'\b(расписание|schedule|занятия|пары)\b', query):
            return "schedule_today"  # Default to today
        
        # Free rooms
        if re.search(r'\b(свободн|free|пуст)\b.*\b(аудитори|room|комнат|кабинет)\b', query):
            return "free_rooms"
        
        # Search patterns
        if re.search(r'\b(найди|найти|поиск|search|когда|where|где)\b', query):
            return "search"
        
        # Settings patterns
        if re.search(r'\b(группа|group|установ|set)\b.*\b([0-9]{4}[A-Za-z]{3})\b', query):
            return "set_group"
        
        if re.search(r'\b(настройк|settings|preferences)\b', query):
            return "settings"
        
        if re.search(r'\b(уведомлен|notification)\b.*\b(включ|on|enable)\b', query):
            return "notifications_on"
        
        if re.search(r'\b(уведомлен|notification)\b.*\b(выключ|off|disable)\b', query):
            return "notifications_off"
        
        return "unknown"
    
    def _generate_response(
        self,
        intent: str,
        query: str,
        user_context: Dict[str, Any]
    ) -> str:
        """Generate response based on detected intent"""
        
        group = user_context.get('group_code')
        
        if intent == "greeting":
            import random
            return random.choice(self.templates["greeting"])
        
        if intent == "help":
            return self.templates["help"]
        
        if intent == "schedule_today":
            return self._get_schedule_response("today", group)
        
        if intent == "schedule_tomorrow":
            return self._get_schedule_response("tomorrow", group)
        
        if intent == "schedule_week":
            return self._get_schedule_response("week", group)
        
        if intent == "next_class":
            return self._get_next_class_response(group)
        
        if intent == "free_rooms":
            return self._get_free_rooms_response()
        
        if intent == "search":
            # Extract search query
            search_term = self._extract_search_term(query)
            return self._search_events(search_term, group)
        
        if intent == "set_group":
            # Extract group code
            match = re.search(r'([0-9]{4}[A-Za-z]{3})', query, re.IGNORECASE)
            if match:
                group_code = match.group(1).upper()
                return self.templates["group_set"].format(group=group_code)
            return "❌ Не удалось определить код группы. Формат: 3401BNA"
        
        if intent == "notifications_on":
            return self.templates["notifications_on"]
        
        if intent == "notifications_off":
            return self.templates["notifications_off"]
        
        return self.templates["unknown"]
    
    def _get_schedule_response(self, period: str, group: str = None) -> str:
        """Get formatted schedule for a period"""
        if not self.calendar_service:
            return "⚠️ Сервис расписания недоступен"
        
        if not group:
            return "⚠️ Группа не указана. Используй: /setgroup [код группы]"
        
        try:
            if period == "today":
                events = self.calendar_service.get_today_events(group=group)
                template = self.templates["schedule_today"]
            elif period == "tomorrow":
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                all_events = self.calendar_service.fetch_events(group=group)
                events = [e for e in all_events if e.get('date') == tomorrow]
                template = self.templates["schedule_tomorrow"]
            else:  # week
                events = self.calendar_service.get_week_events(group=group)
                template = self.templates["schedule_week"]
            
            if not events:
                return self.templates["no_events"]
            
            formatted = self._format_events(events)
            return template.format(events=formatted)
            
        except Exception as e:
            logger.error(f"Error getting schedule: {e}")
            return self.templates["error"]
    
    def _get_next_class_response(self, group: str = None) -> str:
        """Get the next upcoming class"""
        if not self.calendar_service:
            return "⚠️ Сервис расписания недоступен"
        
        if not group:
            return "⚠️ Группа не указана. Используй: /setgroup [код группы]"
        
        try:
            event = self.calendar_service.get_next_event(group=group)
            
            if not event:
                return "✨ Ближайших занятий не найдено!"
            
            formatted = self._format_single_event(event)
            return self.templates["next_class"].format(event=formatted)
            
        except Exception as e:
            logger.error(f"Error getting next class: {e}")
            return self.templates["error"]
    
    def _get_free_rooms_response(self) -> str:
        """Get list of free rooms"""
        if not self.calendar_service:
            return "⚠️ Сервис расписания недоступен"
        
        try:
            rooms = self.calendar_service.get_free_rooms()
            
            if not rooms:
                return "❌ Свободных аудиторий не найдено"
            
            rooms_list = "\n".join([f"🚪 {room}" for room in rooms[:10]])
            return self.templates["free_rooms"].format(rooms=rooms_list)
            
        except Exception as e:
            logger.error(f"Error getting free rooms: {e}")
            return self.templates["error"]
    
    def _search_events(self, search_term: str, group: str = None) -> str:
        """Search for events"""
        if not self.calendar_service:
            return "⚠️ Сервис расписания недоступен"
        
        if not search_term:
            return "🔍 Что найти? Например: 'Найди математика' или 'Когда экзамен?'"
        
        try:
            events = self.calendar_service.search_events(search_term, group=group)
            
            if not events:
                return f"🔍 По запросу '{search_term}' ничего не найдено"
            
            formatted = self._format_events(events[:5])
            return self.templates["search_results"].format(results=formatted)
            
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return self.templates["error"]
    
    def _format_events(self, events: List[Dict]) -> str:
        """Format list of events for display"""
        if not events:
            return "Нет событий"
        
        lines = []
        current_date = None
        
        for event in events:
            event_date = event.get('date', '')
            
            # Add date header if it's a new day
            if event_date != current_date:
                current_date = event_date
                try:
                    date_obj = datetime.strptime(event_date, "%Y-%m-%d")
                    day_name = self.day_names.get(date_obj.weekday(), "")
                    lines.append(f"\n📆 **{event_date}** ({day_name})")
                except:
                    lines.append(f"\n📆 **{event_date}**")
            
            # Format event
            time_str = f"{event.get('start_time', '?')}-{event.get('end_time', '?')}"
            title = event.get('title', 'Без названия')
            room = event.get('room', '-')
            lecturer = event.get('lecturer', '-')
            
            lines.append(f"⏰ {time_str}")
            lines.append(f"📚 {title}")
            lines.append(f"🚪 Ауд. {room} | 👨‍🏫 {lecturer}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_single_event(self, event: Dict) -> str:
        """Format a single event for display"""
        date_str = event.get('date', 'N/A')
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = self.day_names.get(date_obj.weekday(), "")
            date_str = f"{date_str} ({day_name})"
        except:
            pass
        
        lines = [
            f"📆 Дата: {date_str}",
            f"⏰ Время: {event.get('start_time', '?')} - {event.get('end_time', '?')}",
            f"📚 Предмет: {event.get('title', 'N/A')}",
            f"🚪 Аудитория: {event.get('room', 'N/A')}",
            f"👨‍🏫 Преподаватель: {event.get('lecturer', 'N/A')}",
            f"👥 Группа: {event.get('group', 'N/A')}"
        ]
        
        if event.get('description'):
            lines.append(f"📝 Примечание: {event['description']}")
        
        return "\n".join(lines)
    
    def _extract_search_term(self, query: str) -> str:
        """Extract search term from query"""
        # Remove common command words
        patterns = [
            r'найди\s+',
            r'найти\s+',
            r'поиск\s+',
            r'search\s+',
            r'когда\s+',
            r'где\s+',
            r'where\s+',
            r'when\s+'
        ]
        
        result = query
        for pattern in patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        return result.strip()
    
    def get_daily_summary(self, group: str = None) -> str:
        """Generate a daily summary for notifications"""
        if not self.calendar_service or not group:
            return None
        
        try:
            events = self.calendar_service.get_today_events(group=group)
            
            if not events:
                return f"🌅 Доброе утро! Сегодня у группы {group} нет занятий. Отдыхай!"
            
            first_event = events[0]
            last_event = events[-1]
            
            summary = f"""🌅 Доброе утро!

📅 Расписание на сегодня для {group}:
• Занятий: {len(events)}
• Начало: {first_event.get('start_time', '?')}
• Конец: {last_event.get('end_time', '?')}

Первая пара:
📚 {first_event.get('title', 'N/A')}
🚪 Ауд. {first_event.get('room', 'N/A')}

Хорошего дня! 🎓"""
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating daily summary: {e}")
            return None


# Intent classifier using simple patterns (can be replaced with ML model)
class IntentClassifier:
    """Simple intent classifier for user queries"""
    
    INTENTS = [
        "greeting",
        "help",
        "schedule_today",
        "schedule_tomorrow",
        "schedule_week",
        "next_class",
        "free_rooms",
        "search",
        "set_group",
        "settings",
        "notifications_on",
        "notifications_off",
        "feedback",
        "unknown"
    ]
    
    def __init__(self):
        self.patterns = self._load_patterns()
    
    def _load_patterns(self) -> Dict[str, List[str]]:
        """Load intent patterns"""
        return {
            "greeting": ["привет", "здравствуй", "hello", "hi", "hey", "добр"],
            "help": ["помощь", "help", "справка", "что умеешь", "команды"],
            "schedule_today": ["сегодня", "today", "расписание"],
            "schedule_tomorrow": ["завтра", "tomorrow"],
            "schedule_week": ["неделя", "week"],
            "next_class": ["следующ", "next", "ближайш"],
            "free_rooms": ["свободн", "free", "пуст"],
            "search": ["найди", "поиск", "search", "когда", "где"],
        }
    
    def classify(self, text: str) -> Tuple[str, float]:
        """
        Classify the intent of a text
        
        Returns:
            Tuple of (intent, confidence)
        """
        text_lower = text.lower()
        
        scores = {}
        for intent, patterns in self.patterns.items():
            score = sum(1 for p in patterns if p in text_lower)
            if score > 0:
                scores[intent] = score
        
        if not scores:
            return "unknown", 0.0
        
        best_intent = max(scores, key=scores.get)
        confidence = min(scores[best_intent] / len(self.patterns[best_intent]), 1.0)
        
        return best_intent, confidence
