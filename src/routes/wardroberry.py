"""
Wardroberry API Routes - Wardrobe Management
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import base64
import logging

from src.database_manager import DatabaseManager, ProcessingStatus
from src.storage_manager import StorageManager
from src.queue_manager import QueueManager
from src.ai import ClothingAI
from src.helper.verify_token import verify_token, get_user_token, verify_token_sync
from src.helper.exceptions import DatabaseError, StorageError, QueueError, ProcessingError
from src.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class ClothingUploadResponse(BaseModel):
    clothing_id: str
    status: str
    message: str


class ClothingItem(BaseModel):
    id: str
    user_id: str
    category: Optional[str]
    color: Optional[str]
    style: Optional[str]
    season: Optional[str]
    material: Optional[str]
    occasion: Optional[str]
    original_image_url: Optional[str]
    processed_image_url: Optional[str]
    processing_status: str
    confidence: Optional[float]
    created_at: str


class OutfitCreateRequest(BaseModel):
    name: str
    clothing_ids: List[str]
    occasion: Optional[str] = None


class OutfitResponse(BaseModel):
    id: str
    user_id: str
    name: str
    occasion: Optional[str]
    times_worn: int
    created_at: str
    items: List[ClothingItem]


class QueueStatsResponse(BaseModel):
    processing_queue_size: int
    retry_queue_size: int


# Dependency: Get services
def get_db_manager():
    return DatabaseManager()


def get_queue_manager():
    return QueueManager()


def get_ai():
    return ClothingAI()


@router.post("/upload", response_model=ClothingUploadResponse)
async def upload_clothing(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token),
    queue: QueueManager = Depends(get_queue_manager)
):
    """
    Upload a clothing item image for processing

    - Validates image file
    - Uploads to storage
    - Creates pending database entry
    - Queues for AI processing

    Requires: Bearer token authentication
    """
    try:
        # Create managers with user token for RLS
        storage = StorageManager(user_token=user_token)
        db = DatabaseManager(user_token=user_token)

        # Read file data
        file_data = await file.read()

        # Validate image
        is_valid, error_msg = storage.validate_image_file(file.content_type, len(file_data))
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )

        # Upload original image to storage
        logger.info(f"Uploading image for user {user_id[:8]}...")
        file_path, original_url = storage.upload_original_image(
            user_id, file_data, file.filename, file.content_type
        )

        # Create pending clothing entry in database
        logger.info(f"Creating database entry...")
        clothing_id = db.create_pending_clothing_item(user_id, original_url)

        # Queue for processing
        logger.info(f"Queuing for AI processing...")
        task_id = queue.add_clothing_processing_job(
            clothing_id=clothing_id,
            user_id=user_id,
            user_token=user_token,
            file_content=file_data,
            file_name=file.filename,
            content_type=file.content_type,
            priority=0
        )

        return ClothingUploadResponse(
            clothing_id=clothing_id,
            status="queued",
            message="Clothing item uploaded and queued for processing"
        )

    except StorageError as e:
        logger.error(f"Storage error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except QueueError as e:
        logger.error(f"Queue error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Queue error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/clothes", response_model=List[ClothingItem])
async def get_user_clothes(
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token),
    status: Optional[str] = Query(None, regex="^(PENDING|PROCESSING|COMPLETED|FAILED)$"),
    category: Optional[str] = Query(None)
):
    """
    Get all clothing items for authenticated user

    Optional filters:
    - status: PENDING, PROCESSING, COMPLETED, FAILED
    - category: Filter by clothing category

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        # Get all clothes for user
        clothes = db.get_user_clothes(user_id)

        # Apply filters
        if status:
            clothes = [c for c in clothes if c.get('processing_status') == status]

        if category:
            clothes = [c for c in clothes if c.get('category') == category]

        return clothes

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/clothes/{clothing_id}", response_model=ClothingItem)
async def get_clothing_item(
    clothing_id: str,
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Get a specific clothing item by ID

    Requires: Bearer token authentication
    Returns: 404 if not found or doesn't belong to user
    """
    try:
        db = DatabaseManager(user_token=user_token)
        item = db.get_clothing_item(clothing_id)

        if not item:
            raise HTTPException(status_code=404, detail="Clothing item not found")

        # Verify ownership
        if item.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this item")

        return item

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/clothes/{clothing_id}")
async def delete_clothing_item(
    clothing_id: str,
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Delete a clothing item (database + storage)

    Requires: Bearer token authentication
    """
    try:
        # Create managers with user token for RLS
        storage = StorageManager(user_token=user_token)
        db = DatabaseManager(user_token=user_token)

        # Get item to verify ownership
        item = db.get_clothing_item(clothing_id)

        if not item:
            raise HTTPException(status_code=404, detail="Clothing item not found")

        if item.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this item")

        # Delete from storage
        if item.get('original_image_url'):
            storage.delete_image_by_url(storage.original_bucket, item['original_image_url'])
        if item.get('processed_image_url'):
            storage.delete_image_by_url(storage.processed_bucket, item['processed_image_url'])

        # Delete from database
        db.delete_clothing_item(clothing_id)

        return {"message": "Clothing item deleted successfully"}

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except StorageError as e:
        logger.error(f"Storage error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/outfits", response_model=OutfitResponse)
async def create_outfit(
    outfit: OutfitCreateRequest,
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Create a new outfit from clothing items

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        # Verify all clothing items belong to user
        for clothing_id in outfit.clothing_ids:
            item = db.get_clothing_item(clothing_id)
            if not item or item.get('user_id') != user_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Clothing item {clothing_id} not found or not authorized"
                )

        # Create outfit
        outfit_id = db.create_outfit(
            user_id=user_id,
            name=outfit.name,
            clothing_ids=outfit.clothing_ids,
            occasion=outfit.occasion
        )

        # Return created outfit with items
        created_outfit = db.get_outfit(outfit_id)
        return created_outfit

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/outfits", response_model=List[OutfitResponse])
async def get_user_outfits(
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Get all outfits for authenticated user

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        outfits = db.get_user_outfits(user_id)
        return outfits

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/outfits/{outfit_id}", response_model=OutfitResponse)
async def get_outfit(
    outfit_id: str,
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Get a specific outfit by ID

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        outfit = db.get_outfit(outfit_id)

        if not outfit:
            raise HTTPException(status_code=404, detail="Outfit not found")

        if outfit.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this outfit")

        return outfit

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/outfits/{outfit_id}")
async def delete_outfit(
    outfit_id: str,
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Delete an outfit

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        # Verify ownership
        outfit = db.get_outfit(outfit_id)

        if not outfit:
            raise HTTPException(status_code=404, detail="Outfit not found")

        if outfit.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this outfit")

        db.delete_outfit(outfit_id)

        return {"message": "Outfit deleted successfully"}

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_user_stats(
    user_id: str = Depends(verify_token),
    user_token: str = Depends(get_user_token)
):
    """
    Get user wardrobe statistics

    Requires: Bearer token authentication
    """
    try:
        db = DatabaseManager(user_token=user_token)
        stats = db.get_user_statistics(user_id)
        return stats

    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    user_id: str = Depends(verify_token),
    queue: QueueManager = Depends(get_queue_manager)
):
    """
    Get processing queue statistics

    Requires: Bearer token authentication
    """
    try:
        stats = queue.get_queue_stats()
        return QueueStatsResponse(
            processing_queue_size=stats.get('total_pending', 0),
            retry_queue_size=0  # Retries are handled automatically by Celery
        )

    except QueueError as e:
        logger.error(f"Queue error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Queue error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/ws/clothing/{clothing_id}")
async def websocket_clothing_updates(
    websocket: WebSocket,
    clothing_id: str
):
    """
    WebSocket endpoint for real-time clothing processing updates

    Authentication: JWT token in Sec-WebSocket-Protocol header
    Format: Sec-WebSocket-Protocol: Bearer_<token>

    Messages sent:
    - type: "connected" - Connection established
    - type: "progress" - Processing progress update (step, total_steps, message, progress_percent)
    - type: "completed" - Processing completed (result data)
    - type: "error" - Processing failed (error message)
    - type: "status" - General status update

    Example client (JavaScript):
        const ws = new WebSocket('ws://localhost:8000/ws/clothing/<clothing_id>', ['Bearer_' + token]);
    """
    from fastapi.security import HTTPAuthorizationCredentials
    from src.helper.verify_token import TokenError

    user_id = None

    try:
        # Extract JWT from Sec-WebSocket-Protocol header
        # Format: ["Bearer_<token>", ...]
        protocols = websocket.headers.get("sec-websocket-protocol", "")
        token = None

        # Parse protocols (can be comma-separated)
        for protocol in protocols.split(","):
            protocol = protocol.strip()
            if protocol.startswith("Bearer_"):
                token = protocol.replace("Bearer_", "")
                break

        if not token:
            await websocket.close(code=4001, reason="Missing authentication token")
            return

        # Verify JWT token
        try:
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            user_id = verify_token_sync(credentials)
        except TokenError as e:
            logger.error(f"Token verification failed: {e.technical_details}")
            await websocket.close(code=4003, reason="Invalid or expired token")
            return

        # Verify clothing item belongs to user
        try:
            db = DatabaseManager(user_token=token)
            clothing_item = db.get_clothing_item(clothing_id)

            if not clothing_item:
                await websocket.close(code=4004, reason="Clothing item not found")
                return

            if clothing_item.get('user_id') != user_id:
                await websocket.close(code=4003, reason="Not authorized to access this item")
                return

        except Exception as e:
            logger.error(f"Database error during WebSocket auth: {e}")
            await websocket.close(code=5000, reason="Internal server error")
            return

        # Get WebSocket manager and connect
        ws_manager = get_websocket_manager()
        success = await ws_manager.connect(websocket, clothing_id, user_id)

        if not success:
            await websocket.close(code=5000, reason="Failed to establish connection")
            return

        # Keep connection alive and handle messages
        try:
            while True:
                # Wait for messages from client (optional - can be used for heartbeat)
                data = await websocket.receive_text()
                # Echo back for heartbeat/ping-pong
                if data == "ping":
                    await websocket.send_text("pong")

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for clothing {clothing_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Cleanup connection
            await ws_manager.disconnect(websocket, clothing_id)

    except Exception as e:
        logger.error(f"Unexpected error in WebSocket endpoint: {e}")
        try:
            await websocket.close(code=5000, reason="Internal server error")
        except:
            pass
