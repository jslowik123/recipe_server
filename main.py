import fastapi
import uvicorn
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, status, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from src.config import config
from jose import jwt, JWTError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from src.helper.rate_limit import rate_limit_handler, get_user_identifier
from src.helper.verify_token import verify_token, verify_token_sync, security, TokenError
from src.routes.legal import router as legal_router
from src.routes.wardroberry import router as wardroberry_router
from src.routes.support import router as support_router
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting Wardroberry API...")
    logger.info("✅ Application startup complete")
    logger.info("test")
    yield

    # Shutdown
    logger.info("🛑 Shutting down application...")
    logger.info("✅ Application shutdown complete")

app = fastapi.FastAPI(
    title="Wardroberry API - AI-Powered Wardrobe Management",
    version="1.0.0",
    lifespan=lifespan
)
# Rate limiting configuration
limiter = Limiter(key_func=get_user_identifier)
app.state.limiter = limiter  # type: ignore[attr-defined]

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Include routes
app.include_router(legal_router)
app.include_router(wardroberry_router, prefix="/api/wardrobe")
app.include_router(support_router)


# Pydantic Models will be added in wardroberry routes


@app.head("/")
@app.get("/")
def read_root():
    return FileResponse("index.html")


@app.get("/health")
@app.head("/health")
def health_check():
    """
    Health check endpoint for Wardroberry API
    Checks: Redis, Celery, Supabase DB, Supabase Storage, OpenAI
    """
    from src.database_manager import DatabaseManager
    from src.storage_manager import StorageManager
    from src.queue_manager import QueueManager
    from src.ai import ClothingAI

    health_status = {
        "status": "healthy",
        "services": {}
    }

    # Check Redis
    try:
        health_status["services"]["redis"] = check_redis_connection()
    except Exception as e:
        health_status["services"]["redis"] = False
        health_status["status"] = "degraded"

    # Check Celery/Queue
    try:
        queue = QueueManager()
        health_status["services"]["celery"] = queue.health_check()
    except Exception as e:
        health_status["services"]["celery"] = False
        health_status["status"] = "degraded"

    # Check Supabase Database
    try:
        db = DatabaseManager()
        health_status["services"]["database"] = db.health_check()
    except Exception as e:
        health_status["services"]["database"] = False
        health_status["status"] = "degraded"

    # Check Supabase Storage
    try:
        storage = StorageManager()
        health_status["services"]["storage"] = storage.health_check()
    except Exception as e:
        health_status["services"]["storage"] = False
        health_status["status"] = "degraded"

    # Check OpenAI
    try:
        ai = ClothingAI()
        health_status["services"]["openai"] = ai.health_check()
    except Exception as e:
        health_status["services"]["openai"] = False
        health_status["status"] = "degraded"

    return health_status

@app.get("/rate_limit_test")
@limiter.limit("1/minute")
def rate_limit(request: Request):
    return {
        "status": "healthy",
    }


def check_redis_connection():
    """
    Check if Redis is connected
    """
    try:
        import redis
        r = redis.from_url(config.redis_url)
        r.ping()
        return True
    except Exception as e:
        return False


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)