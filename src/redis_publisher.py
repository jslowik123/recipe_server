"""
Synchronous Redis Publisher for Celery Tasks
Publishes WebSocket updates from Celery worker (non-async context)
"""
import json
import logging
from typing import Dict, Any
from datetime import datetime
import redis
from src.config import config

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Synchronous Redis publisher for clothing processing updates"""

    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client = redis.from_url(
            config.redis_url,
            decode_responses=True
        )

    def publish_update(self, clothing_id: str, update_data: Dict[str, Any]):
        """
        Publish a processing update to Redis for WebSocket broadcast

        Args:
            clothing_id: UUID of clothing item
            update_data: Update data (type, status, message, etc.)
        """
        try:
            message = {
                "clothing_id": clothing_id,
                "timestamp": datetime.utcnow().isoformat(),
                **update_data
            }
            self.redis_client.publish("clothing_updates", json.dumps(message))
            logger.debug(f"📡 Published update for clothing {clothing_id}: {update_data.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ Failed to publish update for clothing {clothing_id}: {e}")

    def publish_status(self, clothing_id: str, status: str, message: str, **extra):
        """
        Publish a status update

        Args:
            clothing_id: UUID of clothing item
            status: Status string (e.g., 'processing', 'completed', 'failed')
            message: Human-readable status message
            **extra: Additional data to include
        """
        self.publish_update(
            clothing_id=clothing_id,
            update_data={
                "type": "status",
                "status": status,
                "message": message,
                **extra
            }
        )

    def publish_progress(self, clothing_id: str, step: int, total_steps: int, message: str):
        """
        Publish a progress update

        Args:
            clothing_id: UUID of clothing item
            step: Current step number
            total_steps: Total number of steps
            message: Description of current step
        """
        self.publish_update(
            clothing_id=clothing_id,
            update_data={
                "type": "progress",
                "step": step,
                "total_steps": total_steps,
                "message": message,
                "progress_percent": round((step / total_steps) * 100)
            }
        )

    def publish_completion(self, clothing_id: str, result: Dict[str, Any]):
        """
        Publish a completion update

        Args:
            clothing_id: UUID of clothing item
            result: Processing result data
        """
        self.publish_update(
            clothing_id=clothing_id,
            update_data={
                "type": "completed",
                "status": "completed",
                "message": "Processing completed successfully",
                "result": result
            }
        )

    def publish_error(self, clothing_id: str, error: str):
        """
        Publish an error update

        Args:
            clothing_id: UUID of clothing item
            error: Error message
        """
        self.publish_update(
            clothing_id=clothing_id,
            update_data={
                "type": "error",
                "status": "failed",
                "message": "Processing failed",
                "error": error
            }
        )

    def close(self):
        """Close Redis connection"""
        try:
            self.redis_client.close()
        except Exception as e:
            logger.error(f"❌ Error closing Redis connection: {e}")
