"""
Alert and dispatch routes.
"""
import logging
import smtplib
import uuid
from typing import List
from datetime import datetime
from email.message import EmailMessage

from fastapi import APIRouter, Query, HTTPException
import redis
import os

from api.models import (
    UrgentAlert, WatchAlert, WatchAlertClearResponse,
    DispatchRequest, DispatchResponse,
    PredictionItem, PredictionResponse,
    PolicyPreviewResponse,
    EmailConfig, EmailAlertRequest
)
from api.services import CacheService
from processing.vector_store import get_vector_store
from processing.policy_router import PolicyRouter
from processing.ai_provider import get_ai_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alerts"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)
cache = CacheService(redis_client)


def _get_vector_store():
    """Lazy load vector store."""
    if not hasattr(_get_vector_store, '_instance'):
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        _get_vector_store._instance = get_vector_store(host=milvus_host, port=milvus_port)
    return _get_vector_store._instance


def _get_policy_router():
    """Lazy load policy router."""
    if not hasattr(_get_policy_router, '_instance'):
        _get_policy_router._instance = PolicyRouter()
    return _get_policy_router._instance


def _get_ai_service():
    """Lazy load AI service."""
    return get_ai_service()


def _send_email(recipients: List[str], subject: str, body: str) -> bool:
    """Send email via SMTP."""
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("ALERT_FROM_EMAIL", user or "noreply@video-search.local")
    use_tls = os.getenv("SMTP_TLS", "true").lower() != "false"
    
    if not host or not recipients:
        return False
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    
    with smtplib.SMTP(host, port, timeout=15) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    return True


@router.get("/alerts", response_model=List[UrgentAlert])
async def list_alerts(limit: int = Query(20, ge=1, le=100)):
    """List recent alerts."""
    try:
        alerts = cache.get_recent_alerts(limit=limit)
        return [UrgentAlert(**a) for a in alerts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch alerts: {str(e)}")


@router.get("/watch-alerts/active", response_model=WatchAlert)
async def get_active_watch_alert():
    """Get active OPORD watch alert."""
    from processing.watchlist_manager import WatchlistManager
    manager = WatchlistManager(redis_client)
    alert = manager.get_active_alert()
    if not alert:
        return None
    return WatchAlert(**alert)


@router.post("/watch-alerts/{alert_id}/clear", response_model=WatchAlertClearResponse)
async def clear_watch_alert(alert_id: str):
    """Clear a watch alert and generate commander report."""
    from processing.watchlist_manager import WatchlistManager
    manager = WatchlistManager(redis_client)
    
    active = manager.get_active_alert(include_findings=False)
    if not active or active.get("alert_id") != alert_id:
        raise HTTPException(status_code=404, detail="Watch alert not found")
    
    findings = active.get("findings", [])
    cleared = manager.clear_alert(alert_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Watch alert not found")
    
    alert_payload = {
        **cleared,
        "findings": findings,
        "findings_count": len(findings),
        "latest_finding_at": findings[0]["timestamp"] if findings else None,
    }
    
    ai = _get_ai_service()
    commander_report = ai.generate_report({
        "report_type": "opord_watch_clearance_brief",
        "watch_alert": alert_payload,
        "findings": findings[:10],
    })
    
    return WatchAlertClearResponse(
        alert=WatchAlert(**alert_payload),
        commander_report=commander_report,
    )


@router.get("/predictions", response_model=PredictionResponse)
async def get_predictions():
    """Get risk predictions."""
    try:
        data = cache.get_predictions()
        if not data:
            return PredictionResponse(generated_at=0, items=[])
        
        items = [PredictionItem(**it) for it in data.get("items", [])]
        return PredictionResponse(
            generated_at=int(data.get("generated_at", 0)),
            items=items
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch predictions: {str(e)}")


@router.get("/alerts/policy/{clip_id}", response_model=PolicyPreviewResponse)
async def preview_policy(clip_id: int):
    """Preview policy routing for a clip."""
    try:
        vector_store = _get_vector_store()
        clip = vector_store.get_clip_by_id(clip_id)
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        
        meta = cache.get_clip_metadata(clip_id) or {}
        alert = {
            "id": clip_id,
            "source_name": clip.get("source_name", "unknown"),
            "source_type": clip.get("source_type", "unknown"),
            "urgency_level": meta.get("urgency_level", "low"),
            "detected_objects": meta.get("detected_objects", []),
            "mission_score": float(meta.get("mission_score", 0.0)),
        }
        
        router = _get_policy_router()
        decision = router.route(alert)
        
        return PolicyPreviewResponse(
            agencies=decision.agencies,
            channels=decision.channels,
            recipients=decision.recipients,
            priority=decision.priority,
            rationale=decision.rationale,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate policy: {str(e)}")


@router.post("/alerts/dispatch", response_model=DispatchResponse)
async def dispatch_alert(request: DispatchRequest):
    """Dispatch alert through configured channels."""
    try:
        vector_store = _get_vector_store()
        ai = _get_ai_service()
        policy_router = _get_policy_router()
        
        # Build alert payloads from clips
        alerts = []
        for clip_id in request.clip_ids[:25]:
            clip = vector_store.get_clip_by_id(clip_id)
            if not clip:
                continue
            
            meta = cache.get_clip_metadata(clip_id) or {}
            alerts.append({
                "id": clip_id,
                "source_name": clip.get("source_name", "unknown"),
                "source_type": clip.get("source_type", "unknown"),
                "timestamp": int(clip.get("timestamp", 0)),
                "urgency_level": meta.get("urgency_level", "high"),
                "urgency_score": float(meta.get("urgency_score", 0.6)),
                "mission_score": float(meta.get("mission_score", 0.6)),
                "urgency_reasons": meta.get("urgency_reasons", []),
                "detected_objects": meta.get("detected_objects", []),
                "video_chunk_path": clip.get("video_chunk_path"),
                "thumbnail_path": clip.get("thumbnail_path"),
            })
        
        # Get policy decision
        policy_decision = policy_router.route(alerts[0] if alerts else {})
        policy_payload = {
            "agencies": policy_decision.agencies,
            "channels": policy_decision.channels,
            "recipients": policy_decision.recipients,
            "priority": policy_decision.priority,
            "rationale": policy_decision.rationale,
        }
        
        # Generate report
        from processing.mission_intelligence import MissionIntelligenceEngine
        mission = MissionIntelligenceEngine()
        fallback_report = mission.build_incident_report(request.query, alerts)
        
        try:
            from processing.summarizer_client import SitrepSummarizerClient
            summarizer = SitrepSummarizerClient()
            report = summarizer.generate_sitrep(
                query=request.query,
                alerts=alerts,
                policy=policy_payload,
                commander_intent=request.commander_intent or "Protect life, coordinate multi-agency response, and preserve evidence.",
            )
        except Exception:
            report = fallback_report
        
        # Dispatch to channels
        dispatch_id = str(uuid.uuid4())
        requested_channels = request.channels or ["redis"]
        if requested_channels == ["redis"]:
            requested_channels = sorted(set(requested_channels + policy_decision.channels))
        
        attempted = []
        succeeded = []
        
        recipients = request.recipients or policy_decision.recipients
        
        event_payload = {
            "dispatch_id": dispatch_id,
            "query": request.query,
            "created_at": int(datetime.now().timestamp()),
            "alert": alerts[0] if alerts else None,
            "report": report,
            "policy": policy_payload,
        }
        
        for channel in requested_channels:
            ch = channel.lower().strip()
            attempted.append(ch)
            try:
                if ch == "redis":
                    cache.publish_alert(event_payload)
                    succeeded.append(ch)
                elif ch == "email":
                    subject = f"[Mission Alert] {request.query[:80]}"
                    if _send_email(recipients, subject, report):
                        succeeded.append(ch)
                elif ch == "webhook" and request.webhook_url:
                    import requests
                    resp = requests.post(request.webhook_url, json=event_payload, timeout=8)
                    if 200 <= resp.status_code < 300:
                        succeeded.append(ch)
            except Exception as dispatch_error:
                logger.warning(f"Dispatch channel failed ({ch}): {dispatch_error}")
        
        status = "dispatched" if succeeded else "queued"
        return DispatchResponse(
            status=status,
            dispatch_id=dispatch_id,
            channels_attempted=attempted,
            channels_succeeded=succeeded,
            report=report,
            policy=policy_payload,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch alert: {str(e)}")


@router.post("/alerts/email")
async def send_email_alert(request: EmailAlertRequest):
    """Send email alert."""
    if not request.config.enabled:
        return {"status": "disabled"}
    
    try:
        cfg = request.config
        
        # Build content based on alert type
        if request.alert_type == "watch_match":
            subject = f"[WATCH ALERT] {request.data.get('watch_phrase', 'Unknown')}"
            body = f"""Watch Alert Triggered

Watch Phrase: {request.data.get('watch_phrase', 'Unknown')}
Priority: {request.data.get('priority', 'Unknown')}
Camera: {request.data.get('camera_id', 'Unknown')}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Automated alert from Video Search System.
"""
        elif request.alert_type == "critical_prediction":
            subject = f"[CRITICAL] Risk Prediction: {request.data.get('source_name', 'Unknown')}"
            body = f"""Critical Risk Prediction

Source: {request.data.get('source_name', 'Unknown')}
Risk Score: {request.data.get('risk_score', 0) * 100:.1f}%
Risk Level: {request.data.get('risk_level', 'Unknown')}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Automated alert from Video Search System.
"""
        else:
            subject = f"[ALERT] {request.alert_type}"
            import json
            body = f"""Alert Type: {request.alert_type}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Data: {json.dumps(request.data, indent=2)}

Automated alert from Video Search System.
"""
        
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.from_email or cfg.smtp_user
        msg["To"] = ", ".join(cfg.to_emails)
        msg.set_content(body)
        
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as server:
            server.starttls()
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)
        
        logger.info(f"Email alert sent: {subject}")
        return {"status": "sent", "recipients": len(cfg.to_emails)}
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/alerts/email/test")
async def test_email_config(request: EmailAlertRequest):
    """Test email configuration."""
    try:
        cfg = request.config
        
        msg = EmailMessage()
        msg["Subject"] = "[TEST] Video Search System Email Configuration"
        msg["From"] = cfg.from_email or cfg.smtp_user
        msg["To"] = ", ".join(cfg.to_emails)
        msg.set_content(f"""This is a test email from the Video Search System.

If you received this email, your configuration is working correctly.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")
        
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as server:
            server.starttls()
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)
        
        return {"status": "success", "message": "Test email sent successfully"}
    except Exception as e:
        logger.error(f"Email test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email test failed: {str(e)}")
