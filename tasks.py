import os
from celery import Celery
import requests
from apify_client import ApifyClient
from openai import OpenAI
from dotenv import load_dotenv
import time
import json
from typing import List
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Pydantic Models for simple recipe response (nur Zutaten und Schritte)
class SimpleRecipeResponse(BaseModel):
    ingredients: List[str]
    steps: List[str]

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
def scrape_tiktok_async(self, post_url: str, process_with_ai: bool = True):
    """
    Asynchronously scrape a single TikTok video and optionally process with AI
    """
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={
            'step': 1, 
            'total_steps': 4, 
            'status': 'Initializing Apify client...',
            'url': post_url,
            'details': 'Setting up scraping infrastructure'
        }) 
        
        # Initialize Apify client
        client = ApifyClient("apify_api_iYcAqVugvyZlguYWGWoOY5DVwbDKI83GSqR2")
        
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
        
        run = client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
        
        video_data = {
            "url": post_url,
            "text": "",
            "subtitles": None,
            "processed_recipe": None
        }
            
        if run and "defaultDatasetId" in run:
            dataset_id = run["defaultDatasetId"]
            
            # Get results from dataset
            for item in client.dataset(dataset_id).iterate_items():
                video_data["text"] = item.get("text", "")
                
                # Update progress - processing subtitles
                self.update_state(state='PROGRESS', meta={
                    'step': 4, 
                    'total_steps': 4, 
                    'status': 'Processing video content...',
                    'url': post_url,
                    'details': 'Extracting subtitles and preparing final data'
                })
                
                # Download subtitles if available
                if "videoMeta" in item and "subtitleLinks" in item["videoMeta"] and len(item["videoMeta"]["subtitleLinks"]) > 0:
                    subtitle_url = item["videoMeta"]["subtitleLinks"][0]["downloadLink"]
                    transcript_response = requests.get(subtitle_url)
                    if transcript_response.status_code == 200:
                        video_data["subtitles"] = transcript_response.text
                
                # Process with AI if requested
                if process_with_ai and video_data["text"]:
                    self.update_state(state='PROGRESS', meta={
                        'step': 4, 
                        'total_steps': 4, 
                        'status': 'Processing with AI...',
                        'url': post_url,
                        'details': 'Generating structured recipe using OpenAI'
                    })
                    video_data["processed_recipe"] = process_text_with_ai(video_data["text"])
                
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
        self.update_state(
            state='FAILURE',
            meta={
                'url': post_url,
                'error': str(exc),
                'status': 'Failed to scrape TikTok video',
                'details': f'Error occurred while processing: {str(exc)}'
            }
        )
        raise exc

@celery_app.task
def process_text_with_ai(text: str):
    """
    Process text with OpenAI to extract structured recipe
    """
    try:
        client = OpenAI()
        
        # Simple JSON schema - nur Zutaten und Schritte
        recipe_schema = {
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Liste der Zutaten mit Mengenangaben (z.B. 'Mehl, 250g')"
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Schritt-für-Schritt Anleitung"
                }
            },
            "required": ["ingredients", "steps"]
        }
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Better model for structured output
            messages=[
                {
                    "role": "system", 
                    "content": """Du extrahierst nur Zutaten und Schritte aus Rezept-Texten.
                    
                    Regeln:
                    - Zutaten: Liste mit Mengenangaben (z.B. "Mehl, 250g", "Eier, 2 Stück")
                    - Schritte: Klare Anweisungen in der richtigen Reihenfolge
                    - Nur diese beiden Felder zurückgeben"""
                },
                {
                    "role": "user", 
                    "content": f"Extrahiere nur Zutaten und Schritte aus: {text}"
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "recipe_extraction",
                    "schema": recipe_schema
                }
            },
            max_tokens=1000
        )
        
        # Parse the JSON response
        recipe_json = json.loads(response.choices[0].message.content)
        
        # Validate with Pydantic model
        recipe = SimpleRecipeResponse(**recipe_json)
        
        return recipe.model_dump()
        
    except Exception as e:
        # Return error in simple format
        return {
            "ingredients": [],
            "steps": [f"Fehler beim Verarbeiten mit AI: {str(e)}"]
        }

@celery_app.task
def long_running_task(duration: int = 10):
    """
    Example long-running task for testing
    """
    for i in range(duration):
        time.sleep(1)
        print(f"Task progress: {i+1}/{duration}")
    
    return f"Task completed after {duration} seconds"
