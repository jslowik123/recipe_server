import os
import logging
from typing import Optional, BinaryIO, Tuple
from uuid import uuid4
import mimetypes
from supabase import create_client, Client


class StorageManager:
    """
    StorageManager für Wardroberry App mit Supabase Storage
    Verwaltet Upload, Download und Validierung von Bilddateien
    """
    
    def __init__(self, user_token: str):
        """
        Initialisiert den StorageManager mit Supabase

        Args:
            user_token: JWT token for authenticated requests (respects RLS)
        """
        self.logger = logging.getLogger(__name__)
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_ANON_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL und ANON_KEY müssen gesetzt sein")

        if not user_token:
            raise ValueError("User Token ist erforderlich")

        # Create client with anon key
        self.client: Client = create_client(
            self.supabase_url,
            self.supabase_key
        )

        # Set user token for authenticated requests (respects RLS)
        self.client.postgrest.auth(user_token)

        # Set authorization header for storage operations
        self.client.storage._client.headers['Authorization'] = f'Bearer {user_token}'

        self.original_bucket = "clothing-images-original"  # Originale Uploads
        self.processed_bucket = "clothing-images-processed"  # Verarbeitete/extrahierte Bilder
    
    def validate_image_file(self, content_type: str, file_size: int) -> tuple[bool, str]:
        """
        Validiert eine Bilddatei
        
        Args:
            content_type: MIME-Type der Datei
            file_size: Größe der Datei in Bytes
            
        Returns:
            Tuple (is_valid, error_message)
        """
        # Erlaubte MIME-Types
        allowed_types = [
            'image/jpeg',
            'image/jpg', 
            'image/png',
            'image/webp',
            'image/gif'
        ]
        
        # Content-Type prüfen
        if content_type not in allowed_types:
            return False, f"Dateityp nicht erlaubt. Erlaubt: {', '.join(allowed_types)}"
        
        # Dateigröße prüfen (10MB Maximum)
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            return False, f"Datei zu groß. Maximum: {max_size // (1024*1024)}MB"
        
        # Minimale Dateigröße
        min_size = 1024  # 1KB
        if file_size < min_size:
            return False, "Datei zu klein"
        
        return True, ""
    
    def upload_original_image(self, user_id: str, file_content: bytes, 
                            file_name: str, content_type: str) -> Tuple[str, str]:
        """
        Lädt das originale Kleidungsbild in Supabase Storage hoch
        
        Args:
            user_id: UUID des Nutzers (für RLS)
            file_content: Binärdaten der Datei
            file_name: Ursprünglicher Dateiname
            content_type: MIME-Type
            
        Returns:
            Tuple (file_path, public_url)
        """
        try:
            # Eindeutigen Dateinamen generieren
            file_extension = self._get_file_extension(content_type)
            unique_filename = f"{user_id}/{uuid4()}{file_extension}"
            
            # In Supabase Storage hochladen
            self.client.storage.from_(self.original_bucket).upload(
                path=unique_filename,
                file=file_content,
                file_options={
                    "content-type": content_type,
                    "upsert": False  # Keine Überschreibung
                }
            )

            # Signierte URL generieren (für private Buckets, 1 Jahr gültig)
            signed_url_response = self.client.storage.from_(self.original_bucket).create_signed_url(
                path=unique_filename,
                expires_in=31536000  # 1 Jahr in Sekunden
            )
            signed_url = signed_url_response.get('signedURL') if signed_url_response else None

            if not signed_url:
                raise Exception("Signierte URL konnte nicht erstellt werden")

            self.logger.info(f"Original-Bild hochgeladen: {unique_filename}")
            return unique_filename, signed_url
            
        except Exception as e:
            self.logger.error(f"Fehler beim Hochladen des Original-Bildes: {e}")
            raise
    
    def upload_processed_image(self, user_id: str, clothing_id: str, file_content: bytes, 
                             content_type: str) -> Tuple[str, str]:
        """
        Lädt das verarbeitete/extrahierte Bild hoch
        
        Args:
            user_id: UUID des Nutzers
            clothing_id: UUID des Kleidungsstücks
            file_content: Verarbeitete Bilddaten
            content_type: MIME-Type
            
        Returns:
            Tuple (file_path, public_url)
        """
        try:
            file_extension = self._get_file_extension(content_type)
            unique_filename = f"{user_id}/{clothing_id}_processed{file_extension}"
            
            self.client.storage.from_(self.processed_bucket).upload(
                path=unique_filename,
                file=file_content,
                file_options={
                    "content-type": content_type,
                    "upsert": True  # Überschreibung erlaubt für Updates
                }
            )

            # Signierte URL generieren (für private Buckets, 1 Jahr gültig)
            signed_url_response = self.client.storage.from_(self.processed_bucket).create_signed_url(
                path=unique_filename,
                expires_in=31536000  # 1 Jahr in Sekunden
            )
            signed_url = signed_url_response.get('signedURL') if signed_url_response else None

            if not signed_url:
                raise Exception("Signierte URL konnte nicht erstellt werden")

            self.logger.info(f"Verarbeitetes Bild hochgeladen: {unique_filename}")
            return unique_filename, signed_url
            
        except Exception as e:
            self.logger.error(f"Fehler beim Hochladen des verarbeiteten Bildes: {e}")
            raise
    
    def delete_image(self, bucket_name: str, file_path: str) -> bool:
        """
        Löscht ein Bild aus Supabase Storage

        Args:
            bucket_name: Name des Storage Buckets
            file_path: Pfad zur Datei

        Returns:
            True wenn erfolgreich gelöscht
        """
        try:
            self.client.storage.from_(bucket_name).remove([file_path])
            self.logger.info(f"Bild gelöscht: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Fehler beim Löschen des Bildes: {e}")
            return False

    def delete_image_by_url(self, bucket_name: str, public_url: str) -> bool:
        """
        Löscht ein Bild aus Supabase Storage anhand der Public URL

        Args:
            bucket_name: Name des Storage Buckets
            public_url: Öffentliche URL des Bildes

        Returns:
            True wenn erfolgreich gelöscht
        """
        file_path = self._extract_path_from_url(public_url, bucket_name)
        return self.delete_image(bucket_name, file_path)
    
    def _get_file_extension(self, content_type: str) -> str:
        """Ermittelt Dateierweiterung basierend auf MIME-Type"""
        extensions = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/gif': '.gif'
        }
        return extensions.get(content_type, '.jpg')

    def _extract_path_from_url(self, public_url: str, bucket_name: str) -> str:
        """
        Extrahiert den Dateipfad aus einer Supabase Public URL

        Args:
            public_url: Die öffentliche URL
            bucket_name: Name des Buckets

        Returns:
            Der Dateipfad innerhalb des Buckets
        """
        # Format: {SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}
        try:
            path_prefix = f"/storage/v1/object/public/{bucket_name}/"
            if path_prefix in public_url:
                return public_url.split(path_prefix)[1]
            # Fallback: Versuche nur den letzten Teil nach dem Bucket-Namen
            parts = public_url.split(f"{bucket_name}/")
            if len(parts) > 1:
                return parts[1]
            # Wenn nichts funktioniert, gib die URL zurück (wird wahrscheinlich fehlschlagen)
            self.logger.warning(f"Konnte Pfad nicht aus URL extrahieren: {public_url}")
            return public_url
        except Exception as e:
            self.logger.error(f"Fehler beim Extrahieren des Pfads aus URL: {e}")
            return public_url
    
    def health_check(self) -> bool:
        """
        Überprüft die Storage-Verbindung
        
        Returns:
            True wenn Verbindung funktioniert
        """
        try:
            # Teste Bucket-Zugriff
            self.client.storage.list_buckets()
            return True
        except Exception as e:
            self.logger.error(f"Storage-Verbindung fehlgeschlagen: {e}")
            return False 