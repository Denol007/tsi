"""
Smart Campus Web App - Flask server for Telegram Mini App
"""

import os
import json
import hmac
import hashlib
import logging
import time
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
from app.core.calendar_service import CalendarService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static')
CORS(app)

# Services
db = Database()
credentials = CredentialManager()

# Timezone
TIMEZONE = ZoneInfo(os.getenv('TIMEZONE', 'Europe/Riga'))

# ============== Schedule Cache ==============
# Simple in-memory cache: {user_id: {'events': [...], 'timestamp': time, 'group': group}}
SCHEDULE_CACHE = {}
CACHE_TTL = 300  # 5 minutes in seconds

def get_cached_schedule(user_id: int, group_code: str):
    """Get schedule from cache if valid"""
    cache_entry = SCHEDULE_CACHE.get(user_id)
    if cache_entry:
        # Check if cache is still valid and group matches
        age = time.time() - cache_entry['timestamp']
        if age < CACHE_TTL and cache_entry.get('group') == group_code:
            logger.info(f"Cache hit for user {user_id} (age: {age:.0f}s)")
            return cache_entry['events']
    return None

def set_cached_schedule(user_id: int, group_code: str, events: list):
    """Save schedule to cache"""
    SCHEDULE_CACHE[user_id] = {
        'events': events,
        'timestamp': time.time(),
        'group': group_code
    }
    logger.info(f"Cached {len(events)} events for user {user_id}")

def clear_user_cache(user_id: int):
    """Clear cache for specific user"""
    if user_id in SCHEDULE_CACHE:
        del SCHEDULE_CACHE[user_id]
# ============================================

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
        return jsonify({'error': 'Not logged in', 'schedule': []}), 401
    
    try:
        # Get user's group
        db_user = db.get_user(telegram_id)
        group_code = db_user.get('group_code') if db_user else None
        
        if not group_code:
            return jsonify({'schedule': [], 'message': 'Установи группу: /setgroup'})
        
        # Calculate date range
        now = datetime.now(TIMEZONE)
        
        if period == 'today':
            target_date = now.date()
        elif period == 'tomorrow':
            target_date = (now + timedelta(days=1)).date()
        elif period == 'week':
            target_date = None  # Will get all events
        else:
            target_date = now.date()
        
        # Try to get from cache first
        events = get_cached_schedule(telegram_id, group_code)
        
        if events is None:
            # Cache miss - fetch from TSI
            logger.info(f"Cache miss for user {telegram_id}, fetching from TSI...")
            calendar_service = CalendarService()
            
            try:
                if not calendar_service.login(creds['username'], creds['password']):
                    return jsonify({'schedule': [], 'message': 'Ошибка входа в TSI'})
                
                # Fetch events for the group
                events = calendar_service.fetch_events(group=group_code)
                calendar_service.close()
                
                # Save to cache
                if events:
                    set_cached_schedule(telegram_id, group_code, events)
                    
            except Exception as e:
                logger.error(f"CalendarService error: {e}")
                return jsonify({'schedule': [], 'message': 'Не удалось загрузить расписание'})
        
        if not events:
            return jsonify({'schedule': []})
        
        # Filter events by date
        if period == 'week':
            start_date_str = now.date().strftime('%Y-%m-%d')
            end_date_str = (now + timedelta(days=7)).date().strftime('%Y-%m-%d')
            filtered_events = [
                e for e in events 
                if start_date_str <= e.get('date', '') <= end_date_str
            ]
        else:
            target_date_str = target_date.strftime('%Y-%m-%d')
            filtered_events = [
                e for e in events 
                if e.get('date') == target_date_str
            ]
        
        # Format events
        schedule = []
        for event in filtered_events:
            start_time = event.get('start_time', '')
            end_time = event.get('end_time', '')
            event_date = event.get('date', '')
            
            # Check if current lesson
            is_current = False
            if period == 'today' and start_time and end_time:
                try:
                    now_time = now.strftime('%H:%M')
                    is_current = start_time <= now_time <= end_time
                except:
                    pass
            
            # Format date for week view
            display_date = None
            if period == 'week' and event_date:
                try:
                    display_date = datetime.strptime(event_date, '%Y-%m-%d').strftime('%d.%m')
                except:
                    display_date = event_date
            
            schedule.append({
                'subject': event.get('title', event.get('name', 'Без названия')),
                'teacher': event.get('lecturer', ''),
                'room': event.get('room', ''),
                'start_time': start_time,
                'end_time': end_time,
                'date': display_date,
                'is_current': is_current
            })
        
        # Sort by date and time
        schedule.sort(key=lambda x: (x.get('date') or '', x['start_time']))
        
        return jsonify({'schedule': schedule})
        
    except Exception as e:
        logger.error(f"Schedule error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'schedule': []}), 500

@app.route('/api/schedule/refresh', methods=['POST'])
@require_auth
def refresh_schedule():
    """Force refresh schedule cache"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Clear user's cache
    clear_user_cache(telegram_id)
    logger.info(f"Cache cleared for user {telegram_id}")
    
    return jsonify({'success': True, 'message': 'Кэш очищен'})

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

# ==================== Auth & Settings ====================

@app.route('/api/login', methods=['POST'])
@require_auth
def login_tsi():
    """Login to TSI account"""
    user = request.telegram_user
    telegram_id = user['id']
    
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Введи логин и пароль'}), 400
    
    # Try to login to TSI
    try:
        calendar_service = CalendarService()
        if not calendar_service.login(username, password):
            calendar_service.close()
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'}), 401
        calendar_service.close()
        
        # Save credentials
        credentials.save_credentials(telegram_id, username, password)
        
        # Clear schedule cache
        clear_user_cache(telegram_id)
        
        logger.info(f"User {telegram_id} logged in as {username}")
        return jsonify({'success': True, 'username': username})
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'error': 'Ошибка подключения к TSI'}), 500

@app.route('/api/logout', methods=['POST'])
@require_auth
def logout_tsi():
    """Logout from TSI account"""
    user = request.telegram_user
    telegram_id = user['id']
    
    credentials.delete_credentials(telegram_id)
    clear_user_cache(telegram_id)
    
    logger.info(f"User {telegram_id} logged out")
    return jsonify({'success': True})

@app.route('/api/groups')
@require_auth
def get_groups():
    """Get list of available groups"""
    # Common TSI groups
    groups = [
        {'code': '3401BDA', 'name': '3401BDA - Datorzinātnes (1. kurss)'},
        {'code': '3401BDB', 'name': '3401BDB - Datorzinātnes (1. kurss)'},
        {'code': '3402BDA', 'name': '3402BDA - Datorzinātnes (2. kurss)'},
        {'code': '3402BDB', 'name': '3402BDB - Datorzinātnes (2. kurss)'},
        {'code': '3403BDA', 'name': '3403BDA - Datorzinātnes (3. kurss)'},
        {'code': '3403BDB', 'name': '3403BDB - Datorzinātnes (3. kurss)'},
        {'code': '3401BNA', 'name': '3401BNA - IT (1. kurss)'},
        {'code': '3401BNB', 'name': '3401BNB - IT (1. kurss)'},
        {'code': '3402BNA', 'name': '3402BNA - IT (2. kurss)'},
        {'code': '3402BNB', 'name': '3402BNB - IT (2. kurss)'},
        {'code': '3403BNA', 'name': '3403BNA - IT (3. kurss)'},
        {'code': '3403BNB', 'name': '3403BNB - IT (3. kurss)'},
        {'code': '3401BEA', 'name': '3401BEA - Электроника (1. kurss)'},
        {'code': '3402BEA', 'name': '3402BEA - Электроника (2. kurss)'},
        {'code': '3403BEA', 'name': '3403BEA - Электроника (3. kurss)'},
    ]
    return jsonify({'groups': groups})

@app.route('/api/group', methods=['POST'])
@require_auth
def set_group():
    """Set user's group"""
    user = request.telegram_user
    telegram_id = user['id']
    
    data = request.get_json() or {}
    group_code = data.get('group_code', '').strip().upper()
    
    if not group_code:
        return jsonify({'success': False, 'error': 'Выбери группу'}), 400
    
    # Update or create user
    db_user = db.get_user(telegram_id)
    if db_user:
        db.update_user(telegram_id, group_code=group_code)
    else:
        db.create_user(telegram_id, group_code=group_code)
    
    # Clear cache because group changed
    clear_user_cache(telegram_id)
    
    logger.info(f"User {telegram_id} set group to {group_code}")
    return jsonify({'success': True, 'group_code': group_code})

# ==================== Notes CRUD ====================

@app.route('/api/notes', methods=['POST'])
@require_auth
def create_note():
    """Create a new note"""
    user = request.telegram_user
    telegram_id = user['id']
    
    data = request.get_json() or {}
    content = data.get('content', '').strip()
    title = data.get('title', '').strip() or None
    
    if not content:
        return jsonify({'success': False, 'error': 'Введи текст заметки'}), 400
    
    note_id = db.add_note(telegram_id, content, title=title)
    
    logger.info(f"User {telegram_id} created note {note_id}")
    return jsonify({'success': True, 'id': note_id})

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
@require_auth
def delete_note(note_id):
    """Delete a note"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Verify ownership and delete
    notes = db.get_notes(telegram_id)
    if not any(n['id'] == note_id for n in notes):
        return jsonify({'success': False, 'error': 'Заметка не найдена'}), 404
    
    db.delete_note(note_id)
    
    logger.info(f"User {telegram_id} deleted note {note_id}")
    return jsonify({'success': True})

# ==================== Reminders CRUD ====================

@app.route('/api/reminders', methods=['POST'])
@require_auth
def create_reminder():
    """Create a new reminder"""
    user = request.telegram_user
    telegram_id = user['id']
    
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    remind_at = data.get('remind_at', '').strip()  # Format: "YYYY-MM-DD HH:MM"
    
    if not text:
        return jsonify({'success': False, 'error': 'Введи текст напоминания'}), 400
    
    if not remind_at:
        return jsonify({'success': False, 'error': 'Выбери дату и время'}), 400
    
    try:
        # Parse datetime
        remind_datetime = datetime.strptime(remind_at, '%Y-%m-%dT%H:%M')
        remind_datetime = remind_datetime.replace(tzinfo=TIMEZONE)
        
        # Check if in future
        if remind_datetime <= datetime.now(TIMEZONE):
            return jsonify({'success': False, 'error': 'Выбери время в будущем'}), 400
        
        reminder_id = db.add_reminder(telegram_id, text, remind_datetime)
        
        logger.info(f"User {telegram_id} created reminder {reminder_id}")
        return jsonify({'success': True, 'id': reminder_id})
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Неверный формат даты'}), 400

@app.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
@require_auth
def delete_reminder(reminder_id):
    """Delete a reminder"""
    user = request.telegram_user
    telegram_id = user['id']
    
    # Verify ownership and delete
    reminders = db.get_user_reminders(telegram_id, include_sent=True)
    if not any(r['id'] == reminder_id for r in reminders):
        return jsonify({'success': False, 'error': 'Напоминание не найдено'}), 404
    
    db.delete_reminder(reminder_id)
    
    logger.info(f"User {telegram_id} deleted reminder {reminder_id}")
    return jsonify({'success': True})

# ==================== Main ====================

def create_app():
    """Create Flask app"""
    return app

if __name__ == '__main__':
    port = int(os.getenv('WEB_PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
