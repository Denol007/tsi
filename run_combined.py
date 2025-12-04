#!/usr/bin/env python3
"""
Combined runner for bot + web app
Runs both in a single process using threading
"""

import os
import sys
import threading
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_webapp():
    """Run Flask web app in a thread"""
    try:
        from webapp.app import app
        port = int(os.getenv('PORT', os.getenv('WEB_PORT', 5000)))
        logger.info(f"Starting Web App on port {port}")
        # Use threaded=False since we're already in a thread
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Web App error: {e}")

def run_bot():
    """Run Telegram bot"""
    try:
        from app.bot.bot_v2 import main
        logger.info("Starting Telegram Bot")
        main()
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    
    if mode == 'bot':
        # Just run bot
        run_bot()
    elif mode == 'web':
        # Just run web
        run_webapp()
    elif mode == 'all':
        # Run both - web in thread, bot in main
        logger.info("Starting combined mode: Bot + WebApp")
        
        # Start web app in background thread
        web_thread = threading.Thread(target=run_webapp, daemon=True)
        web_thread.start()
        
        # Run bot in main thread
        run_bot()
    else:
        print(f"Usage: python run_combined.py [bot|web|all]")
        sys.exit(1)
