"""
Celery Worker Entry Point for Wardroberry API

Starts Celery worker with gevent pool for async I/O processing.

Usage:
    python -m src.worker
"""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """
    Starts Celery worker with gevent pool
    """
    print("""
    🧥 Wardroberry Celery Worker (gevent)
    ========================================

    Processing clothing items with Celery + Redis + gevent:
    - Background extraction
    - AI analysis
    - Database updates

    Pool: gevent (async I/O)
    Concurrency: 20 greenlets

    Press Ctrl+C to stop.
    """)

    try:
        from src.tasks import celery_app

        # Start Celery worker with gevent
        logger.info("🚀 Starting Celery worker with gevent pool...")

        celery_app.worker_main([
            'worker',
            '--loglevel=info',
            '--pool=gevent',
            '--concurrency=20',
        ])

    except ImportError as e:
        logger.error(f"❌ Failed to import Celery app: {e}")
        logger.error("Make sure Celery and gevent are installed:")
        logger.error("  pip install celery[redis] gevent")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Worker stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 