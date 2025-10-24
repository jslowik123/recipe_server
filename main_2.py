import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

from storage_manager import StorageManager
from ai import ClothingAI
from database_manager import DatabaseManager, ProcessingStatus
from queue_manager import QueueManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Wardroberry AI API gestartet")
    logger.info("📋 Verfügbare Endpoints:")
    logger.info("  POST /upload-clothing - Kleidungsstück hochladen")
    logger.info("  GET  /clothing/{id}/status - Status-Check")
    logger.info("  GET  /queue/stats - Queue-Statistiken")
    logger.info("  GET  /health - Health Check")
    yield
    # Shutdown
    logger.info("🔄 Wardroberry AI API beendet")

# FastAPI App Setup
app = FastAPI(
    title="Wardroberry AI API",
    description="Asynchroner Upload und Verarbeitung von Kleidungsstücken",
    version="3.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In Produktion spezifische Origins verwenden
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security Setup
security = HTTPBearer(auto_error=False)

# Dependencies
def get_storage_manager() -> StorageManager:
    """Dependency für StorageManager"""
    return StorageManager()

def get_database_manager() -> DatabaseManager:
    """Dependency für DatabaseManager"""
    return DatabaseManager()

def get_queue_manager() -> QueueManager:
    """Dependency für QueueManager"""
    return QueueManager()

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extrahiert die User-ID aus dem JWT-Token (Supabase Auth)
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header fehlt")
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Ungültiger Token: Keine User-ID")
        
        return user_id
        
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Ungültiger JWT Token")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentifizierung fehlgeschlagen")

# ======================
# RESPONSE MODELS
# ======================

class ClothingUploadResponse(BaseModel):
    """Sofortige Antwort nach Upload"""
    id: str
    status: str
    message: str
    created_at: str

class ClothingStatusResponse(BaseModel):
    """Status-Antwort für Polling"""
    id: str
    status: str
    category: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None
    season: Optional[str] = None
    material: Optional[str] = None
    occasion: Optional[str] = None
    confidence: Optional[float] = None
    image_url: Optional[str] = None
    extracted_image_url: Optional[str] = None
    processing_error: Optional[str] = None
    updated_at: str

# ======================
# MAIN ENDPOINTS
# ======================

@app.post("/upload-clothing", response_model=ClothingUploadResponse)
async def upload_clothing_item(
    file: UploadFile = File(..., description="Bilddatei des Kleidungsstücks"),
    user_id: str = Depends(get_current_user_id),
    storage: StorageManager = Depends(get_storage_manager),
    db: DatabaseManager = Depends(get_database_manager),
    queue: QueueManager = Depends(get_queue_manager)
):
    """
    🚀 **HAUPTENDPOINT**: Kleidungsstück hochladen → sofortige Bestätigung
    
    **Workflow:**
    1. ✅ Bild validieren
    2. 📤 Original hochladen
    3. 💾 Pending-Eintrag in DB erstellen
    4. 📋 Job zur Redis-Queue hinzufügen
    5. 🚀 Sofortige Bestätigung an Frontend
    6. 🔄 Worker verarbeitet asynchron (Extraktion + Analyse)
    """
    try:
        # 1. Datei-Validierung
        file_content = await file.read()
        file_size = len(file_content)
        
        is_valid, error_message = storage.validate_image_file(file.content_type, file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)
        
        logger.info(f"📤 Lade Original-Bild hoch für User: {user_id}")
        
        # 2. Original-Bild hochladen
        original_path, original_url = storage.upload_original_image(
            user_id=user_id,
            file_content=file_content,
            file_name=file.filename or "clothing.jpg",
            content_type=file.content_type
        )
        
        # 3. Pending-Eintrag in Datenbank erstellen
        clothing_item = db.create_pending_clothing_item(
            user_id=user_id,
            original_image_url=original_url,
            original_filename=file.filename
        )
        
        # 4. Job zur Verarbeitungs-Queue hinzufügen
        job_added = queue.add_clothing_processing_job(
            clothing_id=clothing_item['id'],
            user_id=user_id,
            file_content=file_content,
            file_name=file.filename or "clothing.jpg",
            content_type=file.content_type,
            priority=0  # Normal priority
        )
        
        if not job_added:
            logger.error(f"❌ Job konnte nicht zur Queue hinzugefügt werden: {clothing_item['id']}")
            # Fallback: Markiere als failed
            db.mark_processing_failed(clothing_item['id'], "Queue-Fehler: Job konnte nicht hinzugefügt werden")
        
        logger.info(f"✅ Kleidungsstück empfangen: {clothing_item['id']}")
        
        # 5. Sofortige Bestätigung zurückgeben
        return ClothingUploadResponse(
            id=clothing_item['id'],
            status=ProcessingStatus.PENDING.value,
            message="Kleidungsstück empfangen! Verarbeitung läuft im Hintergrund.",
            created_at=clothing_item['created_at']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Fehler beim Upload: {e}")
        raise HTTPException(status_code=500, detail=f"Upload fehlgeschlagen: {str(e)}")

@app.get("/clothing/{clothing_id}/status", response_model=ClothingStatusResponse)
async def get_clothing_status(
    clothing_id: str,
    user_id: str = Depends(get_current_user_id),
    db: DatabaseManager = Depends(get_database_manager)
):
    """
    📊 **STATUS-CHECK**: Aktuellen Verarbeitungsstatus abrufen
    
    Für Frontend-Polling um Verarbeitungsfortschritt zu verfolgen
    """
    try:
        clothing_item = db.get_clothing_item(clothing_id)
        
        if not clothing_item:
            raise HTTPException(status_code=404, detail="Kleidungsstück nicht gefunden")
        
        # RLS-Check: Nur eigene Kleidungsstücke
        if clothing_item['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        
        return ClothingStatusResponse(
            id=clothing_item['id'],
            status=clothing_item.get('processing_status', 'unknown'),
            category=clothing_item.get('category'),
            color=clothing_item.get('color'),
            style=clothing_item.get('style'),
            season=clothing_item.get('season'),
            material=clothing_item.get('material'),
            occasion=clothing_item.get('occasion'),
            confidence=clothing_item.get('ai_confidence'),
            image_url=clothing_item.get('image_url'),
            extracted_image_url=clothing_item.get('extracted_image_url'),
            processing_error=clothing_item.get('processing_error'),
            updated_at=clothing_item.get('updated_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Fehler beim Status-Check: {e}")
        raise HTTPException(status_code=500, detail=f"Status-Check fehlgeschlagen: {str(e)}")

@app.get("/queue/stats")
async def get_queue_stats(
    queue: QueueManager = Depends(get_queue_manager)
):
    """
    📊 **QUEUE-STATS**: Aktuelle Queue-Statistiken abrufen
    
    Zeigt Anzahl wartender Jobs in der Verarbeitungsqueue
    """
    try:
        stats = queue.get_queue_stats()
        return stats
        
    except Exception as e:
        logger.error(f"❌ Fehler beim Holen der Queue-Stats: {e}")
        raise HTTPException(status_code=500, detail=f"Queue-Stats fehlgeschlagen: {str(e)}")

@app.get("/health")
async def health_check(
    storage: StorageManager = Depends(get_storage_manager),
    db: DatabaseManager = Depends(get_database_manager),
    queue: QueueManager = Depends(get_queue_manager)
):
    """Überprüft die API, Storage, Database, Queue und KI-Verbindung"""
    try:
        storage_healthy = storage.health_check()
        db_healthy = db.health_check()
        queue_healthy = queue.health_check()
        
        overall_status = "healthy" if (storage_healthy and db_healthy and queue_healthy) else "unhealthy"
        
        # Queue Stats hinzufügen
        queue_stats = queue.get_queue_stats() if queue_healthy else {"error": "Queue nicht erreichbar"}
        
        return {
            "status": overall_status,
            "storage": "connected" if storage_healthy else "disconnected",
            "database": "connected" if db_healthy else "disconnected",
            "queue": "connected" if queue_healthy else "disconnected",
            "queue_stats": queue_stats,
            "timestamp": datetime.now().isoformat(),
            "message": "Wardroberry API bereit" if overall_status == "healthy" else "Service nicht verfügbar"
        }
    except Exception as e:
        logger.error(f"Health Check Fehler: {e}")
        return {
            "status": "unhealthy",
            "storage": "error",
            "database": "error",
            "queue": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)