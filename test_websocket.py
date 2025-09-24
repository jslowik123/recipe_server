#!/usr/bin/env python3
"""
WebSocket Test Script for Apify TikTok Scraper
Tests the real-time WebSocket functionality
"""
import asyncio
import json
import logging
import websockets
from typing import Optional
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WebSocketTestClient:
    def __init__(self, base_url: str = "http://localhost:8000", ws_url: str = "ws://localhost:8000"):
        self.base_url = base_url
        self.ws_url = ws_url
        self.jwt_token: Optional[str] = None

    def authenticate(self, token: str):
        """Set JWT token for authentication"""
        self.jwt_token = token
        logger.info("✅ JWT token set for authentication")

    async def start_task(self, tiktok_url: str, language: str = "de") -> str:
        """Start a TikTok scraping task via HTTP API"""
        if not self.jwt_token:
            raise ValueError("JWT token required. Call authenticate() first.")

        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "url": tiktok_url,
            "language": language
        }

        logger.info(f"🚀 Starting task for URL: {tiktok_url}")

        try:
            response = requests.post(
                f"{self.base_url}/scrape/async",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            task_id = result["task_id"]
            logger.info(f"✅ Task started successfully: {task_id}")
            return task_id

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to start task: {e}")
            raise

    async def monitor_task_websocket(self, task_id: str, max_duration: int = 300):
        """Monitor task progress via WebSocket"""
        if not self.jwt_token:
            raise ValueError("JWT token required. Call authenticate() first.")

        ws_endpoint = f"{self.ws_url}/ws/{task_id}?token={self.jwt_token}"
        logger.info(f"🔌 Connecting to WebSocket: {ws_endpoint}")

        try:
            async with websockets.connect(ws_endpoint) as websocket:
                logger.info("✅ WebSocket connected successfully")

                # Set timeout for the entire monitoring session
                timeout_task = asyncio.create_task(asyncio.sleep(max_duration))
                listen_task = asyncio.create_task(self._listen_for_messages(websocket))

                try:
                    # Wait for either timeout or completion
                    done, pending = await asyncio.wait(
                        [timeout_task, listen_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()

                    if timeout_task in done:
                        logger.warning(f"⏰ WebSocket monitoring timed out after {max_duration}s")
                    else:
                        logger.info("✅ Task completed or WebSocket closed")

                except asyncio.CancelledError:
                    logger.info("🛑 WebSocket monitoring cancelled")

        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 WebSocket connection closed")
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"❌ WebSocket error: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")

    async def _listen_for_messages(self, websocket):
        """Listen for WebSocket messages"""
        try:
            while True:
                try:
                    message = await websocket.recv()
                    await self._handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("🔌 WebSocket connection closed by server")
                    break
                except json.JSONDecodeError:
                    logger.error(f"❌ Invalid JSON received: {message}")
                except Exception as e:
                    logger.error(f"❌ Error handling message: {e}")

        except asyncio.CancelledError:
            logger.info("🛑 Message listener cancelled")

    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'unknown')

            if msg_type == 'progress':
                step = data.get('step', 0)
                total_steps = data.get('total_steps', 5)
                status = data.get('status', 'Processing...')
                details = data.get('details', '')

                progress_pct = (step / total_steps * 100) if total_steps > 0 else 0

                logger.info(f"📊 PROGRESS [{step}/{total_steps}] ({progress_pct:.0f}%): {status}")
                if details:
                    logger.info(f"    💡 Details: {details}")

            elif msg_type == 'completion':
                status = data.get('status', 'UNKNOWN')
                message = data.get('message', 'Task completed')
                recipe_id = data.get('recipe_id')
                recipe_name = data.get('recipe_name', 'Unknown Recipe')

                logger.info(f"🎉 COMPLETED: {message}")
                logger.info(f"    📝 Recipe: {recipe_name}")
                if recipe_id:
                    logger.info(f"    🆔 Recipe ID: {recipe_id}")

                upload_error = data.get('upload_error')
                if upload_error:
                    logger.warning(f"    ⚠️ Upload Error: {upload_error}")

            elif msg_type == 'error':
                status = data.get('status', 'UNKNOWN')
                error = data.get('error', 'Unknown error')
                message = data.get('message', 'Task failed')

                logger.error(f"❌ ERROR: {message}")
                logger.error(f"    🔍 Details: {error}")

            elif msg_type == 'status':
                status = data.get('status', 'UNKNOWN')
                message = data.get('message', 'Status update')
                logger.info(f"ℹ️ STATUS: {message} ({status})")

            else:
                logger.info(f"📦 UNKNOWN MESSAGE TYPE '{msg_type}': {data}")

        except json.JSONDecodeError:
            logger.error(f"❌ Invalid JSON: {message}")
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")

    async def test_http_fallback(self, task_id: str, interval: int = 5, max_polls: int = 60):
        """Test HTTP polling fallback (for comparison)"""
        if not self.jwt_token:
            raise ValueError("JWT token required. Call authenticate() first.")

        headers = {"Authorization": f"Bearer {self.jwt_token}"}

        logger.info(f"🔄 Starting HTTP polling for task: {task_id}")

        for i in range(max_polls):
            try:
                response = requests.get(
                    f"{self.base_url}/task/{task_id}",
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()

                data = response.json()
                status = data.get('status', 'UNKNOWN')

                if status == 'PENDING':
                    logger.info(f"🔄 [{i+1}/{max_polls}] PENDING: {data.get('message', 'Waiting...')}")
                elif status == 'PROGRESS':
                    step = data.get('step', 0)
                    total_steps = data.get('total_steps', 5)
                    current_status = data.get('current_status', 'Processing...')
                    progress_pct = (step / total_steps * 100) if total_steps > 0 else 0

                    logger.info(f"📊 [{i+1}/{max_polls}] PROGRESS [{step}/{total_steps}] ({progress_pct:.0f}%): {current_status}")
                elif status == 'SUCCESS':
                    message = data.get('message', 'Task completed')
                    recipe_name = data.get('recipe_name', 'Unknown Recipe')
                    logger.info(f"🎉 [{i+1}/{max_polls}] COMPLETED: {message}")
                    logger.info(f"    📝 Recipe: {recipe_name}")
                    break
                elif status == 'FAILURE':
                    error = data.get('error', 'Unknown error')
                    logger.error(f"❌ [{i+1}/{max_polls}] FAILED: {error}")
                    break
                else:
                    logger.warning(f"❓ [{i+1}/{max_polls}] UNKNOWN STATUS: {status}")

                await asyncio.sleep(interval)

            except requests.exceptions.RequestException as e:
                logger.error(f"❌ HTTP polling error: {e}")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                break

        else:
            logger.warning(f"⏰ HTTP polling timed out after {max_polls * interval}s")


# Test scenarios
async def main():
    """Main test function"""

    # Test configuration
    TEST_TIKTOK_URL = "https://www.tiktok.com/@example/video/123456789"  # Replace with real URL
    TEST_JWT_TOKEN = "your_jwt_token_here"  # Replace with real token
    BASE_URL = "http://localhost:8000"  # Change for production
    WS_URL = "ws://localhost:8000"      # Change for production

    logger.info("🧪 Starting WebSocket Test Suite")
    logger.info("=" * 60)

    try:
        # Initialize test client
        client = WebSocketTestClient(BASE_URL, WS_URL)
        client.authenticate(TEST_JWT_TOKEN)

        # Test 1: Start a task and monitor via WebSocket
        logger.info("\n🧪 TEST 1: WebSocket Real-time Monitoring")
        logger.info("-" * 40)

        task_id = await client.start_task(TEST_TIKTOK_URL, "de")
        await client.monitor_task_websocket(task_id, max_duration=300)  # 5 minutes

        logger.info("\n✅ WebSocket test completed")

        # Optional Test 2: HTTP Polling comparison
        # logger.info("\n🧪 TEST 2: HTTP Polling (Comparison)")
        # logger.info("-" * 40)
        #
        # task_id_2 = await client.start_task(TEST_TIKTOK_URL, "de")
        # await client.test_http_fallback(task_id_2, interval=5, max_polls=60)

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise

    logger.info("\n🏁 Test suite completed")


if __name__ == "__main__":
    print("""
🧪 WebSocket Test Script for Apify TikTok Scraper

Before running this test:
1. Update TEST_JWT_TOKEN with a valid Supabase JWT token
2. Update TEST_TIKTOK_URL with a real TikTok URL
3. Make sure your services are running (docker-compose up)
4. Update BASE_URL and WS_URL if not running locally

Running test...
    """)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 Test interrupted by user")
    except Exception as e:
        logger.error(f"\n💥 Test failed with error: {e}")
        exit(1)