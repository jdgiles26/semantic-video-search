"""Camera and stream-related Pydantic models."""
from typing import Optional
from pydantic import BaseModel, Field


class CameraRegisterRequest(BaseModel):
    """Request to register an RTSP camera."""
    camera_id: str
    rtsp_url: str


class StreamRegisterRequest(BaseModel):
    """Request to register a live stream (RTSP, HLS, or YouTube Live)."""
    stream_id: str
    stream_url: str
    stream_type: str = "rtsp"  # rtsp, hls, youtube_live


class CameraStatus(BaseModel):
    """Camera/stream status response."""
    camera_id: str
    rtsp_url: Optional[str] = Field(None, alias="stream_url")
    playback_url: Optional[str] = None
    stream_type: Optional[str] = None
    status: str
    last_update: Optional[int] = None
    last_clip_id: Optional[int] = None
    error: Optional[str] = None

    class Config:
        populate_by_name = True
