#!/usr/bin/env python3
"""
Calendar Service - Enhanced TSI Calendar Integration
Provides unified interface for calendar operations
"""

import requests
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CalendarService:
    """Enhanced TSI Calendar service with caching and smart features"""
    
    BASE_URL = "https://mob-back.tsi.lv"
    LOGIN_PAGE = f"{BASE_URL}/login"
    AUTH_URL = f"{BASE_URL}/authenticate"
    CALENDAR_URL = f"{BASE_URL}/calendar"
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"
        })
        self._events_cache: Dict[str, List[Dict]] = {}
        self._is_authenticated = False
    
    def login(self, username: str = None, password: str = None) -> bool:
        """Authenticate with TSI portal"""
        username = username or self.username
        password = password or self.password
        
        if not username or not password:
            raise ValueError("Username and password are required")
        
        try:
            # Get login page and extract CSRF token
            resp = self.session.get(self.LOGIN_PAGE)
            soup = BeautifulSoup(resp.text, "html.parser")
            token_input = soup.find("input", attrs={"name": "_token"})
            
            if not token_input or not token_input.get("value"):
                raise RuntimeError("Could not find CSRF token")
            
            csrf_token = token_input["value"]
            
            # Login with multipart/form-data
            login_data = {
                "_token": (None, csrf_token),
                "username": (None, username),
                "password": (None, password),
            }
            
            headers = {
                "Referer": self.LOGIN_PAGE,
                "Origin": self.BASE_URL,
            }
            
            resp = self.session.post(self.AUTH_URL, files=login_data, headers=headers, allow_redirects=True)
            
            # Check if login was successful
            if "logout" not in resp.text.lower():
                logger.error("Login failed - check credentials")
                return False
            
            self._is_authenticated = True
            self.username = username
            self.password = password
            logger.info("Login successful")
            return True
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self._is_authenticated
    
    def fetch_events(
        self,
        group: str = None,
        lecturer: str = None,
        room: str = None,
        from_date: datetime = None,
        to_date: datetime = None,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch calendar events with filters
        
        Args:
            group: Filter by group code (e.g., "3401BNA")
            lecturer: Filter by lecturer name
            room: Filter by room number
            from_date: Start date for the period
            to_date: End date for the period
            use_cache: Whether to use cached results
            
        Returns:
            List of event dictionaries
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")
        
        # Default date range: current month to 3 months ahead
        if from_date is None:
            from_date = datetime.now().replace(day=1)
        if to_date is None:
            to_date = from_date + relativedelta(months=3)
        
        # Create cache key
        cache_key = f"{group}_{lecturer}_{room}_{from_date.strftime('%Y%m')}_{to_date.strftime('%Y%m')}"
        
        if use_cache and cache_key in self._events_cache:
            logger.info(f"Using cached events for {cache_key}")
            return self._events_cache[cache_key]
        
        # Fetch events
        all_events = []
        current_date = from_date
        
        while current_date <= to_date:
            events = self._fetch_month(
                year=current_date.year,
                month=current_date.month,
                group=group,
                lecturer=lecturer,
                room=room
            )
            all_events.extend(events)
            current_date = current_date + relativedelta(months=1)
        
        # Cache results
        self._events_cache[cache_key] = all_events
        
        return all_events
    
    def _fetch_month(
        self,
        year: int,
        month: int,
        group: str = None,
        lecturer: str = None,
        room: str = None
    ) -> List[Dict[str, Any]]:
        """Fetch calendar data for a specific month"""
        params = {
            "view": "month",
            "date": f"{year}-{month:02d}-01",
            "room": room or "reset_room",
            "lecturer": lecturer or "reset_lecturer",
            "group": group or "reset_group",
            "type[]": "reset_type",
            "year": year,
            "month": month
        }
        
        try:
            resp = self.session.get(self.CALENDAR_URL, params=params)
            resp.raise_for_status()
            return self._parse_events(resp.text)
        except Exception as e:
            logger.error(f"Error fetching month {year}-{month}: {e}")
            return []
    
    def _parse_events(self, html: str) -> List[Dict[str, Any]]:
        """Parse events from calendar HTML"""
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script")
        
        for script in scripts:
            if script.string and "const events" in script.string:
                match = re.search(r'const events = (\{[^;]+\});', script.string, re.DOTALL)
                if match:
                    try:
                        events_by_date = json.loads(match.group(1))
                        events = []
                        for date, date_events in events_by_date.items():
                            for event in date_events:
                                event['date'] = date
                                # Check for cancelled status
                                # TSI uses 'description' field with value 'canceled'
                                description = event.get('description', '').lower().strip()
                                is_cancelled = (
                                    description in ['canceled', 'cancelled', 'отменено', 'atcelts'] or
                                    'cancel' in description or
                                    'отмен' in description or
                                    event.get('status', '').lower() in ['cancelled', 'canceled', 'отменено'] or
                                    event.get('cancelled', False) == True or
                                    event.get('canceled', False) == True
                                )
                                event['is_cancelled'] = is_cancelled
                                events.append(event)
                        return events
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON parse error: {e}")
        
        return []
    
    def get_today_events(self, group: str = None) -> List[Dict[str, Any]]:
        """Get events for today"""
        today = datetime.now().strftime("%Y-%m-%d")
        events = self.fetch_events(group=group)
        return [e for e in events if e.get('date') == today]
    
    def get_week_events(self, group: str = None) -> List[Dict[str, Any]]:
        """Get events for current week"""
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        events = self.fetch_events(group=group)
        return [
            e for e in events
            if start_of_week.strftime("%Y-%m-%d") <= e.get('date', '') <= end_of_week.strftime("%Y-%m-%d")
        ]
    
    def get_next_event(self, group: str = None) -> Optional[Dict[str, Any]]:
        """Get the next upcoming event"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        
        events = self.fetch_events(group=group)
        future_events = []
        
        for event in events:
            event_date = event.get('date', '')
            event_time = event.get('start_time', '00:00')
            
            if event_date > today or (event_date == today and event_time > current_time):
                future_events.append(event)
        
        # Sort by date and time
        future_events.sort(key=lambda e: (e.get('date', ''), e.get('start_time', '')))
        
        return future_events[0] if future_events else None
    
    def get_events_range(self, start_date: datetime, end_date: datetime, group: str = None) -> List[Dict[str, Any]]:
        """Get events within date range"""
        events = self.fetch_events(group=group)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        result = []
        for e in events:
            event_date = e.get('date', '')
            if start_str <= event_date <= end_str:
                # Convert to datetime objects for the result
                try:
                    date_obj = datetime.strptime(event_date, "%Y-%m-%d")
                    start_time = e.get('start_time', '09:00')
                    end_time = e.get('end_time', '10:30')
                    
                    result.append({
                        'subject': e.get('title', e.get('subject', 'Unknown')),
                        'room': e.get('room', ''),
                        'lecturer': e.get('lecturer', ''),
                        'start': datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M"),
                        'end': datetime.strptime(f"{event_date} {end_time}", "%Y-%m-%d %H:%M"),
                        'date': event_date
                    })
                except Exception:
                    continue
        
        return sorted(result, key=lambda x: x['start'])
    
    def search_events(
        self,
        query: str,
        group: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search events by query string"""
        events = self.fetch_events(group=group)
        query_lower = query.lower()
        
        matching = []
        for event in events:
            searchable = f"{event.get('title', '')} {event.get('lecturer', '')} {event.get('room', '')} {event.get('group', '')}".lower()
            if query_lower in searchable:
                matching.append(event)
        
        return matching[:limit]
    
    def get_free_rooms(self, date: str = None, time: str = None) -> List[str]:
        """Get list of free rooms at specified date/time"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        if time is None:
            time = datetime.now().strftime("%H:%M")
        
        # Get all events for the date
        events = self.fetch_events()
        
        # Find occupied rooms
        occupied_rooms = set()
        for event in events:
            if event.get('date') == date:
                start = event.get('start_time', '00:00')
                end = event.get('end_time', '23:59')
                if start <= time <= end:
                    room = event.get('room')
                    if room:
                        occupied_rooms.add(room)
        
        # Known rooms at TSI (this would ideally come from an API)
        all_rooms = {
            "101", "102", "103", "104", "105",
            "201", "202", "203", "204", "205",
            "221", "222", "223",
            "L1 (125)", "L2 (125)", "L3 (125)", "L4 (125)",
            "L5 (125)", "L6 (125)", "L7 (125)", "L8 (125)"
        }
        
        free_rooms = all_rooms - occupied_rooms
        return sorted(list(free_rooms))
    
    def clear_cache(self):
        """Clear the events cache"""
        self._events_cache.clear()
        logger.info("Cache cleared")
    
    def close(self):
        """Close session"""
        self.session.close()
