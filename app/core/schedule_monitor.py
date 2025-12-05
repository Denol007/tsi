#!/usr/bin/env python3
"""
Schedule Monitor - Monitors schedule changes and sends notifications
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScheduleSnapshot:
    """Snapshot of schedule state for a group"""
    group_code: str
    events_hash: str
    events: List[Dict]
    timestamp: datetime = field(default_factory=datetime.now)
    cancelled_ids: Set[str] = field(default_factory=set)


class ScheduleMonitor:
    """
    Monitors schedule changes and detects cancelled classes.
    Runs periodically to check for updates.
    """
    
    def __init__(self, db, credentials_manager, bot=None):
        self.db = db
        self.credentials = credentials_manager
        self.bot = bot  # Telegram bot for sending notifications
        self._snapshots: Dict[str, ScheduleSnapshot] = {}
        self._running = False
        self._check_interval = 300  # 5 minutes
    
    def _generate_event_id(self, event: Dict) -> str:
        """Generate unique ID for an event"""
        key_parts = [
            event.get('date', ''),
            event.get('start_time', ''),
            event.get('end_time', ''),
            event.get('title', ''),
            event.get('group', ''),
        ]
        key = '|'.join(str(p) for p in key_parts)
        return hashlib.md5(key.encode()).hexdigest()[:16]
    
    def _hash_events(self, events: List[Dict]) -> str:
        """Generate hash of events for comparison"""
        # Sort events for consistent hashing
        sorted_events = sorted(events, key=lambda e: (e.get('date', ''), e.get('start_time', '')))
        events_str = json.dumps(sorted_events, sort_keys=True, default=str)
        return hashlib.md5(events_str.encode()).hexdigest()
    
    def check_for_changes(
        self, 
        group_code: str, 
        current_events: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Check for schedule changes compared to previous snapshot.
        
        Returns dict with:
        - 'newly_cancelled': Events that were just cancelled
        - 'new_events': Events that were added
        - 'removed_events': Events that were removed (not cancelled, just gone)
        """
        changes = {
            'newly_cancelled': [],
            'new_events': [],
            'removed_events': [],
            'changed': False
        }
        
        # Generate current event IDs and cancelled set
        current_ids = {}
        current_cancelled = set()
        
        for event in current_events:
            event_id = self._generate_event_id(event)
            current_ids[event_id] = event
            if event.get('is_cancelled', False):
                current_cancelled.add(event_id)
        
        # Get previous snapshot
        prev_snapshot = self._snapshots.get(group_code)
        
        if prev_snapshot is None:
            # First time seeing this group - save snapshot
            self._snapshots[group_code] = ScheduleSnapshot(
                group_code=group_code,
                events_hash=self._hash_events(current_events),
                events=current_events,
                cancelled_ids=current_cancelled
            )
            return changes
        
        # Check for newly cancelled events
        for event_id in current_cancelled:
            if event_id not in prev_snapshot.cancelled_ids:
                event = current_ids.get(event_id)
                if event:
                    changes['newly_cancelled'].append(event)
                    changes['changed'] = True
        
        # Check for new events
        prev_ids = {self._generate_event_id(e) for e in prev_snapshot.events}
        for event_id, event in current_ids.items():
            if event_id not in prev_ids:
                changes['new_events'].append(event)
                changes['changed'] = True
        
        # Check for removed events
        for event_id in prev_ids:
            if event_id not in current_ids:
                # Find the event in prev snapshot
                for prev_event in prev_snapshot.events:
                    if self._generate_event_id(prev_event) == event_id:
                        changes['removed_events'].append(prev_event)
                        changes['changed'] = True
                        break
        
        # Update snapshot
        self._snapshots[group_code] = ScheduleSnapshot(
            group_code=group_code,
            events_hash=self._hash_events(current_events),
            events=current_events,
            cancelled_ids=current_cancelled
        )
        
        return changes
    
    async def notify_users(self, group_code: str, changes: Dict[str, List[Dict]]):
        """Send notifications to users about schedule changes"""
        if not self.bot:
            logger.warning("Bot not set, cannot send notifications")
            return
        
        # Get all users with this group
        users = self.db.get_users_by_group(group_code)
        
        if not users:
            logger.info(f"No users with group {group_code} to notify")
            return
        
        # Prepare notification messages
        for event in changes.get('newly_cancelled', []):
            date_str = event.get('date', '')
            time_str = f"{event.get('start_time', '')} - {event.get('end_time', '')}"
            subject = event.get('title', 'Занятие')
            teacher = event.get('lecturer', '')
            room = event.get('room', '')
            
            message = (
                f"❌ **Пара отменена!**\n\n"
                f"📅 {date_str}\n"
                f"🕐 {time_str}\n"
                f"📚 {subject}\n"
            )
            if teacher:
                message += f"👨‍🏫 {teacher}\n"
            if room:
                message += f"📍 {room}\n"
            
            message += f"\n👥 Группа: {group_code}"
            
            # Send to all users
            for user in users:
                telegram_id = user.get('telegram_id')
                notifications_enabled = user.get('notifications_enabled', True)
                
                if telegram_id and notifications_enabled:
                    try:
                        await self.bot.send_message(
                            chat_id=telegram_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        logger.info(f"Sent cancellation notification to {telegram_id}")
                    except Exception as e:
                        logger.error(f"Failed to send notification to {telegram_id}: {e}")
    
    async def check_group(self, group_code: str, calendar_service) -> Dict:
        """Check a specific group for schedule changes"""
        try:
            # Fetch current events
            today = datetime.now()
            events = calendar_service.fetch_events(
                group=group_code,
                from_date=today,
                to_date=today + timedelta(days=7),
                use_cache=False  # Always fetch fresh data for monitoring
            )
            
            # Check for changes
            changes = self.check_for_changes(group_code, events)
            
            if changes['changed']:
                logger.info(f"Schedule changes detected for {group_code}: "
                          f"{len(changes['newly_cancelled'])} cancelled, "
                          f"{len(changes['new_events'])} new, "
                          f"{len(changes['removed_events'])} removed")
                
                # Send notifications
                await self.notify_users(group_code, changes)
            
            return changes
            
        except Exception as e:
            logger.error(f"Error checking group {group_code}: {e}")
            return {'error': str(e)}
    
    def get_monitored_groups(self) -> List[str]:
        """Get list of groups to monitor based on registered users"""
        users = self.db.get_all_users()
        groups = set()
        
        for user in users:
            group = user.get('group_code')
            if group:
                groups.add(group)
        
        return list(groups)
    
    async def run_check_cycle(self, calendar_service):
        """Run one check cycle for all monitored groups"""
        groups = self.get_monitored_groups()
        logger.info(f"Checking {len(groups)} groups for schedule changes")
        
        for group in groups:
            await self.check_group(group, calendar_service)
            # Small delay between groups to avoid rate limiting
            await asyncio.sleep(1)
    
    async def start_monitoring(self, calendar_service):
        """Start the monitoring loop"""
        self._running = True
        logger.info("Schedule monitoring started")
        
        while self._running:
            try:
                await self.run_check_cycle(calendar_service)
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self._running = False
        logger.info("Schedule monitoring stopped")
