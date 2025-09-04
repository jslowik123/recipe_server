import time
import traceback
import logging
from celery import Celery, states
from celery.exceptions import Ignore
from typing import List
from pydantic import BaseModel

from config import config
from tiktok_scraper import TikTokScraper
from exceptions import TikTokScrapingError

# Configure logging (console only)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console output, no log files
    ]
)
logger = logging.getLogger(__name__)


# Pydantic Models for simple recipe response (nur Zutaten und Schritte)
class SimpleRecipeResponse(BaseModel):
    ingredients: List[str]
    steps: List[str]


# Celery Setup
celery_app = Celery('tasks', broker=config.redis_url, backend=config.redis_url)

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
    Asynchronously scrape a single TikTok video and process with AI using refactored services
    """
    try:
        # Update task state - Initializing
        self.update_state(state='PROGRESS', meta={
            'step': 1, 
            'total_steps': 5, 
            'status': 'Initializing TikTok scraper...',
            'url': post_url,
            'details': 'Setting up scraping services and configuration'
        }) 
        
        # Initialize scraper with services
        scraper = TikTokScraper(video_url=post_url, max_frames=20)
        
        # Update progress - Starting scrape
        self.update_state(state='PROGRESS', meta={
            'step': 2, 
            'total_steps': 5, 
            'status': 'Starting Apify scraper...',
            'url': post_url,
            'details': 'Configuring scraping parameters and running Apify actor'
        })
        
        # Update progress - Processing content
        self.update_state(state='PROGRESS', meta={
            'step': 3, 
            'total_steps': 5, 
            'status': 'Processing video content...',
            'url': post_url,
            'details': 'Extracting subtitles, frames, and text data'
        })
        
        # Update progress - AI processing
        self.update_state(state='PROGRESS', meta={
            'step': 4, 
            'total_steps': 5, 
            'status': 'Processing with AI...',
            'url': post_url,
            'details': 'Using OpenAI to analyze frames and text for recipe extraction'
        })
        
        # Run the complete scraping and processing pipeline
        result = scraper.scrape_and_process(language=language)
        
        # Final update
        self.update_state(state='PROGRESS', meta={
            'step': 5, 
            'total_steps': 5, 
            'status': 'Finalizing results...',
            'url': post_url,
            'details': 'Packaging processed data for return'
        })
        
        # Add processing timestamp
        result['processed_at'] = time.time()
        
        logger.info(f"✅ Successfully completed scraping task for {post_url}")
        return result
        
    except TikTokScrapingError as scraping_exc:
        logger.error(f"❌ TikTok scraping error for {post_url}: {scraping_exc}")
        logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        self.update_state(
            state=states.FAILURE,
            meta={
                'url': post_url,
                'error': str(scraping_exc),
                'status': 'TikTok scraping failed',
                'details': f'Scraping error: {str(scraping_exc)}',
                'exc_type': type(scraping_exc).__name__,
                'exc_message': str(scraping_exc)
            }
        )
        raise Ignore()
        
    except Exception as exc:
        logger.error(f"❌ Unexpected error for {post_url}: {exc}")
        logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        self.update_state(
            state=states.FAILURE,
            meta={
                'url': post_url,
                'error': str(exc),
                'status': 'Unexpected error occurred',
                'details': f'Unexpected error during processing: {str(exc)}',
                'exc_type': type(exc).__name__,
                'exc_message': traceback.format_exc().split('\n')
            }
        )
        raise Ignore()

