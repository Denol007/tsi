#!/usr/bin/env python3
"""
Smart Campus Assistant - Main Entry Point
Run the Telegram bot or Web API server
"""

import sys
import asyncio
import logging
from argparse import ArgumentParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_bot():
    """Run the Telegram bot with login flow and AI"""
    from app.config import config
    from app.bot.bot_v2 import SmartCampusBotV2
    
    if not config.telegram.token:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        logger.info("Please set it in .env file or environment")
        sys.exit(1)
    
    logger.info("Starting Smart Campus Telegram Bot v2...")
    logger.info("Features: In-bot login, AI assistant, encrypted credentials")
    
    bot = SmartCampusBotV2(token=config.telegram.token)
    bot.run()


def run_bot_legacy():
    """Run the original Telegram bot (requires TSI credentials in .env)"""
    from app.config import config
    from app.bot import SmartCampusBot
    
    if not config.telegram.token:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)
    
    logger.info("Starting Smart Campus Telegram Bot (legacy mode)...")
    
    bot = SmartCampusBot(
        token=config.telegram.token,
        tsi_username=config.tsi.username,
        tsi_password=config.tsi.password
    )
    
    bot.run()


def run_web():
    """Run the Web API server"""
    import uvicorn
    from app.config import config
    from app.web.api import create_app
    
    logger.info("Starting Smart Campus Web API...")
    
    app = create_app(
        tsi_username=config.tsi.username,
        tsi_password=config.tsi.password,
        db_path=config.database.path
    )
    
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        reload=config.web.debug
    )


def run_cli():
    """Run the CLI interface (original main.py behavior)"""
    from TSICalendar import TSICalendar, sort_events, filter_events
    from Exporters import TableExporter, JSONExporter, ICSExporter, GoogleCalendarExporter
    import config
    
    print("=" * 80)
    print("Smart Campus Assistant - CLI Mode")
    print("=" * 80)
    
    calendar = TSICalendar()
    
    try:
        # Step 1: Login
        print("\nStep 1: Authenticating...")
        calendar.login()
        
        # Step 2: Fetch calendar data
        print(f"\nStep 2: Fetching calendar data")
        print(f"Date range: {config.DATE_RANGE['from_year']}-{config.DATE_RANGE['from_month']:02d} "
              f"to {config.DATE_RANGE['to_year']}-{config.DATE_RANGE['to_month']:02d}")
        print(f"Filters: Room={config.FILTERS['room']}, Lecturer={config.FILTERS['lecturer']}, "
              f"Group={config.FILTERS['group']}")
        print("-" * 80)
        
        events = calendar.fetch_period(
            config.DATE_RANGE['from_year'],
            config.DATE_RANGE['from_month'],
            config.DATE_RANGE['to_year'],
            config.DATE_RANGE['to_month']
        )
        
        print(f"\nTotal events fetched: {len(events)}")
        
        # Step 3: Filter and sort
        print(f"\nStep 3: Processing events")
        events = filter_events(events)
        events = sort_events(events, config.DISPLAY['sort_by'])
        
        print(f"After filtering: {len(events)} events")
        print(f"Sorting by: {config.DISPLAY['sort_by']}")
        
        if not events:
            print("\nNo events found matching the criteria")
            return
        
        # Step 4: Export to requested formats
        print(f"\nStep 4: Exporting to formats: {', '.join(config.OUTPUT['formats'])}")
        print("-" * 80)
        
        for format_type in config.OUTPUT['formats']:
            format_type = format_type.lower().strip()
            
            if format_type == "table":
                TableExporter.export(events)
            
            elif format_type == "json":
                JSONExporter.export(events)
            
            elif format_type == "ics":
                ICSExporter.export(events)
            
            elif format_type == "google_calendar":
                try:
                    google_exporter = GoogleCalendarExporter()
                    google_exporter.export(events, clear_first=True)
                except ImportError:
                    print("Error: Google Calendar export requires google-auth, google-auth-oauthlib, "
                          "and google-api-python-client packages")
                except Exception as e:
                    print(f"Error exporting to Google Calendar: {e}")
            
            else:
                print(f"Warning: Unknown export format '{format_type}'")
        
        print("\n" + "=" * 80)
        print("Export completed successfully!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        calendar.close()


def main():
    """Main entry point"""
    parser = ArgumentParser(description="Smart Campus Assistant")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["bot", "bot-legacy", "web", "cli", "all"],
        default="bot",
        help="Run mode: bot (Telegram v2 with login), bot-legacy (old style), web (API server), cli, or all"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for web server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    
    args = parser.parse_args()
    
    if args.mode == "bot":
        run_bot()
    elif args.mode == "bot-legacy":
        run_bot_legacy()
    elif args.mode == "web":
        run_web()
    elif args.mode == "cli":
        run_cli()
    elif args.mode == "all":
        # Run both bot and web server (requires asyncio)
        logger.info("Running both Telegram Bot and Web API...")
        logger.warning("Note: 'all' mode is experimental. Consider running separately.")
        
        import threading
        
        # Run web server in a thread
        web_thread = threading.Thread(target=run_web, daemon=True)
        web_thread.start()
        
        # Run bot in main thread
        run_bot()


if __name__ == "__main__":
    main()
