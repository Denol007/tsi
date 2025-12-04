"""
Smart Campus Web App - Flask server for Telegram Mini App
"""

import os
import json
import hmac
import hashlib
import re
import requests
from bs4 import BeautifulSoup
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

# TSI URLs
TSI_BASE_URL = "https://mob-back.tsi.lv"
TSI_LOGIN_PAGE = f"{TSI_BASE_URL}/login"
TSI_AUTH_URL = f"{TSI_BASE_URL}/login"
TSI_CALENDAR_URL = f"{TSI_BASE_URL}/calendar"


def fetch_tsi_schedule(username: str, password: str, group_code: str, start_date, end_date):
    """Fetch schedule directly from TSI"""
    session = requests.Session()
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"
    })
    
    try:
        # Get login page and CSRF token
        resp = session.get(TSI_LOGIN_PAGE)
        soup = BeautifulSoup(resp.text, "html.parser")
        token_input = soup.find("input", attrs={"name": "_token"})
        
        if not token_input or not token_input.get("value"):
            return []
        
        csrf_token = token_input["value"]
        
        # Login
        login_data = {
            "_token": (None, csrf_token),
            "username": (None, username),
            "password": (None, password),
        }
        
        resp = session.post(TSI_AUTH_URL, files=login_data, allow_redirects=True)
        
        if "logout" not in resp.text.lower():
            return []
        
        # Fetch calendar for the month
        all_events = []
        current = datetime(start_date.year, start_date.month, 1)
        end = datetime(end_date.year, end_date.month, 1)
        
        while current <= end:
            params = {
                "view": "month",
                "date": current.strftime("%Y-%m-01"),
                "group": group_code,
                "year": current.year,
                "month": current.month
            }
            
            resp = session.get(TSI_CALENDAR_URL, params=params)
            
            # Parse events from HTML
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup.find_all("script"):
                if script.string and "const events" in script.string:
                    match = re.search(r'const events = (\{[^;]+\});', script.string, re.DOTALL)
                    if match:
                        try:
                            events_by_date = json.loads(match.group(1))
                            for date_str, date_events in events_by_date.items():
                                for event in date_events:
                                    event['date'] = date_str
                                    all_events.append(event)
                        except:
                            pass
            
            # Next month
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        
        session.close()
        return all_events
        
    except Exception as e:
        print(f"TSI fetch error: {e}")
        return []

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
            start_date = now.date()
            end_date = now.date()
            target_date_str = start_date.strftime('%Y-%m-%d')
        elif period == 'tomorrow':
            start_date = (now + timedelta(days=1)).date()
            end_date = start_date
            target_date_str = start_date.strftime('%Y-%m-%d')
        elif period == 'week':
            start_date = now.date()
            end_date = (now + timedelta(days=7)).date()
            target_date_str = None  # All dates in range
        else:
            start_date = now.date()
            end_date = now.date()
            target_date_str = start_date.strftime('%Y-%m-%d')
        
        # Fetch directly from TSI
        all_events = fetch_tsi_schedule(
            creds['username'], 
            creds['password'], 
            group_code, 
            start_date, 
            end_date
        )
        
        if not all_events:
            return jsonify({'schedule': [], 'message': 'Не удалось загрузить расписание'})
        
        # Filter events for the requested period
        schedule = []
        for event in all_events:
            event_date = event.get('date', '')
            
            # Filter by date
            if target_date_str and event_date != target_date_str:
                continue
            
            # For week - check if in range
            if not target_date_str:
                try:
                    ev_date = datetime.strptime(event_date, '%Y-%m-%d').date()
                    if ev_date < start_date or ev_date > end_date:
                        continue
                except:
                    continue
            
            start_time = event.get('start_time', '')
            end_time = event.get('end_time', '')
            
            # Check if current lesson
            is_current = False
            if period == 'today' and start_time and end_time:
                try:
                    now_time = now.strftime('%H:%M')
                    is_current = start_time <= now_time <= end_time
                except:
                    pass
            
            schedule.append({
                'subject': event.get('title', event.get('name', 'Без названия')),
                'teacher': event.get('lecturer', ''),
                'room': event.get('room', ''),
                'start_time': start_time,
                'end_time': end_time,
                'date': datetime.strptime(event_date, '%Y-%m-%d').strftime('%d.%m') if period == 'week' else None,
                'is_current': is_current
            })
        
        # Sort by time
        schedule.sort(key=lambda x: (x.get('date', ''), x['start_time']))
        
        return jsonify({'schedule': schedule})
        
    except Exception as e:
        print(f"Schedule error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'schedule': []}), 500

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
