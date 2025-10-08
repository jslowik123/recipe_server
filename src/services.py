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
import asyncio
import aiohttp
import aiofiles
from typing import List, Dict, Any, Optional

import cv2
import requests
from apify_client import ApifyClient
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime

from src.config import config
from src.exceptions import (
    ApifyError, OpenAIError, VideoProcessingError,
    VideoDownloadError, FrameExtractionError
)
from src.prompt_service import prompt_service

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
            "shouldDownloadVideos": True,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
            "shouldDownloadSlideshowImages": False,
            # Anti-blocking optimizations
            "maxRequestRetries": 5,
            "requestTimeoutSecs": 120,
            "maxConcurrency": 1,  # Reduce concurrency to avoid rate limits
            "proxyConfiguration": {
                "useApifyProxy": True,
                "groups": ["RESIDENTIAL"]
            }
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
            logger.warning("❌ No direct video URL available, trying alternatives...")

            # Try to extract from cover image as fallback
            if "videoMeta" in item and item["videoMeta"] and "coverUrl" in item["videoMeta"]:
                cover_url = item["videoMeta"]["coverUrl"]
                logger.info(f"📸 Using cover image as frame: {cover_url}")
                try:
                    return self._extract_frame_from_image(cover_url)
                except Exception as e:
                    logger.error(f"❌ Failed to extract cover image: {e}")

            # Try yt-dlp as last resort if webVideoUrl is available
            if "webVideoUrl" in item and item["webVideoUrl"]:
                logger.info(f"🎯 Trying yt-dlp extraction from: {item['webVideoUrl']}")
                try:
                    return self._extract_frames_with_ytdlp(item["webVideoUrl"])
                except Exception as e:
                    logger.error(f"❌ yt-dlp extraction failed: {e}")

            logger.warning("⚠️ All frame extraction methods failed, returning empty list")
            return []

    def extract_thumbnail_url(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract thumbnail/cover URL from TikTok video metadata"""
        if "videoMeta" in item and item["videoMeta"] and "coverUrl" in item["videoMeta"]:
            cover_url = item["videoMeta"]["coverUrl"]
            logger.info(f"📸 Found thumbnail URL: {cover_url}")
            return cover_url

        logger.warning("⚠️ No thumbnail URL found in video metadata")
        return None
    
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
            logger.info("📋 Available item keys: " + str(list(item.keys())))
            if "videoMeta" in item and item["videoMeta"]:
                logger.info("📋 VideoMeta keys: " + str(list(item["videoMeta"].keys())))
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
            
            # Intelligent frame extraction for cooking videos
            frames = self._extract_frames_intelligently(cap, total_frames, fps, duration)
            
        finally:
            cap.release()
            
        return frames
    
    def _extract_frames_intelligently(self, cap, total_frames: int, fps: float, duration: float) -> List[str]:
        """
        Extract frames optimized for cooking videos
        """
        frames = []
        
        # Skip very beginning and end (often intro/outro)
        skip_start_percent = 0.05  # Skip first 5%
        skip_end_percent = 0.05    # Skip last 5%
        
        start_frame = int(total_frames * skip_start_percent)
        end_frame = int(total_frames * (1 - skip_end_percent))
        useful_frames = end_frame - start_frame
        
        logger.info(f"🎯 Intelligent extraction: frames {start_frame}-{end_frame} (skipping intro/outro)")
        
        if duration <= 30:
            # Short videos: more dense sampling
            frame_positions = self._get_dense_frame_positions(start_frame, end_frame, self.max_frames)
            logger.info(f"📹 Short video ({duration:.1f}s): dense sampling")
        elif duration <= 120:
            # Medium videos: focus on middle sections  
            frame_positions = self._get_cooking_focused_positions(start_frame, end_frame, duration, fps, self.max_frames)
            logger.info(f"👨‍🍳 Medium video ({duration:.1f}s): cooking-focused sampling")
        else:
            # Long videos: strategic sampling with more middle focus
            frame_positions = self._get_strategic_long_video_positions(start_frame, end_frame, self.max_frames)
            logger.info(f"⏳ Long video ({duration:.1f}s): strategic sampling")
        
        # Extract frames at calculated positions
        frame_count = 0
        for target_position in sorted(frame_positions):
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_position)
            ret, frame = cap.read()
            
            if ret and len(frames) < self.max_frames:
                resized = cv2.resize(frame, (256, 144))
                _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 60])
                base64_frame = base64.b64encode(buffer).decode("utf-8")
                frames.append(base64_frame)
                
                timestamp = target_position / fps if fps > 0 else target_position
                logger.debug(f"🖼️ Extracted frame {len(frames)}/{self.max_frames} at {timestamp:.1f}s")
        
        logger.info(f"✅ Intelligent extraction completed: {len(frames)} frames")
        return frames
    
    def _get_dense_frame_positions(self, start_frame: int, end_frame: int, max_frames: int) -> List[int]:
        """Dense, evenly distributed sampling for short videos"""
        useful_frames = end_frame - start_frame
        interval = max(1, useful_frames // max_frames)
        
        return [start_frame + i * interval for i in range(max_frames) 
                if start_frame + i * interval < end_frame]
    
    def _get_cooking_focused_positions(self, start_frame: int, end_frame: int, duration: float, fps: float, max_frames: int) -> List[int]:
        """Cooking-focused sampling: more frames in middle where action happens"""
        positions = []
        useful_frames = end_frame - start_frame
        
        # 20% from first quarter (setup/ingredients)
        first_quarter_count = max(1, int(max_frames * 0.2))
        first_quarter_end = start_frame + useful_frames // 4
        first_quarter_positions = self._get_evenly_spaced_positions(start_frame, first_quarter_end, first_quarter_count)
        positions.extend(first_quarter_positions)
        
        # 60% from middle half (main cooking action)
        middle_count = max(1, int(max_frames * 0.6))
        middle_start = start_frame + useful_frames // 4
        middle_end = start_frame + 3 * useful_frames // 4  
        middle_positions = self._get_evenly_spaced_positions(middle_start, middle_end, middle_count)
        positions.extend(middle_positions)
        
        # 20% from last quarter (plating/result)
        last_quarter_count = max(1, max_frames - len(positions))
        last_quarter_start = start_frame + 3 * useful_frames // 4
        last_quarter_positions = self._get_evenly_spaced_positions(last_quarter_start, end_frame, last_quarter_count)
        positions.extend(last_quarter_positions)

        return positions

    def _extract_frame_from_image(self, image_url: str) -> List[str]:
        """Extract a single frame from an image URL (like cover image)"""
        try:
            response = requests.get(image_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)

            if response.status_code != 200:
                raise Exception(f"Failed to download image: HTTP {response.status_code}")

            # Convert image to base64
            import base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')
            logger.info(f"✅ Extracted cover image as frame: {len(image_base64)} bytes")
            return [image_base64]

        except Exception as e:
            logger.error(f"❌ Failed to extract image frame: {e}")
            raise

    def _extract_frames_with_ytdlp(self, video_url: str) -> List[str]:
        """Try to extract frames using yt-dlp"""
        try:
            import subprocess
            import tempfile
            import os

            # Check if yt-dlp is available
            try:
                subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning("⚠️ yt-dlp not available, skipping")
                return []

            with tempfile.TemporaryDirectory() as temp_dir:
                video_path = os.path.join(temp_dir, 'video.%(ext)s')

                # Download video with yt-dlp
                cmd = [
                    'yt-dlp',
                    '--no-playlist',
                    '--format', 'best[height<=720]',
                    '--output', video_path,
                    video_url
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                if result.returncode != 0:
                    logger.error(f"❌ yt-dlp failed: {result.stderr}")
                    return []

                # Find the downloaded file
                downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith('video.')]
                if not downloaded_files:
                    logger.error("❌ No video file was downloaded")
                    return []

                actual_video_path = os.path.join(temp_dir, downloaded_files[0])
                logger.info(f"✅ Downloaded video with yt-dlp: {actual_video_path}")

                # Extract frames from downloaded video
                return self._extract_frames_from_file(actual_video_path)

        except Exception as e:
            logger.error(f"❌ yt-dlp extraction failed: {e}")
            raise
    
    def _get_strategic_long_video_positions(self, start_frame: int, end_frame: int, max_frames: int) -> List[int]:
        """Strategic sampling for long videos with emphasis on middle sections"""
        positions = []
        useful_frames = end_frame - start_frame
        
        # 10% from beginning
        beginning_count = max(1, int(max_frames * 0.1))
        beginning_end = start_frame + useful_frames // 10
        positions.extend(self._get_evenly_spaced_positions(start_frame, beginning_end, beginning_count))
        
        # 80% from middle 80%
        middle_count = max(1, int(max_frames * 0.8))
        middle_start = start_frame + useful_frames // 10
        middle_end = start_frame + 9 * useful_frames // 10
        positions.extend(self._get_evenly_spaced_positions(middle_start, middle_end, middle_count))
        
        # 10% from end
        end_count = max(1, max_frames - len(positions))
        end_start = start_frame + 9 * useful_frames // 10
        positions.extend(self._get_evenly_spaced_positions(end_start, end_frame, end_count))
        
        return positions
    
    def _get_evenly_spaced_positions(self, start: int, end: int, count: int) -> List[int]:
        """Get evenly spaced frame positions within a range"""
        if count <= 0 or start >= end:
            return []
        if count == 1:
            return [start + (end - start) // 2]
        
        step = (end - start) / (count - 1)
        return [int(start + i * step) for i in range(count)]


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
        Intelligently chooses processing strategy based on content quality
        """
        try:
            # Combine text sources
            combined_text = self._combine_text_sources(text, subtitles)
            
            logger.info(f"📋 Total text input: {len(combined_text)} characters")
            logger.info(f"🖼️ Frame input: {len(frames) if frames else 0} frames")
            
            if not combined_text and not frames:
                logger.warning("⚠️ No text or frames available for processing")
                return self._create_fallback_recipe("Keine Daten zum Verarbeiten gefunden")
            
            # 🚀 INTELLIGENT PROCESSING STRATEGY
            processing_strategy = self._determine_processing_strategy(combined_text, subtitles, frames)
            logger.info(f"🧠 Selected processing strategy: {processing_strategy}")
            
            if processing_strategy == "text_only":
                # Fast text-only processing for high-quality subtitles
                return self._process_text_only_optimized(combined_text, language)
            elif processing_strategy == "reduced_frames":
                # Reduced frames with good text
                reduced_frames = frames[:5] if frames else []
                logger.info(f"📉 Reduced frames from {len(frames) if frames else 0} to {len(reduced_frames)}")
                user_content = self._build_user_content(combined_text, reduced_frames, language)
                response = self._make_openai_request(user_content, language)
                return self._process_openai_response(response)
            else:
                # Full processing for poor text quality
                user_content = self._build_user_content(combined_text, frames, language)
                response = self._make_openai_request(user_content, language)
                return self._process_openai_response(response)
            
        except Exception as e:
            logger.error(f"❌ OpenAI processing failed: {e}")
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            
            # Fallback to text-only processing
            if text or subtitles:
                logger.info("🔄 Attempting fallback to text-only processing...")
                return self._process_text_only(text or subtitles, language)
            
            return self._create_fallback_recipe(f"Fehler bei Verarbeitung: {str(e)}")
    
    def _determine_processing_strategy(self, combined_text: str, subtitles: str, frames: List[str]) -> str:
        """
        Intelligently determine the best processing strategy based on content quality
        
        Returns:
            "text_only": High-quality subtitles, skip frames for speed
            "reduced_frames": Good text + few frames for verification  
            "full_processing": Poor text, need all frames
        """
        
        # No subtitles = need frames
        if not subtitles or len(subtitles.strip()) < 50:
            logger.info("🖼️ No good subtitles found, using full frame processing")
            return "full_processing"
        
        # Analyze subtitle quality
        subtitle_quality_score = self._analyze_subtitle_quality(subtitles)
        logger.info(f"📊 Subtitle quality score: {subtitle_quality_score}/100")
        
        # High quality subtitles (>80) = text only processing
        if subtitle_quality_score > 80:
            logger.info("✨ High-quality subtitles detected, using text-only processing")
            return "text_only" 
            
        # Medium quality subtitles (50-80) = reduced frames
        elif subtitle_quality_score > 50:
            logger.info("🎯 Medium-quality subtitles, using reduced frames")
            return "reduced_frames"
            
        # Poor quality subtitles (<50) = full processing
        else:
            logger.info("🔍 Poor subtitle quality, using full frame processing")  
            return "full_processing"
    
    def _analyze_subtitle_quality(self, subtitles: str) -> int:
        """
        Analyze subtitle quality and return score 0-100
        Higher score = better quality, more suitable for text-only processing
        """
        if not subtitles:
            return 0
            
        score = 0
        
        # Length check - recipe explanations are usually detailed
        if len(subtitles) > 200:
            score += 25
        elif len(subtitles) > 100:
            score += 15
        
        # Recipe keywords (German/English)
        recipe_keywords = [
            # German
            'zutaten', 'rezept', 'kochen', 'backen', 'mischen', 'rühren', 'teig', 
            'ofen', 'pfanne', 'topf', 'minuten', 'grad', 'salz', 'pfeffer', 
            'zwiebel', 'knoblauch', 'öl', 'butter', 'mehl', 'zucker', 'ei',
            # English  
            'ingredients', 'recipe', 'cooking', 'baking', 'mix', 'stir', 'dough',
            'oven', 'pan', 'pot', 'minutes', 'degrees', 'salt', 'pepper',
            'onion', 'garlic', 'oil', 'butter', 'flour', 'sugar', 'egg'
        ]
        
        keyword_count = sum(1 for keyword in recipe_keywords if keyword.lower() in subtitles.lower())
        score += min(keyword_count * 5, 30)  # Max 30 points for keywords
        
        # Cooking actions/instructions
        action_keywords = [
            'hinzufügen', 'vermischen', 'erhitzen', 'braten', 'dünsten', 'würzen',
            'add', 'mix', 'heat', 'fry', 'sauté', 'season', 'bake', 'boil'
        ]
        
        action_count = sum(1 for action in action_keywords if action.lower() in subtitles.lower())
        score += min(action_count * 3, 20)  # Max 20 points for actions
        
        # Quantity indicators
        quantity_patterns = [
            r'\d+\s*(gramm?|g\b)', r'\d+\s*(ml|liter)', r'\d+\s*(tasse|cup)', 
            r'\d+\s*(löffel|spoon)', r'\d+\s*(stück|piece)', r'\d+\s*minuten?',
            r'\d+\s*grad', r'prise', 'pinch', 'handful', 'etwas', 'some'
        ]
        
        import re
        quantity_matches = sum(1 for pattern in quantity_patterns 
                              if re.search(pattern, subtitles, re.IGNORECASE))
        score += min(quantity_matches * 4, 25)  # Max 25 points for quantities
        
        # Coherence check - avoid fragmented text
        sentences = subtitles.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        
        if avg_sentence_length > 5:  # Good sentence structure
            score += 10
        elif avg_sentence_length > 3:
            score += 5
            
        logger.debug(f"Subtitle analysis: length={len(subtitles)}, keywords={keyword_count}, actions={action_count}, quantities={quantity_matches}")
        
        return min(score, 100)
    
    def _process_text_only_optimized(self, combined_text: str, language: str) -> Dict[str, Any]:
        """
        Optimized text-only processing for high-quality subtitles
        Faster processing with focused prompts
        """
        logger.info(f"⚡ Starting optimized text-only processing with {len(combined_text)} characters")
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": self._get_optimized_system_prompt(language)
                    },
                    {
                        "role": "user", 
                        "content": self._get_optimized_text_prompt(combined_text, language)
                    }
                ],
                temperature=0.2,  # Lower temperature for more focused results
                max_tokens=1000   # Reduced tokens for faster processing
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"⚡ Text-only processing completed: {len(content)} chars")
            
            recipe_json = self._parse_recipe_json(content)
            recipe_json = self._validate_recipe_structure(recipe_json)
            
            return recipe_json
            
        except Exception as e:
            logger.error(f"❌ Optimized text processing failed: {e}")
            return self._create_fallback_recipe(f"Text-only processing failed: {str(e)}")
    
    def _get_optimized_system_prompt(self, language: str) -> str:
        """Optimized system prompt for text-only processing"""
        return prompt_service.get_optimized_system_prompt(language)
    
    def _get_optimized_text_prompt(self, combined_text: str, language: str) -> str:
        """Optimized prompt for text-only processing"""
        language_obj = prompt_service.detect_language(language)
        
        if language_obj.value == "en":
            return f"""Extract a complete recipe from this video transcript:

{combined_text[:1500]}

Create a practical, cookable recipe with specific ingredients and clear steps."""
        else:
            return f"""Extrahiere ein vollständiges Rezept aus diesem Video-Transkript:

{combined_text[:1500]}

Erstelle ein praktisches, kochbares Rezept mit konkreten Zutaten und klaren Schritten."""
    
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
        return prompt_service.get_user_prompt(language, combined_text, len(frames))
    
    def _get_frame_only_prompt(self, frames: List[str], language: str) -> str:
        """Get prompt for frame-only processing"""
        language_obj = prompt_service.detect_language(language)
        
        if language_obj.value == "en":
            return f"""Analyze all {len(frames)} video frames individually and reconstruct the complete recipe:

FRAME ANALYSIS:
- Image 1: What do you see? Which ingredients/steps?
- Image 2: What happens here? What changes?
- Image 3-{len(frames)}: Continue analysis...

Reconstruct a complete recipe even if not everything is explicitly shown. Use your cooking knowledge to create an authentic, cookable recipe.

Respond with JSON: {{"title": "Short Recipe Title", "ingredients": ["specific ingredient with quantity"], "steps": ["detailed step"]}}"""
        elif language_obj.value == "fr":
            return f"""Analysez toutes les {len(frames)} images vidéo individuellement et reconstruisez la recette complète:

ANALYSE DES IMAGES:
- Image 1: Que voyez-vous? Quels ingrédients/étapes?
- Image 2: Que se passe-t-il ici? Quels changements?
- Image 3-{len(frames)}: Suite de l'analyse...

Reconstruisez une recette complète même si tout n'est pas explicitement montré. Utilisez vos connaissances culinaires pour créer une recette authentique et réalisable.

Répondez avec JSON: {{"title": "Titre de Recette Court", "ingredients": ["ingrédient spécifique avec quantité"], "steps": ["étape détaillée"]}}"""
        elif language_obj.value == "es":
            return f"""Analiza todos los {len(frames)} fotogramas de video individualmente y reconstruye la receta completa:

ANÁLISIS DE FOTOGRAMAS:
- Imagen 1: ¿Qué ves? ¿Qué ingredientes/pasos?
- Imagen 2: ¿Qué pasa aquí? ¿Qué cambios?
- Imagen 3-{len(frames)}: Continúa el análisis...

Reconstruye una receta completa incluso si no todo se muestra explícitamente. Usa tu conocimiento culinario para crear una receta auténtica y cocible.

Responde con JSON: {{"title": "Título de Receta Corto", "ingredients": ["ingrediente específico con cantidad"], "steps": ["paso detallado"]}}"""
        elif language_obj.value == "it":
            return f"""Analizza tutti i {len(frames)} fotogrammi video individualmente e ricostruisci la ricetta completa:

ANALISI DEI FOTOGRAMMI:
- Immagine 1: Cosa vedi? Quali ingredienti/passaggi?
- Immagine 2: Cosa succede qui? Quali cambiamenti?
- Immagine 3-{len(frames)}: Continua l'analisi...

Ricostruisci una ricetta completa anche se non tutto è mostrato esplicitamente. Usa la tua conoscenza culinaria per creare una ricetta autentica e cucinabile.

Rispondi con JSON: {{"title": "Titolo Ricetta Breve", "ingredients": ["ingrediente specifico con quantità"], "steps": ["passaggio dettagliato"]}}"""
        elif language_obj.value == "nl":
            return f"""Analyseer alle {len(frames)} video frames individueel en reconstrueer het complete recept:

FRAME ANALYSE:
- Beeld 1: Wat zie je? Welke ingrediënten/stappen?
- Beeld 2: Wat gebeurt hier? Welke veranderingen?
- Beeld 3-{len(frames)}: Vervolg analyse...

Reconstrueer een compleet recept ook als niet alles expliciet wordt getoond. Gebruik je kookkennis om een authentiek, kookbaar recept te maken.

Antwoord met JSON: {{"title": "Korte Recept Titel", "ingredients": ["specifiek ingrediënt met hoeveelheid"], "steps": ["gedetailleerde stap"]}}"""
        else:  # German (default)
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
        return prompt_service.get_system_prompt(language)
    
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
            # Create language-appropriate prompts using PromptService
            language_obj = prompt_service.detect_language(language)
            system_prompt = prompt_service.get_optimized_system_prompt(language)
            
            if language_obj.value == "en":
                user_prompt = f"Extract or reconstruct a recipe from the following text:\n\n{text[:2000]}"
            else:
                user_prompt = f"Extrahiere oder rekonstruiere ein Rezept aus folgendem Text:\n\n{text[:2000]}"
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": system_prompt
                    },
                    {
                        "role": "user", 
                        "content": user_prompt
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


class SupabaseService:
    """Service for uploading recipes to Supabase with user authentication"""

    def __init__(self):
        # Use anon key for authenticated requests (not service key)
        self.client: Client = create_client(
            config.supabase_url,
            config.supabase_key  # This should be the anon key
        )
        self.storage_bucket = "recipe-thumbnails"
        logger.info(f"🗄️ Supabase client initialized for URL: {config.supabase_url}")

    async def upload_thumbnail(
        self,
        thumbnail_url: str,
        recipe_id: str,
        user_id: str,
        jwt_token: Optional[str] = None
    ) -> Optional[str]:
        """
        Download thumbnail from TikTok and upload to Supabase Storage

        Args:
            thumbnail_url: TikTok cover/thumbnail URL
            recipe_id: Unique recipe ID for filename
            user_id: User ID for RLS policy
            jwt_token: JWT token for authenticated upload

        Returns:
            Public URL of uploaded thumbnail, or None if failed
        """
        if not thumbnail_url:
            logger.warning("⚠️ No thumbnail URL provided")
            return None

        try:
            # Create authenticated client with JWT token
            if jwt_token:
                # Create a new client with the JWT token for this upload
                auth_client = create_client(
                    config.supabase_url,
                    config.supabase_key
                )
                # Set authorization header for storage operations
                auth_client.storage._client.headers['Authorization'] = f'Bearer {jwt_token}'
                logger.info(f"🔐 Created authenticated client for user_id: {user_id}")
            else:
                auth_client = self.client
                logger.warning("⚠️ No JWT token provided, using default client")

            # Download thumbnail from TikTok
            logger.info(f"📥 Downloading thumbnail from: {thumbnail_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(thumbnail_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to download thumbnail: HTTP {response.status}")
                        return None

                    thumbnail_data = await response.read()
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    logger.info(f"✅ Downloaded thumbnail: {len(thumbnail_data)} bytes, type: {content_type}")

            # Determine file extension
            extension = 'jpg'
            if 'png' in content_type:
                extension = 'png'
            elif 'webp' in content_type:
                extension = 'webp'

            # Upload to Supabase Storage with user_id in path for RLS
            file_path = f"{user_id}/{recipe_id}.{extension}"
            logger.info(f"📤 Uploading thumbnail to Supabase Storage: {self.storage_bucket}/{file_path}")

            upload_response = auth_client.storage.from_(self.storage_bucket).upload(
                path=file_path,
                file=thumbnail_data,
                file_options={"content-type": content_type, "upsert": "true"}
            )

            # Get public URL (will work with RLS for authenticated users)
            public_url = auth_client.storage.from_(self.storage_bucket).get_public_url(file_path)
            logger.info(f"✅ Thumbnail uploaded successfully: {public_url}")

            return public_url

        except Exception as e:
            logger.error(f"❌ Failed to upload thumbnail: {e}")
            return None

    async def upload_recipe(
        self,
        user_id: str,
        recipe_data: Dict[str, Any],
        original_url: str,
        thumbnail_url: Optional[str] = None,
        jwt_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload a processed recipe to Supabase with user authentication

        Args:
            user_id: The authenticated user ID from JWT
            recipe_data: Processed recipe data from OpenAI
            original_url: Original TikTok video URL
            thumbnail_url: Optional TikTok thumbnail URL to upload
            jwt_token: JWT token for user authentication

        Returns:
            The created recipe record
        """
        try:
            # Set user session if JWT token provided
            if jwt_token:
                # Set authorization header using _headers
                self.client.auth._headers['Authorization'] = f'Bearer {jwt_token}'
                logger.info(f"🔐 Set JWT authorization header for user_id: {user_id}")

            # Extract recipe from the processed data - it's nested in 'result'
            result_data = recipe_data.get('result', {})
            recipe = result_data.get('processed_recipe', {})

            # Debug: Log the actual recipe structure
            logger.info(f"🔍 Debug: recipe_data keys: {list(recipe_data.keys())}")
            logger.info(f"🔍 Debug: result_data keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'No result_data'}")
            logger.info(f"🔍 Debug: processed_recipe type: {type(recipe)}")
            logger.info(f"🔍 Debug: processed_recipe keys: {list(recipe.keys()) if isinstance(recipe, dict) else 'Not a dict'}")
            logger.info(f"🔍 Debug: recipe content preview: {str(recipe)[:200]}...")

            # Prepare recipe data for Supabase (without thumbnail_url first)
            recipe_record = {
                'name': recipe.get('title', 'Untitled Recipe')[:255],  # Truncate to prevent DB errors
                'description': recipe.get('title', 'Extracted recipe from TikTok')[:255],
                'original_link': original_url[:500],
                'ingredients': recipe.get('ingredients', []),
                'steps': recipe.get('steps', []),
                'user_id': user_id,
                'created_at': datetime.utcnow().isoformat() + "Z"
            }

            logger.info(f"📤 Uploading recipe to Supabase: {recipe_record['name']}")
            logger.debug(f"📋 Recipe data: {len(recipe_record['ingredients'])} ingredients, {len(recipe_record['steps'])} steps")

            # Insert with user authentication - RLS will allow this
            response = self.client.table('recipes').insert(recipe_record).execute()

            if response.data and len(response.data) > 0:
                created_recipe = response.data[0]
                recipe_id = created_recipe.get('id')
                logger.info(f"✅ Successfully uploaded recipe to Supabase: ID={recipe_id}")

                # Upload thumbnail if URL provided
                if thumbnail_url and recipe_id:
                    logger.info(f"📸 Uploading thumbnail for recipe {recipe_id}")
                    thumbnail_storage_url = await self.upload_thumbnail(
                        thumbnail_url=thumbnail_url,
                        recipe_id=str(recipe_id),
                        user_id=user_id,
                        jwt_token=jwt_token
                    )

                    # Update recipe with thumbnail URL
                    if thumbnail_storage_url:
                        update_response = self.client.table('recipes').update({
                            'thumbnail_url': thumbnail_storage_url
                        }).eq('id', recipe_id).execute()

                        if update_response.data and len(update_response.data) > 0:
                            created_recipe = update_response.data[0]
                            logger.info(f"✅ Updated recipe with thumbnail URL: {thumbnail_storage_url}")
                        else:
                            logger.warning("⚠️ Failed to update recipe with thumbnail URL")
                    else:
                        logger.warning("⚠️ Thumbnail upload failed, recipe saved without thumbnail")

                return created_recipe
            else:
                logger.error("❌ Supabase upload failed: No data returned")
                raise Exception("No data returned from Supabase insert")

        except Exception as e:
            logger.error(f"❌ Failed to upload recipe to Supabase: {e}")
            # Only log recipe_record if it was defined
            if 'recipe_record' in locals():
                logger.error(f"📋 Recipe data that failed: {recipe_record}")
            raise Exception(f"Supabase upload failed: {str(e)}")

    def _truncate_string(self, text: str, max_length: int) -> str:
        """Helper to safely truncate strings"""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return f"{text[:max_length-3]}..."