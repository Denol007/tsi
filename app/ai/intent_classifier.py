#!/usr/bin/env python3
"""
Intent Classifier for Smart Campus Assistant
Uses pattern matching and optionally ML for intent detection
"""

import re
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Intent classifier using pattern matching
    Can be extended with ML models (BERT, etc.)
    """
    
    # Intent definitions with patterns and keywords
    # IMPORTANT: Order matters! More specific intents should come first
    INTENT_PATTERNS = {
        # Reminders - check BEFORE schedule patterns!
        "add_reminder": {
            "patterns": [
                r"\b(напомни|напоминани|remind|напомнить|уведоми|reminder)\b.*\b(\d{1,2}[:.]\d{2}|\d+\s*(час|мин|min|hour)|через|завтра|сегодня|послезавтра)\b",
                r"\b(напомни|remind|напомнить)\s+.+\b",
                r"\b(создай|добавь|поставь)\s+(напоминани|remind|уведомлени)\b",
            ],
            "keywords": ["напомни", "напоминание", "remind", "reminder", "напомнить"],
            "examples": ["Напомни мне завтра в 10:00 про лабу", "Remind me at 5pm", "Напомни через час позвонить"]
        },
        "show_reminders": {
            "patterns": [
                r"\b(мои|все|покажи|список)\s*(напоминани\w*|reminder\w*)\b",
                r"\bнапоминани\w*\b"
            ],
            "keywords": ["напоминания", "reminders"],
            "examples": ["Мои напоминания", "Покажи напоминания", "Show reminders"]
        },
        # Notes
        "add_note": {
            "patterns": [
                r"\b(добавь|создай|запиши|сохрани)\s*(заметк\w*|note)\b",
                r"\b(заметк\w*|note)\s*[:]\s*.+\b"
            ],
            "keywords": ["заметка", "note", "запиши", "запомни"],
            "examples": ["Добавь заметку: купить молоко", "Запиши заметку"]
        },
        "show_notes": {
            "patterns": [
                r"\b(мои|все|покажи|список)\s*(заметк\w*|notes?)\b",
                r"\bзаметки\b"
            ],
            "keywords": ["заметки", "notes"],
            "examples": ["Мои заметки", "Покажи заметки", "Show notes"]
        },
        "greeting": {
            "patterns": [
                r"\b(привет|здравствуй|добр\w+\s+(утр|день|вечер)|hello|hi|hey)\b",
                r"^/start$"
            ],
            "keywords": ["привет", "hello", "hi", "здравствуй"],
            "examples": ["Привет!", "Hello", "Добрый день"]
        },
        "help": {
            "patterns": [
                r"\b(помо[гщ]|help|справк|что (ты )?умеешь|команд)\w*\b",
                r"^/help$"
            ],
            "keywords": ["помощь", "help", "справка"],
            "examples": ["Помоги", "What can you do?", "/help"]
        },
        "schedule_today": {
            "patterns": [
                r"\b(расписани\w*|schedule|занят\w*|пар\w*).*(сегодня|today)\b",
                r"\b(сегодня|today).*(расписани\w*|schedule|занят\w*|пар\w*)\b",
                r"^(сегодня|today)$"
            ],
            "keywords": ["сегодня", "today", "расписание"],
            "examples": ["Расписание на сегодня", "What's today's schedule?"]
        },
        "schedule_tomorrow": {
            "patterns": [
                r"\b(расписани\w*|schedule|занят\w*).*(завтра|tomorrow)\b",
                r"\b(завтра|tomorrow).*(расписани\w*|schedule|занят\w*)\b",
                r"^(завтра|tomorrow)$"
            ],
            "keywords": ["завтра", "tomorrow"],
            "examples": ["Что завтра?", "Tomorrow's classes"]
        },
        "schedule_week": {
            "patterns": [
                r"\b(расписани\w*|schedule).*(недел\w*|week)\b",
                r"\b(недел\w*|week).*(расписани\w*|schedule)\b",
                r"^(на неделю|this week)$"
            ],
            "keywords": ["неделя", "week"],
            "examples": ["Расписание на неделю", "Weekly schedule"]
        },
        "schedule_date": {
            "patterns": [
                r"\b(расписани\w*|schedule).*((\d{1,2})[./](\d{1,2}))\b",
                r"\b(\d{4}-\d{2}-\d{2})\b"
            ],
            "keywords": [],
            "examples": ["Расписание на 15.12", "Schedule for 2025-01-15"]
        },
        "next_class": {
            "patterns": [
                r"\b(следующ\w*|next|ближайш\w*|скоро).*(пар\w*|занят\w*|лекци\w*|class|lesson)\b",
                r"\b(когда|when).*(следующ\w*|next)\b"
            ],
            "keywords": ["следующая", "next", "ближайшая"],
            "examples": ["Когда следующая пара?", "Next class?"]
        },
        "free_rooms": {
            "patterns": [
                r"\b(свободн\w*|free|пуст\w*).*(аудитори\w*|room|кабинет\w*|комнат\w*)\b",
                r"\b(аудитори\w*|room).*(свободн\w*|free)\b"
            ],
            "keywords": ["свободные", "free", "аудитории"],
            "examples": ["Свободные аудитории", "Free rooms now"]
        },
        "room_info": {
            "patterns": [
                r"\b(где|where|как найти|как пройти).*(аудитори\w*|room|кабинет)\s*(\d+|[A-Z]\d+)\b",
                r"\bаудитори\w*\s*(\d+|[A-Z]\d+)\b"
            ],
            "keywords": ["где", "аудитория", "найти"],
            "examples": ["Где аудитория 221?", "How to find room L5?"]
        },
        "lecturer_info": {
            "patterns": [
                r"\b(кто|who|информаци\w*).*(преподават\w*|lecturer|профессор|доцент)\b",
                r"\b(преподават\w*|lecturer).*(информаци\w*|контакт\w*)\b"
            ],
            "keywords": ["преподаватель", "lecturer", "профессор"],
            "examples": ["Кто преподаватель?", "Lecturer contact"]
        },
        "search": {
            "patterns": [
                r"\b(найди|найти|поиск|search|искать)\s+(.+)\b",
                r"\b(когда|when|где|where)\s+(.+)\b"
            ],
            "keywords": ["найди", "search", "поиск"],
            "examples": ["Найди математику", "When is physics?"]
        },
        "set_group": {
            "patterns": [
                r"\b(групп\w*|group)\s*[:=]?\s*([0-9]{4}[A-Za-z]{3})\b",
                r"\b(установ\w*|set).*(групп\w*|group)\s*([0-9]{4}[A-Za-z]{3})\b",
                r"^/setgroup\s+([0-9]{4}[A-Za-z]{3})$"
            ],
            "keywords": ["группа", "group", "установить"],
            "examples": ["Моя группа 3401BNA", "/setgroup 5502DTL"]
        },
        "get_group": {
            "patterns": [
                r"\b(моя|my).*(групп\w*|group)\b",
                r"\b(какая|what).*(групп\w*|group)\b"
            ],
            "keywords": ["моя", "группа"],
            "examples": ["Какая моя группа?", "My group"]
        },
        "settings": {
            "patterns": [
                r"\b(настройк\w*|settings|preferences|параметр\w*)\b",
                r"^/settings$"
            ],
            "keywords": ["настройки", "settings"],
            "examples": ["Настройки", "/settings"]
        },
        "notifications_on": {
            "patterns": [
                r"\b(уведомлен\w*|notification).*(включ\w*|on|enable|вкл)\b",
                r"\b(включ\w*|enable).*(уведомлен\w*|notification)\b"
            ],
            "keywords": ["уведомления", "включить"],
            "examples": ["Включить уведомления", "Enable notifications"]
        },
        "notifications_off": {
            "patterns": [
                r"\b(уведомлен\w*|notification).*(выключ\w*|off|disable|откл)\b",
                r"\b(выключ\w*|disable).*(уведомлен\w*|notification)\b"
            ],
            "keywords": ["уведомления", "выключить"],
            "examples": ["Выключить уведомления", "Disable notifications"]
        },
        "feedback": {
            "patterns": [
                r"\b(отзыв|feedback|оценк\w*|rate)\b",
                r"^/feedback$"
            ],
            "keywords": ["отзыв", "feedback", "оценка"],
            "examples": ["Оставить отзыв", "/feedback"]
        },
        "exam_schedule": {
            "patterns": [
                r"\b(экзамен\w*|exam|зачёт|зачет|сессия|session)\b"
            ],
            "keywords": ["экзамен", "exam", "сессия"],
            "examples": ["Когда экзамены?", "Exam schedule"]
        },
        "campus_info": {
            "patterns": [
                r"\b(кампус|campus|здани\w*|building|корпус)\b",
                r"\b(библиотек\w*|library|столов\w*|cafeteria|буфет)\b"
            ],
            "keywords": ["кампус", "campus", "библиотека"],
            "examples": ["Где библиотека?", "Campus info"]
        }
    }
    
    def __init__(self):
        """Initialize the classifier"""
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency"""
        self.compiled_patterns = {}
        for intent, data in self.INTENT_PATTERNS.items():
            self.compiled_patterns[intent] = [
                re.compile(pattern, re.IGNORECASE | re.UNICODE)
                for pattern in data["patterns"]
            ]
    
    def classify(self, text: str) -> Tuple[str, float, Dict]:
        """
        Classify the intent of a text
        
        Args:
            text: Input text to classify
            
        Returns:
            Tuple of (intent, confidence, metadata)
        """
        text = text.strip()
        if not text:
            return "unknown", 0.0, {}
        
        text_lower = text.lower()
        
        # PRIORITY CHECK: specific phrases first, then general keywords
        # Order matters! Check "show" intents BEFORE "add" intents
        
        # Check for SHOW intents first (more specific)
        show_notes_triggers = ["какие у меня заметки", "мои заметки", "покажи заметки", "список заметок", "все заметки"]
        for trigger in show_notes_triggers:
            if trigger in text_lower:
                logger.info(f"Priority match: '{trigger}' -> show_notes")
                return "show_notes", 0.95, {"priority_keyword": trigger}
        
        show_reminders_triggers = ["какие у меня напоминания", "мои напоминания", "покажи напоминания", "список напоминаний"]
        for trigger in show_reminders_triggers:
            if trigger in text_lower:
                logger.info(f"Priority match: '{trigger}' -> show_reminders")
                return "show_reminders", 0.95, {"priority_keyword": trigger}
        
        # Check for ADD intents (require action words)
        add_note_triggers = ["добавь заметк", "создай заметк", "запиши заметк", "сохрани заметк", "заметка:"]
        for trigger in add_note_triggers:
            if trigger in text_lower:
                logger.info(f"Priority match: '{trigger}' -> add_note")
                return "add_note", 0.95, {"priority_keyword": trigger}
        
        add_reminder_triggers = ["напомни", "remind", "напомнить", "создай напоминани", "добавь напоминани"]
        for trigger in add_reminder_triggers:
            if trigger in text_lower:
                logger.info(f"Priority match: '{trigger}' -> add_reminder")
                return "add_reminder", 0.95, {"priority_keyword": trigger}
        
        # Check each intent
        scores = {}
        matches = {}
        
        for intent, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    # Score based on match quality
                    match_ratio = len(match.group()) / len(text)
                    score = 0.5 + (match_ratio * 0.5)  # 0.5 to 1.0
                    
                    if intent not in scores or score > scores[intent]:
                        scores[intent] = score
                        matches[intent] = match.groups()
        
        # Also check keywords
        for intent, data in self.INTENT_PATTERNS.items():
            keyword_matches = sum(1 for kw in data["keywords"] if kw in text_lower)
            if keyword_matches > 0:
                keyword_score = min(keyword_matches * 0.2, 0.6)
                if intent in scores:
                    scores[intent] = min(scores[intent] + keyword_score, 1.0)
                else:
                    scores[intent] = keyword_score
        
        if not scores:
            return "unknown", 0.0, {}
        
        # Get best intent
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent]
        
        # Extract metadata
        metadata = {
            "match_groups": matches.get(best_intent, ()),
            "all_scores": scores
        }
        
        return best_intent, confidence, metadata
    
    def get_intent_examples(self, intent: str) -> List[str]:
        """Get example phrases for an intent"""
        if intent in self.INTENT_PATTERNS:
            return self.INTENT_PATTERNS[intent].get("examples", [])
        return []
    
    def get_all_intents(self) -> List[str]:
        """Get list of all supported intents"""
        return list(self.INTENT_PATTERNS.keys())
    
    def add_custom_intent(
        self,
        intent_name: str,
        patterns: List[str],
        keywords: List[str] = None,
        examples: List[str] = None
    ):
        """Add a custom intent"""
        self.INTENT_PATTERNS[intent_name] = {
            "patterns": patterns,
            "keywords": keywords or [],
            "examples": examples or []
        }
        self.compiled_patterns[intent_name] = [
            re.compile(pattern, re.IGNORECASE | re.UNICODE)
            for pattern in patterns
        ]
        logger.info(f"Added custom intent: {intent_name}")
