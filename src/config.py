"""
Configuration management for Wardroberry API
"""
import os
from dotenv import load_dotenv
from src.helper.exceptions import ConfigurationError

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration management"""

    def __init__(self):
        # Don't validate on init - allow lazy loading
        pass

    @property
    def openai_api_key(self) -> str:
        """Get OpenAI API key"""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("OPENAI_API_KEY not found in environment variables")
        return key

    @property
    def redis_host(self) -> str:
        """Get Redis host"""
        return os.getenv('REDIS_HOST', 'localhost')

    @property
    def redis_port(self) -> int:
        """Get Redis port"""
        return int(os.getenv('REDIS_PORT', '6379'))

    @property
    def redis_password(self) -> str:
        """Get Redis password"""
        return os.getenv('REDIS_PASSWORD', '')

    @property
    def redis_db(self) -> int:
        """Get Redis database number"""
        return int(os.getenv('REDIS_DB', '0'))

    @property
    def redis_url(self) -> str:
        """Get Redis URL (for backwards compatibility)"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

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
    def supabase_anon_key(self) -> str:
        """Get Supabase anon/public key"""
        key = os.getenv("SUPABASE_ANON_KEY")
        if not key:
            raise ConfigurationError("SUPABASE_ANON_KEY not found in environment variables")
        return key

# Global config instance
config = Config()