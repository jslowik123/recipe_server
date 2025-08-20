#!/usr/bin/env python3
"""
Enhanced recipe extraction test with comprehensive debugging
"""

import os
import sys
import json
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv
import logging
import traceback

# Load environment variables
load_dotenv()

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apify_client import ApifyClient
from openai import OpenAI
import requests

# Configure logging (console only)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console output, no log files
    ]
)
logger = logging.getLogger(__name__)

class EnhancedRecipeExtractor:
    """Enhanced recipe extraction with comprehensive debugging"""
    
    def __init__(self):
        self.apify_client = None
        self.openai_client = None
        self.setup_clients()
    
    def setup_clients(self):
        """Initialize API clients"""
        try:
            # Setup Apify client
            apify_token = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
            if not apify_token:
                raise ValueError("APIFY_API_TOKEN not found")
            
            self.apify_client = ApifyClient(apify_token)
            logger.info(f"✅ Apify client initialized with token: {apify_token[:8]}...{apify_token[-4:]}")
            
            # Setup OpenAI client  
            openai_key = os.getenv('OPENAI_API_KEY')
            if not openai_key:
                raise ValueError("OPENAI_API_KEY not found")
            
            self.openai_client = OpenAI()
            logger.info(f"✅ OpenAI client initialized with key: {openai_key[:8]}...{openai_key[-4:]}")
            
        except Exception as e:
            logger.error(f"❌ Client setup failed: {e}")
            raise
    
    def scrape_tiktok_data(self, url: str) -> Optional[Dict]:
        """Scrape TikTok data using Apify"""
        logger.info(f"🔍 Starting TikTok scrape for: {url}")
        
        try:
            run_input = {
                "postURLs": [url],
                "scrapeRelatedVideos": False,
                "resultsPerPage": 1,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
                "shouldDownloadSubtitles": True,
                "shouldDownloadSlideshowImages": False,
            }
            
            logger.info("🚀 Starting Apify actor...")
            start_time = time.time()
            
            run = self.apify_client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
            
            scrape_duration = time.time() - start_time
            logger.info(f"⏱️ Scraping completed in {scrape_duration:.1f} seconds")
            
            if not run or "defaultDatasetId" not in run:
                logger.error("❌ No dataset returned from Apify")
                return None
            
            dataset_id = run["defaultDatasetId"]
            logger.info(f"📊 Processing dataset: {dataset_id}")
            
            # Get first (and only) item
            for item in self.apify_client.dataset(dataset_id).iterate_items():
                logger.info(f"📄 Dataset item keys: {list(item.keys())}")
                
                # Check if there's an error
                if 'error' in item:
                    error_msg = item.get('error', 'Unknown error')
                    logger.error(f"❌ Apify scraping error: {error_msg}")
                    if 'not found or is private' in str(error_msg).lower():
                        logger.error("❌ Video is private, deleted, or URL is invalid")
                        return {"error": "Video not accessible", "details": error_msg}
                
                # Log key information
                text = item.get('text', '')
                logger.info(f"📝 Text content: {len(text)} characters")
                if text:
                    logger.info(f"📝 Text preview: {text[:200]}...")
                
                # Check video metadata
                video_meta = item.get('videoMeta', {})
                if video_meta:
                    logger.info(f"🎥 VideoMeta keys: {list(video_meta.keys())}")
                    
                    # Check for subtitle links
                    subtitle_links = video_meta.get('subtitleLinks', [])
                    logger.info(f"📋 Found {len(subtitle_links)} subtitle links")
                    
                    # Check for video URLs
                    video_urls = []
                    for key in ['downloadAddr', 'playAddr']:
                        if key in video_meta and video_meta[key]:
                            video_urls.append((key, video_meta[key]))
                    logger.info(f"🎬 Found {len(video_urls)} video URLs")
                else:
                    logger.warning("⚠️ No videoMeta found in item")
                
                return item
            
            logger.warning("⚠️ No items found in dataset")
            return None
            
        except Exception as e:
            logger.error(f"❌ TikTok scraping failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return None
    
    def extract_subtitles(self, video_meta: Dict) -> Optional[str]:
        """Extract subtitles from video metadata"""
        logger.info("📋 Attempting subtitle extraction...")
        
        subtitle_links = video_meta.get('subtitleLinks', [])
        if not subtitle_links:
            logger.info("ℹ️ No subtitle links found")
            return None
        
        for i, subtitle_link in enumerate(subtitle_links):
            try:
                download_url = subtitle_link.get('downloadLink')
                if not download_url:
                    logger.warning(f"⚠️ Subtitle link {i+1} has no download URL")
                    continue
                
                logger.info(f"📥 Downloading subtitles from link {i+1}: {download_url[:50]}...")
                
                response = requests.get(download_url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                
                if response.status_code == 200:
                    subtitles = response.text
                    logger.info(f"✅ Downloaded subtitles: {len(subtitles)} characters")
                    logger.info(f"📋 Subtitle preview: {subtitles[:200]}...")
                    return subtitles
                else:
                    logger.warning(f"⚠️ Subtitle download failed: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"❌ Error downloading subtitle {i+1}: {e}")
        
        logger.warning("⚠️ All subtitle downloads failed")
        return None
    
    def process_with_openai(self, text: str = "", subtitles: str = "", url: str = "") -> Dict:
        """Process content with OpenAI"""
        logger.info("🤖 Starting OpenAI processing...")
        
        # Combine text sources
        combined_text = ""
        if subtitles:
            combined_text += f"SUBTITLES: {subtitles}\n\n"
            logger.info(f"📋 Added subtitles: {len(subtitles)} chars")
        if text and text != subtitles:
            combined_text += f"TEXT: {text}\n\n"
            logger.info(f"📝 Added text: {len(text)} chars")
        
        if not combined_text:
            logger.warning("⚠️ No text content available for processing")
            return {
                "title": "No Content Available",
                "ingredients": [],
                "steps": ["Keine Textdaten zum Verarbeiten verfügbar"]
            }
        
        try:
            logger.info(f"🚀 Sending {len(combined_text)} characters to OpenAI...")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """Du bist ein erfahrener Koch und Rezept-Experte. Analysiere den gegebenen Text und rekonstruiere daraus ein vollständiges, kochbares Rezept.

AUFGABE:
1. Analysiere den gesamten Text nach Hinweisen auf Zutaten, Mengen, und Zubereitungsschritte
2. Rekonstruiere ein vollständiges Rezept auch wenn nicht alle Details explizit genannt werden
3. Nutze dein Kochwissen um fehlende aber typische Schritte/Zutaten zu ergänzen
4. Schätze realistische Mengen basierend auf dem Kontext

AUSGABE:
- Aussagekräftiger Titel der das Gericht beschreibt
- Konkrete Zutaten mit realistischen Mengenangaben  
- Detaillierte Zubereitungsschritte mit Zeiten/Temperaturen wo sinnvoll

Antworte IMMER mit korrektem JSON: {"title": "Beschreibender Titel", "ingredients": ["Zutat mit Menge"], "steps": ["Detaillierter Schritt"]}"""
                    },
                    {
                        "role": "user",
                        "content": f"Rekonstruiere ein vollständiges Rezept aus folgendem Inhalt:\n\n{combined_text}"
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            logger.info("✅ OpenAI request successful")
            
            content = response.choices[0].message.content.strip()
            logger.info(f"📤 Response length: {len(content)} characters")
            logger.info(f"📤 Response preview: {content[:300]}...")
            
            # Enhanced JSON parsing
            recipe = self.parse_recipe_json(content)
            
            # Log token usage and cost
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                logger.info(f"💰 Token usage - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens}")
            
            return recipe
            
        except Exception as e:
            logger.error(f"❌ OpenAI processing failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return {
                "title": "Processing Error",
                "ingredients": [],
                "steps": [f"Fehler bei der KI-Verarbeitung: {str(e)}"]
            }
    
    def parse_recipe_json(self, content: str) -> Dict:
        """Enhanced JSON parsing with multiple fallback strategies"""
        logger.info("🔍 Parsing recipe JSON...")
        
        import re
        
        # Strategy 1: Direct JSON parsing
        try:
            if content.strip().startswith('{') and content.strip().endswith('}'):
                recipe = json.loads(content)
                logger.info("✅ Direct JSON parsing successful")
                return self.validate_recipe_structure(recipe)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Direct JSON parsing failed: {e}")
        
        # Strategy 2: Extract from markdown code blocks
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*?"ingredients".*?"steps".*?\})',
            r'(\{.*?\})'
        ]
        
        for i, pattern in enumerate(patterns):
            try:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    recipe = json.loads(match.group(1))
                    logger.info(f"✅ JSON extraction successful with pattern {i+1}")
                    return self.validate_recipe_structure(recipe)
            except json.JSONDecodeError:
                continue
        
        # Strategy 3: Manual extraction as fallback
        logger.warning("⚠️ JSON parsing failed, attempting manual extraction...")
        return self.manual_recipe_extraction(content)
    
    def validate_recipe_structure(self, recipe: Dict) -> Dict:
        """Validate and fix recipe structure"""
        if not isinstance(recipe.get("title"), str):
            recipe["title"] = "Untitled Recipe"
        if not isinstance(recipe.get("ingredients"), list):
            recipe["ingredients"] = []
        if not isinstance(recipe.get("steps"), list):
            recipe["steps"] = []
        
        logger.info(f"🔍 Validated recipe: {recipe['title']} - {len(recipe['ingredients'])} ingredients, {len(recipe['steps'])} steps")
        return recipe
    
    def manual_recipe_extraction(self, content: str) -> Dict:
        """Fallback manual extraction from free text"""
        logger.info("🔧 Attempting manual recipe extraction...")
        
        # Basic pattern matching for ingredients and steps
        import re
        
        # Look for common recipe patterns
        title_patterns = [
            r'["\']([^"\']*recipe[^"\']*)["\']',
            r'["\']([A-Z][^"\']{10,50})["\']'
        ]
        
        title = "Extracted Recipe"
        for pattern in title_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                title = match.group(1)
                break
        
        # Extract possible ingredients (lines with measurements)
        ingredient_patterns = [
            r'(\d+.*?(?:cup|tbsp|tsp|gram|ml|liter|piece|slice).*?)(?:\n|$)',
            r'([A-Z][a-z]+.*?(?:cup|tbsp|tsp|gram|ml|liter).*?)(?:\n|$)'
        ]
        
        ingredients = []
        for pattern in ingredient_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            ingredients.extend(matches)
        
        # Extract possible steps (numbered or action words)
        step_patterns = [
            r'(\d+\..*?)(?:\n|$)',
            r'((?:Mix|Add|Cook|Heat|Stir|Bake|Fry).*?)(?:\n|$)'
        ]
        
        steps = []
        for pattern in step_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            steps.extend(matches)
        
        result = {
            "title": title,
            "ingredients": ingredients[:10],  # Limit results
            "steps": steps[:15]
        }
        
        logger.info(f"🔧 Manual extraction result: {len(result['ingredients'])} ingredients, {len(result['steps'])} steps")
        return result
    
    def extract_recipe(self, url: str) -> Dict:
        """Main extraction method"""
        logger.info(f"🎯 Starting complete recipe extraction for: {url}")
        logger.info("=" * 80)
        
        try:
            # Step 1: Scrape TikTok data
            data = self.scrape_tiktok_data(url)
            if not data:
                return {"error": "Failed to scrape TikTok data"}
            
            # Step 2: Extract text and subtitles
            text = data.get('text', '')
            subtitles = None
            
            video_meta = data.get('videoMeta', {})
            if video_meta:
                subtitles = self.extract_subtitles(video_meta)
            
            # Step 3: Process with OpenAI
            recipe = self.process_with_openai(text, subtitles, url)
            
            # Final result
            result = {
                "url": url,
                "recipe": recipe,
                "metadata": {
                    "text_length": len(text),
                    "has_subtitles": bool(subtitles),
                    "subtitle_length": len(subtitles) if subtitles else 0,
                    "processing_timestamp": time.time()
                }
            }
            
            logger.info("🎉 Recipe extraction completed successfully!")
            logger.info("=" * 80)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Complete extraction failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return {"error": str(e)}

def main():
    """Test the enhanced extractor"""
    # Test URLs - Updated with more recent TikTok recipe videos
    test_urls = [
        # Try newer Gordon Ramsay videos (these IDs are more recent format)
        "https://www.tiktok.com/@gordon_ramsayofficial/video/7350000000000000000",  # Placeholder - replace with actual
        # Popular recipe creators with more recent videos
        "https://www.tiktok.com/@cooking_with_shereen/video/7350000000000000000",  # Placeholder
        # Use this search pattern to find working URLs: @username/video/[17-19 digit ID starting with 7]
    ]
    
    logger.info("🚨 IMPORTANT: The test URLs above are placeholders!")
    logger.info("🔍 To test with real videos:")
    logger.info("   1. Go to TikTok and find a recipe video")
    logger.info("   2. Copy the URL (should look like: https://www.tiktok.com/@username/video/7xxxxxxxxxxxxxxxxx)")
    logger.info("   3. Replace the test_urls above or run: python enhanced_recipe_test.py 'YOUR_URL_HERE'")
    
    # Check if URL provided as command line argument
    import sys
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        logger.info(f"🎯 Using URL from command line: {test_url}")
        test_urls = [test_url]
    else:
        logger.warning("⚠️ No URL provided. Using placeholder URLs that will likely fail.")
        logger.info("💡 Usage: python enhanced_recipe_test.py 'https://www.tiktok.com/@user/video/ID'")
        return
    
    try:
        extractor = EnhancedRecipeExtractor()
        
        for url in test_urls:
            logger.info(f"\n🧪 Testing URL: {url}")
            result = extractor.extract_recipe(url)
            
            if "error" in result:
                logger.error(f"❌ Extraction failed: {result['error']}")
            else:
                logger.info("✅ Extraction successful!")
                recipe = result.get('recipe', {})
                metadata = result.get('metadata', {})
                
                print("\n" + "="*60)
                print("📋 EXTRACTION RESULTS")
                print("="*60)
                print(f"🔗 URL: {url}")
                print(f"📝 Title: {recipe.get('title', 'N/A')}")
                print(f"🥘 Ingredients ({len(recipe.get('ingredients', []))}): {recipe.get('ingredients', [])}")
                print(f"👨‍🍳 Steps ({len(recipe.get('steps', []))}): {recipe.get('steps', [])}")
                print(f"📊 Metadata: {metadata}")
                print("="*60)
                
                # Results are tracked in Excel file automatically
                # No need to save separate JSON files
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        logger.error(f"📋 Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()