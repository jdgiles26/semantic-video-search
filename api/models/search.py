"""Search-related Pydantic models."""
from typing import List, Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Single search result item."""
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
    clip_score: Optional[float] = None
    detected_objects: Optional[list] = None
    object_overlap_score: Optional[float] = None
    urgency_score: Optional[float] = None
    urgency_level: Optional[str] = None
    urgency_reasons: Optional[List[str]] = None
    mission_score: Optional[float] = None
    correlation_score: Optional[float] = None
    correlated_sources: Optional[List[str]] = None


class UrgentAlert(BaseModel):
    """Urgent alert from mission intelligence."""
    id: int
    source_name: str
    source_type: str
    timestamp: int
    urgency_level: str
    urgency_score: float
    mission_score: float
    urgency_reasons: List[str] = Field(default_factory=list)
    detected_objects: List = Field(default_factory=list)
    video_chunk_path: Optional[str] = None
    thumbnail_path: Optional[str] = None


class SearchResponse(BaseModel):
    """Search API response."""
    query: str
    results: List[SearchResult]
    total_count: int
    alerts: List[UrgentAlert] = Field(default_factory=list)
    report_preview: Optional[str] = None
