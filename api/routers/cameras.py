"""
Camera and stream management routes.
"""
import logging
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
import redis
import os

from api.models import CameraRegisterRequest, StreamRegisterRequest, CameraStatus
from api.services import CacheService, StreamService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cameras", tags=["cameras"])

# Initialize Redis client
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)
cache = CacheService(redis_client)
stream_service = StreamService()

VIDEO_CHUNKS_ROOT = Path("/tmp/video_chunks").resolve()


def _build_chunk_playback_url(chunk_path: Optional[str]) -> Optional[str]:
    if not chunk_path or chunk_path.startswith("placeholder://"):
        return None

    try:
        resolved = Path(chunk_path).resolve()
        relative = resolved.relative_to(VIDEO_CHUNKS_ROOT)
        return f"/video-chunks/{relative.as_posix()}"
    except Exception:
        return None


def _resolve_playback_url(
    stream_url: Optional[str],
    stream_type: Optional[str],
    latest_chunk_path: Optional[str],
) -> Optional[str]:
    if stream_type in {"hls", "youtube", "youtube_live"} and stream_url:
        return stream_url
    return _build_chunk_playback_url(latest_chunk_path)


@router.post("/register", response_model=CameraStatus)
async def register_camera(request: CameraRegisterRequest):
    """Register a new RTSP camera for processing."""
    try:
        cache.redis.hset(f"camera:{request.camera_id}", mapping={
            "rtsp_url": request.rtsp_url,
            "stream_type": "rtsp",
            "status": "pending",
            "registered_at": int(datetime.now().timestamp())
        })
        
        # Queue for processing
        task = {
            "action": "start",
            "camera_id": request.camera_id,
            "rtsp_url": request.rtsp_url,
            "stream_type": "rtsp"
        }
        cache.queue_task("rtsp_tasks", task)
        
        logger.info(f"Registered camera: {request.camera_id}")
        
        return CameraStatus(
            camera_id=request.camera_id,
            rtsp_url=request.rtsp_url,
            playback_url=_resolve_playback_url(request.rtsp_url, "rtsp", None),
            stream_type="rtsp",
            status="pending"
        )
    except Exception as e:
        logger.error(f"Failed to register camera: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register camera: {str(e)}")


@router.post("/streams/register", response_model=CameraStatus)
async def register_stream(request: StreamRegisterRequest):
    """
    Register a new live stream (RTSP, HLS, or YouTube Live).
    Auto-detects stream type if not specified.
    """
    try:
        # Validate URL
        is_valid, error_msg = stream_service.validate_stream_url(request.stream_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Detect stream type
        stream_type = request.stream_type
        if stream_type == "auto":
            stream_type = stream_service.detect_stream_type(request.stream_url)
        
        # Store config
        cache.redis.hset(f"camera:{request.stream_id}", mapping={
            "rtsp_url": request.stream_url,
            "stream_type": stream_type,
            "status": "pending",
            "registered_at": int(datetime.now().timestamp())
        })
        
        # Queue for processing
        task = {
            "action": "start_hls" if stream_type in ("hls", "youtube", "youtube_live") else "start",
            "stream_id": request.stream_id,
            "stream_url": request.stream_url,
            "stream_type": stream_type
        }
        cache.queue_task("rtsp_tasks", task)
        
        logger.info(f"Registered {stream_type} stream: {request.stream_id}")
        
        return CameraStatus(
            camera_id=request.stream_id,
            rtsp_url=request.stream_url,
            playback_url=_resolve_playback_url(request.stream_url, stream_type, None),
            stream_type=stream_type,
            status="pending"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register stream: {str(e)}")


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str):
    """Stop processing a camera/stream."""
    try:
        task = {
            "action": "stop",
            "camera_id": camera_id
        }
        cache.queue_task("rtsp_tasks", task)
        return {"message": f"Stop command sent for: {camera_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop camera: {str(e)}")


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str):
    """Remove a registered camera/stream."""
    try:
        task = {
            "action": "stop",
            "camera_id": camera_id
        }
        cache.queue_task("rtsp_tasks", task)
        cache.redis.delete(cache.camera_key(camera_id))
        cache.redis.delete(f"live_detections:{camera_id}")
        return {"message": f"Removed camera: {camera_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove camera: {str(e)}")


@router.get("", response_model=List[CameraStatus])
async def list_cameras():
    """List all registered cameras/streams."""
    try:
        cameras = []
        for cam in cache.list_cameras():
            cameras.append(CameraStatus(
                camera_id=cam["camera_id"],
                rtsp_url=cam.get("rtsp_url"),
                playback_url=_resolve_playback_url(
                    cam.get("rtsp_url"),
                    cam.get("stream_type"),
                    cam.get("latest_chunk_path"),
                ),
                stream_type=cam.get("stream_type"),
                status=cam.get("status", "unknown"),
                last_update=int(cam["last_update"]) if cam.get("last_update") else None,
                last_clip_id=int(cam["last_clip_id"]) if cam.get("last_clip_id") else None,
                error=cam.get("error")
            ))
        return cameras
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list cameras: {str(e)}")


@router.get("/{camera_id}", response_model=CameraStatus)
async def get_camera(camera_id: str):
    """Get status of a specific camera."""
    info = cache.get_camera(camera_id)
    if not info:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraStatus(
        camera_id=camera_id,
        rtsp_url=info.get("rtsp_url"),
        playback_url=_resolve_playback_url(
            info.get("rtsp_url"),
            info.get("stream_type"),
            info.get("latest_chunk_path"),
        ),
        stream_type=info.get("stream_type"),
        status=info.get("status", "unknown"),
        last_update=int(info["last_update"]) if info.get("last_update") else None,
        last_clip_id=int(info["last_clip_id"]) if info.get("last_clip_id") else None,
        error=info.get("error")
    )
