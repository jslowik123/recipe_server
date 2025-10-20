import fastapi
import uvicorn
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import HTTPException, Depends, status, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from src.tasks import scrape_tiktok_async, celery_app
from src.config import config
from jose import jwt, JWTError
from src.websocket_manager import initialize_websocket_manager, get_websocket_manager
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from src.helper.rate_limit import rate_limit_handler, get_user_identifier
from src.helper.verify_token import verify_token, verify_token_sync, security
import markdown

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
# Rate limiting configuration
limiter = Limiter(key_func=get_user_identifier)
app.state.limiter = limiter  # type: ignore[attr-defined]

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# Pydantic Models
class TikTokScrapeRequest(BaseModel):
    url: str
    language: str

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


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

@app.get("/rate_limit_test")
@limiter.limit("1/minute")
def rate_limit(request: Request):
    return {
        "status": "healthy",
    }

@app.post("/scrape/async", response_model=TaskResponse)
@limiter.limit("1/minute")
def scrape_tiktok_videos_async(
    request: Request,
    body: TikTokScrapeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Start asynchronous TikTok scraping task for a single URL
    """
    try:
        # Verify JWT token and get user_id
        user_id = verify_token_sync(credentials)
        jwt_token = credentials.credentials

        # Validate URL
        if not body.url or not body.url.strip():
            raise HTTPException(status_code=422, detail="URL is required and cannot be empty")

        # Start the async task with JWT token
        task = scrape_tiktok_async.delay(body.url.strip(), body.language, user_id, jwt_token)
        
        return TaskResponse(
            task_id=task.id,
            status="PENDING",
            message=f"Started scraping TikTok video: {body.url}. Use /task/{task.id} to check progress."
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
    except Exception as e:
        return False


# Legal document helpers
def get_legal_document(doc_type: str, lang: str = "de") -> dict:
    """
    Load legal document from legal/{lang}/{doc_type}_content_{lang}.md

    Args:
        doc_type: Type of document (privacy_policy, terms_of_service, imprint)
        lang: Language code (de, en)

    Returns:
        dict with content and metadata
    """
    # Validate inputs
    valid_types = ["privacy_policy", "terms_of_service", "imprint"]
    valid_langs = ["de", "en"]

    if doc_type not in valid_types:
        raise HTTPException(status_code=404, detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}")

    if lang not in valid_langs:
        raise HTTPException(status_code=400, detail=f"Invalid language. Supported: {', '.join(valid_langs)}")

    # Build file path using your naming convention
    file_path = Path("legal") / lang / f"{doc_type}_content_{lang}.md"

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {doc_type} ({lang}). Please create {file_path}"
        )

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "type": doc_type,
            "language": lang,
            "content": content,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {str(e)}")


def render_legal_html(doc: dict) -> str:
    """
    Render legal document as HTML page

    Args:
        doc: Document dict from get_legal_document()

    Returns:
        HTML string
    """
    html_content = markdown.markdown(doc["content"])

    # Map document types to titles
    titles = {
        "privacy_policy": {"de": "Datenschutzerklärung", "en": "Privacy Policy"},
        "terms_of_service": {"de": "Nutzungsbedingungen", "en": "Terms of Service"},
        "imprint": {"de": "Impressum", "en": "Imprint"}
    }

    title = titles.get(doc["type"], {}).get(doc["language"], "Legal Document")

    return f"""<!DOCTYPE html>
<html lang="{doc['language']}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        h1 {{
            border-bottom: 2px solid #007AFF;
            padding-bottom: 10px;
        }}
        h2 {{
            margin-top: 30px;
            color: #007AFF;
        }}
        h3 {{
            margin-top: 20px;
        }}
        a {{
            color: #007AFF;
        }}
        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
        }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""


@app.get("/legal/privacy")
def get_privacy_policy(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get privacy policy / Datenschutzerklärung

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/privacy?lang=de&format=html
    - /legal/privacy?lang=en&format=json
    """
    doc = get_legal_document("privacy_policy", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })


@app.get("/legal/terms")
def get_terms_of_service(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get terms of service / Nutzungsbedingungen

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/terms?lang=de&format=html
    - /legal/terms?lang=en&format=json
    """
    doc = get_legal_document("terms_of_service", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })


@app.get("/legal/imprint")
def get_imprint(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get imprint / Impressum

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/imprint?lang=de&format=html
    - /legal/imprint?lang=en&format=json
    """
    doc = get_legal_document("imprint", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)