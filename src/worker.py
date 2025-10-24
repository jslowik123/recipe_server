import os
import sys
import time
import json
import logging
import redis
from typing import Dict, Any
from datetime import datetime
from storage_manager import StorageManager
from ai import ClothingAI
from database_manager import DatabaseManager, ProcessingStatus

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ClothingProcessor:
    """
    Asynchroner Worker für Kleidungsstück-Verarbeitung
    Verarbeitet Jobs aus Redis Queue
    """
    
    def __init__(self):
        """Initialisiert Worker mit Redis Connection und Services"""
        # Redis Connection
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
        
        # Queue Namen
        self.queue_name = "clothing_processing_queue"
        self.retry_queue = "clothing_processing_retry"
        
        # Services
        self.storage = StorageManager()
        self.ai = ClothingAI()
        self.db = DatabaseManager()
        
        logger.info("🚀 ClothingProcessor Worker initialisiert")
        logger.info(f"📡 Redis: {os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', 6379)}")
    
    def add_job(self, clothing_id: str, user_id: str, file_content_b64: str, 
                file_name: str, content_type: str, priority: int = 0) -> bool:
        """
        Fügt einen Verarbeitungs-Job zur Queue hinzu
        
        Args:
            clothing_id: UUID des Kleidungsstücks
            user_id: UUID des Nutzers
            file_content_b64: Base64-kodierter Dateiinhalt
            file_name: Dateiname
            content_type: MIME-Type
            priority: Priorität (0 = normal, höher = wichtiger)
            
        Returns:
            True wenn Job erfolgreich hinzugefügt
        """
        try:
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
            
            # Job zu Queue hinzufügen (Redis List)
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
            logger.error(f"❌ Fehler beim Hinzufügen des Jobs: {e}")
            return False
    
    def process_job(self, job_data: Dict[str, Any]) -> bool:
        """
        Verarbeitet einen einzelnen Job
        
        Args:
            job_data: Job-Daten aus der Queue
            
        Returns:
            True wenn erfolgreich verarbeitet
        """
        clothing_id = job_data['clothing_id']
        user_id = job_data['user_id']
        
        try:
            logger.info(f"🔄 Starte Verarbeitung für Kleidungsstück: {clothing_id}")
            
            # Status auf "processing" setzen
            self.db.update_processing_status(clothing_id, ProcessingStatus.PROCESSING)
            
            # File Content dekodieren
            import base64
            file_content = base64.b64decode(job_data['file_content_b64'])
            
            # 1. Kleidung aus Hintergrund extrahieren
            logger.info("🖼️ Extrahiere Kleidung aus Hintergrund...")
            extracted_image_bytes = self.ai.extract_clothing(file_content)
            
            # 2. Extrahiertes Bild hochladen
            extracted_path, extracted_url = self.storage.upload_processed_image(
                user_id=user_id,
                clothing_id=clothing_id,
                file_content=extracted_image_bytes,
                content_type=job_data['content_type']
            )
            
            # 3. AI-Analyse durchführen
            logger.info("🤖 Führe AI-Analyse durch...")
            ai_analysis = self.ai.analyze_clothing_image(extracted_image_bytes)
            
            # 4. Verarbeitung als abgeschlossen markieren
            completed_item = self.db.complete_clothing_processing(
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
            
            logger.info(f"✅ Verarbeitung abgeschlossen für: {clothing_id}")
            logger.info(f"🎯 Erkannt: {ai_analysis['category']} ({ai_analysis['color']}, {ai_analysis['style']})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Fehler bei der Verarbeitung von {clothing_id}: {e}")
            
            # Fehler in DB markieren
            try:
                self.db.mark_processing_failed(clothing_id, str(e))
            except Exception as db_error:
                logger.error(f"❌ Zusätzlicher DB-Fehler: {db_error}")
            
            return False
    
    def handle_failed_job(self, job_data: Dict[str, Any]) -> None:
        """
        Behandelt fehlgeschlagene Jobs (Retry-Logik)
        
        Args:
            job_data: Fehlgeschlagene Job-Daten
        """
        retry_count = job_data.get('retry_count', 0)
        max_retries = int(os.getenv('MAX_RETRIES', '3'))
        
        if retry_count < max_retries:
            # Retry-Count erhöhen
            job_data['retry_count'] = retry_count + 1
            job_data['retry_at'] = datetime.utcnow().isoformat()
            
            # Zurück in die Retry-Queue
            retry_json = json.dumps(job_data)
            self.redis_client.rpush(self.retry_queue, retry_json)
            
            logger.warning(f"🔄 Job {job_data['clothing_id']} für Retry vorgemerkt (Versuch {retry_count + 1}/{max_retries})")
        else:
            logger.error(f"❌ Job {job_data['clothing_id']} endgültig fehlgeschlagen nach {max_retries} Versuchen")
    
    def process_retry_queue(self) -> None:
        """Verarbeitet Jobs aus der Retry-Queue"""
        try:
            # Retry-Job holen (mit Timeout)
            retry_data = self.redis_client.blpop(self.retry_queue, timeout=1)
            
            if retry_data:
                _, job_json = retry_data
                job_data = json.loads(job_json)
                
                retry_count = job_data.get('retry_count', 0)
                logger.info(f"🔄 Verarbeite Retry-Job: {job_data['clothing_id']} (Versuch {retry_count})")
                
                # Job erneut verarbeiten
                success = self.process_job(job_data)
                
                if not success:
                    self.handle_failed_job(job_data)
                    
        except Exception as e:
            logger.error(f"❌ Fehler bei Retry-Queue Verarbeitung: {e}")
    
    def run(self) -> None:
        """
        Hauptschleife des Workers
        Wartet auf Jobs und verarbeitet sie
        """
        logger.info("🚀 Worker gestartet - Warte auf Jobs...")
        
        # Health Check der Services
        if not self._health_check():
            logger.error("❌ Health Check fehlgeschlagen - Worker wird beendet")
            sys.exit(1)
        
        while True:
            try:
                # Retry-Queue zuerst verarbeiten
                self.process_retry_queue()
                
                # Haupt-Queue verarbeiten (blockierend mit Timeout)
                job_data = self.redis_client.blpop(self.queue_name, timeout=5)
                
                if job_data:
                    # Job aus Queue holen
                    _, job_json = job_data
                    job_data_dict = json.loads(job_json)
                    
                    clothing_id = job_data_dict['clothing_id']
                    logger.info(f"📦 Neuer Job empfangen: {clothing_id}")
                    
                    # Job verarbeiten
                    success = self.process_job(job_data_dict)
                    
                    if not success:
                        self.handle_failed_job(job_data_dict)
                
                # Kurze Pause zwischen Iterationen
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                logger.info("🛑 Worker wird beendet (Ctrl+C)")
                break
            except Exception as e:
                logger.error(f"❌ Unerwarteter Fehler in Worker-Schleife: {e}")
                time.sleep(5)  # Längere Pause bei Fehlern
    
    def _health_check(self) -> bool:
        """
        Überprüft die Verbindungen zu allen Services
        
        Returns:
            True wenn alle Services erreichbar
        """
        try:
            # Redis Check
            self.redis_client.ping()
            logger.info("✅ Redis-Verbindung OK")
            
            # Storage Check
            storage_ok = self.storage.health_check()
            logger.info(f"✅ Storage: {'OK' if storage_ok else 'FEHLER'}")
            
            # Database Check
            db_ok = self.db.health_check()
            logger.info(f"✅ Database: {'OK' if db_ok else 'FEHLER'}")
            
            # AI Check
            ai_ok = self.ai.health_check()
            logger.info(f"✅ AI: {'OK' if ai_ok else 'FEHLER'}")
            
            return storage_ok and db_ok and ai_ok
            
        except Exception as e:
            logger.error(f"❌ Health Check Fehler: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Holt Statistiken über die Queues
        
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


def main():
    """Hauptfunktion - startet den Worker"""
    print("""
    🧥 Wardroberry Clothing Processor Worker
    ========================================
    
    Verarbeitet Kleidungsstücke aus Redis Queue:
    - Hintergrund-Extraktion
    - AI-Analyse 
    - Database-Updates
    
    Drücken Sie Ctrl+C zum Beenden.
    """)
    
    # Worker erstellen und starten
    processor = ClothingProcessor()
    processor.run()


if __name__ == "__main__":
    main() 