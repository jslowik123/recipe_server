import os
import json
import base64
import logging
import redis
from typing import Dict, Any, Optional
from datetime import datetime
from celery.result import AsyncResult

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Queue Manager für Wardroberry
    Verwaltet Celery Tasks für asynchrone Verarbeitung
    """

    def __init__(self):
        """Initialisiert Redis Connection und Celery"""
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True
        )

        # Import Celery App
        from src.tasks import celery_app, process_clothing_image
        self.celery_app = celery_app
        self.process_clothing_task = process_clothing_image
        
    def add_clothing_processing_job(self, clothing_id: str, user_id: str,
                                  user_token: str, file_content: bytes, file_name: str,
                                  content_type: str, priority: int = 0) -> Optional[str]:
        """
        Fügt einen Kleidungsstück-Verarbeitungsjob zur Celery Queue hinzu

        Args:
            clothing_id: UUID des Kleidungsstücks
            user_id: UUID des Nutzers
            user_token: JWT token for authenticated storage access
            file_content: Binäre Dateidaten
            file_name: Dateiname
            content_type: MIME-Type
            priority: Priorität (0-10, höher = wichtiger)

        Returns:
            Task ID wenn erfolgreich, None bei Fehler
        """
        try:
            # File Content als Base64 kodieren
            file_content_b64 = base64.b64encode(file_content).decode('utf-8')

            # Celery Task starten
            result = self.process_clothing_task.apply_async(
                args=[clothing_id, user_id, user_token, file_content_b64, file_name, content_type],
                priority=priority,
                retry=True,
                retry_policy={
                    'max_retries': 3,
                    'interval_start': 60,
                    'interval_step': 60,
                    'interval_max': 180,
                }
            )

            logger.info(f"✅ Celery Task gestartet: {clothing_id} (Task ID: {result.id}, Priorität: {priority})")
            return result.id

        except Exception as e:
            logger.error(f"❌ Fehler beim Starten des Celery Tasks: {e}")
            return None
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Holt Statistiken über die Celery Queue

        Returns:
            Dict mit Queue-Statistiken
        """
        try:
            # Celery Inspect API
            inspect = self.celery_app.control.inspect()

            # Get active tasks
            active_tasks = inspect.active()
            active_count = sum(len(tasks) for tasks in (active_tasks or {}).values())

            # Get scheduled tasks
            scheduled_tasks = inspect.scheduled()
            scheduled_count = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())

            # Get reserved (waiting) tasks
            reserved_tasks = inspect.reserved()
            reserved_count = sum(len(tasks) for tasks in (reserved_tasks or {}).values())

            return {
                'active': active_count,
                'scheduled': scheduled_count,
                'reserved': reserved_count,
                'total_pending': active_count + scheduled_count + reserved_count,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Fehler beim Holen der Celery Stats: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def health_check(self) -> bool:
        """
        Überprüft die Redis-Verbindung und Celery Verfügbarkeit

        Returns:
            True wenn Redis und Celery erreichbar
        """
        try:
            # Redis Check
            self.redis_client.ping()

            # Celery Worker Check
            inspect = self.celery_app.control.inspect()
            stats = inspect.stats()
            if not stats:
                logger.warning("⚠️ Keine aktiven Celery Worker gefunden")
                return False

            return True
        except Exception as e:
            logger.error(f"❌ Health Check fehlgeschlagen: {e}")
            return False

    def purge_queue(self) -> int:
        """
        Leert alle Celery Tasks aus der Queue (nur für Development/Testing)

        Returns:
            Anzahl der gelöschten Tasks
        """
        try:
            purged = self.celery_app.control.purge()
            logger.info(f"🗑️ Celery Queue geleert: {purged} Tasks gelöscht")
            return purged
        except Exception as e:
            logger.error(f"❌ Fehler beim Leeren der Queue: {e}")
            return 0

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Holt den Status eines bestimmten Celery Tasks

        Args:
            task_id: Celery Task ID

        Returns:
            Dict mit Task-Status
        """
        try:
            result = AsyncResult(task_id, app=self.celery_app)

            return {
                'task_id': task_id,
                'status': result.state,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'result': result.result if result.ready() else None,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Fehler beim Holen des Task-Status: {e}")
            return {
                'task_id': task_id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            } 