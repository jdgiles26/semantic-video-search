"""Dispatch/alert-related Pydantic models."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DispatchRequest(BaseModel):
    """Alert dispatch request."""
    query: str
    clip_ids: List[int] = Field(default_factory=list)
    recipients: List[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    channels: List[str] = Field(default_factory=lambda: ["redis"])
    commander_intent: Optional[str] = None


class DispatchResponse(BaseModel):
    """Alert dispatch response."""
    status: str
    dispatch_id: str
    channels_attempted: List[str]
    channels_succeeded: List[str]
    report: str
    policy: dict = Field(default_factory=dict)
