# Smart Campus Assistant 🎓

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot-blue.svg" alt="Telegram">
  <img src="https://img.shields.io/badge/FastAPI-REST%20API-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-Educational-yellow.svg" alt="License">
</p>

An intelligent campus assistant for TSI (Transport and Telecommunication Institute) students. Get your schedule, find free rooms, and receive smart recommendations through Telegram bot or REST API.

> 🔧 Built on top of [TTICalendarV2Python](https://github.com/foxybbb/TTICalendarV2Python)

## ✨ Features

### 📅 Schedule Management
- View daily, weekly, and monthly schedules
- Get next upcoming class
- Search for specific subjects or lecturers
- Export to ICS format

### 🤖 AI Assistant
- Natural language queries in Russian and English
- Intent recognition for smart responses
- Contextual recommendations
- **🔌 Multi-provider AI** - Groq, Gemini, Ollama, OpenAI support

### 🔐 In-Bot Authentication
- Secure TSI login through Telegram bot
- Encrypted credential storage (Fernet + PBKDF2)
- No need to store credentials in .env file

### ⏰ Reminders & Notes
- Set custom reminders with date/time
- Automatic reminder notifications
- Personal notes storage
- Deadline tracking

### 🚪 Campus Services
- Find free rooms in real-time
- Room location information
- Lecturer contacts

### 📊 Additional Features
- Statistics and analytics
- Weather integration (Riga)
- Motivational quotes

### 📱 Multiple Interfaces
- **Telegram Bot** - Chat-based interface
- **REST API** - For custom integrations
- **CLI** - Command-line interface

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/foxybbb/TTICalendarV2Python.git smart_campus_assistant
cd smart_campus_assistant
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` file with your credentials:

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token

# Optional - AI Providers (at least one recommended)
GROQ_API_KEY=your_groq_key      # Free! Get at console.groq.com
GEMINI_API_KEY=your_gemini_key  # Free! Get at aistudio.google.com
```

### 4. Run the application

**Telegram Bot:**
```bash
python run.py bot
```

**Web API:**
```bash
python run.py web
```

**CLI Mode (original behavior):**
```bash
python run.py cli
```

## 📁 Project Structure

```
smart_campus_assistant/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── core/
│   │   ├── __init__.py
│   │   ├── calendar_service.py # TSI calendar integration
│   │   └── database.py         # SQLite database
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── assistant.py        # AI assistant
│   │   └── intent_classifier.py # Intent detection
│   ├── bot/
│   │   ├── __init__.py
│   │   └── bot.py              # Telegram bot
│   └── web/
│       ├── __init__.py
│       └── api.py              # FastAPI REST API
├── TSICalendar.py              # Original calendar scraper
├── Exporters.py                # Export utilities
├── config.py                   # Legacy config (compatibility)
├── main.py                     # Original entry point
├── run.py                      # New unified entry point
├── requirements.txt
├── .env.example
└── README.md
```

## 🤖 Telegram Bot Commands

### Basic Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help |
| `/login` | Login to TSI account |
| `/logout` | Logout from TSI account |
| `/settings` | Bot settings |

### Schedule Commands

| Command | Description |
|---------|-------------|
| `/today` | Today's schedule |
| `/tomorrow` | Tomorrow's schedule |
| `/week` | This week's schedule |
| `/next` | Next upcoming class |
| `/search <query>` | Search schedule |

### Features Commands

| Command | Description |
|---------|-------------|
| `/stats` | Your learning statistics |
| `/exams` | Upcoming exams |
| `/weather` | Weather in Riga |
| `/motivation` | Random motivational quote |
| `/notes` | Your personal notes |
| `/deadlines` | Your deadlines |
| `/freerooms` | Available rooms now |

### Reminders & Notes Commands

| Command | Description |
|---------|-------------|
| `/remind <time> <text>` | Set reminder |
| `/reminders` | Show all reminders |
| `/note <text>` | Add a note |
| `/notes` | Show all notes |

### Natural Language Examples

```
"Что сегодня?" → Shows today's schedule
"Когда следующая пара?" → Shows next class
"Найди математику" → Searches for math classes
"Свободные аудитории" → Shows free rooms
"Напомни завтра в 10:00 про лабу" → Sets a reminder
"Запиши заметку: купить тетрадь" → Saves a note
```

## 🌐 REST API Endpoints

### Schedule

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/schedule/today` | Today's events |
| GET | `/api/schedule/week` | This week's events |
| GET | `/api/schedule/next` | Next event |
| GET | `/api/schedule/events` | Events with filters |
| GET | `/api/schedule/search` | Search events |

### Rooms

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rooms/free` | Free rooms |

### Assistant

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/assistant/query` | Query the AI |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/users` | Create user |
| GET | `/api/users/{id}` | Get user |
| PATCH | `/api/users/{id}` | Update user |

### API Documentation

When running the web server:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `GROQ_API_KEY` | No | Groq API key (free AI) |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `DATABASE_PATH` | No | SQLite database path |
| `ENCRYPTION_KEY` | No | Key for credential encryption |
| `TIMEZONE` | No | Timezone (default: Europe/Riga) |

### Getting a Telegram Bot Token

1. Open Telegram and find [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the token to your `.env` file

### Getting Free AI API Keys

**Groq (Recommended - Fast & Free):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and create API key
3. Add to `.env`: `GROQ_API_KEY=your_key`

**Google Gemini (Free):**
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Get API key
3. Add to `.env`: `GEMINI_API_KEY=your_key`

## 🔧 Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black app/
flake8 app/
```

### Adding New Intents

Edit `app/ai/intent_classifier.py`:

```python
INTENT_PATTERNS = {
    "my_new_intent": {
        "patterns": [r"\b(keyword1|keyword2)\b"],
        "keywords": ["keyword1", "keyword2"],
        "examples": ["Example phrase 1", "Example phrase 2"]
    },
    # ...
}
```

## 📝 Original Features (from TTICalendarV2Python)

This project extends the original TTICalendarV2Python with:
- Telegram bot interface
- REST API
- AI-powered assistant
- User management
- Notifications system

Original features preserved:
- TSI portal authentication
- Calendar data fetching
- Table, JSON, ICS exports
- Timezone/DST handling

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is for educational purposes at TSI.

## 🙏 Acknowledgments

- [TTICalendarV2Python](https://github.com/foxybbb/TTICalendarV2Python) - Original calendar scraper
- Transport and Telecommunication Institute (TSI)
- Python-telegram-bot community
- FastAPI framework

## 📞 Support

For issues or questions:
- Check the [Issues](https://github.com/your-repo/issues) page
- Make sure your credentials are correct
- Verify your network connection

---

Made with ❤️ for TSI students
