"""
Custom exceptions for TikTok scraping service
"""

class TikTokScrapingError(Exception):
    """Base exception for TikTok scraping operations"""
    pass

class ApifyError(TikTokScrapingError):
    """Raised when Apify API operations fail"""
    pass

class OpenAIError(TikTokScrapingError):
    """Raised when OpenAI API operations fail"""
    pass

class VideoProcessingError(TikTokScrapingError):
    """Raised when video processing operations fail"""
    pass

class ConfigurationError(TikTokScrapingError):
    """Raised when configuration is invalid or missing"""
    pass

class VideoDownloadError(VideoProcessingError):
    """Raised when video download fails"""
    pass

class FrameExtractionError(VideoProcessingError):
    """Raised when frame extraction fails"""
    pass