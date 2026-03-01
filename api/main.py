"""
Video Search API - FastAPI backend for semantic video search
"""
import os
import uuid
import shutil
from typing import List, Optional
from datetime import datetime
import json
import logging

from fastapi import FastAPI, Query, HTTPException, File, UploadFile, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import redis

# Add processing module to path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'processing'))

from embedding import get_embedder, get_embedder_for_mode
from vector_store import get_vector_store
from hybrid_search import HybridScorer, enhance_search_results

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Search API",
    description="Semantic video search platform with RTSP, URL, and upload support",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize connections
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
milvus_host = os.getenv("MILVUS_HOST", "localhost")
milvus_port = os.getenv("MILVUS_PORT", "19530")
storage_path = os.getenv("STORAGE_PATH", "/tmp/video_uploads")

redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# Lazy initialization of embedder, vector store, and hybrid scorer
_embedders = {}
_vector_store = None
_hybrid_scorer = None

def get_embedder_instance(model_key: str = 'standard'):
    """Get embedder for specified model key."""
    global _embedders
    if model_key not in _embedders:
        logger.info(f"Lazy loading embedder for model: {model_key}")
        _embedders[model_key] = get_embedder(model_key)
    return _embedders[model_key]

def get_vector_store_instance(embedding_dim: int = 512):
    """Get vector store instance, creating if needed."""
    global _vector_store
    if _vector_store is None:
        logger.info("Lazy loading vector store...")
        _vector_store = get_vector_store(host=milvus_host, port=milvus_port, 
                                         embedding_dim=embedding_dim)
    return _vector_store

def get_hybrid_scorer():
    """Get hybrid scorer instance for YOLO+CLIP search."""
    global _hybrid_scorer
    if _hybrid_scorer is None:
        logger.info("Lazy loading hybrid scorer...")
        _hybrid_scorer = HybridScorer()
    return _hybrid_scorer

# Ensure storage directory exists
os.makedirs(storage_path, exist_ok=True)


# Pydantic models
class SearchResult(BaseModel):
    id: int
    score: float
    source_type: str
    source_name: str
    timestamp: int
    video_chunk_path: str
    thumbnail_path: Optional[str] = None
    start_offset: int
    end_offset: int
    frame_count: int


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_count: int


class CameraRegisterRequest(BaseModel):
    camera_id: str
    rtsp_url: str


class CameraStatus(BaseModel):
    camera_id: str
    rtsp_url: Optional[str] = None
    status: str
    last_update: Optional[int] = None
    last_clip_id: Optional[int] = None


class URLProcessRequest(BaseModel):
    url: str
    max_duration: Optional[int] = None  # Maximum seconds to process


class TaskStatus(BaseModel):
    task_id: str
    type: Optional[str] = None
    status: str
    url: Optional[str] = None
    filename: Optional[str] = None
    clips_processed: int = 0
    frames_processed: int = 0
    error: Optional[str] = None


class StatsResponse(BaseModel):
    total_clips: int
    collection_name: str
    embedding_dim: int
    active_cameras: int
    pending_tasks: int


# API Endpoints

@app.get("/")
async def root():
    """API health check."""
    return {
        "status": "healthy",
        "service": "Video Search API",
        "version": "1.0.0"
    }


@app.get("/query", response_model=SearchResponse)
async def search_videos(
    query: str = Query(..., min_length=1, description="Natural language search query"),
    top_k: int = Query(10, ge=1, le=100, description="Number of results to return"),
    source_type: Optional[str] = Query(None, description="Filter by source type: live, url, upload"),
    source_name: Optional[str] = Query(None, description="Filter by source name/camera ID"),
    min_timestamp: Optional[int] = Query(None, description="Filter by minimum timestamp"),
    max_timestamp: Optional[int] = Query(None, description="Filter by maximum timestamp"),
    mode: str = Query('clip', description="Search mode: clip, yolo_hybrid, advanced_clip")
):
    """
    Search for video clips using natural language.
    
    Search modes:
    - clip: Standard CLIP semantic search (fast, good accuracy)
    - yolo_hybrid: CLIP + YOLO object detection for improved accuracy
    - advanced_clip: Larger CLIP model (ViT-L-14) for better semantic understanding
    
    Example queries:
    - "person wearing a red jacket"
    - "white truck entering parking lot"
    - "dog playing in the park"
    """
    try:
        # Determine which embedder to use based on mode
        embedder_key = 'advanced' if mode == 'advanced_clip' else 'standard'
        embedder = get_embedder_instance(embedder_key)
        
        # Get vector store with appropriate dimension
        vector_store = get_vector_store_instance(embedding_dim=embedder.embedding_dim)
        
        # Generate text embedding for the query
        query_embedding = embedder.encode_text(query)
        
        # Search vector database (get more results for hybrid re-ranking)
        search_top_k = top_k * 3 if mode == 'yolo_hybrid' else top_k
        
        try:
            results = vector_store.search(
                query_vector=query_embedding,
                top_k=search_top_k,
                source_type=source_type,
                source_name=source_name,
                min_timestamp=min_timestamp,
                max_timestamp=max_timestamp
            )
        except Exception as search_err:
            # If advanced model fails (dimension mismatch), fall back to standard
            error_str = str(search_err).lower()
            logger.warning(f"Search error: {error_str}")
            if mode == 'advanced_clip' and ('dimension mismatch' in error_str or 'vector dimension' in error_str or 'sizeof' in error_str):
                logger.warning("Advanced CLIP dimension mismatch, falling back to standard CLIP")
                embedder = get_embedder_instance('standard')
                vector_store = get_vector_store_instance(embedding_dim=embedder.embedding_dim)
                query_embedding = embedder.encode_text(query)
                results = vector_store.search(
                    query_vector=query_embedding,
                    top_k=search_top_k,
                    source_type=source_type,
                    source_name=source_name,
                    min_timestamp=min_timestamp,
                    max_timestamp=max_timestamp
                )
            else:
                raise
        
        # Apply hybrid scoring if requested
        if mode == 'yolo_hybrid':
            hybrid_scorer = get_hybrid_scorer()
            results = enhance_search_results(query, results, hybrid_scorer, top_k=top_k)
        
        # Format results
        search_results = [SearchResult(**r) for r in results]
        
        return SearchResponse(
            query=query,
            results=search_results,
            total_count=len(search_results)
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/cameras/register", response_model=CameraStatus)
async def register_camera(request: CameraRegisterRequest):
    """
    Register a new RTSP camera for processing.
    
    The camera will be added to the processing queue and frames will be
    continuously sampled and indexed for search.
    """
    try:
        # Add to Redis for persistence
        redis_client.hset(f"camera:{request.camera_id}", mapping={
            "rtsp_url": request.rtsp_url,
            "status": "pending",
            "registered_at": int(datetime.now().timestamp())
        })
        
        # Queue the camera for processing
        task = {
            "action": "start",
            "camera_id": request.camera_id,
            "rtsp_url": request.rtsp_url
        }
        redis_client.rpush("rtsp_tasks", json.dumps(task))
        
        logger.info(f"Registered camera: {request.camera_id}")
        
        return CameraStatus(
            camera_id=request.camera_id,
            rtsp_url=request.rtsp_url,
            status="pending"
        )
        
    except Exception as e:
        logger.error(f"Failed to register camera: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register camera: {str(e)}")


@app.post("/cameras/{camera_id}/stop")
async def stop_camera(camera_id: str):
    """Stop processing a camera stream."""
    try:
        task = {
            "action": "stop",
            "camera_id": camera_id
        }
        redis_client.rpush("rtsp_tasks", json.dumps(task))
        
        return {"message": f"Stop command sent for camera: {camera_id}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop camera: {str(e)}")


@app.get("/cameras", response_model=List[CameraStatus])
async def list_cameras():
    """List all registered cameras and their status."""
    try:
        cameras = []
        for key in redis_client.scan_iter(match="camera:*"):
            camera_id = key.split(":")[1]
            info = redis_client.hgetall(key)
            cameras.append(CameraStatus(
                camera_id=camera_id,
                rtsp_url=info.get("rtsp_url"),
                status=info.get("status", "unknown"),
                last_update=int(info["last_update"]) if info.get("last_update") else None,
                last_clip_id=int(info["last_clip_id"]) if info.get("last_clip_id") else None
            ))
        return cameras
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list cameras: {str(e)}")


@app.get("/cameras/{camera_id}", response_model=CameraStatus)
async def get_camera_status(camera_id: str):
    """Get status of a specific camera."""
    info = redis_client.hgetall(f"camera:{camera_id}")
    if not info:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraStatus(
        camera_id=camera_id,
        rtsp_url=info.get("rtsp_url"),
        status=info.get("status", "unknown"),
        last_update=int(info["last_update"]) if info.get("last_update") else None,
        last_clip_id=int(info["last_clip_id"]) if info.get("last_clip_id") else None
    )


@app.post("/videos/url", response_model=TaskStatus)
async def process_video_url(request: URLProcessRequest, background_tasks: BackgroundTasks):
    """
    Submit a video URL for processing.
    
    The video will be downloaded and processed asynchronously.
    Use the returned task_id to check processing status.
    """
    try:
        task_id = str(uuid.uuid4())
        
        # Store initial task status
        redis_client.hset(f"task:{task_id}", mapping={
            "type": "url",
            "url": request.url,
            "status": "queued",
            "clips_processed": 0,
            "frames_processed": 0
        })
        
        # Queue the task
        task = {
            "task_id": task_id,
            "type": "url",
            "url": request.url,
            "max_duration": request.max_duration
        }
        redis_client.rpush("video_tasks", json.dumps(task))
        
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


@app.post("/videos/upload", response_model=TaskStatus)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    max_duration: Optional[int] = Form(None)
):
    """
    Upload a video file for processing.
    
    The file will be saved and processed asynchronously.
    Supported formats: mp4, avi, mov, mkv, webm
    """
    try:
        # Validate file extension
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format. Allowed: {allowed_extensions}"
            )
        
        task_id = str(uuid.uuid4())
        
        # Save uploaded file
        upload_dir = os.path.join(storage_path, "uploads", task_id)
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file.filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Store initial task status
        redis_client.hset(f"task:{task_id}", mapping={
            "type": "upload",
            "filename": file.filename,
            "status": "queued",
            "clips_processed": 0,
            "frames_processed": 0
        })
        
        # Queue the task
        task = {
            "task_id": task_id,
            "type": "upload",
            "file_path": file_path,
            "original_filename": file.filename,
            "max_duration": max_duration
        }
        redis_client.rpush("video_tasks", json.dumps(task))
        
        logger.info(f"Queued upload task: {task_id}")
        
        return TaskStatus(
            task_id=task_id,
            type="upload",
            status="queued",
            filename=file.filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {str(e)}")


@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get the status of a processing task."""
    info = redis_client.hgetall(f"task:{task_id}")
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
        error=info.get("error")
    )


@app.get("/tasks", response_model=List[TaskStatus])
async def list_tasks(status: Optional[str] = Query(None, description="Filter by status")):
    """List all processing tasks."""
    try:
        tasks = []
        for key in redis_client.scan_iter(match="task:*"):
            task_id = key.split(":")[1]
            info = redis_client.hgetall(key)
            
            if status and info.get("status") != status:
                continue
            
            tasks.append(TaskStatus(
                task_id=task_id,
                type=info.get("type"),
                status=info.get("status", "unknown"),
                url=info.get("url"),
                filename=info.get("filename"),
                clips_processed=int(info.get("clips_processed", 0)),
                frames_processed=int(info.get("frames_processed", 0)),
                error=info.get("error")
            ))
        
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get system statistics."""
    try:
        # Get vector store stats
        vector_store = get_vector_store_instance()
        collection_stats = vector_store.get_collection_stats()
        
        # Count active cameras
        active_cameras = 0
        for key in redis_client.scan_iter(match="camera:*"):
            info = redis_client.hgetall(key)
            if info.get("status") == "active":
                active_cameras += 1
        
        # Count pending tasks
        pending_tasks = redis_client.llen("video_tasks") + redis_client.llen("rtsp_tasks")
        
        return StatsResponse(
            total_clips=collection_stats["total_clips"],
            collection_name=collection_stats["collection_name"],
            embedding_dim=collection_stats["embedding_dim"],
            active_cameras=active_cameras,
            pending_tasks=pending_tasks
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@app.delete("/clips/{source_name}")
async def delete_clips(source_name: str):
    """Delete all clips from a specific source."""
    try:
        vector_store = get_vector_store_instance()
        count = vector_store.delete_clips_by_source(source_name)
        return {"message": f"Deleted {count} clips from source: {source_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete clips: {str(e)}")


@app.get("/thumbnails/{path:path}")
async def get_thumbnail(path: str):
    """Serve thumbnail images."""
    thumbnail_path = os.path.join("/tmp/video_thumbnails", path)
    
    # Security check - ensure path is within thumbnails directory
    real_path = os.path.realpath(thumbnail_path)
    real_base = os.path.realpath("/tmp/video_thumbnails")
    
    if not real_path.startswith(real_base):
        raise HTTPException(status_code=403, detail="Invalid path")
    
    if not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    return FileResponse(real_path)


@app.get("/video-chunks/{path:path}")
async def get_video_chunk(path: str):
    """Serve video chunk files."""
    chunk_path = os.path.join("/tmp/video_chunks", path)
    
    # Security check - ensure path is within chunks directory
    real_path = os.path.realpath(chunk_path)
    real_base = os.path.realpath("/tmp/video_chunks")
    
    if not real_path.startswith(real_base):
        raise HTTPException(status_code=403, detail="Invalid path")
    
    if not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail="Video chunk not found")
    
    return FileResponse(real_path, media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
