"""AI-related Pydantic models."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AIConfigRequest(BaseModel):
    """AI provider configuration request."""
    provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llava:7b"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    webgpu_enabled: bool = False


class AIAnalysisRequest(BaseModel):
    """AI analysis request."""
    prompt: str = ""
    context: dict = Field(default_factory=dict)
    analysis_type: str = "general"


class AIAnalysisResponse(BaseModel):
    """AI analysis response."""
    summary: str
    threat_level: str = "low"
    threat_score: float = 0.0
    alerts: List[dict] = Field(default_factory=list)
    predictions: List[str] = Field(default_factory=list)
    correlations: List[dict] = Field(default_factory=list)
    priorities: List[dict] = Field(default_factory=list)
    trends: List[str] = Field(default_factory=list)
    detected_themes: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    provider_used: str = ""
    model_used: str = ""
    confidence: float = 0.0
    analysis_factors: List[dict] = Field(default_factory=list)


class LogicExplanation(BaseModel):
    """Logic explanation for scoring/prediction systems."""
    component: str
    description: str
    formula: str
    factors: List[dict]
    example: str
