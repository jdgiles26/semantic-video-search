"""
Redis cache service for consistent data access patterns.
"""
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import redis

logger = logging.getLogger(__name__)


class CacheService:
    """Service for Redis cache operations with consistent patterns."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    # Key generators
    def clip_meta_key(self, clip_id: int) -> str:
        return f"clip_meta:{clip_id}"
    
    def asset_key(self, asset_id: str) -> str:
        return f"upload_asset:{asset_id}"
    
    def camera_key(self, camera_id: str) -> str:
        return f"camera:{camera_id}"
    
    def task_key(self, task_id: str) -> str:
        return f"task:{task_id}"
    
    # Clip metadata operations
    def get_clip_metadata(self, clip_id: int) -> Optional[Dict[str, Any]]:
        """Load clip metadata from Redis."""
        try:
            raw = self.redis.hgetall(self.clip_meta_key(clip_id))
            if not raw:
                return None
            
            meta = {}
            json_fields = {
                "detected_objects", "object_scores", "clip_tags", "extra",
                "urgency_reasons", "watch_assessment"
            }
            
            for k, v in raw.items():
                if k in json_fields:
                    try:
                        meta[k] = json.loads(v)
                    except Exception:
                        meta[k] = v
                else:
                    meta[k] = v
            return meta
        except Exception as e:
            logger.error(f"Failed to load clip metadata for {clip_id}: {e}")
            return None
    
    def set_clip_metadata(self, clip_id: int, metadata: Dict[str, Any]) -> bool:
        """Store clip metadata in Redis."""
        try:
            # Serialize JSON fields
            json_fields = {
                "detected_objects", "object_scores", "clip_tags", "extra",
                "urgency_reasons", "watch_assessment"
            }
            
            mapping = {}
            for k, v in metadata.items():
                if k in json_fields and not isinstance(v, str):
                    mapping[k] = json.dumps(v)
                else:
                    mapping[k] = str(v) if v is not None else ""
            
            self.redis.hset(self.clip_meta_key(clip_id), mapping=mapping)
            return True
        except Exception as e:
            logger.error(f"Failed to store clip metadata for {clip_id}: {e}")
            return False
    
    # Asset operations
    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get uploaded asset metadata."""
        raw = self.redis.hgetall(self.asset_key(asset_id))
        if not raw:
            return None
        
        return {
            "asset_id": raw.get("asset_id", asset_id),
            "filename": raw.get("filename", ""),
            "media_kind": raw.get("media_kind", "document"),
            "mime_type": raw.get("mime_type", "application/octet-stream"),
            "file_size": int(raw.get("file_size", 0) or 0),
            "status": raw.get("status", "ready"),
            "created_at": int(raw.get("created_at", 0) or 0),
            "task_id": raw.get("task_id") or None,
            "thumbnail_path": raw.get("thumbnail_path") or None,
            "file_path": raw.get("file_path", ""),
            "excerpt": raw.get("excerpt") or None,
            "notes": raw.get("notes") or None,
        }
    
    def list_assets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List uploaded assets."""
        assets = []
        for key in self.redis.scan_iter(match="upload_asset:*"):
            raw = self.redis.hgetall(key)
            if raw:
                assets.append({
                    "asset_id": raw.get("asset_id", key.split(":", 1)[-1]),
                    "filename": raw.get("filename", ""),
                    "media_kind": raw.get("media_kind", "document"),
                    "mime_type": raw.get("mime_type", "application/octet-stream"),
                    "file_size": int(raw.get("file_size", 0) or 0),
                    "status": raw.get("status", "ready"),
                    "created_at": int(raw.get("created_at", 0) or 0),
                    "task_id": raw.get("task_id") or None,
                    "thumbnail_path": raw.get("thumbnail_path") or None,
                    "file_path": raw.get("file_path", ""),
                    "excerpt": raw.get("excerpt") or None,
                    "notes": raw.get("notes") or None,
                })
        
        assets.sort(key=lambda a: a.get("created_at", 0), reverse=True)
        return assets[:limit]
    
    # Camera operations
    def get_camera(self, camera_id: str) -> Optional[Dict[str, str]]:
        """Get camera/stream status."""
        return self.redis.hgetall(self.camera_key(camera_id)) or None
    
    def list_cameras(self) -> List[Dict[str, Any]]:
        """List all cameras/streams."""
        cameras = []
        for key in self.redis.scan_iter(match="camera:*"):
            camera_id = key.split(":", 1)[-1]
            info = self.redis.hgetall(key)
            if info:
                cameras.append({
                    "camera_id": camera_id,
                    **info
                })
        return cameras
    
    def update_camera_status(self, camera_id: str, status: str, **fields) -> bool:
        """Update camera status and fields."""
        try:
            mapping = {"status": status, **fields}
            if "last_update" not in mapping:
                mapping["last_update"] = int(datetime.now().timestamp())
            self.redis.hset(self.camera_key(camera_id), mapping=mapping)
            return True
        except Exception as e:
            logger.error(f"Failed to update camera {camera_id}: {e}")
            return False
    
    # Task operations
    def get_task(self, task_id: str) -> Optional[Dict[str, str]]:
        """Get task status."""
        return self.redis.hgetall(self.task_key(task_id)) or None
    
    def list_tasks(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all tasks with optional status filter."""
        tasks = []
        for key in self.redis.scan_iter(match="task:*"):
            task_id = key.split(":", 1)[-1]
            info = self.redis.hgetall(key)
            
            if info:
                if status_filter and info.get("status") != status_filter:
                    continue
                
                tasks.append({
                    "task_id": task_id,
                    **info
                })
        
        return sorted(tasks, key=lambda t: t.get("task_id", ""), reverse=True)
    
    # Mission events
    def add_mission_event(self, event: Dict[str, Any], trim_size: int = 2000) -> bool:
        """Add a mission event to the stream."""
        try:
            self.redis.lpush("mission:events", json.dumps(event))
            self.redis.ltrim("mission:events", 0, trim_size - 1)
            return True
        except Exception as e:
            logger.error(f"Failed to add mission event: {e}")
            return False
    
    def get_mission_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent mission events."""
        events = []
        for raw in self.redis.lrange("mission:events", 0, max(0, limit - 1)):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    events.append(parsed)
            except Exception:
                continue
        return events
    
    # Predictions
    def get_predictions(self) -> Optional[Dict[str, Any]]:
        """Get cached predictions."""
        raw = self.redis.get("risk:predictions")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return None
    
    # Live detections
    def add_live_detection(self, camera_id: str, detection: Dict[str, Any], trim_size: int = 100) -> bool:
        """Add a live detection for a camera."""
        try:
            key = f"live_detections:{camera_id}"
            self.redis.lpush(key, json.dumps(detection))
            self.redis.ltrim(key, 0, trim_size - 1)
            return True
        except Exception as e:
            logger.error(f"Failed to add live detection: {e}")
            return False
    
    def get_live_detections(self, camera_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent live detections for a camera."""
        detections = []
        key = f"live_detections:{camera_id}"
        for raw in self.redis.lrange(key, 0, limit - 1):
            try:
                detections.append(json.loads(raw))
            except Exception:
                continue
        return detections
    
    # Queue operations
    def queue_task(self, queue_name: str, task: Dict[str, Any]) -> bool:
        """Add a task to a Redis queue."""
        try:
            self.redis.rpush(queue_name, json.dumps(task))
            return True
        except Exception as e:
            logger.error(f"Failed to queue task to {queue_name}: {e}")
            return False
    
    def publish_alert(self, alert: Dict[str, Any], max_size: int = 200) -> bool:
        """Publish an alert to the alerts stream."""
        try:
            self.redis.lpush("alerts:events", json.dumps(alert))
            self.redis.ltrim("alerts:events", 0, max_size - 1)
            return True
        except Exception as e:
            logger.error(f"Failed to publish alert: {e}")
            return False
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        alerts = []
        for raw in self.redis.lrange("alerts:events", 0, max(0, limit - 1)):
            try:
                payload = json.loads(raw)
                if payload.get("alert"):
                    alerts.append(payload["alert"])
            except Exception:
                continue
        return alerts
