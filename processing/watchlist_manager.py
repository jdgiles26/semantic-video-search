"""Automated OPORD-driven watchlist activation and finding correlation."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional


WATCH_ACTIVE_KEY = "watch:active"
WATCH_HISTORY_KEY = "watch:history"


WATCH_RULES = [
    {"phrase": "suspicious person", "labels": ["person"], "priority": "critical"},
    {"phrase": "suspicious vehicle", "labels": ["car", "truck", "bus", "motorcycle"], "priority": "high"},
    {"phrase": "armed person", "labels": ["person"], "priority": "critical"},
    {"phrase": "weapon", "labels": ["person"], "priority": "critical"},
    {"phrase": "boat", "labels": ["boat"], "priority": "high"},
]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


class WatchlistManager:
    """Manage one active OPORD-driven watch alert and its findings."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def _findings_key(self, alert_id: str) -> str:
        return f"watch:findings:{alert_id}"

    def _seen_key(self, alert_id: str) -> str:
        return f"watch:seen:{alert_id}"

    def _extract_json_snapshot(self, content: str) -> Dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {}
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def derive_alert_from_document(
        self,
        filename: str,
        content: str,
        mime_type: str = "",
    ) -> Optional[Dict[str, Any]]:
        basename = os.path.splitext(os.path.basename(filename or ""))[0]
        filename_text = _normalize_text(re.sub(r"([a-z])([A-Z])", r"\1 \2", basename.replace("_", " ").replace("-", " ")))
        content_text = _normalize_text(content)
        combined = f"{filename_text} {content_text}".strip()

        matched_rule = None
        for rule in WATCH_RULES:
            if rule["phrase"] in combined:
                matched_rule = rule
                break

        if not matched_rule:
            return None

        snapshot = self._extract_json_snapshot(content)
        topics = snapshot.get("topics", []) if isinstance(snapshot.get("topics"), list) else []
        entities = snapshot.get("entities", []) if isinstance(snapshot.get("entities"), list) else []
        keywords = snapshot.get("keywords", []) if isinstance(snapshot.get("keywords"), list) else []

        alert_id = str(uuid.uuid4())
        excerpt = " ".join((content or "").split())[:1200]
        return {
            "alert_id": alert_id,
            "status": "active",
            "created_at": int(time.time()),
            "source_filename": filename,
            "mime_type": mime_type,
            "watch_phrase": matched_rule["phrase"],
            "watch_labels": matched_rule["labels"],
            "watch_label": matched_rule["labels"][0],
            "priority": matched_rule["priority"],
            "topics": topics[:8],
            "entities": entities[:12],
            "keywords": keywords[:12],
            "banner_message": f"OPORD watch active: prioritizing '{matched_rule['phrase']}' detections and correlations.",
            "opord_excerpt": excerpt,
        }

    def activate_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        self.redis.set(WATCH_ACTIVE_KEY, json.dumps(alert))
        self.redis.lpush(WATCH_HISTORY_KEY, json.dumps(alert))
        self.redis.ltrim(WATCH_HISTORY_KEY, 0, 49)
        return alert

    def get_active_alert(self, include_findings: bool = True, limit: int = 20) -> Optional[Dict[str, Any]]:
        raw = self.redis.get(WATCH_ACTIVE_KEY)
        if not raw:
            return None
        try:
            alert = json.loads(raw)
        except Exception:
            return None
        if not isinstance(alert, dict):
            return None
        findings = self.get_findings(alert.get("alert_id", ""), limit=limit) if include_findings else []
        alert["findings"] = findings
        alert["findings_count"] = len(findings)
        alert["latest_finding_at"] = findings[0]["timestamp"] if findings else None
        return alert

    def get_findings(self, alert_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        if not alert_id:
            return []
        findings: List[Dict[str, Any]] = []
        for raw in self.redis.lrange(self._findings_key(alert_id), 0, max(0, limit - 1)):
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                findings.append(parsed)
        return findings

    def match_detection(
        self,
        alert: Optional[Dict[str, Any]],
        detected_objects: Any,
        text_haystack: str = "",
    ) -> Dict[str, Any]:
        if not alert:
            return {"matched": False, "matched_labels": [], "matched_terms": []}
        labels = []
        for obj in detected_objects or []:
            if isinstance(obj, dict) and obj.get("label"):
                labels.append(str(obj["label"]).lower())
            elif isinstance(obj, str):
                labels.append(obj.lower())
        text = _normalize_text(text_haystack)
        watch_labels = {str(label).lower() for label in alert.get("watch_labels", [])}
        watch_phrase = _normalize_text(alert.get("watch_phrase", ""))
        matched_labels = sorted(set(labels).intersection(watch_labels))
        matched_terms = [watch_phrase] if watch_phrase and watch_phrase in text else []
        return {
            "matched": bool(matched_labels or matched_terms),
            "matched_labels": matched_labels,
            "matched_terms": matched_terms,
        }

    def add_finding(self, alert_id: str, finding: Dict[str, Any]) -> bool:
        if not alert_id or not finding:
            return False
        finding_id = str(finding.get("finding_id") or finding.get("event_id") or "")
        if finding_id and self.redis.sismember(self._seen_key(alert_id), finding_id):
            return False
        if finding_id:
            self.redis.sadd(self._seen_key(alert_id), finding_id)
        self.redis.lpush(self._findings_key(alert_id), json.dumps(finding))
        self.redis.ltrim(self._findings_key(alert_id), 0, 99)
        return True

    def clear_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        active = self.get_active_alert(include_findings=False)
        if not active or active.get("alert_id") != alert_id:
            return None
        active["status"] = "cleared"
        active["cleared_at"] = int(time.time())
        self.redis.delete(WATCH_ACTIVE_KEY)
        self.redis.lpush(WATCH_HISTORY_KEY, json.dumps(active))
        self.redis.ltrim(WATCH_HISTORY_KEY, 0, 49)
        return active
