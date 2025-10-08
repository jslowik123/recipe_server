"""
Configuration management for TikTok scraping service
"""
import os
from dotenv import load_dotenv
from src.exceptions import ConfigurationError

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        self._validate_config()
    
    @property
    def apify_token(self) -> str:
        """Get Apify API token"""
        token = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
        if not token:
            raise ConfigurationError("APIFY_API_TOKEN or APIFY_API_KEY not found in environment variables")
        return token
    
    @property
    def openai_api_key(self) -> str:
        """Get OpenAI API key"""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("OPENAI_API_KEY not found in environment variables")
        return key
    
    @property
    def redis_url(self) -> str:
        """Get Redis URL"""
        return os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    @property
    def supabase_jwt_secret(self) -> str:
        """Get Supabase JWT secret"""
        secret = os.getenv("SUPABASE_JWT_SECRET")
        if not secret:
            raise ConfigurationError("SUPABASE_JWT_SECRET not found in environment variables")
        return secret

    @property
    def supabase_url(self) -> str:
        """Get Supabase URL"""
        url = os.getenv("SUPABASE_URL")
        if not url:
            raise ConfigurationError("SUPABASE_URL not found in environment variables")
        return url

    @property
    def supabase_key(self) -> str:
        """Get Supabase service role key"""
        key = os.getenv("SUPABASE_KEY")
        if not key:
            raise ConfigurationError("SUPABASE_KEY not found in environment variables")
        return key
    
    def _validate_config(self):
        """Validate that all required configuration is present"""
        try:
            # Test all critical config values
            _ = self.apify_token
            _ = self.openai_api_key
            _ = self.supabase_jwt_secret
            _ = self.supabase_url
            _ = self.supabase_key
        except ConfigurationError as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")

# Global config instance
config = Config()