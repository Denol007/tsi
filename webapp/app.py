"""
Smart Campus Web App - Flask server for Telegram Mini App
"""

import os
import json
import hmac
import hashlib
from urllib.parse import parse_qsl
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Import from app
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Database
from app.core.credentials import CredentialManager

# Initialize Flask app
app = Flask(__name__, static_folder='static')
CORS(app)

# Services
db = Database()
credentials = CredentialManager()

# Timezone
TIMEZONE = ZoneInfo(os.getenv('TIMEZONE', 'Europe/Riga'))

def get_bot_token():
    """Get bot token from environment"""
    return os.getenv('TELEGRAM_BOT_TOKEN', '')

def validate_telegram_data(init_data: str) -> dict | None:
    """
    Validate Telegram WebApp init data
    Returns user data if valid, None otherwise
    """
    if not init_data:
        return None
    
    try:
        # Parse init data
        parsed = dict(parse_qsl(init_data))
        
        # Get hash
        received_hash = parsed.pop('hash', '')
        if not received_hash:
            return None
        
        # Sort and create data check string
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(parsed.items())
        )
        
        # Create secret key
        bot_token = get_bot_token()
        secret_key = hmac.new(
            b'WebAppData',
            bot_token.encode(),
            hashlib.sha256
        ).digest()
        
        # Calculate hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare hashes
        if not hmac.compare_digest(received_hash, calculated_hash):
            # For development, allow without validation
            if os.getenv('DEBUG', 'false').lower() == 'true':
                if 'user' in parsed:
                    return json.loads(parsed['user'])
            return None
        
        # Return user data
        if 'user' in parsed:
            return json.loads(parsed['user'])
        
        return None
        
    except Exception as e:
        print(f"Validation error: {e}")
        return None

def require_auth(f):
    """Decorator to require Telegram authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        init_data = request.args.get('init_data', '')
        user = validate_telegram_data(init_data)
        
        if not user:
            # For development, try to get user from header
            if os.getenv('DEBUG', 'false').lower() == 'true':
                user_id = request.headers.get('X-User-ID')
                if user_id:
                    user = {'id': int(user_id)}
        
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        request.telegram_user = user
        return f(*args, **kwargs)
    return decorated

# ==================== Static Files ====================

@app.route('/')
def index():
    """Serve main page"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    """Serve static files"""
    return send_from_directory('static', path)

# ==================== API Routes ====================

@app.route('/api/user')
@require_auth
def get_user():
    """Get user info"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Get from database
    db_user = db.get_user(telegram_id)
    
    if not db_user:
        return jsonify({
            'id': telegram_id,
            'is_logged_in': False
        })
    
    return jsonify({
        'id': telegram_id,
        'username': db_user.get('username'),
        'group_code': db_user.get('group_code'),
        'is_logged_in': credentials.has_credentials(telegram_id)
    })

@app.route('/api/schedule/<period>')
@require_auth
def get_schedule(period):
    """Get schedule for period (today, tomorrow, week)"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Check if logged in
    creds = credentials.get_credentials(telegram_id)
    if not creds:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        # Get user's group
        db_user = db.get_user(telegram_id)
        group_code = db_user.get('group_code') if db_user else None
        
        if not group_code:
            return jsonify({'schedule': [], 'message': 'Group not set'})
        
        # Calculate date range
        now = datetime.now(TIMEZONE)
        
        if period == 'today':
            start_date = now.date()
            end_date = now.date()
        elif period == 'tomorrow':
            start_date = (now + timedelta(days=1)).date()
            end_date = start_date
        elif period == 'week':
            start_date = now.date()
            end_date = (now + timedelta(days=7)).date()
        else:
            start_date = now.date()
            end_date = now.date()
        
        # Try to get cached events from database
        cached = db.get_cached_events(telegram_id, start_date, end_date)
        
        if cached:
            lessons = cached
        else:
            # No cache - return empty with message
            return jsonify({
                'schedule': [],
                'message': 'Напиши боту /today чтобы загрузить расписание'
            })
        
        # Format response
        schedule = []
        for lesson in lessons:
            start_time = lesson.get('start')
            end_time = lesson.get('end')
            
            # Parse datetime if string
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                except:
                    pass
            if isinstance(end_time, str):
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                except:
                    pass
            
            # Check if current
            is_current = False
            if isinstance(start_time, datetime) and isinstance(end_time, datetime):
                # Make timezone aware if needed
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=TIMEZONE)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=TIMEZONE)
                is_current = start_time <= now <= end_time
            
            schedule.append({
                'subject': lesson.get('title', lesson.get('summary', 'Без названия')),
                'teacher': lesson.get('teacher', ''),
                'room': lesson.get('room', lesson.get('location', '')),
                'start_time': start_time.strftime('%H:%M') if isinstance(start_time, datetime) else str(start_time),
                'end_time': end_time.strftime('%H:%M') if isinstance(end_time, datetime) else str(end_time),
                'date': start_time.strftime('%d.%m') if isinstance(start_time, datetime) and period == 'week' else None,
                'is_current': is_current
            })
        
        # Sort by time
        schedule.sort(key=lambda x: x['start_time'])
        
        return jsonify({'schedule': schedule})
        
    except Exception as e:
        print(f"Schedule error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes')
@require_auth
def get_notes():
    """Get user's notes"""
    user = request.telegram_user
    telegram_id = user['id']
    
    notes = db.get_notes(telegram_id)
    
    formatted = []
    for note in notes:
        formatted.append({
            'id': note['id'],
            'title': note.get('title', 'Заметка'),
            'content': note['content'][:100] + ('...' if len(note['content']) > 100 else ''),
            'created_at': note.get('created_at', '')
        })
    
    return jsonify({'notes': formatted})

@app.route('/api/reminders')
@require_auth
def get_reminders():
    """Get user's reminders"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Use correct method name
    reminders = db.get_user_reminders(telegram_id, include_sent=False)
    
    formatted = []
    for r in reminders:
        formatted.append({
            'id': r['id'],
            'text': r['text'],
            'remind_at': r.get('remind_at', '')
        })
    
    return jsonify({'reminders': formatted})

# ==================== Main ====================

def create_app():
    """Create Flask app"""
    return app

if __name__ == '__main__':
    port = int(os.getenv('WEB_PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
