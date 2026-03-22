"""
Asset management routes.
"""
import logging
import mimetypes
import os
import shutil
import uuid
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
import redis

from api.models import TaskStatus, UploadedAsset
from api.services import CacheService, DocumentService
from processing.thumbnail_generator import get_thumbnail_generator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)
cache = CacheService(redis_client)
doc_service = DocumentService()

storage_path = os.getenv("STORAGE_PATH", "/tmp/video_uploads")
os.makedirs(storage_path, exist_ok=True)

# File type constants
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".json", ".csv", ".tsv", ".log", ".rtf", ".doc", ".docx", ".xls",
    ".xlsx", ".xlsm", ".ppt", ".pptx", ".yaml", ".yml", ".xml", ".html", ".htm", ".odt"
}


def _classify_upload(filename: str, mime_type: Optional[str]) -> str:
    """Classify uploaded file type."""
    ext = Path(filename).suffix.lower()
    mime = (mime_type or "").lower()
    
    if ext in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    if ext in VIDEO_EXTENSIONS or mime.startswith("video/"):
        return "video"
    if ext in DOCUMENT_EXTENSIONS or mime.startswith("text/") or "pdf" in mime or "document" in mime:
        return "document"
    return "document"


def _sanitize_token(value: str) -> str:
    """Sanitize a token for safe use in filenames."""
    import re
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._")
    return cleaned or "asset"


def _build_document_preview(filename: str, media_kind: str):
    """Build a preview image for documents."""
    from PIL import Image, ImageDraw
    
    width, height = 640, 360
    background = {
        "document": (27, 31, 46),
        "image": (18, 56, 76),
        "video": (18, 44, 31),
    }.get(media_kind, (27, 31, 46))
    
    img = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(img)
    ext = Path(filename).suffix.upper().replace(".", "") or media_kind.upper()
    
    draw.rounded_rectangle(
        (28, 28, width - 28, height - 28),
        radius=24, outline=(93, 114, 139), width=3
    )
    draw.text((48, 52), ext[:12], fill=(141, 225, 255))
    draw.text((48, 122), Path(filename).name[:42], fill=(240, 246, 252))
    draw.text((48, 168), f"{media_kind.title()} preview", fill=(139, 148, 158))
    draw.text((48, 212), "Stored locally and available for review", fill=(139, 148, 158))
    
    import numpy as np
    return np.array(img)


def _generate_thumbnail(file_path: str, asset_id: str, filename: str, media_kind: str) -> Optional[str]:
    """Generate thumbnail for uploaded file."""
    thumb_gen = get_thumbnail_generator()
    safe_source = _sanitize_token(asset_id)
    
    try:
        if media_kind == "image":
            from PIL import Image
            image = Image.open(file_path).convert("RGB")
            import numpy as np
            thumbs = thumb_gen.generate_from_frame(np.array(image), safe_source, 0)
        elif media_kind == "video":
            thumbs = thumb_gen.generate_from_video(file_path, safe_source, 0)
        else:
            import numpy as np
            thumbs = thumb_gen.generate_from_frame(
                _build_document_preview(filename, media_kind),
                safe_source, 0
            )
        return thumbs.get("medium") if thumbs else None
    except Exception as exc:
        logger.warning(f"Failed to generate thumbnail for {filename}: {exc}")
        return None


@router.post("/videos", response_model=TaskStatus)
async def upload_video(
    file: UploadFile = File(...),
    max_duration: Optional[int] = Form(None)
):
    """Upload a video, image, or document for processing."""
    try:
        allowed = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
        ext = Path(file.filename).suffix.lower()
        
        if ext not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {allowed}"
            )
        
        task_id = str(uuid.uuid4())
        asset_id = str(uuid.uuid4())
        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        media_kind = _classify_upload(file.filename, mime_type)
        
        # Save file
        upload_dir = Path(storage_path) / "uploads" / task_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / file.filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        created_at = int(datetime.now().timestamp())
        file_size = file_path.stat().st_size
        thumbnail_path = _generate_thumbnail(str(file_path), asset_id, file.filename, media_kind)
        excerpt = doc_service.extract_text(str(file_path), file.filename) if media_kind == "document" else None
        
        # Determine status and notes
        if media_kind == "document":
            asset_status = "ready"
            if excerpt:
                asset_notes = f"Document text extracted from {ext or 'document'} and ready for review."
            else:
                asset_notes = "Preview generated. Text extraction could not recover readable content."
        elif media_kind == "image":
            asset_status = "ready"
            asset_notes = "Image stored locally and available for review."
        else:  # video
            asset_status = "queued_for_processing"
            asset_notes = "Video stored locally. Background clip indexing will populate searchable segments."
        
        # Store asset metadata
        cache.redis.hset(f"upload_asset:{asset_id}", mapping={
            "asset_id": asset_id,
            "task_id": task_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "mime_type": mime_type,
            "media_kind": media_kind,
            "file_size": file_size,
            "status": asset_status,
            "created_at": created_at,
            "thumbnail_path": thumbnail_path or "",
            "excerpt": excerpt or "",
            "notes": asset_notes,
        })
        
        # Store task
        task_status = "queued" if media_kind == "video" else "completed"
        cache.redis.hset(f"task:{task_id}", mapping={
            "type": "upload",
            "filename": file.filename,
            "status": task_status,
            "clips_processed": 0,
            "frames_processed": 0,
            "asset_id": asset_id,
            "media_kind": media_kind,
            "thumbnail_path": thumbnail_path or "",
        })
        
        # Queue video for processing
        if media_kind == "video":
            task = {
                "task_id": task_id,
                "asset_id": asset_id,
                "type": "upload",
                "file_path": str(file_path),
                "original_filename": file.filename,
                "max_duration": max_duration
            }
            cache.queue_task("video_tasks", task)
            logger.info(f"Queued video upload task: {task_id}")
        else:
            logger.info(f"Stored uploaded {media_kind} asset: {asset_id}")
        
        return TaskStatus(
            task_id=task_id,
            type="upload",
            status=task_status,
            filename=file.filename,
            asset_id=asset_id,
            media_kind=media_kind,
            thumbnail_path=thumbnail_path
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload: {str(e)}")


@router.get("/assets", response_model=List[UploadedAsset])
async def list_assets(limit: int = Query(30, ge=1, le=200)):
    """List uploaded assets."""
    try:
        return [UploadedAsset(**asset) for asset in cache.list_assets(limit=limit)]
    except Exception as e:
        logger.error(f"Failed to list assets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list assets: {str(e)}")


@router.get("/assets/{asset_id}", response_model=UploadedAsset)
async def get_asset(asset_id: str):
    """Get asset metadata."""
    asset = cache.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return UploadedAsset(**asset)


@router.get("/assets/{asset_id}/file")
async def get_asset_file(asset_id: str):
    """Download asset file."""
    asset = cache.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    file_path = asset.get("file_path", "")
    real_path = Path(file_path).resolve()
    real_base = Path(storage_path).resolve()
    
    # Security check
    if not str(real_path).startswith(str(real_base)):
        raise HTTPException(status_code=403, detail="Invalid asset path")
    
    if not real_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    media_type = asset.get("mime_type") or mimetypes.guess_type(str(real_path))[0] or "application/octet-stream"
    return FileResponse(real_path, media_type=media_type, filename=asset.get("filename"))
