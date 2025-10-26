"""
Celery Tasks for Wardroberry API
Async processing with Redis broker
"""
import os
import base64
import logging
from typing import Dict, Any
from celery import Celery
from datetime import datetime

from src.storage_manager import StorageManager
from src.ai import ClothingAI
from src.database_manager import DatabaseManager, ProcessingStatus
from src.config import config

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Celery App Configuration
celery_app = Celery(
    'wardroberry',
    broker=config.redis_url,
    backend=config.redis_url
)

# Celery Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    task_acks_late=True,  # Acknowledge after task completion
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_default_retry_delay=60,  # 1 minute retry delay
    task_max_retries=3,
)


@celery_app.task(bind=True, name='wardroberry.process_clothing_image')
def process_clothing_image(
    self,
    clothing_id: str,
    user_id: str,
    user_token: str,
    file_content_b64: str,
    file_name: str,
    content_type: str
) -> Dict[str, Any]:
    """
    Celery Task: Process clothing image with AI analysis

    Args:
        self: Celery task instance (for retry)
        clothing_id: UUID of clothing item
        user_id: UUID of user
        user_token: JWT token for authenticated storage access
        file_content_b64: Base64-encoded file content
        file_name: Original filename
        content_type: MIME type

    Returns:
        Dict with processing results
    """
    try:
        logger.info(f"🔄 Starting processing for clothing: {clothing_id}")

        # Initialize services with user token
        storage = StorageManager(user_token=user_token)
        ai = ClothingAI()
        db = DatabaseManager(user_token=user_token)

        # Update status to processing
        db.update_processing_status(clothing_id, ProcessingStatus.PROCESSING)

        # Decode file content
        file_content = base64.b64decode(file_content_b64)

        # 1. Extract clothing from background
        logger.info("🖼️ Extracting clothing from background...")
        extracted_image_bytes = ai.extract_clothing(file_content)

        # 2. Upload extracted image
        extracted_path, extracted_url = storage.upload_processed_image(
            user_id=user_id,
            clothing_id=clothing_id,
            file_content=extracted_image_bytes,
            content_type=content_type
        )

        # 3. AI Analysis
        logger.info("🤖 Performing AI analysis...")
        ai_analysis = ai.analyze_clothing_image(extracted_image_bytes)

        # 4. Mark as completed
        completed_item = db.complete_clothing_processing(
            clothing_id=clothing_id,
            extracted_image_url=extracted_url,
            category=ai_analysis['category'],
            color=ai_analysis['color'],
            style=ai_analysis['style'],
            season=ai_analysis['season'],
            material=ai_analysis['material'],
            occasion=ai_analysis['occasion'],
            confidence=ai_analysis['confidence']
        )

        logger.info(f"✅ Processing completed for: {clothing_id}")
        logger.info(f"🎯 Detected: {ai_analysis['category']} ({ai_analysis['color']}, {ai_analysis['style']})")

        return {
            'success': True,
            'clothing_id': clothing_id,
            'category': ai_analysis['category'],
            'color': ai_analysis['color'],
            'style': ai_analysis['style'],
            'processed_at': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Error processing {clothing_id}: {e}")

        # Mark as failed in database
        try:
            db = DatabaseManager(user_token=user_token)
            db.mark_processing_failed(clothing_id, str(e))
        except Exception as db_error:
            logger.error(f"❌ Additional DB error: {db_error}")

        # Retry the task (max 3 times with exponential backoff)
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"❌ Max retries exceeded for {clothing_id}")
            return {
                'success': False,
                'clothing_id': clothing_id,
                'error': str(e),
                'failed_at': datetime.utcnow().isoformat()
            }


@celery_app.task(name='wardroberry.health_check')
def health_check_task() -> Dict[str, bool]:
    """
    Celery Task: Health check for all services

    Returns:
        Dict with service health status
    """
    try:
        ai = ClothingAI()
        db = DatabaseManager()

        return {
            'celery': True,
            'ai': ai.health_check(),
            'database': db.health_check()
        }
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return {
            'celery': True,
            'error': str(e)
        }
