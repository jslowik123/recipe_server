"""
WebSocket Manager for real-time clothing processing updates
Handles WebSocket connections and Redis pub/sub for processing status updates
"""
import json
import asyncio
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis
from datetime import datetime

logger = logging.getLogger(__name__)


class ClothingWebSocketManager:
    """Manages WebSocket connections for clothing processing updates"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        # Active connections: clothing_id -> set of websockets
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.listener_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize Redis connection and pub/sub"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe("clothing_updates")
            logger.info("✅ WebSocket manager initialized with Redis pub/sub")

            # Start listener in background
            self.listener_task = asyncio.create_task(self.listen_for_updates())
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebSocket manager: {e}")
            raise

    async def connect(self, websocket: WebSocket, clothing_id: str, user_id: str) -> bool:
        """
        Connect a WebSocket for a clothing item

        Args:
            websocket: FastAPI WebSocket connection
            clothing_id: UUID of clothing item to track
            user_id: Authenticated user ID (already verified from JWT)

        Returns:
            True if connection successful
        """
        try:
            await websocket.accept()

            # Add connection to tracking
            if clothing_id not in self.connections:
                self.connections[clothing_id] = set()
            self.connections[clothing_id].add(websocket)

            logger.info(f"🔌 WebSocket connected for clothing {clothing_id} (user: {user_id[:8]}...)")

            # Send connection confirmation
            await websocket.send_json({
                "type": "connected",
                "clothing_id": clothing_id,
                "message": "Connected to clothing processing updates",
                "timestamp": datetime.utcnow().isoformat()
            })

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect WebSocket for clothing {clothing_id}: {e}")
            return False

    async def disconnect(self, websocket: WebSocket, clothing_id: str):
        """Disconnect a WebSocket from a clothing item"""
        try:
            if clothing_id in self.connections:
                self.connections[clothing_id].discard(websocket)
                if not self.connections[clothing_id]:
                    del self.connections[clothing_id]
            logger.info(f"🔌 WebSocket disconnected from clothing {clothing_id}")
        except Exception as e:
            logger.error(f"❌ Error disconnecting WebSocket: {e}")

    async def publish_update(self, clothing_id: str, update_data: Dict[str, Any]):
        """
        Publish a processing update to Redis for WebSocket broadcast

        Args:
            clothing_id: UUID of clothing item
            update_data: Update data to send (type, status, message, etc.)
        """
        if not self.redis_client:
            logger.warning("⚠️ Redis client not initialized, cannot publish update")
            return

        try:
            message = {
                "clothing_id": clothing_id,
                "timestamp": datetime.utcnow().isoformat(),
                **update_data
            }
            await self.redis_client.publish("clothing_updates", json.dumps(message))
            logger.debug(f"📡 Published update for clothing {clothing_id}: {update_data.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ Failed to publish update for clothing {clothing_id}: {e}")

    async def broadcast_to_clothing(self, clothing_id: str, message: Dict[str, Any]):
        """Broadcast a message to all WebSockets connected to a clothing item"""
        if clothing_id not in self.connections:
            logger.debug(f"No active connections for clothing {clothing_id}")
            return

        disconnected = set()
        success_count = 0

        for websocket in self.connections[clothing_id].copy():
            try:
                await websocket.send_json(message)
                success_count += 1
            except WebSocketDisconnect:
                disconnected.add(websocket)
            except Exception as e:
                logger.error(f"❌ Error sending to WebSocket: {e}")
                disconnected.add(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            self.connections[clothing_id].discard(websocket)

        if not self.connections[clothing_id]:
            del self.connections[clothing_id]

        if success_count > 0:
            logger.debug(f"📤 Broadcast to {success_count} clients for clothing {clothing_id}")

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
                        clothing_id = data.get('clothing_id')
                        if clothing_id:
                            await self.broadcast_to_clothing(clothing_id, data)
                    except json.JSONDecodeError:
                        logger.error("❌ Invalid JSON in Redis message")
                    except Exception as e:
                        logger.error(f"❌ Error processing Redis message: {e}")
        except asyncio.CancelledError:
            logger.info("👂 Update listener cancelled")
        except Exception as e:
            logger.error(f"❌ Error in update listener: {e}")

    async def cleanup(self):
        """Cleanup resources"""
        try:
            # Cancel listener task
            if self.listener_task:
                self.listener_task.cancel()
                try:
                    await self.listener_task
                except asyncio.CancelledError:
                    pass

            # Close connections
            if self.pubsub:
                await self.pubsub.unsubscribe("clothing_updates")
                await self.pubsub.close()
            if self.redis_client:
                await self.redis_client.close()
            logger.info("🧹 WebSocket manager cleaned up")
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")


# Global instance
websocket_manager: Optional[ClothingWebSocketManager] = None


def get_websocket_manager() -> ClothingWebSocketManager:
    """Get the global WebSocket manager instance"""
    global websocket_manager
    if websocket_manager is None:
        raise RuntimeError("WebSocket manager not initialized")
    return websocket_manager


async def initialize_websocket_manager(redis_url: str) -> ClothingWebSocketManager:
    """Initialize the global WebSocket manager"""
    global websocket_manager
    websocket_manager = ClothingWebSocketManager(redis_url)
    await websocket_manager.initialize()
    return websocket_manager