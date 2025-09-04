import os
from celery import Celery, states
from celery.exceptions import Ignore
import requests
from apify_client import ApifyClient
from openai import OpenAI
from dotenv import load_dotenv
import time
import json
import traceback
from typing import List
from pydantic import BaseModel
import cv2
import base64
import tempfile
import logging

# Configure logging (console only)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console output, no log files
    ]
)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()


class TikTokWorker:
    def __init__(self, video_url, max_frames = 20):
        self.post_url = video_url
        self.max_frames = max_frames

    def download_and_extract_frames(self, video_url):
        """
        Download video and extract frames as base64 encoded images
        """
        video_path = None
        
        try:
            response = requests.get(video_url, stream=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)

            if response.status_code != 200:
                logger.error(f"❌ Failed to download video: HTTP {response.status_code}")
                return []
            
            # Get content length if available
            content_length = response.headers.get('content-length')

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
                total_size = 0
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                    total_size += len(chunk)
                video_path = tmp_file.name
                logger.info(f"💾 Downloaded {total_size / 1024 / 1024:.1f} MB to {video_path}")
            
            # Extract frames
            logger.info(f"🎞️ Opening video file for frame extraction...")
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"❌ Could not open video file: {video_path}")
                os.remove(video_path)
                return []
            
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
                    height, width = frame.shape[:2]
                    resized = cv2.resize(frame, (256, 144))
                    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    base64_frame = base64.b64encode(buffer).decode("utf-8")
                    frames.append(base64_frame)
                    
                    logger.debug(f"🖼️ Extracted frame {len(frames)}/{self.max_frames} at position {frame_count}/{total_frames} (original: {width}x{height}, resized: 256x144)")
                
                frame_count += 1
            
            cap.release()
            os.remove(video_path)
            
            logger.info(f"✅ Successfully extracted {len(frames)} frames from video")
            return frames
            
        except Exception as e:
            logger.error(f"❌ Frame extraction failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            
            # Clean up temp file if it exists
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    logger.info(f"🧹 Cleaned up temporary file: {video_path}")
                except:
                    pass
            
            return []
        
    def init_apify(self):
        # Initialize Apify client
        apify_token = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
        
        # Debug: Check if token is loaded
        if not apify_token:
            logger.error("❌ APIFY_API_TOKEN not found in environment")
            raise ValueError("APIFY_API_TOKEN or APIFY_API_KEY not found in environment variables. Please check your .env file.")
        
        logger.info(f"🔑 Using Apify token: {apify_token[:8]}...{apify_token[-4:]}")
        self.client = ApifyClient(apify_token)
        
    def start_run(self):
        # Scrape single video
        run_input = {
            "postURLs": [self.post_url],
            "scrapeRelatedVideos": False,
            "resultsPerPage": 1,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
            "shouldDownloadSlideshowImages": False,
        }
        
        # Run the scraper
        # Note: self.update_state wird von der aufrufenden Celery-Task bereitgestellt
        
        try:
            run = self.client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
        except Exception as apify_error:
            error_msg = str(apify_error)
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(f"Apify API authentication failed. Please check your APIFY_API_TOKEN in .env file. Error: {error_msg}")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ValueError(f"Apify API access forbidden. Check your token permissions. Error: {error_msg}")
            else:
                raise ValueError(f"Apify API error: {error_msg}")
        
        video_data = {
            "url": self.post_url,
            "text": "",
            "subtitles": None,
            "processed_recipe": None
        }
        return run, video_data, self.client.dataset
    
    def download_subtitles(self, video_data, item):
        subtitle_links = []
        if "videoMeta" in item:
            if "subtitleLinks" in item["videoMeta"] and item["videoMeta"]["subtitleLinks"]:
                subtitle_links = item["videoMeta"]["subtitleLinks"]
                logger.info(f"🔍 Found {len(subtitle_links)} subtitle links")
                        
                        # Try all subtitle links, not just the first one
                for subtitle_link in subtitle_links:
                    try:
                        subtitle_url = subtitle_link.get("downloadLink")
                        if subtitle_url:
                            transcript_response = requests.get(subtitle_url, timeout=15)
                            if transcript_response.status_code == 200:
                                video_data["subtitles"] = transcript_response.text
                                break
                            else:
                                logger.warning(f"⚠️ Subtitle download failed with status: {transcript_response.status_code}")
                    except Exception as subtitle_error:
                        logger.error(f"❌ Error downloading subtitle: {subtitle_error}")
                else:
                        logger.info("🚫 No subtitle links found in videoMeta")
        else:
                    logger.info("🚫 No videoMeta found in item")
                
        if not video_data.get("subtitles"):
            logger.warning("⚠️ No subtitles were successfully downloaded")

    def extract_video_frames(self, item):
        frames = []
        video_download_url = None
                
        # Try multiple sources for video URL
        if "mediaUrls" in item and item["mediaUrls"] and len(item["mediaUrls"]) > 0:
            video_download_url = item["mediaUrls"][0]
        elif "videoMeta" in item and item["videoMeta"] and "downloadAddr" in item["videoMeta"]:
            video_download_url = item["videoMeta"]["downloadAddr"]
        elif "videoMeta" in item and item["videoMeta"] and "playAddr" in item["videoMeta"]:
            video_download_url = item["videoMeta"]["playAddr"]
        else:
            logger.warning("⚠️ No video download URL found in any expected location")

                
        if video_download_url:
            frames = self.download_and_extract_frames(video_download_url)
        else:
            logger.error("❌ No video URL available for frame extraction")
        return frames
    

    def process_text_with_ai(self, text: str, language: str = ""):
        """
        Fallback: Process text with OpenAI to extract structured recipe
        """
        logger.info(f"📝 Starting text-only AI processing with {len(text)} characters")
        
        try:
            client = OpenAI()
            
            if not text or len(text.strip()) < 10:
                logger.warning("⚠️ Text too short or empty for meaningful processing")
                return {
                    "title": "Untitled Recipe",
                    "ingredients": [],
                    "steps": ["Text zu kurz oder leer für Rezept-Extraktion"]
                }
            
            logger.info(f"🚀 Sending text to OpenAI gpt-4o-mini...")
            response = client.chat.completions.create(
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
                        
                        Antworte nur mit JSON: {{\"title\": \"Aussagekräftiger Titel\", \"ingredients\": [\"Zutat mit Menge\"], \"steps\": [\"Detaillierter Schritt\"]}}"""
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
            
            try:
                # Try parsing the JSON
                if content.startswith('{'):
                    recipe = json.loads(content)
                else:
                    # Extract JSON from response
                    import re
                    json_match = re.search(r'{.*?}', content, re.DOTALL)
                    if json_match:
                        recipe = json.loads(json_match.group(0))
                    else:
                        raise ValueError("No JSON found in response")
                
                logger.info(f"✅ Text-only processing successful: {recipe.get('title', 'N/A')}")
                return recipe
                
            except (json.JSONDecodeError, ValueError) as parse_error:
                logger.error(f"❌ JSON parsing failed in text fallback: {parse_error}")
                logger.error(f"💬 Raw response: {content}")
                return {
                    "title": "Untitled Recipe",
                    "ingredients": [],
                    "steps": ["Konnte kein strukturiertes Rezept aus Text extrahieren"]
                }
            
        except Exception as e:
            logger.error(f"❌ Text-only processing failed: {e}")
            return {
                "title": "Untitled Recipe",
                "ingredients": [],
                "steps": [f"Fehler bei Text-Verarbeitung: {str(e)}"]
            }
    
    def process_video_with_openai(self, text: str = "", subtitles: str = "", frames: List[str] = None, url: str = "", task_id: str = "", language: str = ""):
        """
        Process video frames and text with OpenAI for recipe extraction
        """
        logger.info(f"🤖 Starting OpenAI processing for task {task_id}")
        
        try:
            # Validate OpenAI API key
            openai_key = os.getenv('OPENAI_API_KEY')
            if not openai_key:
                logger.error("❌ OPENAI_API_KEY not found in environment")
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            
            logger.info(f"🔑 Using OpenAI API key: {openai_key[:8]}...{openai_key[-4:]}")
            client = OpenAI()
            
            # Combine text sources
            combined_text = ""
            if subtitles:
                combined_text += f"SUBTITLES: {subtitles}\n\n"
                logger.info(f"📝 Added subtitles: {len(subtitles)} characters")
            if text and text != subtitles:
                combined_text += f"TEXT: {text}\n\n"
                logger.info(f"📝 Added text: {len(text)} characters")
            
            logger.info(f"📋 Total text input: {len(combined_text)} characters")
            logger.info(f"🖼️ Frame input: {len(frames) if frames else 0} frames")
            
            if not combined_text and not frames:
                logger.warning("⚠️ No text or frames available for processing")
                return {
                    "title": "Untitled Recipe",
                    "ingredients": [],
                    "steps": ["Keine Daten zum Verarbeiten gefunden"]
                }
            
            # Build message content
            user_content = []
            
            if combined_text:
                # Language-specific prompts
                if language.lower() == "en":
                    prompt_text = f"""Reconstruct the complete recipe from the following information:

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
                    prompt_text = f"""Rekonstruiere das komplette Rezept aus folgenden Informationen:

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

                user_content.append({
                    "type": "text",
                    "text": prompt_text
                })
            else:
                user_content.append({
                    "type": "text", 
                    "text": f"""Analysiere alle {len(frames)} Video-Frames einzeln und rekonstruiere das komplette Rezept:

    FRAME-ANALYSE:
    - Bild 1: Was siehst du? Welche Zutaten/Schritte?
    - Bild 2: Was passiert hier? Welche Veränderungen?
    - Bild 3-{len(frames)}: Fortsetzung der Analyse...

    Rekonstruiere daraus ein vollständiges Rezept auch wenn nicht alles explizit gezeigt wird. Nutze dein Kochwissen um ein authentisches, kochbares Rezept zu erstellen.

    Antworte mit JSON: {{"title": "Kurzer Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge"], "steps": ["detaillierter Schritt"]}}"""
                })
            
            # Add frames if available - ALLE Frames für detaillierte Analyse
            if frames:
                for i, frame in enumerate(frames, 1):  # ALLE verfügbaren Frames
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{frame}"}
                    })
            
            start_time = time.time()
            model_used = "gpt-4o-mini"
            
            logger.info(f"🚀 Sending request to OpenAI {model_used}...")
            logger.info(f"📊 Request contains: {len(user_content)} content items")
            
            try:
                response = client.chat.completions.create(
                    model=model_used,
                    messages=[
                        {
                            "role": "system",
                            "content": f"""Du bist ein erfahrener Koch und Rezept-Experte. Analysiere JEDES einzelne Video-Frame detailliert und rekonstruiere das komplette Rezept. Antworte in {"English" if language == "en" else "deutscher"} Sprache.

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
            except Exception as api_error:
                logger.error(f"❌ OpenAI API error: {api_error}")
                raise api_error
            
            processing_time = time.time() - start_time
            
            # Extract token usage
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else 0
            print(f"Prompt Tokens: {prompt_tokens}, Completion Tokens: {completion_tokens} ")
            
            
            content = response.choices[0].message.content.strip()
            logger.info(f"💬 OpenAI response length: {len(content)} characters")
            logger.info(f"💬 First 200 chars: {content[:200]}...")
            
            # Parse JSON response with enhanced error handling
            recipe_json = None
            try:
                # Try direct JSON parsing first
                if content.startswith('{') and content.endswith('}'):
                    recipe_json = json.loads(content)
                    logger.info("✅ Direct JSON parsing successful")
                else:
                    # Try to extract JSON from markdown or other formatting
                    import re
                    # More flexible JSON extraction
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
                                logger.info(f"✅ JSON extraction successful with pattern: {pattern[:20]}...")
                                break
                            except json.JSONDecodeError:
                                continue
                    
                    if not recipe_json:
                        logger.warning("⚠️ No valid JSON found, creating fallback structure")
                        recipe_json = {"title": "Untitled Recipe", "ingredients": [], "steps": []}
                        
            except json.JSONDecodeError as json_error:
                logger.error(f"❌ JSON parsing failed: {json_error}")
                logger.error(f"💬 Raw content: {content}")
                recipe_json = {"title": "Untitled Recipe", "ingredients": [], "steps": []}
            
            # Validate structure
            if not isinstance(recipe_json.get("title"), str):
                recipe_json["title"] = "Untitled Recipe"
            if not isinstance(recipe_json.get("ingredients"), list):
                recipe_json["ingredients"] = []
            if not isinstance(recipe_json.get("steps"), list):
                recipe_json["steps"] = []
            
            # Log final recipe structure
            logger.info(f"🍽️ Final recipe: Title='{recipe_json.get('title', 'N/A')}', Ingredients={len(recipe_json.get('ingredients', []))}, Steps={len(recipe_json.get('steps', []))}")
            
            logger.info(f"📊 Processing successful - Tokens: {total_tokens}")
                
            return recipe_json
            
        except Exception as e:
            logger.error(f"❌ OpenAI processing failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            
            
            # Fallback to text-only processing
            logger.info("🔄 Attempting fallback to text-only processing...")
            return self.process_text_with_ai(text or subtitles, language)


                        
                        