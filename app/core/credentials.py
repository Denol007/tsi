#!/usr/bin/env python3
"""
Secure Credential Manager
Encrypts and stores user credentials safely
"""

import os
import base64
import hashlib
import secrets
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """Get persistent data directory for Railway volume or local"""
    railway_data = Path("/app/data")
    if railway_data.exists() and os.access(railway_data, os.W_OK):
        return railway_data
    return Path.cwd()


class CredentialManager:
    """
    Secure credential storage with encryption
    Uses Fernet symmetric encryption with PBKDF2 key derivation
    """
    
    def __init__(self, db_path: str = None, master_key: str = None):
        """
        Initialize credential manager
        
        Args:
            db_path: Path to SQLite database
            master_key: Master encryption key (generated if not provided)
        """
        if db_path is None:
            db_path = str(get_data_dir() / "smart_campus.db")
        self.db_path = db_path
        logger.info(f"🔐 Credentials DB path: {self.db_path}")
        self._master_key = master_key or os.getenv("ENCRYPTION_KEY") or self._generate_master_key()
        self._fernet = self._create_fernet()
        self._init_database()
    
    def _generate_master_key(self) -> str:
        """Generate a new master key"""
        key = secrets.token_urlsafe(32)
        logger.warning(
            f"Generated new encryption key. Add this to .env:\n"
            f"ENCRYPTION_KEY={key}"
        )
        return key
    
    def _create_fernet(self) -> Fernet:
        """Create Fernet cipher from master key"""
        # Derive a proper key using PBKDF2
        salt = b"smart_campus_salt_v1"  # Static salt (could be made configurable)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._master_key.encode()))
        return Fernet(key)
    
    def _init_database(self):
        """Initialize credentials table"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Encrypted credentials table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    encrypted_username BLOB,
                    encrypted_password BLOB,
                    is_verified BOOLEAN DEFAULT 0,
                    last_login TIMESTAMP,
                    login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Session tokens table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE,
                    cookies_encrypted BLOB,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES user_credentials(telegram_id)
                )
            """)
            
            conn.commit()
            logger.info("Credentials database initialized")
    
    def encrypt(self, data: str) -> bytes:
        """Encrypt a string"""
        return self._fernet.encrypt(data.encode())
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt data"""
        return self._fernet.decrypt(encrypted_data).decode()
    
    def store_credentials(
        self,
        telegram_id: int,
        username: str,
        password: str
    ) -> bool:
        """
        Store encrypted credentials for a user
        
        Args:
            telegram_id: Telegram user ID
            username: TSI username (e.g., st12345)
            password: TSI password
            
        Returns:
            True if stored successfully
        """
        try:
            encrypted_username = self.encrypt(username)
            encrypted_password = self.encrypt(password)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_credentials 
                    (telegram_id, encrypted_username, encrypted_password, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        encrypted_username = excluded.encrypted_username,
                        encrypted_password = excluded.encrypted_password,
                        updated_at = excluded.updated_at,
                        is_verified = 0
                """, (telegram_id, encrypted_username, encrypted_password, datetime.now()))
                conn.commit()
            
            logger.info(f"Credentials stored for user {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            return False
    
    def get_credentials(self, telegram_id: int) -> Optional[Dict[str, str]]:
        """
        Get decrypted credentials for a user
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            Dict with 'username' and 'password' or None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT encrypted_username, encrypted_password, is_verified, locked_until
                    FROM user_credentials
                    WHERE telegram_id = ?
                """, (telegram_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                encrypted_username, encrypted_password, is_verified, locked_until = row
                
                # Check if account is locked
                if locked_until:
                    lock_time = datetime.fromisoformat(locked_until)
                    if datetime.now() < lock_time:
                        logger.warning(f"Account {telegram_id} is locked until {locked_until}")
                        return None
                
                return {
                    "username": self.decrypt(encrypted_username),
                    "password": self.decrypt(encrypted_password),
                    "is_verified": bool(is_verified)
                }
                
        except Exception as e:
            logger.error(f"Error getting credentials: {e}")
            return None
    
    def verify_credentials(self, telegram_id: int, verified: bool = True) -> bool:
        """Mark credentials as verified after successful login"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_credentials
                    SET is_verified = ?, last_login = ?, login_attempts = 0, updated_at = ?
                    WHERE telegram_id = ?
                """, (verified, datetime.now(), datetime.now(), telegram_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error verifying credentials: {e}")
            return False
    
    def record_failed_login(self, telegram_id: int, max_attempts: int = 5) -> bool:
        """
        Record a failed login attempt
        
        Returns:
            True if account is now locked
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get current attempts
                cursor.execute("""
                    SELECT login_attempts FROM user_credentials
                    WHERE telegram_id = ?
                """, (telegram_id,))
                
                row = cursor.fetchone()
                if not row:
                    return False
                
                attempts = row[0] + 1
                locked_until = None
                
                if attempts >= max_attempts:
                    # Lock for 15 minutes
                    from datetime import timedelta
                    locked_until = datetime.now() + timedelta(minutes=15)
                    logger.warning(f"Account {telegram_id} locked until {locked_until}")
                
                cursor.execute("""
                    UPDATE user_credentials
                    SET login_attempts = ?, locked_until = ?, updated_at = ?
                    WHERE telegram_id = ?
                """, (attempts, locked_until, datetime.now(), telegram_id))
                conn.commit()
                
                return attempts >= max_attempts
                
        except Exception as e:
            logger.error(f"Error recording failed login: {e}")
            return False
    
    def delete_credentials(self, telegram_id: int) -> bool:
        """Delete user credentials"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_credentials WHERE telegram_id = ?
                """, (telegram_id,))
                cursor.execute("""
                    DELETE FROM user_sessions WHERE telegram_id = ?
                """, (telegram_id,))
                conn.commit()
            
            logger.info(f"Credentials deleted for user {telegram_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials: {e}")
            return False
    
    def has_credentials(self, telegram_id: int) -> bool:
        """Check if user has stored credentials"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM user_credentials WHERE telegram_id = ?
                """, (telegram_id,))
                return cursor.fetchone() is not None
        except:
            return False
    
    def store_session(
        self,
        telegram_id: int,
        session_token: str,
        cookies: Dict[str, str],
        expires_hours: int = 24
    ) -> bool:
        """Store encrypted session for reuse"""
        try:
            from datetime import timedelta
            
            encrypted_cookies = self.encrypt(str(cookies))
            expires_at = datetime.now() + timedelta(hours=expires_hours)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete old sessions
                cursor.execute("""
                    DELETE FROM user_sessions WHERE telegram_id = ?
                """, (telegram_id,))
                
                # Insert new session
                cursor.execute("""
                    INSERT INTO user_sessions 
                    (telegram_id, session_token, cookies_encrypted, expires_at)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, session_token, encrypted_cookies, expires_at))
                conn.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error storing session: {e}")
            return False
    
    def get_session(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get valid session if exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT session_token, cookies_encrypted, expires_at
                    FROM user_sessions
                    WHERE telegram_id = ? AND expires_at > ?
                """, (telegram_id, datetime.now()))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                token, encrypted_cookies, expires = row
                cookies = eval(self.decrypt(encrypted_cookies))  # Safe since we encrypted it
                
                return {
                    "token": token,
                    "cookies": cookies,
                    "expires_at": expires
                }
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None


# Singleton instance
credential_manager = CredentialManager()
