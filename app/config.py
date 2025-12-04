#!/usr/bin/env python3
"""
Smart Campus Assistant - Configuration
Environment-based configuration management
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class TSIConfig:
    """TSI API Configuration"""
    username: str = field(default_factory=lambda: os.getenv("TSI_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("TSI_PASSWORD", ""))
    base_url: str = "https://mob-back.tsi.lv"
    
    @property
    def login_page(self) -> str:
        return f"{self.base_url}/login"
    
    @property
    def auth_url(self) -> str:
        return f"{self.base_url}/authenticate"
    
    @property
    def calendar_url(self) -> str:
        return f"{self.base_url}/calendar"


@dataclass
class TelegramConfig:
    """Telegram Bot Configuration"""
    token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    admin_ids: list = field(default_factory=lambda: [
        int(id) for id in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if id
    ])


@dataclass
class DatabaseConfig:
    """Database Configuration"""
    path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "smart_campus.db"))
    

@dataclass
class WebConfig:
    """Web API Configuration"""
    host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    cors_origins: list = field(default_factory=lambda: os.getenv("CORS_ORIGINS", "*").split(","))


@dataclass
class GoogleCalendarConfig:
    """Google Calendar Configuration"""
    calendar_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CALENDAR_ID", ""))
    credentials_file: str = field(default_factory=lambda: os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    token_file: str = field(default_factory=lambda: os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Europe/Riga"))
    location: str = "Transport and Telecommunication Institute, Lauvas iela 2, Riga, LV-1019, Latvia"


@dataclass
class AppConfig:
    """Main Application Configuration"""
    tsi: TSIConfig = field(default_factory=TSIConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    web: WebConfig = field(default_factory=WebConfig)
    google_calendar: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)
    
    # App settings
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    
    def validate(self) -> bool:
        """Validate required configuration"""
        errors = []
        
        if not self.tsi.username:
            errors.append("TSI_USERNAME is required")
        if not self.tsi.password:
            errors.append("TSI_PASSWORD is required")
        if not self.telegram.token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True


# Global config instance
config = AppConfig()


# Legacy compatibility with original config.py format
USERNAME = config.tsi.username
PASSWORD = config.tsi.password

FILTERS = {
    "room": "reset_room",
    "lecturer": "reset_lecturer",
    "group": "reset_group",
    "type": "reset_type"
}

DATE_RANGE = {
    "from_year": 2025,
    "from_month": 1,
    "to_year": 2025,
    "to_month": 12
}

DISPLAY = {
    "sort_by": "date",
    "show_canceled": True
}

OUTPUT = {
    "formats": ["table", "json", "ics"],
    "json_file": "calendar_events.json",
    "ics_file": "calendar_events.ics"
}

GOOGLE_CALENDAR = {
    "calendar_id": config.google_calendar.calendar_id,
    "credentials_file": config.google_calendar.credentials_file,
    "token_file": config.google_calendar.token_file,
    "timezone": config.google_calendar.timezone,
    "location": config.google_calendar.location
}

BASE_URL = config.tsi.base_url
LOGIN_PAGE = config.tsi.login_page
AUTH_URL = config.tsi.auth_url
CALENDAR_URL = config.tsi.calendar_url
