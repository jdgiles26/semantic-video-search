"""Asset/upload-related Pydantic models."""
from typing import Optional
from pydantic import BaseModel


class UploadedAsset(BaseModel):
    """Uploaded asset metadata."""
    asset_id: str
    filename: str
    media_kind: str
    mime_type: str = "application/octet-stream"
    file_size: int = 0
    status: str = "ready"
    created_at: int
    task_id: Optional[str] = None
    thumbnail_path: Optional[str] = None
    file_path: str
    excerpt: Optional[str] = None
    notes: Optional[str] = None
