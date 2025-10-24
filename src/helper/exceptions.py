"""
Custom exceptions for Wardroberry API
"""

# Legacy exceptions (kept for compatibility)
class ApifyError(Exception):
    """Raised when Apify API operations fail"""
    pass

class OpenAIError(Exception):
    """Raised when OpenAI API operations fail"""
    pass


# Wardroberry exceptions
class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid"""
    pass


class DatabaseError(Exception):
    """Raised when database operations fail"""
    pass


class StorageError(Exception):
    """Raised when file storage operations fail"""
    pass


class ProcessingError(Exception):
    """Raised when async processing fails"""
    pass


class QueueError(Exception):
    """Raised when queue operations fail"""
    pass
