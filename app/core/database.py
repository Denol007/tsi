#!/usr/bin/env python3
"""
Database module for Smart Campus Assistant
Handles user data, preferences, and event caching
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging
import os
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_timezone():
    """Get configured timezone"""
    tz_name = os.getenv('TIMEZONE', 'Europe/Riga')
    try:
        return ZoneInfo(tz_name)
    except:
        return ZoneInfo('Europe/Riga')


def get_data_dir() -> Path:
    """Get persistent data directory for Railway volume or local"""
    railway_data = Path("/app/data")
    
    # Try to create the directory if it doesn't exist
    try:
        railway_data.mkdir(parents=True, exist_ok=True)
        if os.access(railway_data, os.W_OK):
            return railway_data
    except Exception as e:
        logger.warning(f"Cannot use Railway volume: {e}")
    
    return Path.cwd()


class Database:
    """SQLite database for user management and caching"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(get_data_dir() / "smart_campus.db")
        self.db_path = db_path
        logger.info(f"📂 Database path: {self.db_path}")
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    student_id TEXT,
                    group_code TEXT,
                    language TEXT DEFAULT 'en',
                    notifications_enabled BOOLEAN DEFAULT 1,
                    reminder_minutes INTEGER DEFAULT 15,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User preferences table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    preference_key TEXT,
                    preference_value TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, preference_key)
                )
            """)
            
            # Cached events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE,
                    date TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    title TEXT,
                    room TEXT,
                    group_code TEXT,
                    lecturer TEXT,
                    event_type TEXT,
                    description TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Reminders table (with text support)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    telegram_id INTEGER,
                    event_id TEXT,
                    reminder_text TEXT,
                    reminder_time TIMESTAMP,
                    is_sent BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Notes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    title TEXT,
                    content TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User queries log (for AI learning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query TEXT,
                    response TEXT,
                    intent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Feedback table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query_id INTEGER,
                    rating INTEGER,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (query_id) REFERENCES query_log(id)
                )
            """)
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    # User Management
    def create_user(
        self,
        telegram_id: int,
        username: str = None,
        student_id: str = None,
        group_code: str = None
    ) -> int:
        """Create a new user"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (telegram_id, username, student_id, group_code)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, username, student_id, group_code))
            conn.commit()
            
            cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user by Telegram ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_users_by_group(self, group_code: str) -> List[Dict[str, Any]]:
        """Get all users with a specific group code"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE group_code = ?",
                (group_code.upper(),)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_user(self, telegram_id: int, **kwargs) -> bool:
        """Update user data"""
        if not kwargs:
            return False
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [datetime.now(), telegram_id]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE users 
                SET {set_clause}, updated_at = ?
                WHERE telegram_id = ?
            """, values)
            conn.commit()
            return cursor.rowcount > 0
    
    def set_user_preference(self, telegram_id: int, key: str, value: str) -> bool:
        """Set a user preference"""
        user = self.get_user(telegram_id)
        if not user:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences (user_id, preference_key, preference_value)
                VALUES (?, ?, ?)
            """, (user['id'], key, value))
            conn.commit()
            return True
    
    def get_user_preference(self, telegram_id: int, key: str) -> Optional[str]:
        """Get a user preference"""
        user = self.get_user(telegram_id)
        if not user:
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT preference_value FROM user_preferences
                WHERE user_id = ? AND preference_key = ?
            """, (user['id'], key))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_user_preferences(self, telegram_id: int) -> Dict[str, str]:
        """Get all user preferences"""
        user = self.get_user(telegram_id)
        if not user:
            return {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT preference_key, preference_value FROM user_preferences
                WHERE user_id = ?
            """, (user['id'],))
            results = cursor.fetchall()
            return {row[0]: row[1] for row in results}
    
    def delete_user_preference(self, telegram_id: int, key: str) -> bool:
        """Delete a user preference"""
        user = self.get_user(telegram_id)
        if not user:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM user_preferences
                WHERE user_id = ? AND preference_key = ?
            """, (user['id'], key))
            conn.commit()
            return cursor.rowcount > 0
    
    # Event Caching
    def cache_events(self, events: List[Dict[str, Any]]) -> int:
        """Cache a list of events"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cached_count = 0
            
            for event in events:
                event_id = f"{event.get('date')}_{event.get('start_time')}_{event.get('title', '')[:30]}"
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO cached_events 
                        (event_id, date, start_time, end_time, title, room, group_code, lecturer, event_type, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        event_id,
                        event.get('date'),
                        event.get('start_time'),
                        event.get('end_time'),
                        event.get('title'),
                        event.get('room'),
                        event.get('group'),
                        event.get('lecturer'),
                        event.get('type'),
                        event.get('description')
                    ))
                    cached_count += 1
                except Exception as e:
                    logger.warning(f"Error caching event: {e}")
            
            conn.commit()
            logger.info(f"Cached {cached_count} events")
            return cached_count
    
    def get_cached_events(
        self,
        group_code: str = None,
        date: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get cached events with optional filters"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM cached_events WHERE 1=1"
            params = []
            
            if group_code:
                query += " AND group_code LIKE ?"
                params.append(f"%{group_code}%")
            
            if date:
                query += " AND date = ?"
                params.append(date)
            
            query += " ORDER BY date, start_time LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    # Reminders
    def create_reminder(
        self,
        telegram_id: int,
        event_id: str,
        reminder_time: datetime
    ) -> int:
        """Create a reminder for an event"""
        user = self.get_user(telegram_id)
        if not user:
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reminders (user_id, event_id, reminder_time)
                VALUES (?, ?, ?)
            """, (user['id'], event_id, reminder_time))
            conn.commit()
            return cursor.lastrowid
    
    def add_text_reminder(
        self,
        telegram_id: int,
        text: str,
        reminder_time: datetime
    ) -> int:
        """Create a text reminder"""
        user = self.get_user(telegram_id)
        user_id = user['id'] if user else None
        
        # Convert to string for SQLite (remove timezone info for consistent storage)
        if reminder_time.tzinfo:
            reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"Adding reminder for {telegram_id}: '{text}' at {reminder_time_str}")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reminders (user_id, telegram_id, reminder_text, reminder_time)
                VALUES (?, ?, ?, ?)
            """, (user_id, telegram_id, text, reminder_time_str))
            conn.commit()
            return cursor.lastrowid
    
    def get_user_reminders(self, telegram_id: int, include_sent: bool = False) -> List[Dict[str, Any]]:
        """Get all reminders for a user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if include_sent:
                cursor.execute("""
                    SELECT * FROM reminders 
                    WHERE telegram_id = ?
                    ORDER BY reminder_time
                """, (telegram_id,))
            else:
                cursor.execute("""
                    SELECT * FROM reminders 
                    WHERE telegram_id = ? AND is_sent = 0
                    ORDER BY reminder_time
                """, (telegram_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_reminder(self, reminder_id: int, telegram_id: int) -> bool:
        """Delete a reminder"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM reminders WHERE id = ? AND telegram_id = ?
            """, (reminder_id, telegram_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_pending_reminders(self) -> List[Dict[str, Any]]:
        """Get all pending reminders that should be sent"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Use timezone-aware time, but convert to string for SQLite comparison
            now = datetime.now(get_timezone())
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"Checking reminders at {now_str}")
            
            # Use LEFT JOIN and COALESCE to handle both user_id and telegram_id
            cursor.execute("""
                SELECT r.*, 
                       COALESCE(r.telegram_id, u.telegram_id) as tg_id,
                       u.username
                FROM reminders r
                LEFT JOIN users u ON r.user_id = u.id
                WHERE r.is_sent = 0 AND r.reminder_time <= ?
            """, (now_str,))
            
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                # Use tg_id which has the coalesced value
                d['telegram_id'] = d.get('tg_id') or d.get('telegram_id')
                results.append(d)
            
            if results:
                logger.info(f"Found {len(results)} pending reminders")
            
            return results
    
    def mark_reminder_sent(self, reminder_id: int) -> bool:
        """Mark a reminder as sent"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE reminders SET is_sent = 1 WHERE id = ?
            """, (reminder_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # Query Logging
    def log_query(
        self,
        telegram_id: int,
        query: str,
        response: str,
        intent: str = None
    ) -> int:
        """Log a user query for analytics"""
        user = self.get_user(telegram_id)
        if not user:
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO query_log (user_id, query, response, intent)
                VALUES (?, ?, ?, ?)
            """, (user['id'], query, response, intent))
            conn.commit()
            return cursor.lastrowid
    
    def add_feedback(
        self,
        telegram_id: int,
        query_id: int,
        rating: int,
        comment: str = None
    ) -> bool:
        """Add feedback for a query"""
        user = self.get_user(telegram_id)
        if not user:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedback (user_id, query_id, rating, comment)
                VALUES (?, ?, ?, ?)
            """, (user['id'], query_id, rating, comment))
            conn.commit()
            return True
    
    # Statistics
    def get_user_stats(self, telegram_id: int) -> Dict[str, Any]:
        """Get statistics for a user"""
        user = self.get_user(telegram_id)
        if not user:
            return {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total queries
            cursor.execute("""
                SELECT COUNT(*) FROM query_log WHERE user_id = ?
            """, (user['id'],))
            total_queries = cursor.fetchone()[0]
            
            # Average rating
            cursor.execute("""
                SELECT AVG(rating) FROM feedback WHERE user_id = ?
            """, (user['id'],))
            avg_rating = cursor.fetchone()[0]
            
            return {
                "total_queries": total_queries,
                "average_rating": round(avg_rating, 2) if avg_rating else None,
                "member_since": user['created_at']
            }
    
    # Notes
    def add_note(self, telegram_id: int, title: str, content: str, tags: str = None) -> int:
        """Add a note for user"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes (telegram_id, title, content, tags)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, title, content, tags))
            conn.commit()
            return cursor.lastrowid
    
    def get_notes(self, telegram_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all notes for user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notes 
                WHERE telegram_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (telegram_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_note(self, note_id: int, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific note"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notes WHERE id = ? AND telegram_id = ?
            """, (note_id, telegram_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_note(self, note_id: int, telegram_id: int, title: str = None, content: str = None, tags: str = None) -> bool:
        """Update a note"""
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if tags is not None:
            updates.append("tags = ?")
            params.append(tags)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.extend([note_id, telegram_id])
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE notes SET {', '.join(updates)}
                WHERE id = ? AND telegram_id = ?
            """, params)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_note(self, note_id: int, telegram_id: int) -> bool:
        """Delete a note"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM notes WHERE id = ? AND telegram_id = ?
            """, (note_id, telegram_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def search_notes(self, telegram_id: int, query: str) -> List[Dict[str, Any]]:
        """Search notes by title or content"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notes 
                WHERE telegram_id = ? AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)
                ORDER BY updated_at DESC
            """, (telegram_id, f"%{query}%", f"%{query}%", f"%{query}%"))
            return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close any open connections (for cleanup)"""
        pass
