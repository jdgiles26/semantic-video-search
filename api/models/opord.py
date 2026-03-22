"""OPORD-related Pydantic models."""
from typing import List, Dict, Any
from pydantic import BaseModel


class OpordParseRequest(BaseModel):
    """OPORD parse request."""
    text: str
    source_filename: str = ""
    mime_type: str = ""


class OpordParseResponse(BaseModel):
    """OPORD parse response."""
    watch_phrase: str
    watch_labels: List[str]
    priority: str
    topics: List[str]
    keywords: List[str]
    entities: List[Dict[str, Any]]
    persons: List[str]
    locations: List[str]
    excerpt: str
    parser_used: str
    confidence: float
