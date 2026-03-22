"""
AI analysis and configuration routes.
"""
import json
import logging
from typing import List

from fastapi import APIRouter, Query, HTTPException
import redis
import os

from api.models import (
    AIConfigRequest, AIAnalysisRequest, AIAnalysisResponse,
    LogicExplanation
)
from processing.ai_provider import get_ai_service, update_ai_config, AIConfig, AIProvider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)


def _get_ai():
    """Get AI service instance."""
    return get_ai_service()


def _to_ai_response(result) -> AIAnalysisResponse:
    """Convert AI result to response model."""
    return AIAnalysisResponse(
        summary=result.summary,
        threat_level=result.threat_level,
        threat_score=result.threat_score,
        alerts=result.alerts,
        predictions=result.predictions,
        correlations=result.correlations,
        priorities=result.priorities,
        trends=result.trends,
        detected_themes=result.detected_themes,
        recommendations=result.recommendations,
        provider_used=result.provider_used,
        model_used=result.model_used,
        confidence=result.confidence,
        analysis_factors=result.analysis_factors,
    )


@router.get("/providers")
async def list_providers():
    """List available AI providers."""
    ai = _get_ai()
    return {"providers": ai.get_available_providers()}


@router.get("/config")
async def get_config():
    """Get current AI configuration."""
    ai = _get_ai()
    return {
        "provider": ai.config.provider.value,
        "ollama_base_url": ai.config.ollama_base_url,
        "ollama_model": ai.config.ollama_model,
        "openai_api_key": "",
        "openai_key_configured": bool(ai.config.openai_api_key),
        "openai_base_url": ai.config.openai_base_url,
        "openai_model": ai.config.openai_model,
        "webgpu_enabled": ai.config.webgpu_enabled,
    }


@router.get("/ollama/status")
async def get_ollama_status():
    """Get Ollama backend status."""
    ai = _get_ai()
    for provider in ai.get_available_providers():
        if provider.get("provider") == AIProvider.OLLAMA.value:
            return provider
    raise HTTPException(status_code=404, detail="Ollama provider unavailable")


@router.get("/ollama/models")
async def list_ollama_models():
    """List available Ollama models."""
    ai = _get_ai()
    return {
        "models": ai.get_ollama_models(),
        "status": await get_ollama_status(),
    }


@router.post("/config")
async def configure_ai(request: AIConfigRequest):
    """Update AI configuration."""
    try:
        config = AIConfig(
            provider=AIProvider(request.provider),
            ollama_base_url=request.ollama_base_url,
            ollama_model=request.ollama_model,
            openai_api_key=request.openai_api_key,
            openai_base_url=request.openai_base_url,
            openai_model=request.openai_model,
            webgpu_enabled=request.webgpu_enabled
        )
        ai = update_ai_config(config)
        return {
            "status": "configured",
            "providers": ai.get_available_providers(),
            "config": {
                "provider": ai.config.provider.value,
                "ollama_base_url": ai.config.ollama_base_url,
                "ollama_model": ai.config.ollama_model,
                "openai_api_key": "",
                "openai_key_configured": bool(ai.config.openai_api_key),
                "openai_base_url": ai.config.openai_base_url,
                "openai_model": ai.config.openai_model,
                "webgpu_enabled": ai.config.webgpu_enabled,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analyze", response_model=AIAnalysisResponse)
async def analyze(request: AIAnalysisRequest):
    """Run AI analysis."""
    ai = _get_ai()
    result = ai.analyze(request.prompt, request.context)
    return _to_ai_response(result)


@router.get("/analyze/threats", response_model=AIAnalysisResponse)
async def analyze_threats(limit: int = Query(20, ge=1, le=100)):
    """AI threat analysis from recent events."""
    try:
        events = []
        for raw in redis_client.lrange("mission:events", 0, limit - 1):
            try:
                events.append(json.loads(raw))
            except Exception:
                continue
        
        ai = _get_ai()
        result = ai.analyze_threat(events)
        return _to_ai_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/predictions", response_model=AIAnalysisResponse)
async def analyze_predictions():
    """AI-enhanced risk prediction analysis."""
    try:
        raw = redis_client.get("risk:predictions")
        predictions = json.loads(raw).get("items", []) if raw else []
        
        historical = []
        for raw_event in redis_client.lrange("mission:events", 0, 50):
            if raw_event:
                try:
                    historical.append(json.loads(raw_event))
                except Exception:
                    pass
        
        ai = _get_ai()
        result = ai.predict_risk(predictions, historical)
        return _to_ai_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/correlations", response_model=AIAnalysisResponse)
async def analyze_correlations(limit: int = Query(30, ge=1, le=100)):
    """AI cross-source correlation analysis."""
    try:
        events = []
        for raw in redis_client.lrange("mission:events", 0, limit - 1):
            if raw:
                try:
                    events.append(json.loads(raw))
                except Exception:
                    pass
        
        ai = _get_ai()
        result = ai.correlate_sources(events)
        return _to_ai_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/mission-review", response_model=AIAnalysisResponse)
async def analyze_mission_review(limit: int = Query(20, ge=5, le=100)):
    """Broad mission review across sources."""
    try:
        from api.services import CacheService
        cache = CacheService(redis_client)
        
        # Build context
        events = cache.get_mission_events(limit=limit)
        assets = cache.list_assets(limit=10)
        predictions_data = cache.get_predictions()
        predictions = predictions_data.get("items", []) if predictions_data else []
        live_streams = []
        for cam in cache.list_cameras()[:10]:
            live_streams.append({
                "camera_id": cam["camera_id"],
                "rtsp_url": cam.get("rtsp_url"),
                "status": cam.get("status", "unknown"),
                "last_update": int(cam.get("last_update", 0)) if cam.get("last_update") else None,
            })
        
        # Get clip metadata
        clips = []
        for event in events[:10]:
            clip_id = event.get("id")
            meta = cache.get_clip_metadata(int(clip_id)) if clip_id else {}
            clips.append({
                "id": clip_id,
                "source_name": event.get("source_name"),
                "source_type": event.get("source_type"),
                "timestamp": event.get("timestamp"),
                "urgency_level": event.get("urgency_level"),
                "urgency_score": event.get("urgency_score"),
                "mission_score": event.get("mission_score"),
                "detected_objects": meta.get("detected_objects") or event.get("detected_objects", []),
                "clip_tags": meta.get("clip_tags", []),
            })
        
        alerts = [
            event for event in events
            if str(event.get("urgency_level", "")).lower() in {"critical", "high", "medium"}
        ][:10]
        
        context = {
            "clips": clips,
            "assets": assets,
            "events": events,
            "alerts": alerts,
            "predictions": predictions,
            "live_streams": live_streams,
        }
        
        ai = _get_ai()
        result = ai.review_mission_context(context)
        return _to_ai_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/overview")
async def generate_overview():
    """Generate operational overview report."""
    try:
        from processing.vector_store import get_vector_store
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        vector_store = get_vector_store(host=milvus_host, port=milvus_port)
        stats = vector_store.get_collection_stats()
        
        raw_alerts = redis_client.lrange("alerts:events", 0, 9)
        alerts = []
        for raw in raw_alerts:
            if raw:
                try:
                    alerts.append(json.loads(raw).get("alert", {}))
                except Exception:
                    pass
        
        raw_pred = redis_client.get("risk:predictions")
        predictions = json.loads(raw_pred).get("items", []) if raw_pred else []
        
        ai = _get_ai()
        report = ai.generate_overview(stats, alerts, predictions)
        return {"report": report, "providers": ai.get_available_providers()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logic/explanations", response_model=List[LogicExplanation])
async def get_logic_explanations():
    """Get logic explanations for scoring systems."""
    return [
        LogicExplanation(
            component="Risk Score (Proactive Forecast)",
            description="30-minute risk forecast combining recent activity signals with trend analysis",
            formula="risk_score = 0.55 × min(1, signal_60m / 5) + 0.45 × min(1, trend)",
            factors=[
                {"name": "signal_15m", "weight": 0.45, "description": "Weighted sum of events in last 15 minutes"},
                {"name": "signal_60m", "weight": 0.55, "description": "Weighted sum of events in last 60 minutes"},
                {"name": "trend", "weight": 0.45, "description": "Ratio of signal_15m to signal_60m indicating acceleration"},
            ],
            example="If signal_60m=3.5 and trend=1.2, risk_score = 0.55×0.7 + 0.45×1.0 = 0.835 (HIGH)"
        ),
        LogicExplanation(
            component="Mission Score",
            description="Combined relevance score for search results",
            formula="mission_score = 0.65×clip_score + 0.20×object_overlap + 0.15×urgency_score",
            factors=[
                {"name": "clip_score", "weight": 0.65, "description": "CLIP embedding cosine similarity (0-1)"},
                {"name": "object_overlap", "weight": 0.20, "description": "Query term overlap with detected objects"},
                {"name": "urgency_score", "weight": 0.15, "description": "Keyword-based urgency from query terms"},
            ],
            example="clip_score=0.82, object_overlap=0.6, urgency=0.4 → mission_score = 0.713"
        ),
        LogicExplanation(
            component="Urgency Score",
            description="Query-based urgency detection from mission-critical keywords",
            formula="urgency_score = Σ(term_weights) capped at 1.0",
            factors=[
                {"name": "critical_terms", "weight": 0.45, "description": "active shooter, explosion, hostage"},
                {"name": "high_terms", "weight": 0.25, "description": "weapon, fire, intruder, assault"},
                {"name": "medium_terms", "weight": 0.12, "description": "suspicious, trespass, accident"},
            ],
            example="Query 'active shooter near entrance' → critical(0.45) + high terms → urgency = 0.70"
        ),
    ]
