"""
Live stream detection routes.
"""
import logging
import base64
from typing import List
from io import BytesIO

from fastapi import APIRouter, Query, HTTPException
import redis
import os
import numpy as np
from PIL import Image

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from api.models import LiveDetectRequest, LiveDetectResponse, DetectionResult
from processing.watchlist_manager import WatchlistManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["live"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)


def _get_detector():
    """Lazy load object detector."""
    if not hasattr(_get_detector, '_instance'):
        from processing.object_detector import get_object_detector
        _get_detector._instance = get_object_detector()
    return _get_detector._instance


def _get_ai():
    """Lazy load AI service."""
    from processing.ai_provider import get_ai_service
    return get_ai_service()


@router.post("/detect", response_model=LiveDetectResponse)
async def live_detect(request: LiveDetectRequest):
    """
    Real-time object detection on a live stream frame.
    Accepts base64-encoded JPEG frame.
    """
    if not CV2_AVAILABLE:
        raise HTTPException(status_code=500, detail="OpenCV not available")
    
    try:
        # Decode base64 image
        frame_data = request.frame_data
        if ',' in frame_data:
            frame_data = frame_data.split(',')[1]
        
        img_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise ValueError("Failed to decode image")
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Run detection
        detector = _get_detector()
        detections_raw = detector.detect(frame_rgb) if detector else []
        
        detections = [
            DetectionResult(
                label=det.label,
                confidence=round(det.confidence, 3),
                bbox=list(det.bbox)
            )
            for det in detections_raw
        ]
        
        # Check watch alert match
        watch_match = False
        watch_phrase = None
        manager = WatchlistManager(redis_client)
        active_alert = manager.get_active_alert(include_findings=False)
        
        if active_alert:
            watch_labels = set(label.lower() for label in active_alert.get("watch_labels", []))
            for det in detections:
                if det.label.lower() in watch_labels and det.confidence >= 0.3:
                    watch_match = True
                    watch_phrase = active_alert.get("watch_phrase")
                    break
        
        # AI analysis for high-confidence detections
        analysis = None
        if len(detections) > 0 and any(d.confidence > 0.6 for d in detections):
            try:
                ai = _get_ai()
                context = {
                    "camera_id": request.camera_id,
                    "detections": [{"label": d.label, "confidence": d.confidence} for d in detections],
                    "timestamp": request.timestamp,
                }
                result = ai.review_watch_target({
                    **context,
                    "watch_phrase": watch_phrase or "suspicious activity",
                })
                analysis = {
                    "summary": result.summary,
                    "threat_level": result.threat_level,
                    "watch_assessment": result.watch_assessment,
                }
            except Exception as ai_err:
                logger.warning(f"AI analysis failed: {ai_err}")
        
        # Store detection
        from api.services import CacheService
        cache = CacheService(redis_client)
        cache.add_live_detection(request.camera_id, {
            "timestamp": request.timestamp,
            "detections": [{"label": d.label, "confidence": d.confidence} for d in detections],
            "watch_match": watch_match,
        })
        
        return LiveDetectResponse(
            camera_id=request.camera_id,
            timestamp=request.timestamp,
            detections=detections,
            analysis=analysis,
            watch_match=watch_match,
            watch_phrase=watch_phrase
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Live detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")


@router.get("/detections/{camera_id}")
async def get_live_detections(camera_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get recent detections for a camera."""
    try:
        from api.services import CacheService
        cache = CacheService(redis_client)
        detections = cache.get_live_detections(camera_id, limit=limit)
        return {"camera_id": camera_id, "detections": detections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch detections: {str(e)}")
