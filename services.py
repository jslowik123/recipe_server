"""
Service layer for TikTok scraping operations
"""
import os
import json
import time
import base64
import tempfile
import traceback
import logging
from typing import List, Dict, Any, Optional

import cv2
import requests
from apify_client import ApifyClient
from openai import OpenAI

from config import config
from exceptions import (
    ApifyError, OpenAIError, VideoProcessingError, 
    VideoDownloadError, FrameExtractionError
)

logger = logging.getLogger(__name__)


class ApifyService:
    """Service for handling Apify API operations"""
    
    def __init__(self):
        self.client = ApifyClient(config.apify_token)
        logger.info(f"🔑 Apify client initialized with token: {config.apify_token[:8]}...{config.apify_token[-4:]}")
    
    def scrape_video(self, video_url: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Scrape a single TikTok video using Apify
        
        Returns:
            tuple: (run_result, video_data_dict)
        """
        run_input = {
            "postURLs": [video_url],
            "scrapeRelatedVideos": False,
            "resultsPerPage": 1,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
            "shouldDownloadSlideshowImages": False,
        }
        
        try:
            logger.info(f"🚀 Starting Apify scraper for: {video_url}")
            run = self.client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
            
            video_data = {
                "url": video_url,
                "text": "",
                "subtitles": None,
                "processed_recipe": None
            }
            
            return run, video_data
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise ApifyError(f"Apify API authentication failed. Check your APIFY_API_TOKEN. Error: {error_msg}")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ApifyError(f"Apify API access forbidden. Check token permissions. Error: {error_msg}")
            else:
                raise ApifyError(f"Apify API error: {error_msg}")


class VideoProcessor:
    """Service for video processing operations"""
    
    def __init__(self, max_frames: int = 20):
        self.max_frames = max_frames
    
    def extract_subtitles(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract subtitles from Apify item"""
        subtitle_links = []
        
        if "videoMeta" in item:
            if "subtitleLinks" in item["videoMeta"] and item["videoMeta"]["subtitleLinks"]:
                subtitle_links = item["videoMeta"]["subtitleLinks"]
                logger.info(f"🔍 Found {len(subtitle_links)} subtitle links")
                
                # Try all subtitle links
                for subtitle_link in subtitle_links:
                    try:
                        subtitle_url = subtitle_link.get("downloadLink")
                        if subtitle_url:
                            response = requests.get(subtitle_url, timeout=15)
                            if response.status_code == 200:
                                logger.info("✅ Successfully downloaded subtitles")
                                return response.text
                            else:
                                logger.warning(f"⚠️ Subtitle download failed with status: {response.status_code}")
                    except Exception as e:
                        logger.error(f"❌ Error downloading subtitle: {e}")
            else:
                logger.info("🚫 No subtitle links found in videoMeta")
        else:
            logger.info("🚫 No videoMeta found in item")
        
        logger.warning("⚠️ No subtitles were successfully downloaded")
        return None
    
    def extract_frames(self, item: Dict[str, Any]) -> List[str]:
        """Extract video frames from Apify item"""
        video_download_url = self._get_video_url(item)
        
        if video_download_url:
            return self._download_and_extract_frames(video_download_url)
        else:
            logger.error("❌ No video URL available for frame extraction")
            return []
    
    def _get_video_url(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract video download URL from various possible locations in item"""
        if "mediaUrls" in item and item["mediaUrls"] and len(item["mediaUrls"]) > 0:
            return item["mediaUrls"][0]
        elif "videoMeta" in item and item["videoMeta"] and "downloadAddr" in item["videoMeta"]:
            return item["videoMeta"]["downloadAddr"]
        elif "videoMeta" in item and item["videoMeta"] and "playAddr" in item["videoMeta"]:
            return item["videoMeta"]["playAddr"]
        else:
            logger.warning("⚠️ No video download URL found in any expected location")
            return None
    
    def _download_and_extract_frames(self, video_url: str) -> List[str]:
        """Download video and extract frames as base64 encoded images"""
        video_path = None
        
        try:
            response = requests.get(video_url, stream=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)

            if response.status_code != 200:
                raise VideoDownloadError(f"Failed to download video: HTTP {response.status_code}")
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
                total_size = 0
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                    total_size += len(chunk)
                video_path = tmp_file.name
                logger.info(f"💾 Downloaded {total_size / 1024 / 1024:.1f} MB to {video_path}")
            
            # Extract frames
            return self._extract_frames_from_file(video_path)
            
        except Exception as e:
            if isinstance(e, VideoDownloadError):
                raise
            raise VideoProcessingError(f"Frame extraction failed: {e}")
        finally:
            # Clean up temp file
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    logger.info(f"🧹 Cleaned up temporary file: {video_path}")
                except Exception:
                    logger.warning(f"⚠️ Failed to clean up temporary file: {video_path}")
    
    def _extract_frames_from_file(self, video_path: str) -> List[str]:
        """Extract frames from video file"""
        logger.info(f"🎞️ Opening video file for frame extraction...")
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise FrameExtractionError(f"Could not open video file: {video_path}")
        
        try:
            frames = []
            frame_count = 0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"📊 Video info: {total_frames} frames, {fps:.1f} FPS, {duration:.1f}s duration")
            
            # Extract frames evenly distributed across video
            frame_interval = max(1, total_frames // self.max_frames)
            logger.info(f"🔢 Extracting every {frame_interval}th frame (max {self.max_frames} frames)")
            
            while cap.isOpened() and len(frames) < self.max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_count % frame_interval == 0:
                    # Resize frame to reduce size
                    resized = cv2.resize(frame, (256, 144))
                    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    base64_frame = base64.b64encode(buffer).decode("utf-8")
                    frames.append(base64_frame)
                    
                    logger.debug(f"🖼️ Extracted frame {len(frames)}/{self.max_frames}")
                
                frame_count += 1
            
            logger.info(f"✅ Successfully extracted {len(frames)} frames from video")
            return frames
            
        finally:
            cap.release()


class OpenAIService:
    """Service for OpenAI API operations"""
    
    def __init__(self):
        self.client = OpenAI(api_key=config.openai_api_key)
        logger.info(f"🔑 OpenAI client initialized with key: {config.openai_api_key[:8]}...{config.openai_api_key[-4:]}")
    
    def process_video_content(
        self, 
        text: str = "", 
        subtitles: str = "", 
        frames: List[str] = None, 
        language: str = ""
    ) -> Dict[str, Any]:
        """
        Process video content with OpenAI for recipe extraction
        """
        try:
            # Combine text sources
            combined_text = self._combine_text_sources(text, subtitles)
            
            logger.info(f"📋 Total text input: {len(combined_text)} characters")
            logger.info(f"🖼️ Frame input: {len(frames) if frames else 0} frames")
            
            if not combined_text and not frames:
                logger.warning("⚠️ No text or frames available for processing")
                return self._create_fallback_recipe("Keine Daten zum Verarbeiten gefunden")
            
            # Build message content
            user_content = self._build_user_content(combined_text, frames, language)
            
            # Make OpenAI request
            response = self._make_openai_request(user_content, language)
            
            # Process response
            return self._process_openai_response(response)
            
        except Exception as e:
            logger.error(f"❌ OpenAI processing failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            
            # Fallback to text-only processing
            if text or subtitles:
                logger.info("🔄 Attempting fallback to text-only processing...")
                return self._process_text_only(text or subtitles, language)
            
            return self._create_fallback_recipe(f"Fehler bei Verarbeitung: {str(e)}")
    
    def _combine_text_sources(self, text: str, subtitles: str) -> str:
        """Combine text and subtitles into single string"""
        combined_text = ""
        if subtitles:
            combined_text += f"SUBTITLES: {subtitles}\n\n"
            logger.info(f"📝 Added subtitles: {len(subtitles)} characters")
        if text and text != subtitles:
            combined_text += f"TEXT: {text}\n\n"
            logger.info(f"📝 Added text: {len(text)} characters")
        return combined_text
    
    def _build_user_content(self, combined_text: str, frames: List[str], language: str) -> List[Dict[str, Any]]:
        """Build user content for OpenAI request"""
        user_content = []
        
        if combined_text:
            prompt_text = self._get_prompt_text(combined_text, frames, language)
            user_content.append({"type": "text", "text": prompt_text})
        else:
            frame_prompt = self._get_frame_only_prompt(frames, language)
            user_content.append({"type": "text", "text": frame_prompt})
        
        # Add frames if available
        if frames:
            for frame in frames:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{frame}"}
                })
        
        return user_content
    
    def _get_prompt_text(self, combined_text: str, frames: List[str], language: str) -> str:
        """Get appropriate prompt text based on language"""
        if language.lower() == "en":
            return f"""Reconstruct the complete recipe from the following information:

{combined_text}

DETAILED ANALYSIS OF ALL VIDEO FRAMES:
Analyze each of the {len(frames)} images individually:
- What do you see in image 1, 2, 3, etc.?
- Which ingredients are visible?
- Which cooking steps are shown?
- What quantities can you estimate?
- Which techniques are being used?

Reconstruct a complete, cookable recipe with:
- A descriptive title (e.g., "Creamy Pasta Carbonara" or "Quick Vegetable Stir-fry")
- Specific ingredients with realistic quantities
- Detailed preparation steps
- Add missing but necessary steps

Respond with complete JSON: {{"title": "Short, descriptive recipe title", "ingredients": ["specific ingredient with quantity"], "steps": ["detailed step with times/temperatures"]}}"""
        else:  # German (default)
            return f"""Rekonstruiere das komplette Rezept aus folgenden Informationen:

{combined_text}

DETAILANALYSE ALLER VIDEO-FRAMES:
Analysiere jedes der {len(frames)} Bilder einzeln:
- Was siehst du in Bild 1, 2, 3, etc.?
- Welche Zutaten sind sichtbar?
- Welche Kochschritte werden gezeigt?
- Welche Mengen kannst du schätzen?
- Welche Techniken werden verwendet?

Rekonstruiere daraus ein vollständiges, kochbares Rezept mit:
- Einem aussagekräftigen Titel (z.B. "Cremige Pasta Carbonara" oder "Schnelle Gemüsepfanne")
- Konkreten Zutaten und realistischen Mengen
- Detaillierten Zubereitungsschritten
- Ergänze fehlende aber notwendige Schritte

Antworte mit vollständigem JSON: {{"title": "Kurzer, aussagekräftiger Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge"], "steps": ["detaillierter Schritt mit Zeiten/Temperaturen"]}}"""
    
    def _get_frame_only_prompt(self, frames: List[str], language: str) -> str:
        """Get prompt for frame-only processing"""
        return f"""Analysiere alle {len(frames)} Video-Frames einzeln und rekonstruiere das komplette Rezept:

FRAME-ANALYSE:
- Bild 1: Was siehst du? Welche Zutaten/Schritte?
- Bild 2: Was passiert hier? Welche Veränderungen?
- Bild 3-{len(frames)}: Fortsetzung der Analyse...

Rekonstruiere daraus ein vollständiges Rezept auch wenn nicht alles explizit gezeigt wird. Nutze dein Kochwissen um ein authentisches, kochbares Rezept zu erstellen.

Antworte mit JSON: {{"title": "Kurzer Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge"], "steps": ["detaillierter Schritt"]}}"""
    
    def _make_openai_request(self, user_content: List[Dict[str, Any]], language: str) -> Any:
        """Make request to OpenAI API"""
        logger.info(f"🚀 Sending request to OpenAI gpt-4o-mini...")
        logger.info(f"📊 Request contains: {len(user_content)} content items")
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(language)
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            logger.info(f"✅ OpenAI request successful")
            return response
            
        except Exception as e:
            raise OpenAIError(f"OpenAI API request failed: {e}")
    
    def _get_system_prompt(self, language: str) -> str:
        """Get system prompt based on language"""
        return f"""Du bist ein erfahrener Koch und Rezept-Experte. Analysiere JEDES einzelne Video-Frame detailliert und rekonstruiere das komplette Rezept. Antworte in {"English" if language == "en" else "deutscher"} Sprache.

WICHTIGE REGELN:
1. Schaue dir JEDES Bild genau an - analysiere Zutaten, Mengen, Kochgeschirr, Techniken
2. Rekonstruiere das Rezept auch wenn es nicht explizit gezeigt wird
3. Schätze Mengen basierend auf dem was du siehst (Tassen, Löffel, Portionsgrößen)
4. Leite Zubereitungsschritte aus den Bildern ab (was passiert in welcher Reihenfolge?)
5. Nutze dein Kochwissen um fehlende Schritte zu ergänzen (Gewürze, Garzeiten, Temperaturen)
6. Falls nur Beschreibung vorhanden: Erstelle ein vollständiges, authentisches Rezept basierend auf der Beschreibung

BEISPIEL für "Lasagne":
- Analysiere alle sichtbaren Zutaten in den Frames
- Rekonstruiere die Schichtung
- Ergänze typische Mengen und Zubereitungszeiten
- Gib konkrete, umsetzbare Schritte

Antworte IMMER mit vollständigem JSON: {{"title": "Kurzer, aussagekräftiger Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge", ...], "steps": ["detaillierter Schritt", ...]}}"""
    
    def _process_openai_response(self, response: Any) -> Dict[str, Any]:
        """Process OpenAI response and extract recipe JSON"""
        content = response.choices[0].message.content.strip()
        logger.info(f"💬 OpenAI response length: {len(content)} characters")
        
        # Parse JSON response with enhanced error handling
        recipe_json = self._parse_recipe_json(content)
        
        # Validate and fix structure
        recipe_json = self._validate_recipe_structure(recipe_json)
        
        logger.info(f"🍽️ Final recipe: Title='{recipe_json.get('title', 'N/A')}', Ingredients={len(recipe_json.get('ingredients', []))}, Steps={len(recipe_json.get('steps', []))}")
        
        return recipe_json
    
    def _parse_recipe_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON from OpenAI response with multiple fallback strategies"""
        try:
            # Try direct JSON parsing first
            if content.startswith('{') and content.endswith('}'):
                return json.loads(content)
            
            # Try to extract JSON from markdown or other formatting
            import re
            json_patterns = [
                r'```json\s*({.*?})\s*```',  # Markdown code blocks
                r'```\s*({.*?})\s*```',      # Generic code blocks
                r'({.*?"ingredients".*?"steps".*?})',  # JSON with required fields
                r'({.*?})'  # Any JSON-like structure
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, content, re.DOTALL)
                if json_match:
                    try:
                        recipe_json = json.loads(json_match.group(1))
                        logger.info(f"✅ JSON extraction successful with pattern")
                        return recipe_json
                    except json.JSONDecodeError:
                        continue
            
            logger.warning("⚠️ No valid JSON found, creating fallback structure")
            return self._create_fallback_recipe("Konnte JSON nicht parsen")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            return self._create_fallback_recipe("JSON parsing fehlgeschlagen")
    
    def _validate_recipe_structure(self, recipe_json: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fix recipe JSON structure"""
        if not isinstance(recipe_json.get("title"), str):
            recipe_json["title"] = "Untitled Recipe"
        if not isinstance(recipe_json.get("ingredients"), list):
            recipe_json["ingredients"] = []
        if not isinstance(recipe_json.get("steps"), list):
            recipe_json["steps"] = []
        
        return recipe_json
    
    def _process_text_only(self, text: str, language: str = "") -> Dict[str, Any]:
        """Fallback: Process text with OpenAI to extract structured recipe"""
        logger.info(f"📝 Starting text-only AI processing with {len(text)} characters")
        
        try:
            if not text or len(text.strip()) < 10:
                logger.warning("⚠️ Text too short or empty for meaningful processing")
                return self._create_fallback_recipe("Text zu kurz oder leer für Rezept-Extraktion")
            
            logger.info(f"🚀 Sending text to OpenAI gpt-4o-mini...")
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": f"""Du bist ein Rezept-Experte. Extrahiere aus dem gegebenen Text ein strukturiertes Rezept. Antworte in {"English" if language == "en" else "deutscher"} Sprache.
                        
Wenn der Text ein Rezept enthält, extrahiere:
                        - Einen beschreibenden Titel
                        - Alle Zutaten mit Mengenangaben
                        - Schritt-für-Schritt Anweisungen
                        
                        Wenn kein klares Rezept erkennbar ist, erstelle basierend auf der Beschreibung ein plausibles Rezept.
                        
                        Antworte nur mit JSON: {{"title": "Aussagekräftiger Titel", "ingredients": ["Zutat mit Menge"], "steps": ["Detaillierter Schritt"]}}"""
                    },
                    {
                        "role": "user", 
                        "content": f"Extrahiere oder rekonstruiere ein Rezept aus folgendem Text:\n\n{text[:2000]}"
                    }
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"💬 Text-only response: {len(content)} chars")
            
            recipe_json = self._parse_recipe_json(content)
            logger.info(f"✅ Text-only processing successful: {recipe_json.get('title', 'N/A')}")
            return recipe_json
            
        except Exception as e:
            logger.error(f"❌ Text-only processing failed: {e}")
            return self._create_fallback_recipe(f"Fehler bei Text-Verarbeitung: {str(e)}")
    
    def _create_fallback_recipe(self, error_message: str) -> Dict[str, Any]:
        """Create a fallback recipe structure"""
        return {
            "title": "Untitled Recipe",
            "ingredients": [],
            "steps": [error_message]
        }