"""Core functionality module"""
import os
from pathlib import Path


def get_data_dir() -> Path:
    """
    Get persistent data directory.
    On Railway with volume: /app/data
    Locally: current directory
    """
    # Check if running on Railway with volume mount
    railway_data = Path("/app/data")
    if railway_data.exists() and os.access(railway_data, os.W_OK):
        return railway_data
    
    # Local development - use project root
    return Path.cwd()


def get_db_path(filename: str = "smart_campus.db") -> str:
    """Get full path to database file"""
    return str(get_data_dir() / filename)


from .calendar_service import CalendarService
from .database import Database
