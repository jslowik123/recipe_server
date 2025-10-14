import fastapi
import uvicorn
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, HTTPException, Depends, status, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
from src.tasks import scrape_tiktok_async, celery_app
from src.config import config
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from datetime import datetime
from src.websocket_manager import initialize_websocket_manager, get_websocket_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting application...")

    # Initialize WebSocket manager
    ws_manager = initialize_websocket_manager(config.redis_url, celery_app)
    await ws_manager.initialize()

    # Start background listener for Redis pub/sub
    listener_task = asyncio.create_task(ws_manager.listen_for_updates())

    logger.info("✅ Application startup complete")

    yield

    # Shutdown
    logger.info("🛑 Shutting down application...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    await ws_manager.cleanup()
    logger.info("✅ Application shutdown complete")


app = fastapi.FastAPI(
    title="Apify TikTok Scraper with WebSockets",
    version="2.0.0",
    lifespan=lifespan
)
security = HTTPBearer()
# Pydantic Models
class TikTokScrapeRequest(BaseModel):
    url: str
    language: str

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


def verify_token_sync(credentials: HTTPAuthorizationCredentials) -> str:
    """Synchronous JWT token verification"""
    try:
        jwt_secret = config.supabase_jwt_secret
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT Secret nicht konfiguriert",
        )

    token = credentials.credentials
    try:
        # JWT verifizieren
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",  # Muss mit Supabase übereinstimmen
        )
        user_id = payload.get("sub")  # Enthält die Supabase User-ID
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger Token",
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ist abgelaufen",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token",
        )

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Async wrapper for JWT verification (for dependency injection)"""
    return verify_token_sync(credentials)

@app.head("/")
@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.get("/health")
@app.head("/health")
def health_check():
    return {
        "status": "healthy",
        "redis_connected": check_redis_connection(),
        "services": ["web", "redis", "worker"]
    }

@app.post("/scrape/async", response_model=TaskResponse)
def scrape_tiktok_videos_async(request: TikTokScrapeRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Start asynchronous TikTok scraping task for a single URL
    """
    try:
        # Verify JWT token and get user_id
        user_id = verify_token_sync(credentials)
        jwt_token = credentials.credentials

        # Validate URL
        if not request.url or not request.url.strip():
            raise HTTPException(status_code=422, detail="URL is required and cannot be empty")

        # Start the async task with JWT token
        task = scrape_tiktok_async.delay(request.url.strip(), request.language, user_id, jwt_token)
        
        return TaskResponse(
            task_id=task.id,
            status="PENDING",
            message=f"Started scraping TikTok video: {request.url}. Use /task/{task.id} to check progress."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start task: {str(e)}")


@app.get("/task/{task_id}")
def get_task_status(task_id: str, user_id: str = Depends(verify_token)):
    """
    Get the status and result of a task
    """
    try:
        task_result = celery_app.AsyncResult(task_id)
        
        if task_result.state == 'PENDING':
            return {
                "task_id": task_id,
                "status": "PENDING",
                "message": "Task is waiting to be processed"
            }
        elif task_result.state == 'PROGRESS':
            progress_info = task_result.info or {}
            return {
                "task_id": task_id,
                "status": "PROGRESS",
                "step": progress_info.get('step', 0),
                "total_steps": 5,
                "current_status": progress_info.get('status', 'Processing...'),
                "details": progress_info.get('details', ''),
                "url": progress_info.get('url', ''),
                "message": progress_info.get('status', 'Processing...')
            }
        elif task_result.state == 'SUCCESS':
            result = task_result.result

            # New response format: recipe is already uploaded to Supabase
            if result and isinstance(result, dict):
                return {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "message": result.get('message', 'Recipe successfully processed'),
                    "recipe_id": result.get('recipe_id'),
                    "recipe_name": result.get('recipe_name', 'Recipe'),
                    "upload_error": result.get('upload_error')  # Only present if upload failed
                }

            return {
                "task_id": task_id,
                "status": "SUCCESS",
                "message": "Recipe processing completed",
                "recipe_id": None,
                "recipe_name": "Unknown Recipe"
            }
        else:  # FAILURE
            return {
                "task_id": task_id,
                "status": "FAILURE",
                "error": str(task_result.info)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")

@app.get("/tasks/active")
def get_active_tasks(user_id: str = Depends(verify_token)):
    """
    Get list of active tasks
    """
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        return {"active_tasks": active_tasks}
    except Exception as e:
        return {"error": f"Failed to get active tasks: {str(e)}"}


@app.websocket("/wss/{task_id}")
async def websocket_task_updates(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(..., description="JWT token for authentication")
):
    """
    WebSocket Secure endpoint for real-time task updates

    Usage:
    - Connect to: /wss/{task_id}?token={jwt_token}
    - Receives real-time JSON messages about task progress
    - Automatically disconnects when task completes or fails
    """
    ws_manager = get_websocket_manager()

    try:
        # Verify JWT token from query parameter
        try:
            jwt_secret = config.supabase_jwt_secret
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                audience="authenticated"
            )
            user_id = payload.get("sub")
            if not user_id:
                await websocket.close(code=4001, reason="Invalid token")
                return
        except (jwt.ExpiredSignatureError, JWTError):
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

        # Connect and verify task ownership
        connected = await ws_manager.connect(websocket, task_id, user_id)
        if not connected:
            return

        logger.info(f"🔌 WebSocket connected: task={task_id}, user={user_id}")

        try:
            # Keep connection alive and handle disconnection
            while True:
                try:
                    # Wait for client messages (ping/pong, etc.)
                    message = await websocket.receive_text()

                    # Handle ping/pong for connection keepalive
                    if message == "ping":
                        await websocket.send_text("pong")

                except WebSocketDisconnect:
                    logger.info(f"🔌 WebSocket disconnected: task={task_id}")
                    break

        except Exception as e:
            logger.error(f"❌ WebSocket error for task {task_id}: {e}")

    except Exception as e:
        logger.error(f"❌ WebSocket connection error: {e}")
        try:
            await websocket.close(code=4000, reason="Internal server error")
        except:
            pass
    finally:
        # Clean up connection
        await ws_manager.disconnect(websocket, task_id)

def check_redis_connection():
    """
    Check if Redis is connected
    """
    try:
        import redis
        r = redis.from_url(config.redis_url)
        r.ping()
        return True
    except:
        return False

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)