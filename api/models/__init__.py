"""
Pydantic models for API request/response validation.
"""
from .search import SearchResult, UrgentAlert, SearchResponse
from .camera import CameraRegisterRequest, StreamRegisterRequest, CameraStatus
from .task import URLProcessRequest, TaskStatus
from .stats import StatsResponse
from .asset import UploadedAsset
from .watch import WatchFinding, WatchAlert, WatchAlertClearResponse
from .dispatch import DispatchRequest, DispatchResponse
from .prediction import PredictionItem, PredictionResponse
from .policy import PolicyPreviewResponse
from .ai import AIConfigRequest, AIAnalysisRequest, AIAnalysisResponse, LogicExplanation
from .live import LiveDetectRequest, DetectionResult, LiveDetectResponse
from .opord import OpordParseRequest, OpordParseResponse
from .email import EmailConfig, EmailAlertRequest

__all__ = [
    # Search
    "SearchResult",
    "UrgentAlert", 
    "SearchResponse",
    # Camera/Stream
    "CameraRegisterRequest",
    "StreamRegisterRequest",
    "CameraStatus",
    # Task
    "URLProcessRequest",
    "TaskStatus",
    # Stats
    "StatsResponse",
    # Asset
    "UploadedAsset",
    # Watch
    "WatchFinding",
    "WatchAlert",
    "WatchAlertClearResponse",
    # Dispatch
    "DispatchRequest",
    "DispatchResponse",
    # Prediction
    "PredictionItem",
    "PredictionResponse",
    # Policy
    "PolicyPreviewResponse",
    # AI
    "AIConfigRequest",
    "AIAnalysisRequest",
    "AIAnalysisResponse",
    "LogicExplanation",
    # Live
    "LiveDetectRequest",
    "DetectionResult",
    "LiveDetectResponse",
    # OPORD
    "OpordParseRequest",
    "OpordParseResponse",
    # Email
    "EmailConfig",
    "EmailAlertRequest",
]
