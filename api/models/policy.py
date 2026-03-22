"""Policy-related Pydantic models."""
from typing import List
from pydantic import BaseModel


class PolicyPreviewResponse(BaseModel):
    """Policy routing preview response."""
    agencies: List[str]
    channels: List[str]
    recipients: List[str]
    priority: str
    rationale: List[str]
