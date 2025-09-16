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
from detailed_logger import get_task_logger, finalize_task_log
from services import SupabaseService

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
def scrape_tiktok_async(self, post_url: str, language: str, user_id: str):
    """
    Asynchronously scrape a single TikTok video and process with AI using refactored services
    """
    task_id = self.request.id
    task_logger = get_task_logger(task_id)

    # Log task start
    task_logger.log("INFO", "🚀 TASK GESTARTET", {
        "task_id": task_id,
        "post_url": post_url,
        "language": language,
        "user_id": user_id,
        "max_frames": 20,
        "start_time": time.time()
    })

    try:
        # Update task state - Initializing
        task_logger.log_step(1, 5, "Initialisiere TikTok Scraper", {
            "url": post_url,
            "language": language,
            "service_config": "TikTokScraper mit max_frames=20"
        })

        self.update_state(state='PROGRESS', meta={
            'step': 1,
            'total_steps': 5,
            'status': 'Initializing TikTok scraper...',
            'url': post_url,
            'details': 'Setting up scraping services and configuration'
        })

        # Initialize scraper with services
        scraper = TikTokScraper(video_url=post_url, max_frames=20, task_id=task_id)
        task_logger.log("INFO", "TikTokScraper erfolgreich initialisiert", {
            "scraper_config": {
                "video_url": post_url,
                "max_frames": 20,
                "services": ["ApifyService", "VideoProcessor", "OpenAIService"]
            }
        })

        # Update progress - Starting scrape
        task_logger.log_step(2, 5, "Starte Apify Scraper", {
            "operation": "scrape_video",
            "apify_actor": "TikTok Scraper",
            "url": post_url
        })

        self.update_state(state='PROGRESS', meta={
            'step': 2,
            'total_steps': 5,
            'status': 'Starting Apify scraper...',
            'url': post_url,
            'details': 'Configuring scraping parameters and running Apify actor'
        })

        # Update progress - Processing content
        task_logger.log_step(3, 5, "Verarbeite Video-Inhalte", {
            "operations": ["subtitle_extraction", "frame_extraction", "text_extraction"],
            "max_frames": 20
        })

        self.update_state(state='PROGRESS', meta={
            'step': 3,
            'total_steps': 5,
            'status': 'Processing video content...',
            'url': post_url,
            'details': 'Extracting subtitles, frames, and text data'
        })

        # Update progress - AI processing
        task_logger.log_step(4, 5, "KI-Verarbeitung mit OpenAI", {
            "ai_model": "OpenAI GPT",
            "processing_type": "recipe_extraction",
            "language": language,
            "input_data": ["text", "subtitles", "frames"]
        })

        self.update_state(state='PROGRESS', meta={
            'step': 4,
            'total_steps': 5,
            'status': 'Processing with AI...',
            'url': post_url,
            'details': 'Using OpenAI to analyze frames and text for recipe extraction'
        })

        # Run the complete scraping and processing pipeline
        task_logger.log("INFO", "Starte vollständige Scraping- und Verarbeitungs-Pipeline")
        result = scraper.scrape_and_process(language=language)
        task_logger.log_raw_data("scraper_result", result)

        # Final update
        task_logger.log_step(5, 5, "Finalisiere Ergebnisse", {
            "result_keys": list(result.keys()) if isinstance(result, dict) else [],
            "has_recipe": "processed_recipe" in str(result),
            "result_status": result.get("status") if isinstance(result, dict) else "unknown"
        })

        self.update_state(state='PROGRESS', meta={
            'step': 5,
            'total_steps': 5,
            'status': 'Finalizing results...',
            'url': post_url,
            'details': 'Packaging processed data for return'
        })

        # Add processing timestamp
        result['processed_at'] = time.time()

        # Upload to Supabase
        try:
            supabase_service = SupabaseService()
            uploaded_recipe = supabase_service.upload_recipe(
                user_id=user_id,
                recipe_data=result,
                original_url=post_url
            )

            task_logger.log_success("Rezept erfolgreich zu Supabase hochgeladen", {
                "recipe_id": uploaded_recipe.get('id'),
                "recipe_name": uploaded_recipe.get('name'),
                "user_id": user_id
            })

            logger.info(f"📤 Recipe uploaded to Supabase: ID={uploaded_recipe.get('id')}")

            # Return simple success message instead of full recipe data
            result = {
                "status": "success",
                "message": "Recipe successfully processed and saved",
                "recipe_id": uploaded_recipe.get('id'),
                "recipe_name": uploaded_recipe.get('name')
            }

        except Exception as upload_error:
            task_logger.log_error(upload_error, "Supabase Upload Failed", {
                "url": post_url,
                "user_id": user_id,
                "error_message": str(upload_error)
            })

            logger.error(f"❌ Failed to upload recipe to Supabase: {upload_error}")

            # Return the original result if upload fails
            result['upload_error'] = str(upload_error)

        # Log final success
        task_logger.log_success("Task erfolgreich abgeschlossen", {
            "final_result_keys": list(result.keys()) if isinstance(result, dict) else [],
            "processing_time": time.time(),
            "url": post_url,
            "has_ai_recipe": "processed_recipe" in str(result),
            "uploaded_to_supabase": "recipe_id" in result
        })

        logger.info(f"✅ Successfully completed scraping task for {post_url}")

        # Finalize log
        finalize_task_log(task_id, "SUCCESS", {
            "url": post_url,
            "language": language,
            "user_id": user_id,
            "result_status": result.get("status", "unknown"),
            "has_recipe": "processed_recipe" in str(result),
            "uploaded_to_supabase": "recipe_id" in result
        })

        return result
        
    except TikTokScrapingError as scraping_exc:
        task_logger.log_error(scraping_exc, "TikTok Scraping Pipeline", {
            "url": post_url,
            "language": language,
            "task_id": task_id,
            "error_category": "TikTokScrapingError"
        })

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

        # Finalize log with failure
        finalize_task_log(task_id, "FAILURE", {
            "url": post_url,
            "language": language,
            "user_id": user_id,
            "error_type": "TikTokScrapingError",
            "error_message": str(scraping_exc)
        })

        raise Ignore()

    except Exception as exc:
        task_logger.log_error(exc, "Unexpected Error in Pipeline", {
            "url": post_url,
            "language": language,
            "task_id": task_id,
            "error_category": "UnexpectedError"
        })

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

        # Finalize log with failure
        finalize_task_log(task_id, "FAILURE", {
            "url": post_url,
            "language": language,
            "user_id": user_id,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "full_traceback": traceback.format_exc()
        })

        raise Ignore()

