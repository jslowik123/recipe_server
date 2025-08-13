import fastapi
import uvicorn
from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from tasks import scrape_tiktok_async, long_running_task, celery_app
import os

app = fastapi.FastAPI(title="Apify TikTok Scraper with Redis", version="1.0.0")

# Pydantic Models
class TikTokScrapeRequest(BaseModel):
    url: str
    process_with_ai: bool = True



class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

@app.get("/")
def read_root():
    return {"message": "Apify TikTok Scraper with Redis Queue", "redis_connected": check_redis_connection()}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "redis_connected": check_redis_connection(),
        "services": ["web", "redis", "worker"]
    }

@app.post("/scrape/async", response_model=TaskResponse)
def scrape_tiktok_videos_async(request: TikTokScrapeRequest):
    """
    Start asynchronous TikTok scraping task for a single URL
    """
    try:
        # Validate URL
        if not request.url or not request.url.strip():
            raise HTTPException(status_code=422, detail="URL is required and cannot be empty")
        
        # Start the async task
        task = scrape_tiktok_async.delay(request.url.strip(), request.process_with_ai)
        
        return TaskResponse(
            task_id=task.id,
            status="PENDING",
            message=f"Started scraping TikTok video: {request.url}. Use /task/{task.id} to check progress."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start task: {str(e)}")


@app.get("/task/{task_id}")
def get_task_status(task_id: str):
    """
    Get the status and result of a task
    """
    try:
        task_result = celery_app.AsyncResult(task_id)
        
        if task_result.state == 'PENDING':
            return {
                "task_id": task_id,
                "status": "PENDING",
                "message": "Task is waiting to be processed"
            }
        elif task_result.state == 'PROGRESS':
            progress_info = task_result.info or {}
            return {
                "task_id": task_id,
                "status": "PROGRESS",
                "step": progress_info.get('step', 0),
                "total_steps": progress_info.get('total_steps', 1),
                "current_status": progress_info.get('status', 'Processing...'),
                "details": progress_info.get('details', ''),
                "url": progress_info.get('url', ''),
                "message": progress_info.get('status', 'Processing...')
            }
        elif task_result.state == 'SUCCESS':
            result = task_result.result
            response = {
                "task_id": task_id,
                "status": "SUCCESS",
                "result": result
            }
            
            # If there's AI processing, make it more visible
            if result and isinstance(result, dict):
                video_result = result.get('result', {})
                if video_result and video_result.get('processed_recipe'):
                    response["ai_recipe"] = video_result['processed_recipe']
                    response["has_ai_processing"] = True
                else:
                    response["has_ai_processing"] = False
                    
                # Also add summary info for easier access
                response["summary"] = {
                    "url": result.get('url', ''),
                    "has_subtitles": result.get('has_subtitles', False),
                    "has_ai_processing": result.get('has_ai_processing', False),
                    "processed_at": result.get('processed_at', '')
                }
            
            return response
        else:  # FAILURE
            return {
                "task_id": task_id,
                "status": "FAILURE",
                "error": str(task_result.info)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")

@app.post("/test/long-task")
def start_long_task(duration: int = 10):
    """
    Start a test long-running task
    """
    task = long_running_task.delay(duration)
    return {
        "task_id": task.id,
        "message": f"Started {duration}s test task. Use /task/{task.id} to check progress."
    }

@app.get("/tasks/active")
def get_active_tasks():
    """
    Get list of active tasks
    """
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        return {"active_tasks": active_tasks}
    except Exception as e:
        return {"error": f"Failed to get active tasks: {str(e)}"}

def check_redis_connection():
    """
    Check if Redis is connected
    """
    try:
        import redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        r = redis.from_url(redis_url)
        r.ping()
        return True
    except:
        return False

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)