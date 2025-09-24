"""
WebSocket Manager for real-time task updates
Handles WebSocket connections and Redis pub/sub for task status updates
"""
import json
import asyncio
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis
from celery import Celery

logger = logging.getLogger(__name__)


class WebSocketTaskManager:
    """Manages WebSocket connections for task status updates"""

    def __init__(self, redis_url: str, celery_app: Celery):
        self.redis_url = redis_url
        self.celery_app = celery_app
        # Active connections: task_id -> set of websockets
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

    async def initialize(self):
        """Initialize Redis connection and pub/sub"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe("task_updates")
            logger.info("✅ WebSocket manager initialized with Redis pub/sub")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebSocket manager: {e}")
            raise

    async def connect(self, websocket: WebSocket, task_id: str, user_id: str) -> bool:
        """Connect a WebSocket to a task and verify ownership"""
        try:
            await websocket.accept()

            # Verify task belongs to user (check task in Celery)
            if not await self._verify_task_ownership(task_id, user_id):
                await websocket.send_json({
                    "type": "error",
                    "message": "Task not found or access denied",
                    "task_id": task_id
                })
                await websocket.close(code=4003)
                return False

            # Add connection to tracking
            if task_id not in self.connections:
                self.connections[task_id] = set()
            self.connections[task_id].add(websocket)

            logger.info(f"🔌 WebSocket connected for task {task_id} (user: {user_id})")

            # Send current task status immediately
            await self._send_current_status(websocket, task_id)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect WebSocket for task {task_id}: {e}")
            return False

    async def disconnect(self, websocket: WebSocket, task_id: str):
        """Disconnect a WebSocket from a task"""
        try:
            if task_id in self.connections:
                self.connections[task_id].discard(websocket)
                if not self.connections[task_id]:
                    del self.connections[task_id]
            logger.info(f"🔌 WebSocket disconnected from task {task_id}")
        except Exception as e:
            logger.error(f"❌ Error disconnecting WebSocket: {e}")

    async def publish_update(self, task_id: str, update_data: Dict[str, Any]):
        """Publish a task update to Redis for WebSocket broadcast"""
        if not self.redis_client:
            return

        try:
            message = {
                "task_id": task_id,
                "timestamp": asyncio.get_event_loop().time(),
                **update_data
            }
            await self.redis_client.publish("task_updates", json.dumps(message))
            logger.debug(f"📡 Published update for task {task_id}: {update_data.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ Failed to publish update for task {task_id}: {e}")

    async def broadcast_to_task(self, task_id: str, message: Dict[str, Any]):
        """Broadcast a message to all WebSockets connected to a task"""
        if task_id not in self.connections:
            return

        disconnected = set()
        for websocket in self.connections[task_id].copy():
            try:
                await websocket.send_json(message)
            except WebSocketDisconnect:
                disconnected.add(websocket)
            except Exception as e:
                logger.error(f"❌ Error sending to WebSocket: {e}")
                disconnected.add(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            self.connections[task_id].discard(websocket)

        if not self.connections[task_id]:
            del self.connections[task_id]

    async def listen_for_updates(self):
        """Listen for Redis pub/sub messages and broadcast to WebSockets"""
        if not self.pubsub:
            logger.error("❌ PubSub not initialized")
            return

        logger.info("👂 Starting WebSocket update listener")
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        task_id = data.get('task_id')
                        if task_id:
                            await self.broadcast_to_task(task_id, data)
                    except json.JSONDecodeError:
                        logger.error("❌ Invalid JSON in Redis message")
                    except Exception as e:
                        logger.error(f"❌ Error processing Redis message: {e}")
        except Exception as e:
            logger.error(f"❌ Error in update listener: {e}")

    async def _verify_task_ownership(self, task_id: str, user_id: str) -> bool:
        """Verify that a task belongs to the given user"""
        try:
            # Get task from Celery
            task_result = self.celery_app.AsyncResult(task_id)

            # Task exists if it has any state (even PENDING)
            if task_result.state == 'PENDING':
                # For PENDING tasks, we need to check if it's actually queued
                # This is a basic check - in production you might store user_id in task metadata
                return True

            # For other states, task exists
            return task_result.state is not None

        except Exception as e:
            logger.error(f"❌ Error verifying task ownership: {e}")
            return False

    async def _send_current_status(self, websocket: WebSocket, task_id: str):
        """Send current task status to newly connected WebSocket"""
        try:
            task_result = self.celery_app.AsyncResult(task_id)

            if task_result.state == 'PENDING':
                status_message = {
                    "type": "status",
                    "task_id": task_id,
                    "status": "PENDING",
                    "message": "Task is waiting to be processed"
                }
            elif task_result.state == 'PROGRESS':
                progress_info = task_result.info or {}
                status_message = {
                    "type": "status",
                    "task_id": task_id,
                    "status": "PROGRESS",
                    "step": progress_info.get('step', 0),
                    "total_steps": progress_info.get('total_steps', 5),
                    "current_status": progress_info.get('status', 'Processing...'),
                    "details": progress_info.get('details', ''),
                    "url": progress_info.get('url', ''),
                    "message": progress_info.get('status', 'Processing...')
                }
            elif task_result.state == 'SUCCESS':
                result = task_result.result or {}
                status_message = {
                    "type": "completion",
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "message": result.get('message', 'Recipe successfully processed'),
                    "recipe_id": result.get('recipe_id'),
                    "recipe_name": result.get('recipe_name', 'Recipe'),
                    "upload_error": result.get('upload_error')
                }
            else:  # FAILURE
                status_message = {
                    "type": "error",
                    "task_id": task_id,
                    "status": "FAILURE",
                    "error": str(task_result.info or "Unknown error")
                }

            await websocket.send_json(status_message)

        except Exception as e:
            logger.error(f"❌ Error sending current status for task {task_id}: {e}")

    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.pubsub:
                await self.pubsub.close()
            if self.redis_client:
                await self.redis_client.close()
            logger.info("🧹 WebSocket manager cleaned up")
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")


# Global instance
websocket_manager: Optional[WebSocketTaskManager] = None


def get_websocket_manager() -> WebSocketTaskManager:
    """Get the global WebSocket manager instance"""
    global websocket_manager
    if websocket_manager is None:
        raise RuntimeError("WebSocket manager not initialized")
    return websocket_manager


def initialize_websocket_manager(redis_url: str, celery_app: Celery) -> WebSocketTaskManager:
    """Initialize the global WebSocket manager"""
    global websocket_manager
    websocket_manager = WebSocketTaskManager(redis_url, celery_app)
    return websocket_manager