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

# Pydantic Models for simple recipe response (nur Zutaten und Schritte)
class SimpleRecipeResponse(BaseModel):
    ingredients: List[str]
    steps: List[str]

def download_and_extract_frames(video_url: str, max_frames: int = 20):
    """
    Download video and extract frames as base64 encoded images
    """
    logger.info(f"🎬 Starting frame extraction from: {video_url}")
    video_path = None
    
    try:
        # Download video to temporary file
        logger.info(f"📥 Downloading video with timeout 30s...")
        response = requests.get(video_url, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=30)
        
        logger.info(f"📥 Video download response: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"❌ Failed to download video: HTTP {response.status_code}")
            return []
        
        # Get content length if available
        content_length = response.headers.get('content-length')
        if content_length:
            logger.info(f"📦 Video size: {int(content_length) / 1024 / 1024:.1f} MB")
        
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
        frame_interval = max(1, total_frames // max_frames)
        logger.info(f"🔢 Extracting every {frame_interval}th frame (max {max_frames} frames)")
        
        while cap.isOpened() and len(frames) < max_frames:
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
                
                logger.debug(f"🖼️ Extracted frame {len(frames)}/{max_frames} at position {frame_count}/{total_frames} (original: {width}x{height}, resized: 256x144)")
            
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
    

# Celery Setup
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
celery_app = Celery('tasks', broker=redis_url, backend=redis_url)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,  # Results expire after 1 hour
)

@celery_app.task(bind=True)
def scrape_tiktok_async(self, post_url: str, language: str):
    """
    Asynchronously scrape a single TikTok video and optionally process with AI
    """
    logger.info(f"🚀 Starting TikTok scraping task for: {post_url}")
    
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={
            'step': 1, 
            'total_steps': 5, 
            'status': 'Initializing Apify client...',
            'url': post_url,
            'details': 'Setting up scraping infrastructure'
        }) 
        
        # Initialize Apify client
        apify_token = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
        
        # Debug: Check if token is loaded
        if not apify_token:
            logger.error("❌ APIFY_API_TOKEN not found in environment")
            raise ValueError("APIFY_API_TOKEN or APIFY_API_KEY not found in environment variables. Please check your .env file.")
        
        logger.info(f"🔑 Using Apify token: {apify_token[:8]}...{apify_token[-4:]}")
        client = ApifyClient(apify_token)
        
        # Update progress - preparing scrape
        self.update_state(state='PROGRESS', meta={
            'step': 2, 
            'total_steps': 4, 
            'status': 'Preparing to scrape TikTok video...',
            'url': post_url,
            'details': 'Configuring scraping parameters and starting actor'
        })
            
        # Scrape single video
        run_input = {
            "postURLs": [post_url],
            "scrapeRelatedVideos": False,
            "resultsPerPage": 1,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
            "shouldDownloadSlideshowImages": False,
        }
        
        # Run the scraper
        self.update_state(state='PROGRESS', meta={
            'step': 3, 
            'total_steps': 4, 
            'status': 'Scraping TikTok video data...',
            'url': post_url,
            'details': 'Running Apify actor to extract video content and metadata'
        })
        
        try:
            run = client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
        except Exception as apify_error:
            error_msg = str(apify_error)
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(f"Apify API authentication failed. Please check your APIFY_API_TOKEN in .env file. Error: {error_msg}")
            elif "403" in error_msg or "Forbidden" in error_msg:
                raise ValueError(f"Apify API access forbidden. Check your token permissions. Error: {error_msg}")
            else:
                raise ValueError(f"Apify API error: {error_msg}")
        
        video_data = {
            "url": post_url,
            "text": "",
            "subtitles": None,
            "processed_recipe": None
        }
            
        if run and "defaultDatasetId" in run:
            dataset_id = run["defaultDatasetId"]
            
            # Get results from dataset
            logger.info(f"📋 Processing dataset results from: {dataset_id}")
            
            for item_idx, item in enumerate(client.dataset(dataset_id).iterate_items()):
                logger.info(f"📄 Processing item {item_idx + 1} from dataset")
                
                # Log available keys in the item
                logger.info(f"🔑 Available keys in item: {list(item.keys())}")
                
                # Check for scraping errors first
                if 'error' in item:
                    error_msg = item.get('error', 'Unknown error')
                    logger.error(f"❌ Apify scraping error: {error_msg}")
                    if 'not found or is private' in str(error_msg).lower():
                        raise ValueError(f"Video not accessible: {error_msg}. The video may be private, deleted, or the URL is invalid.")
                    else:
                        raise ValueError(f"Scraping failed: {error_msg}")
                
                video_data["text"] = item.get("text", "")
                logger.info(f"📝 Extracted text length: {len(video_data['text'])} characters")
                
                # Update progress - processing subtitles
                self.update_state(state='PROGRESS', meta={
                    'step': 4, 
                    'total_steps': 5, 
                    'status': 'Processing video content...',
                    'url': post_url,
                    'details': 'Extracting subtitles and preparing final data'
                })
                
                # Download subtitles if available - ENHANCED SUBTITLE EXTRACTION
                subtitle_links = []
                if "videoMeta" in item:
                    logger.info(f"🎥 Found videoMeta with keys: {list(item['videoMeta'].keys()) if item['videoMeta'] else 'None'}")
                    
                    if "subtitleLinks" in item["videoMeta"] and item["videoMeta"]["subtitleLinks"]:
                        subtitle_links = item["videoMeta"]["subtitleLinks"]
                        logger.info(f"🔍 Found {len(subtitle_links)} subtitle links")
                        
                        # Try all subtitle links, not just the first one
                        for i, subtitle_link in enumerate(subtitle_links):
                            try:
                                subtitle_url = subtitle_link.get("downloadLink")
                                if subtitle_url:
                                    logger.info(f"📥 Downloading subtitles from link {i+1}: {subtitle_url[:50]}...")
                                    transcript_response = requests.get(subtitle_url, timeout=15)
                                    if transcript_response.status_code == 200:
                                        video_data["subtitles"] = transcript_response.text
                                        logger.info(f"✅ Successfully downloaded subtitles: {len(video_data['subtitles'])} characters")
                                        break
                                    else:
                                        logger.warning(f"⚠️ Subtitle download failed with status: {transcript_response.status_code}")
                            except Exception as subtitle_error:
                                logger.error(f"❌ Error downloading subtitle {i+1}: {subtitle_error}")
                    else:
                        logger.info("🚫 No subtitle links found in videoMeta")
                else:
                    logger.info("🚫 No videoMeta found in item")
                
                if not video_data.get("subtitles"):
                    logger.warning("⚠️ No subtitles were successfully downloaded")
                
                # Extract video frames if available - ENHANCED FRAME EXTRACTION
                frames = []
                video_download_url = None
                
                # Try multiple sources for video URL
                if "mediaUrls" in item and item["mediaUrls"] and len(item["mediaUrls"]) > 0:
                    video_download_url = item["mediaUrls"][0]
                    logger.info(f"🎥 Found video URL in mediaUrls: {video_download_url[:50]}...")
                elif "videoMeta" in item and item["videoMeta"] and "downloadAddr" in item["videoMeta"]:
                    video_download_url = item["videoMeta"]["downloadAddr"]
                    logger.info(f"🎥 Found video URL in videoMeta.downloadAddr: {video_download_url[:50]}...")
                elif "videoMeta" in item and item["videoMeta"] and "playAddr" in item["videoMeta"]:
                    video_download_url = item["videoMeta"]["playAddr"]
                    logger.info(f"🎥 Found video URL in videoMeta.playAddr: {video_download_url[:50]}...")
                else:
                    logger.warning("⚠️ No video download URL found in any expected location")
                    if "videoMeta" in item and item["videoMeta"]:
                        logger.info(f"🔍 Available videoMeta keys: {list(item['videoMeta'].keys())}")
                
                if video_download_url:
                    self.update_state(state='PROGRESS', meta={
                        'step': 4, 
                        'total_steps': 5, 
                        'status': 'Extracting video frames...',
                        'url': post_url,
                        'details': 'Downloading video and extracting frames for AI analysis'
                    })
                    frames = download_and_extract_frames(video_download_url, max_frames=20)
                    logger.info(f"🖼️ Frame extraction result: {len(frames)} frames extracted")
                else:
                    logger.error("❌ No video URL available for frame extraction")
                
                # Process with AI (always process for recipe extraction)
                self.update_state(state='PROGRESS', meta={
                    'step': 5, 
                    'total_steps': 5, 
                    'status': 'Processing with AI...',
                    'url': post_url,
                    'details': 'Using OpenAI to analyze frames and subtitles for recipe extraction'
                })
                
                # Log what data we're sending to AI
                text_info = f"Text: {len(video_data.get('text', ''))} chars" if video_data.get('text') else "Text: None"
                subtitle_info = f"Subtitles: {len(video_data.get('subtitles', ''))} chars" if video_data.get('subtitles') else "Subtitles: None"
                frame_info = f"Frames: {len(frames)} images"
                logger.info(f"🤖 Sending to AI: {text_info}, {subtitle_info}, {frame_info}")
                
                # Call AI processing function directly (not as Celery task)
                video_data["processed_recipe"] = process_video_with_openai(
                    text=video_data.get("text", ""),
                    subtitles=video_data.get("subtitles", ""),
                    frames=frames,
                    url=post_url,
                    task_id=self.request.id,
                    language=language

                )
                
                logger.info(f"✅ AI processing completed for {post_url}")
                
                break  # Only process first item since we're handling single URL
            

        return {
            'status': 'SUCCESS',
            'url': post_url,
            'result': video_data,
            'processed_at': time.time(),
            'has_subtitles': video_data.get('subtitles') is not None,
            'has_ai_processing': video_data.get('processed_recipe') is not None
        }
        
    except Exception as exc:
        logger.error(f"❌ Scraping failed for {post_url}: {exc}")
        logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        
        self.update_state(
            state=states.FAILURE,
            meta={
                'url': post_url,
                'error': str(exc),
                'status': 'Failed to scrape TikTok video',
                'details': f'Error occurred while processing: {str(exc)}',
                'exc_type': type(exc).__name__,
                'exc_message': traceback.format_exc().split('\n')
            }
        )
        raise Ignore()

def process_video_with_openai(text: str = "", subtitles: str = "", frames: List[str] = None, url: str = "", task_id: str = "", language: str = ""):
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
        return process_text_with_ai(text or subtitles, language)

def process_text_with_ai(text: str, language: str = ""):
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

