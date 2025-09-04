"""
Refactored TikTok scraper using service pattern
"""
import logging
from typing import Dict, Any, Optional

from services import ApifyService, VideoProcessor, OpenAIService
from exceptions import TikTokScrapingError

logger = logging.getLogger(__name__)


class TikTokScraper:
    """
    Main orchestrator for TikTok video scraping and processing
    Uses service pattern for better separation of concerns
    """
    
    def __init__(self, video_url: str, max_frames: int = 20):
        self.video_url = video_url
        self.max_frames = max_frames
        
        # Initialize services
        self.apify_service = ApifyService()
        self.video_processor = VideoProcessor(max_frames=max_frames)
        self.openai_service = OpenAIService()
    
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
            run, video_data = self.apify_service.scrape_video(self.video_url)
            
            if not run or "defaultDatasetId" not in run:
                raise TikTokScrapingError("No dataset ID found in Apify run result")
            
            # Step 2: Process Apify results
            dataset_id = run["defaultDatasetId"]
            dataset = self.apify_service.client.dataset
            
            for item in dataset(dataset_id).iterate_items():
                # Check for scraping errors first
                if 'error' in item:
                    error_msg = item.get('error', 'Unknown error')
                    logger.error(f"❌ Apify scraping error: {error_msg}")
                    if 'not found or is private' in str(error_msg).lower():
                        raise TikTokScrapingError(f"Video not accessible: {error_msg}. The video may be private, deleted, or the URL is invalid.")
                    else:
                        raise TikTokScrapingError(f"Scraping failed: {error_msg}")
                
                # Extract basic text
                video_data["text"] = item.get("text", "")
                
                # Step 3: Extract subtitles
                logger.info("📝 Extracting subtitles...")
                video_data["subtitles"] = self.video_processor.extract_subtitles(item)
                
                # Step 4: Extract frames
                logger.info("🖼️ Extracting video frames...")
                frames = self.video_processor.extract_frames(item)
                
                # Step 5: Process with AI
                logger.info("🤖 Processing with OpenAI...")
                video_data["processed_recipe"] = self.openai_service.process_video_content(
                    text=video_data.get("text", ""),
                    subtitles=video_data.get("subtitles", ""),
                    frames=frames,
                    language=language
                )
                
                # Only process first item since we're handling single URL
                break
            
            logger.info("✅ Scraping pipeline completed successfully")
            return {
                'status': 'SUCCESS',
                'url': self.video_url,
                'result': video_data,
                'has_subtitles': video_data.get('subtitles') is not None,
                'has_ai_processing': video_data.get('processed_recipe') is not None
            }
            
        except Exception as e:
            logger.error(f"❌ Scraping pipeline failed for {self.video_url}: {e}")
            raise TikTokScrapingError(f"Pipeline failed: {str(e)}") from e