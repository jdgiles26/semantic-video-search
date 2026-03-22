"""
Task management routes.
"""
import logging
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
import redis
import os

from api.models import URLProcessRequest, TaskStatus
from api.services import CacheService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)
cache = CacheService(redis_client)


@router.post("/url", response_model=TaskStatus)
async def process_video_url(request: URLProcessRequest, background_tasks: BackgroundTasks):
    """Submit a video URL for processing."""
    try:
        task_id = str(uuid.uuid4())
        
        # Store initial status
        cache.redis.hset(f"task:{task_id}", mapping={
            "type": "url",
            "url": request.url,
            "status": "queued",
            "clips_processed": 0,
            "frames_processed": 0,
            "created_at": int(datetime.now().timestamp())
        })
        
        # Queue task
        task = {
            "task_id": task_id,
            "type": "url",
            "url": request.url,
            "max_duration": request.max_duration
        }
        cache.queue_task("video_tasks", task)
        
        logger.info(f"Queued URL task: {task_id}")
        
        return TaskStatus(
            task_id=task_id,
            type="url",
            status="queued",
            url=request.url
        )
    except Exception as e:
        logger.error(f"Failed to queue URL task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get the status of a processing task."""
    info = cache.get_task(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatus(
        task_id=task_id,
        type=info.get("type"),
        status=info.get("status", "unknown"),
        url=info.get("url"),
        filename=info.get("filename"),
        clips_processed=int(info.get("clips_processed", 0)),
        frames_processed=int(info.get("frames_processed", 0)),
        error=info.get("error"),
        asset_id=info.get("asset_id"),
        media_kind=info.get("media_kind"),
        thumbnail_path=info.get("thumbnail_path"),
    )


@router.get("", response_model=List[TaskStatus])
async def list_tasks(status: Optional[str] = Query(None, description="Filter by status")):
    """List all processing tasks."""
    try:
        tasks = []
        for task in cache.list_tasks(status_filter=status):
            tasks.append(TaskStatus(
                task_id=task["task_id"],
                type=task.get("type"),
                status=task.get("status", "unknown"),
                url=task.get("url"),
                filename=task.get("filename"),
                clips_processed=int(task.get("clips_processed", 0)),
                frames_processed=int(task.get("frames_processed", 0)),
                error=task.get("error"),
                asset_id=task.get("asset_id"),
                media_kind=task.get("media_kind"),
                thumbnail_path=task.get("thumbnail_path"),
            ))
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")
