"""
Video Search API - FastAPI backend for semantic video search

Refactored modular architecture with:
- Separate routers for each domain
- Shared services for business logic
- Pydantic models for validation
- Consistent error handling
"""
import os
import sys
from pathlib import Path

# Add processing module to path
sys.path.append(str(Path(__file__).parent.parent / "processing"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Video Search API",
    description="Semantic video search platform with RTSP, URL, and upload support",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from api.routers import (
    search_router,
    cameras_router,
    tasks_router,
    assets_router,
    alerts_router,
    ai_router,
    live_router,
    opord_router,
)

# Include all routers
app.include_router(search_router, prefix="/query")
app.include_router(cameras_router)
app.include_router(tasks_router)
app.include_router(assets_router)
app.include_router(alerts_router)
app.include_router(ai_router)
app.include_router(live_router)
app.include_router(opord_router)

# Root endpoint
@app.get("/")
async def root():
    """API health check."""
    return {
        "status": "healthy",
        "service": "Video Search API",
        "version": "2.0.0",
        "features": [
            "semantic_search",
            "live_streams",
            "video_upload",
            "opord_parsing",
            "ai_analysis",
            "risk_predictions",
        ]
    }


# Stats endpoint (kept in main for simplicity)
@app.get("/stats")
async def get_stats():
    """Get system statistics."""
    try:
        import redis
        from processing.vector_store import get_vector_store
        
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True
        )
        
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        vector_store = get_vector_store(host=milvus_host, port=milvus_port)
        collection_stats = vector_store.get_collection_stats()
        
        # Count active cameras
        active_cameras = 0
        for key in redis_client.scan_iter(match="camera:*"):
            info = redis_client.hgetall(key)
            if info.get("status") == "active":
                active_cameras += 1
        
        # Count pending tasks
        pending_tasks = redis_client.llen("video_tasks") + redis_client.llen("rtsp_tasks")
        
        return {
            "total_clips": collection_stats["total_clips"],
            "collection_name": collection_stats["collection_name"],
            "embedding_dim": collection_stats["embedding_dim"],
            "active_cameras": active_cameras,
            "pending_tasks": pending_tasks
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {
            "total_clips": 0,
            "collection_name": "unknown",
            "embedding_dim": 512,
            "active_cameras": 0,
            "pending_tasks": 0,
            "error": str(e)
        }


# Static file serving for thumbnails and video chunks
@app.get("/thumbnails/{path:path}")
async def get_thumbnail(path: str):
    """Serve thumbnail images."""
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    
    thumbnail_path = Path("/tmp/video_thumbnails") / path
    real_path = thumbnail_path.resolve()
    real_base = Path("/tmp/video_thumbnails").resolve()
    
    if not str(real_path).startswith(str(real_base)):
        raise HTTPException(status_code=403, detail="Invalid path")
    
    if not real_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    return FileResponse(real_path)


@app.get("/video-chunks/{path:path}")
async def get_video_chunk(path: str):
    """Serve video chunk files."""
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    
    chunk_path = Path("/tmp/video_chunks") / path
    real_path = chunk_path.resolve()
    real_base = Path("/tmp/video_chunks").resolve()
    
    if not str(real_path).startswith(str(real_base)):
        raise HTTPException(status_code=403, detail="Invalid path")
    
    if not real_path.exists():
        raise HTTPException(status_code=404, detail="Video chunk not found")
    
    return FileResponse(real_path, media_type="video/mp4")


# Cleanup endpoint
@app.delete("/clips/{source_name}")
async def delete_clips(source_name: str):
    """Delete all clips from a specific source."""
    try:
        from processing.vector_store import get_vector_store
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        vector_store = get_vector_store(host=milvus_host, port=milvus_port)
        count = vector_store.delete_clips_by_source(source_name)
        return {"message": f"Deleted {count} clips from source: {source_name}"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to delete clips: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
