"""Stats-related Pydantic models."""
from pydantic import BaseModel


class StatsResponse(BaseModel):
    """System statistics response."""
    total_clips: int
    collection_name: str
    embedding_dim: int
    active_cameras: int
    pending_tasks: int
