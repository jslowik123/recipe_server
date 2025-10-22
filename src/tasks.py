import time
import traceback
import logging
import json
import redis
from celery import Celery, states
from celery.exceptions import Ignore

from src.config import config
from src.tiktok_scraper import TikTokScraper
from src.helper.exceptions import TikTokScrapingError
from src.detailed_logger import get_task_logger, finalize_task_log
from src.services import SupabaseService

# Configure logging (console only)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console output, no log files
    ]
)
logger = logging.getLogger(__name__)

# Celery Setup
celery_app = Celery('tasks', broker=config.redis_url, backend=config.redis_url)

# Redis client for WebSocket updates
redis_client = redis.from_url(config.redis_url)


def publish_websocket_update(task_id: str, update_type: str, data: dict):
    """Publish WebSocket update to Redis for real-time client notifications"""
    try:
        message = {
            "type": update_type,
            "task_id": task_id,
            "timestamp": time.time(),
            **data
        }
        redis_client.publish("task_updates", json.dumps(message))
        logger.debug(f"📡 Published {update_type} update for task {task_id}")
    except Exception as e:
        logger.error(f"❌ Failed to publish WebSocket update: {e}")

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
def scrape_tiktok_async(self, post_url: str, language: str, user_id: str, jwt_token: str = None):
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

        progress_data = {
            'step': 1,
            'total_steps': 5,
            'status': 'Initializing TikTok scraper...',
            'url': post_url,
            'details': 'Setting up scraping services and configuration'
        }
        self.update_state(state='PROGRESS', meta=progress_data)
        publish_websocket_update(task_id, "progress", progress_data)

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

        progress_data = {
            'step': 2,
            'total_steps': 5,
            'status': 'Starting Apify scraper...',
            'url': post_url,
            'details': 'Configuring scraping parameters and running Apify actor'
        }
        self.update_state(state='PROGRESS', meta=progress_data)
        publish_websocket_update(task_id, "progress", progress_data)

        # Update progress - Processing content
        task_logger.log_step(3, 5, "Verarbeite Video-Inhalte", {
            "operations": ["subtitle_extraction", "frame_extraction", "text_extraction"],
            "max_frames": 20
        })

        progress_data = {
            'step': 3,
            'total_steps': 5,
            'status': 'Processing video content...',
            'url': post_url,
            'details': 'Extracting subtitles, frames, and text data'
        }
        self.update_state(state='PROGRESS', meta=progress_data)
        publish_websocket_update(task_id, "progress", progress_data)

        # Update progress - AI processing
        task_logger.log_step(4, 5, "KI-Verarbeitung mit OpenAI", {
            "ai_model": "OpenAI GPT",
            "processing_type": "recipe_extraction",
            "language": language,
            "input_data": ["text", "subtitles", "frames"]
        })

        progress_data = {
            'step': 4,
            'total_steps': 5,
            'status': 'Processing with AI...',
            'url': post_url,
            'details': 'Using OpenAI to analyze frames and text for recipe extraction'
        }
        self.update_state(state='PROGRESS', meta=progress_data)
        publish_websocket_update(task_id, "progress", progress_data)

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

        progress_data = {
            'step': 5,
            'total_steps': 5,
            'status': 'Finalizing results...',
            'url': post_url,
            'details': 'Packaging processed data for return'
        }
        self.update_state(state='PROGRESS', meta=progress_data)
        publish_websocket_update(task_id, "progress", progress_data)

        # Add processing timestamp
        result['processed_at'] = time.time()

        # Upload to Supabase
        try:
            supabase_service = SupabaseService()

            task_logger.log("INFO", "Bereite Supabase-Upload vor", {
                "user_id": user_id
            })

            # Upload recipe
            import asyncio
            uploaded_recipe = asyncio.run(supabase_service.upload_recipe(
                user_id=user_id,
                recipe_data=result,
                original_url=post_url,
                jwt_token=jwt_token
            ))

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

            # Publish completion update to WebSocket
            publish_websocket_update(task_id, "completion", {
                "status": "SUCCESS",
                "message": result['message'],
                "recipe_id": result['recipe_id'],
                "recipe_name": result['recipe_name']
            })

        except Exception as upload_error:
            task_logger.log_error(upload_error, "Supabase Upload Failed", {
                "url": post_url,
                "user_id": user_id,
                "error_message": str(upload_error)
            })

            logger.error(f"❌ Failed to upload recipe to Supabase: {upload_error}")

            # Return error for upload failure
            result = {
                "status": "FAILURE",
                "error_code": "UPLOAD_FAILED",
                "should_refund": True,
                "technical_details": str(upload_error),
                "upload_error": str(upload_error)
            }

            # Publish completion with upload error to WebSocket
            publish_websocket_update(task_id, "error", {
                "status": "FAILURE",
                "error_code": "UPLOAD_FAILED",
                "should_refund": True,
                "technical_details": str(upload_error)
            })

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

        error_data = {
            "status": "FAILURE",
            "error_code": "SCRAPING_ERROR",
            "should_refund": True,
            "technical_details": str(scraping_exc)
        }
        self.update_state(state=states.FAILURE, meta=error_data)

        # Publish error to WebSocket
        publish_websocket_update(task_id, "error", {
            "status": "FAILURE",
            "error_code": "SCRAPING_ERROR",
            "should_refund": True,
            "technical_details": str(scraping_exc)
        })

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

        error_data = {
            "status": "FAILURE",
            "error_code": "PROCESSING_ERROR",
            "should_refund": True,
            "technical_details": str(exc)
        }
        self.update_state(state=states.FAILURE, meta=error_data)

        # Publish error to WebSocket
        publish_websocket_update(task_id, "error", {
            "status": "FAILURE",
            "error_code": "PROCESSING_ERROR",
            "should_refund": True,
            "technical_details": str(exc)
        })

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

