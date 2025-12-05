#!/usr/bin/env python3
"""Test script to see TSI event format"""
import os
import json
from dotenv import load_dotenv
load_dotenv()

from app.core.calendar_service import CalendarService

# You need to provide credentials
username = input("Enter TSI username (e.g. st83486): ").strip()
password = input("Enter TSI password: ").strip()

print("\nConnecting to TSI...")
service = CalendarService()

if service.login(username, password):
    print("✅ Login successful!")
    
    group = input("Enter group code (e.g. 3301BDA): ").strip().upper()
    
    print(f"\nFetching events for {group}...")
    events = service.fetch_events(group=group, use_cache=False)
    
    print(f"\nFound {len(events)} events")
    print("\n" + "="*60)
    print("FIRST 5 EVENTS (all fields):")
    print("="*60)
    
    for i, event in enumerate(events[:5]):
        print(f"\n--- Event {i+1} ---")
        for key, value in sorted(event.items()):
            print(f"  {key}: {repr(value)}")
    
    # Look for any cancelled ones
    print("\n" + "="*60)
    print("SEARCHING FOR CANCELLED INDICATORS...")
    print("="*60)
    
    for event in events:
        title = str(event.get('title', '')).lower()
        status = str(event.get('status', '')).lower()
        
        # Check for any cancellation indicators
        indicators = ['cancel', 'отмен', 'cancelled', 'canceled']
        
        for ind in indicators:
            if ind in title or ind in status:
                print(f"\nFOUND POSSIBLE CANCELLED: {event.get('title')}")
                for key, value in sorted(event.items()):
                    print(f"  {key}: {repr(value)}")
                break
        
        # Also check for any unusual fields
        for key in event.keys():
            if key not in ['date', 'start_time', 'end_time', 'title', 'lecturer', 'room', 'group', 'is_cancelled', 'type']:
                val = event.get(key)
                if val:
                    print(f"  Unusual field found: {key} = {repr(val)}")
    
    print("\nDone!")
else:
    print("❌ Login failed")
