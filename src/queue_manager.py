import os
import json
import base64
import logging
import redis
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Queue Manager für Wardroberry
    Verwaltet die Redis-Queue für asynchrone Verarbeitung
    """
    
    def __init__(self):
        """Initialisiert Redis Connection"""
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
        
        # Queue Namen
        self.queue_name = "clothing_processing_queue"
        self.retry_queue = "clothing_processing_retry"
        
    def add_clothing_processing_job(self, clothing_id: str, user_id: str, 
                                  file_content: bytes, file_name: str, 
                                  content_type: str, priority: int = 0) -> bool:
        """
        Fügt einen Kleidungsstück-Verarbeitungsjob zur Queue hinzu
        
        Args:
            clothing_id: UUID des Kleidungsstücks
            user_id: UUID des Nutzers
            file_content: Binäre Dateidaten
            file_name: Dateiname
            content_type: MIME-Type
            priority: Priorität (0 = normal, höher = wichtiger)
            
        Returns:
            True wenn Job erfolgreich hinzugefügt
        """
        try:
            # File Content als Base64 kodieren
            file_content_b64 = base64.b64encode(file_content).decode('utf-8')
            
            job_data = {
                'clothing_id': clothing_id,
                'user_id': user_id,
                'file_content_b64': file_content_b64,
                'file_name': file_name,
                'content_type': content_type,
                'created_at': datetime.utcnow().isoformat(),
                'retry_count': 0,
                'priority': priority
            }
            
            # Job zu Queue hinzufügen
            job_json = json.dumps(job_data)
            
            if priority > 0:
                # High priority - an den Anfang der Queue
                self.redis_client.lpush(self.queue_name, job_json)
            else:
                # Normal priority - an das Ende der Queue
                self.redis_client.rpush(self.queue_name, job_json)
            
            logger.info(f"✅ Job hinzugefügt zur Queue: {clothing_id} (Priorität: {priority})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Fehler beim Hinzufügen des Jobs zur Queue: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Holt Statistiken über die Queue
        
        Returns:
            Dict mit Queue-Statistiken
        """
        try:
            main_queue_length = self.redis_client.llen(self.queue_name)
            retry_queue_length = self.redis_client.llen(self.retry_queue)
            
            return {
                'main_queue_length': main_queue_length,
                'retry_queue_length': retry_queue_length,
                'total_pending': main_queue_length + retry_queue_length,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Fehler beim Holen der Queue-Stats: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def health_check(self) -> bool:
        """
        Überprüft die Redis-Verbindung
        
        Returns:
            True wenn Redis erreichbar
        """
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"❌ Redis Health Check fehlgeschlagen: {e}")
            return False
    
    def clear_queue(self, queue_name: Optional[str] = None) -> int:
        """
        Leert eine Queue (nur für Development/Testing)
        
        Args:
            queue_name: Name der Queue (optional, default: main queue)
            
        Returns:
            Anzahl der gelöschten Jobs
        """
        try:
            target_queue = queue_name or self.queue_name
            deleted_count = self.redis_client.delete(target_queue)
            logger.info(f"🗑️ Queue {target_queue} geleert: {deleted_count} Jobs gelöscht")
            return deleted_count
        except Exception as e:
            logger.error(f"❌ Fehler beim Leeren der Queue: {e}")
            return 0
    
    def peek_next_job(self) -> Optional[Dict[str, Any]]:
        """
        Schaut sich den nächsten Job in der Queue an (ohne ihn zu entfernen)
        
        Returns:
            Job-Daten oder None wenn Queue leer
        """
        try:
            # Schaut sich das erste Element in der Queue an
            job_json = self.redis_client.lindex(self.queue_name, 0)
            
            if job_json:
                return json.loads(job_json)
            return None
            
        except Exception as e:
            logger.error(f"❌ Fehler beim Peek der Queue: {e}")
            return None 