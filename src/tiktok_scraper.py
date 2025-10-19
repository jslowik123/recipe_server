"""
Refactored TikTok scraper using service pattern
"""
import logging
from typing import Dict, Any, Optional

from src.services import ApifyService, VideoProcessor, OpenAIService
from src.helper.exceptions import TikTokScrapingError
from src.detailed_logger import TaskLogger

logger = logging.getLogger(__name__)


class TikTokScraper:
    """
    Main orchestrator for TikTok video scraping and processing
    Uses service pattern for better separation of concerns
    """
    
    def __init__(self, video_url: str, max_frames: int = 20, task_id: Optional[str] = None):
        self.video_url = video_url
        self.max_frames = max_frames
        self.task_id = task_id
        self.task_logger = TaskLogger.get_logger(task_id) if task_id else None

        # Initialize services
        self.apify_service = ApifyService()
        self.video_processor = VideoProcessor(max_frames=max_frames)
        self.openai_service = OpenAIService()

        if self.task_logger:
            self.task_logger.log("INFO", "TikTokScraper Services initialisiert", {
                "video_url": video_url,
                "max_frames": max_frames,
                "services_loaded": ["ApifyService", "VideoProcessor", "OpenAIService"]
            })
    
    def scrape_and_process(self, language: str = "de") -> Dict[str, Any]:
        """
        Complete scraping and processing pipeline

        Args:
            language: Language for AI processing ("de" or "en")

        Returns:
            Dict containing processed video data
        """
        try:
            # Step 1: Scrape video with Apify
            logger.info(f"🚀 Starting scraping pipeline for: {self.video_url}")
            if self.task_logger:
                self.task_logger.log("INFO", "🚀 Starte Apify Video Scraping", {
                    "url": self.video_url,
                    "service": "ApifyService"
                })

            run, video_data = self.apify_service.scrape_video(self.video_url)

            if self.task_logger:
                self.task_logger.log("INFO", "Apify Scraping abgeschlossen", {
                    "run_id": run.get("id", "unknown") if run else "none",
                    "has_dataset": "defaultDatasetId" in run if run else False,
                    "video_data_keys": list(video_data.keys()) if video_data else []
                })

            if not run or "defaultDatasetId" not in run:
                raise TikTokScrapingError("No dataset ID found in Apify run result")

            # Step 2: Process Apify results
            dataset_id = run["defaultDatasetId"]
            dataset = self.apify_service.client.dataset

            if self.task_logger:
                self.task_logger.log("INFO", "Verarbeite Apify Dataset", {
                    "dataset_id": dataset_id
                })

            for item in dataset(dataset_id).iterate_items():
                # Check for scraping errors first
                if 'error' in item:
                    error_msg = item.get('error', 'Unknown error')
                    logger.error(f"❌ Apify scraping error: {error_msg}")

                    if self.task_logger:
                        self.task_logger.log_error(Exception(error_msg), "Apify Dataset Error", {
                            "error_message": error_msg,
                            "dataset_id": dataset_id,
                            "url": self.video_url
                        })

                    if 'not found or is private' in str(error_msg).lower():
                        raise TikTokScrapingError(f"Video not accessible: {error_msg}. The video may be private, deleted, or the URL is invalid.")
                    else:
                        raise TikTokScrapingError(f"Scraping failed: {error_msg}")

                # Log raw dataset item
                if self.task_logger:
                    self.task_logger.log_raw_data("apify_dataset_item", item)

                # Extract basic text
                video_data["text"] = item.get("text", "")

                if self.task_logger:
                    self.task_logger.log("INFO", "Text aus Video extrahiert", {
                        "text_length": len(video_data.get("text", "") or ""),
                        "has_text": bool(video_data.get("text"))
                    })

                # Step 3: Extract subtitles
                logger.info("📝 Extracting subtitles...")
                if self.task_logger:
                    self.task_logger.log("INFO", "📝 Extrahiere Untertitel", {
                        "item_keys": list(item.keys()),
                        "has_subtitles_data": "subtitles" in item
                    })

                video_data["subtitles"] = self.video_processor.extract_subtitles(item)

                if self.task_logger:
                    self.task_logger.log("INFO", "Untertitel-Extraktion abgeschlossen", {
                        "subtitles_length": len(video_data["subtitles"] or "") if video_data.get("subtitles") else 0,
                        "has_subtitles": bool(video_data.get("subtitles"))
                    })

                # Step 4: Extract frames
                logger.info("🖼️ Extracting video frames...")
                if self.task_logger:
                    self.task_logger.log("INFO", "🖼️ Extrahiere Video-Frames", {
                        "max_frames": self.max_frames
                    })

                frames = self.video_processor.extract_frames(item)

                if self.task_logger:
                    self.task_logger.log("INFO", "Frame-Extraktion abgeschlossen", {
                        "frames_count": len(frames) if frames else 0,
                        "frames_type": type(frames).__name__,
                        "has_frames": bool(frames)
                    })

                # Step 5: Process with AI
                logger.info("🤖 Processing with OpenAI...")
                if self.task_logger:
                    self.task_logger.log("INFO", "🤖 Starte OpenAI Verarbeitung", {
                        "language": language,
                        "input_data": {
                            "text_length": len(video_data.get("text", "") or ""),
                            "subtitles_length": len(video_data.get("subtitles", "") or ""),
                            "frames_count": len(frames) if frames else 0
                        }
                    })

                video_data["processed_recipe"] = self.openai_service.process_video_content(
                    text=video_data.get("text", "") or "",
                    subtitles=video_data.get("subtitles", "") or "",
                    frames=frames or [],
                    language=language
                )

                if self.task_logger:
                    self.task_logger.log("INFO", "OpenAI Verarbeitung abgeschlossen", {
                        "recipe_generated": bool(video_data.get("processed_recipe")),
                        "recipe_type": type(video_data.get("processed_recipe")).__name__
                    })
                    self.task_logger.log_raw_data("processed_recipe", video_data.get("processed_recipe"))

                # Only process first item since we're handling single URL
                break

            logger.info("✅ Scraping pipeline completed successfully")

            final_result = {
                'status': 'SUCCESS',
                'url': self.video_url,
                'result': video_data,
                'has_subtitles': video_data.get('subtitles') is not None,
                'has_ai_processing': video_data.get('processed_recipe') is not None
            }

            if self.task_logger:
                self.task_logger.log("INFO", "✅ Scraping Pipeline erfolgreich abgeschlossen", {
                    "final_result_keys": list(final_result.keys()),
                    "video_data_keys": list(video_data.keys()),
                    "has_subtitles": final_result['has_subtitles'],
                    "has_ai_processing": final_result['has_ai_processing']
                })

            return final_result

        except Exception as e:
            logger.error(f"❌ Scraping pipeline failed for {self.video_url}: {e}")

            if self.task_logger:
                self.task_logger.log_error(e, "Scraping Pipeline Fehler", {
                    "url": self.video_url,
                    "language": language,
                    "pipeline_step": "unknown"
                })

            raise TikTokScrapingError(f"Pipeline failed: {str(e)}") from e