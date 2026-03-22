"""Prediction-related Pydantic models."""
from typing import List
from pydantic import BaseModel


class PredictionItem(BaseModel):
    """Single risk prediction item."""
    source_name: str
    risk_score: float
    recent_signal_15m: float
    recent_signal_60m: float
    trend: float
    forecast_horizon_minutes: int
    risk_level: str


class PredictionResponse(BaseModel):
    """Risk predictions response."""
    generated_at: int
    items: List[PredictionItem]
