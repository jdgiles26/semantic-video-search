"""Live detection-related Pydantic models."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class LiveDetectRequest(BaseModel):
    """Live stream frame detection request."""
    camera_id: str
    frame_data: str  # base64 encoded JPEG
    timestamp: int


class DetectionResult(BaseModel):
    """Single detection result."""
    label: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]


class LiveDetectResponse(BaseModel):
    """Live detection response."""
    camera_id: str
    timestamp: int
    detections: List[DetectionResult]
    analysis: Optional[Dict[str, Any]] = None
    watch_match: bool = False
    watch_phrase: Optional[str] = None
