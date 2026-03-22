"""Task-related Pydantic models."""
from typing import Optional
from pydantic import BaseModel


class URLProcessRequest(BaseModel):
    """Request to process a video from URL."""
    url: str
    max_duration: Optional[int] = None  # Maximum seconds to process


class TaskStatus(BaseModel):
    """Task status response."""
    task_id: str
    type: Optional[str] = None
    status: str
    url: Optional[str] = None
    filename: Optional[str] = None
    clips_processed: int = 0
    frames_processed: int = 0
    error: Optional[str] = None
    asset_id: Optional[str] = None
    media_kind: Optional[str] = None
    thumbnail_path: Optional[str] = None
