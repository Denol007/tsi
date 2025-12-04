#!/usr/bin/env python3
"""
AI Provider - Multi-provider AI integration
Supports: Groq (free), Google Gemini (free), Ollama (local), OpenAI
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Chat message"""
    role: str  # "user", "assistant", "system"
    content: str


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    def chat(self, messages: List[Message], **kwargs) -> str:
        """Send chat messages and get response"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available"""
        pass


class GroqProvider(AIProvider):
    """
    Groq AI Provider - FREE and FAST!
    Get API key at: https://console.groq.com/keys
    Models: llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it
    """
    
    def __init__(self, api_key: str = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def chat(self, messages: List[Message], **kwargs) -> str:
        if not self.is_available():
            raise ValueError("Groq API key not configured")
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024)
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise


class GeminiProvider(AIProvider):
    """
    Google Gemini Provider - FREE tier available!
    Get API key at: https://aistudio.google.com/apikey
    Models: gemini-1.5-flash, gemini-1.5-pro
    """
    
    def __init__(self, api_key: str = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def chat(self, messages: List[Message], **kwargs) -> str:
        if not self.is_available():
            raise ValueError("Gemini API key not configured")
        
        import requests
        
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            if msg.role == "system":
                # Gemini handles system prompts differently
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"[System Instruction]: {msg.content}"}]
                })
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })
        
        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 1024)
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                json=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise


class OllamaProvider(AIProvider):
    """
    Ollama Provider - FREE local AI!
    Install: https://ollama.ai
    Models: llama3.2, mistral, gemma2, qwen2.5
    """
    
    def __init__(self, base_url: str = None, model: str = "llama3.2"):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model
    
    def is_available(self) -> bool:
        import requests
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def chat(self, messages: List[Message], **kwargs) -> str:
        import requests
        
        data = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7)
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=data,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise


class OpenAIProvider(AIProvider):
    """
    OpenAI Provider - Paid but high quality
    Models: gpt-4o-mini, gpt-4o, gpt-3.5-turbo
    """
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def chat(self, messages: List[Message], **kwargs) -> str:
        if not self.is_available():
            raise ValueError("OpenAI API key not configured")
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024)
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


class AIManager:
    """
    Manages multiple AI providers with fallback support
    """
    
    # System prompt for Smart Campus Assistant
    SYSTEM_PROMPT = """Ты Smart Campus Assistant - умный помощник для студентов TSI (Transport and Telecommunication Institute).

ВАЖНО: Ты НЕ знаешь реальное расписание! Используй КОМАНДЫ в квадратных скобках, и система подставит реальные данные.
НИКОГДА не придумывай расписание, аудитории или время занятий! Только добавляй команды.

Твои возможности:
- Помощь с расписанием занятий (показать на сегодня, завтра, неделю)
- Напоминания и заметки
- Управление настройками пользователя (группа, язык)
- Общие вопросы

Правила ответов:
1. Отвечай ОЧЕНЬ кратко - 1-2 предложения максимум
2. Используй emoji
3. НЕ ПРИДУМЫВАЙ расписание - используй команды!
4. Отвечай на языке вопроса
5. Будь дружелюбным и полезным

КОМАНДЫ РАСПИСАНИЯ (добавляй в ответ для выполнения):
- [SCHEDULE_TODAY] - показать расписание на сегодня
- [SCHEDULE_TOMORROW] - показать расписание на завтра
- [SCHEDULE_WEEK] - показать расписание на неделю
- [NEXT_CLASS] - показать следующее занятие
- [FREE_ROOMS] - показать свободные аудитории
- [SEARCH:запрос] - поиск по расписанию

КОМАНДЫ НАСТРОЕК (для изменения настроек пользователя):
- [SET_GROUP:код_группы] - установить группу (пример: [SET_GROUP:3401BNA] или [SET_GROUP:4201-2BDA])
- [SET_LANGUAGE:язык] - установить язык интерфейса (ru/en/lv)
- [TOGGLE_NOTIFICATIONS] - включить/выключить уведомления
- [SHOW_SETTINGS] - показать текущие настройки

КОМАНДЫ НАПОМИНАНИЙ И ЗАМЕТОК:
- [ADD_REMINDER:дата время текст] - добавить напоминание (пример: [ADD_REMINDER:завтра 10:00 Сдать лабу])
- [SHOW_REMINDERS] - показать все напоминания
- [ADD_NOTE:текст] - добавить заметку
- [SHOW_NOTES] - показать все заметки

Примеры ответов:
- "Установи группу 4201-2BDA" → "✅ Устанавливаю группу! [SET_GROUP:4201-2BDA]"
- "Покажи мои настройки" → "Показываю настройки! [SHOW_SETTINGS]"
- "Напомни мне завтра в 10:00 про лабу" → "✅ Добавляю напоминание! [ADD_REMINDER:завтра 10:00 Лабораторная работа]"
- "Напомни сегодня в 14:30 сдать отчет" → "✅ Добавляю напоминание! [ADD_REMINDER:сегодня 14:30 Сдать отчет]"
- "Покажи мои напоминания" → "📋 Вот твои напоминания: [SHOW_REMINDERS]"
- "Запиши заметку: купить тетрадь" → "📝 Записываю! [ADD_NOTE:Купить тетрадь]"
- "Мои заметки" → "📝 Твои заметки: [SHOW_NOTES]" """
    
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
        self.primary_provider: Optional[str] = None
        self._init_providers()
    
    def _init_providers(self):
        """Initialize all available providers"""
        # Try providers in order of preference (free first)
        providers_config = [
            ("groq", GroqProvider),
            ("gemini", GeminiProvider),
            ("ollama", OllamaProvider),
            ("openai", OpenAIProvider),
        ]
        
        for name, provider_class in providers_config:
            try:
                provider = provider_class()
                if provider.is_available():
                    self.providers[name] = provider
                    if self.primary_provider is None:
                        self.primary_provider = name
                    logger.info(f"AI Provider '{name}' is available")
            except Exception as e:
                logger.debug(f"Provider {name} not available: {e}")
        
        if not self.providers:
            logger.warning("No AI providers available! Using fallback responses.")
    
    def set_primary_provider(self, name: str):
        """Set the primary AI provider"""
        if name in self.providers:
            self.primary_provider = name
            logger.info(f"Primary AI provider set to: {name}")
        else:
            raise ValueError(f"Provider '{name}' not available")
    
    def get_available_providers(self) -> List[str]:
        """Get list of available providers"""
        return list(self.providers.keys())
    
    def chat(
        self,
        user_message: str,
        conversation_history: List[Message] = None,
        user_context: Dict[str, Any] = None
    ) -> str:
        """
        Send a message and get AI response
        
        Args:
            user_message: User's message
            conversation_history: Previous messages for context
            user_context: User info (group, name, etc.)
        
        Returns:
            AI response text
        """
        # Build messages
        messages = [Message(role="system", content=self._build_system_prompt(user_context))]
        
        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history[-10:])  # Keep last 10 messages
        
        # Add current message
        messages.append(Message(role="user", content=user_message))
        
        # Try primary provider first, then fallback
        providers_to_try = []
        if self.primary_provider:
            providers_to_try.append(self.primary_provider)
        providers_to_try.extend([p for p in self.providers.keys() if p != self.primary_provider])
        
        for provider_name in providers_to_try:
            try:
                provider = self.providers[provider_name]
                response = provider.chat(messages)
                logger.info(f"Got response from {provider_name}")
                return response
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}")
                continue
        
        # Fallback response if no AI available
        return self._fallback_response(user_message)
    
    def _build_system_prompt(self, user_context: Dict[str, Any] = None) -> str:
        """Build system prompt with user context"""
        prompt = self.SYSTEM_PROMPT
        
        if user_context:
            context_info = []
            if user_context.get("group_code"):
                context_info.append(f"Группа студента: {user_context['group_code']}")
            if user_context.get("username"):
                context_info.append(f"Имя пользователя: {user_context['username']}")
            if user_context.get("language"):
                context_info.append(f"Предпочитаемый язык: {user_context['language']}")
            
            if context_info:
                prompt += f"\n\nКонтекст пользователя:\n" + "\n".join(context_info)
        
        return prompt
    
    def _fallback_response(self, user_message: str) -> str:
        """Fallback response when no AI provider is available"""
        msg_lower = user_message.lower()
        
        if any(w in msg_lower for w in ["привет", "hello", "hi", "здравствуй"]):
            return "👋 Привет! Я Smart Campus Assistant. К сожалению, AI-модуль сейчас недоступен, но я могу помочь с базовыми командами. Напиши /help для списка команд."
        
        if any(w in msg_lower for w in ["расписание", "schedule", "сегодня", "today"]):
            return "📅 Для просмотра расписания используй команду /today или /week. [SCHEDULE_TODAY]"
        
        if any(w in msg_lower for w in ["помощь", "help", "команд"]):
            return """🤖 Доступные команды:
• /today - расписание на сегодня
• /tomorrow - расписание на завтра
• /week - расписание на неделю
• /next - следующая пара
• /setgroup - установить группу
• /freerooms - свободные аудитории"""
        
        return "🤔 AI-модуль временно недоступен. Используй /help для списка команд."


# Singleton instance
ai_manager = AIManager()
