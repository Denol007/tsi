#!/usr/bin/env python3
"""
Smart Campus Web API
FastAPI-based REST API for the Smart Campus Assistant
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

from app.core.calendar_service import CalendarService
from app.core.database import Database
from app.ai.assistant import AIAssistant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic models for request/response
class UserCreate(BaseModel):
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    student_id: Optional[str] = None
    group_code: Optional[str] = None


class UserUpdate(BaseModel):
    group_code: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    reminder_minutes: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[int]
    username: Optional[str]
    group_code: Optional[str]
    notifications_enabled: bool
    reminder_minutes: int


class EventResponse(BaseModel):
    date: str
    start_time: str
    end_time: str
    title: str
    room: Optional[str]
    group: Optional[str]
    lecturer: Optional[str]
    type: Optional[str]
    description: Optional[str]


class QueryRequest(BaseModel):
    query: str
    group_code: Optional[str] = None


class QueryResponse(BaseModel):
    response: str
    intent: str


class ScheduleParams(BaseModel):
    group: Optional[str] = None
    lecturer: Optional[str] = None
    room: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None


# Global instances (will be initialized in create_app)
calendar_service: CalendarService = None
database: Database = None
assistant: AIAssistant = None


def create_app(
    tsi_username: str = None,
    tsi_password: str = None,
    db_path: str = "smart_campus.db"
) -> FastAPI:
    """Create and configure the FastAPI application"""
    
    global calendar_service, database, assistant
    
    # Initialize services
    database = Database(db_path)
    
    if tsi_username and tsi_password:
        calendar_service = CalendarService(tsi_username, tsi_password)
        if calendar_service.login():
            assistant = AIAssistant(calendar_service, database)
            logger.info("Calendar service initialized")
        else:
            logger.warning("Failed to initialize calendar service")
    
    # Create FastAPI app
    app = FastAPI(
        title="Smart Campus Assistant API",
        description="API for TSI campus schedule and assistant",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ==================== Routes ====================
    
    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Root endpoint with basic info"""
        return """
        <html>
            <head>
                <title>Smart Campus Assistant API</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 50px; background: #f5f5f5; }
                    .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    h1 { color: #333; }
                    a { color: #007bff; }
                    .endpoint { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🎓 Smart Campus Assistant API</h1>
                    <p>Welcome to the Smart Campus Assistant API!</p>
                    
                    <h2>Documentation</h2>
                    <div class="endpoint">
                        <a href="/docs">📖 Swagger UI Documentation</a>
                    </div>
                    <div class="endpoint">
                        <a href="/redoc">📚 ReDoc Documentation</a>
                    </div>
                    
                    <h2>Quick Links</h2>
                    <div class="endpoint">
                        <code>GET /api/health</code> - Health check
                    </div>
                    <div class="endpoint">
                        <code>GET /api/schedule/today</code> - Today's schedule
                    </div>
                    <div class="endpoint">
                        <code>POST /api/assistant/query</code> - Ask the assistant
                    </div>
                </div>
            </body>
        </html>
        """
    
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": database is not None,
                "calendar": calendar_service is not None and calendar_service.is_authenticated(),
                "assistant": assistant is not None
            }
        }
    
    # ==================== Schedule Endpoints ====================
    
    @app.get("/api/schedule/today", response_model=List[EventResponse])
    async def get_today_schedule(group: Optional[str] = Query(None)):
        """Get today's schedule"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            events = calendar_service.get_today_events(group=group)
            return events
        except Exception as e:
            logger.error(f"Error getting today's schedule: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/schedule/week", response_model=List[EventResponse])
    async def get_week_schedule(group: Optional[str] = Query(None)):
        """Get this week's schedule"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            events = calendar_service.get_week_events(group=group)
            return events
        except Exception as e:
            logger.error(f"Error getting week's schedule: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/schedule/next", response_model=Optional[EventResponse])
    async def get_next_class(group: Optional[str] = Query(None)):
        """Get the next upcoming class"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            event = calendar_service.get_next_event(group=group)
            return event
        except Exception as e:
            logger.error(f"Error getting next class: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/schedule/events", response_model=List[EventResponse])
    async def get_events(
        group: Optional[str] = Query(None),
        lecturer: Optional[str] = Query(None),
        room: Optional[str] = Query(None),
        from_date: Optional[date] = Query(None),
        to_date: Optional[date] = Query(None)
    ):
        """Get events with filters"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            from_datetime = datetime.combine(from_date, datetime.min.time()) if from_date else None
            to_datetime = datetime.combine(to_date, datetime.max.time()) if to_date else None
            
            events = calendar_service.fetch_events(
                group=group,
                lecturer=lecturer,
                room=room,
                from_date=from_datetime,
                to_date=to_datetime
            )
            return events
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/schedule/search", response_model=List[EventResponse])
    async def search_events(
        query: str = Query(..., min_length=1),
        group: Optional[str] = Query(None),
        limit: int = Query(10, ge=1, le=50)
    ):
        """Search events by query"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            events = calendar_service.search_events(query, group=group, limit=limit)
            return events
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            raise HTTPException(500, str(e))
    
    # ==================== Rooms Endpoints ====================
    
    @app.get("/api/rooms/free")
    async def get_free_rooms(
        date: Optional[str] = Query(None),
        time: Optional[str] = Query(None)
    ):
        """Get free rooms at specified date/time"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            rooms = calendar_service.get_free_rooms(date=date, time=time)
            return {"free_rooms": rooms, "count": len(rooms)}
        except Exception as e:
            logger.error(f"Error getting free rooms: {e}")
            raise HTTPException(500, str(e))
    
    # ==================== Assistant Endpoints ====================
    
    @app.post("/api/assistant/query", response_model=QueryResponse)
    async def query_assistant(request: QueryRequest):
        """Query the AI assistant"""
        if not assistant:
            raise HTTPException(503, "Assistant service not available")
        
        try:
            user_context = {"group_code": request.group_code} if request.group_code else {}
            response, intent = assistant.process_query(request.query, user_context)
            return QueryResponse(response=response, intent=intent)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            raise HTTPException(500, str(e))
    
    # ==================== User Endpoints ====================
    
    @app.post("/api/users", response_model=Dict)
    async def create_user(user: UserCreate):
        """Create a new user"""
        try:
            user_id = database.create_user(
                telegram_id=user.telegram_id,
                username=user.username,
                student_id=user.student_id,
                group_code=user.group_code
            )
            return {"id": user_id, "message": "User created successfully"}
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/users/{telegram_id}")
    async def get_user(telegram_id: int):
        """Get user by Telegram ID"""
        user = database.get_user(telegram_id)
        if not user:
            raise HTTPException(404, "User not found")
        return user
    
    @app.patch("/api/users/{telegram_id}")
    async def update_user(telegram_id: int, user: UserUpdate):
        """Update user"""
        update_data = {k: v for k, v in user.dict().items() if v is not None}
        if not update_data:
            raise HTTPException(400, "No update data provided")
        
        success = database.update_user(telegram_id, **update_data)
        if not success:
            raise HTTPException(404, "User not found")
        
        return {"message": "User updated successfully"}
    
    @app.get("/api/users/{telegram_id}/stats")
    async def get_user_stats(telegram_id: int):
        """Get user statistics"""
        stats = database.get_user_stats(telegram_id)
        if not stats:
            raise HTTPException(404, "User not found")
        return stats
    
    # ==================== Export Endpoints ====================
    
    @app.get("/api/export/ics")
    async def export_ics(
        group: str = Query(...),
        from_date: Optional[date] = Query(None),
        to_date: Optional[date] = Query(None)
    ):
        """Export schedule to ICS format"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        # TODO: Implement ICS export
        return {"message": "ICS export coming soon", "group": group}
    
    @app.get("/api/export/json")
    async def export_json(
        group: str = Query(...),
        from_date: Optional[date] = Query(None),
        to_date: Optional[date] = Query(None)
    ):
        """Export schedule to JSON format"""
        if not calendar_service:
            raise HTTPException(503, "Calendar service not available")
        
        try:
            from_datetime = datetime.combine(from_date, datetime.min.time()) if from_date else None
            to_datetime = datetime.combine(to_date, datetime.max.time()) if to_date else None
            
            events = calendar_service.fetch_events(
                group=group,
                from_date=from_datetime,
                to_date=to_datetime
            )
            
            return {
                "group": group,
                "exported_at": datetime.now().isoformat(),
                "event_count": len(events),
                "events": events
            }
        except Exception as e:
            logger.error(f"Error exporting JSON: {e}")
            raise HTTPException(500, str(e))
    
    return app


# Create default app instance
app = create_app()
