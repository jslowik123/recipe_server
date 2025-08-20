#!/usr/bin/env python3
"""
Simple TikTok URL tester to find working videos before full extraction
"""

import os
import sys
from dotenv import load_dotenv
from apify_client import ApifyClient
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_tiktok_url(url: str):
    """Test if a TikTok URL works with Apify"""
    logger.info(f"🧪 Testing URL: {url}")
    
    try:
        apify_token = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
        if not apify_token:
            logger.error("❌ No Apify token found")
            return False
        
        client = ApifyClient(apify_token)
        
        # Minimal test run
        run_input = {
            "postURLs": [url],
            "scrapeRelatedVideos": False,
            "resultsPerPage": 1,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": True,
        }
        
        logger.info("🚀 Testing with Apify...")
        run = client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)
        
        if run and "defaultDatasetId" in run:
            dataset_id = run["defaultDatasetId"]
            
            for item in client.dataset(dataset_id).iterate_items():
                if 'error' in item:
                    error_msg = item.get('error', 'Unknown error')
                    logger.error(f"❌ FAILED: {error_msg}")
                    return False
                
                text = item.get('text', '')
                has_video_meta = bool(item.get('videoMeta'))
                
                logger.info(f"✅ SUCCESS!")
                logger.info(f"   📝 Text length: {len(text)} chars")
                logger.info(f"   🎥 Has video metadata: {has_video_meta}")
                
                if has_video_meta:
                    video_meta = item['videoMeta']
                    subtitle_count = len(video_meta.get('subtitleLinks', []))
                    logger.info(f"   📋 Subtitle links: {subtitle_count}")
                
                return True
        
        logger.error("❌ No dataset returned")
        return False
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("🔍 TikTok URL Tester")
        print("Usage: python url_tester.py 'https://www.tiktok.com/@user/video/ID'")
        print()
        print("📋 Examples of URLs to try:")
        print("  • https://www.tiktok.com/@gordon_ramsayofficial/video/[LATEST_VIDEO_ID]")
        print("  • https://www.tiktok.com/@cooking_with_shereen/video/[LATEST_VIDEO_ID]")
        print("  • https://www.tiktok.com/@recipesbybryan/video/[LATEST_VIDEO_ID]")
        print()
        print("💡 To find working URLs:")
        print("  1. Go to TikTok.com")
        print("  2. Search for recipe videos")
        print("  3. Copy the URL from a public video")
        print("  4. Paste it here to test")
        return
    
    url = sys.argv[1]
    
    if not url.startswith('https://www.tiktok.com/'):
        logger.error("❌ Invalid URL format. Must start with https://www.tiktok.com/")
        return
    
    success = test_tiktok_url(url)
    
    if success:
        print(f"\n🎉 SUCCESS! This URL works:")
        print(f"   {url}")
        print(f"\n💡 You can now test recipe extraction with:")
        print(f"   python enhanced_recipe_test.py '{url}'")
    else:
        print(f"\n❌ FAILED! This URL doesn't work.")
        print(f"   Reasons could be:")
        print(f"   • Video is private")
        print(f"   • Video was deleted")
        print(f"   • Invalid URL format")
        print(f"   • TikTok blocking/rate limiting")
        print(f"\n💡 Try finding a different public recipe video on TikTok")

if __name__ == "__main__":
    main()