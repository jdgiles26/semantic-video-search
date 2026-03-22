"""Policy-based routing for mission alerts by source, objects, and urgency."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any
import json
import os


@dataclass
class PolicyDecision:
    agencies: List[str]
    channels: List[str]
    recipients: List[str]
    priority: str
    rationale: List[str]


class PolicyRouter:
    """Simple policy engine for routing incidents to agencies and channels."""

    def __init__(self) -> None:
        self.email_map = self._load_email_map()

    @staticmethod
    def _load_email_map() -> Dict[str, List[str]]:
        raw = os.getenv("POLICY_EMAIL_MAP", "")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return {str(k): [str(vv) for vv in v] for k, v in parsed.items() if isinstance(v, list)}
        except Exception:
            return {}

    @staticmethod
    def _labels(alert: Dict[str, Any]) -> List[str]:
        labels: List[str] = []
        for obj in alert.get("detected_objects", []) or []:
            if isinstance(obj, dict) and obj.get("label"):
                labels.append(str(obj["label"]).lower())
            elif isinstance(obj, str):
                labels.append(obj.lower())
        return labels

    def route(self, alert: Dict[str, Any]) -> PolicyDecision:
        source_name = str(alert.get("source_name", "")).lower()
        urgency = str(alert.get("urgency_level", "low")).lower()
        labels = self._labels(alert)

        agencies = ["command-center"]
        channels = ["redis"]
        rationale: List[str] = []

        # Urgency-first policy
        if urgency in {"critical", "high"}:
            channels.extend(["email", "webhook"])
            rationale.append(f"urgency:{urgency}")

        # Object-based policy
        if any(lbl in {"person", "knife", "weapon", "gun"} for lbl in labels):
            agencies.append("law-enforcement")
            rationale.append("object:threat-human")

        if any(lbl in {"fire", "smoke"} for lbl in labels):
            agencies.append("fire-rescue")
            rationale.append("object:fire-smoke")

        if any(lbl in {"person", "injury", "bleeding"} for lbl in labels):
            agencies.append("ems")
            rationale.append("object:medical")

        # Source-based policy
        if "port" in source_name or "harbor" in source_name or "coast" in source_name:
            agencies.append("maritime-ops")
            rationale.append("source:maritime")

        if "airport" in source_name or "runway" in source_name:
            agencies.append("aviation-ops")
            rationale.append("source:aviation")

        if alert.get("source_type") == "live":
            agencies.append("live-ops")
            rationale.append("source_type:live")

        # Normalize
        seen = set()
        agencies = [a for a in agencies if not (a in seen or seen.add(a))]
        seen = set()
        channels = [c for c in channels if not (c in seen or seen.add(c))]

        recipients: List[str] = []
        for agency in agencies:
            recipients.extend(self.email_map.get(agency, []))
        recipients = sorted(set(recipients))

        priority = urgency if urgency in {"critical", "high", "medium"} else "low"
        if not rationale:
            rationale = ["default-policy"]

        return PolicyDecision(
            agencies=agencies,
            channels=channels,
            recipients=recipients,
            priority=priority,
            rationale=rationale,
        )
