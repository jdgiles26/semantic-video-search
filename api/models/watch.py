"""Watch alert-related Pydantic models."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class WatchFinding(BaseModel):
    """Single watch alert finding."""
    finding_id: str
    alert_id: str
    watch_phrase: str
    source_name: str
    source_type: str
    timestamp: int
    detected_objects: List[dict] = Field(default_factory=list)
    matched_labels: List[str] = Field(default_factory=list)
    video_chunk_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    ai_summary: Optional[str] = None
    watch_assessment: dict = Field(default_factory=dict)
    correlated_sources: List[str] = Field(default_factory=list)
    mission_score: Optional[float] = None
    urgency_level: Optional[str] = None


class WatchAlert(BaseModel):
    """Active watch alert."""
    alert_id: str
    status: str
    created_at: int
    source_filename: str
    mime_type: str = ""
    watch_phrase: str
    watch_labels: List[str] = Field(default_factory=list)
    watch_label: str
    priority: str
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    banner_message: str
    opord_excerpt: Optional[str] = None
    findings: List[WatchFinding] = Field(default_factory=list)
    findings_count: int = 0
    latest_finding_at: Optional[int] = None
    cleared_at: Optional[int] = None


class WatchAlertClearResponse(BaseModel):
    """Watch alert clearance response."""
    alert: WatchAlert
    commander_report: str
