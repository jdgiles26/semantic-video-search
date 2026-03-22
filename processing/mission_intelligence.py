"""Mission-oriented search enrichment and urgency automation utilities."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any


@dataclass
class QueryIntent:
    tokens: List[str]
    urgency_score: float
    priority_terms: List[str]


class MissionIntelligenceEngine:
    """
    Mission intelligence processor for urgency scoring and cross-source correlation.
    
    Urgency Scoring:
        - critical terms (+0.45): active shooter, explosion, hostage, etc.
        - high terms (+0.25): weapon, fire, intruder, assault, etc.
        - medium terms (+0.12): suspicious, accident, anomaly, etc.
        
    Mission Score Formula:
        standard: 0.65 × base_score + 0.20 × object_overlap + 0.15 × urgency
        mission_ai: 0.50 × base_score + 0.25 × object_overlap + 0.25 × urgency
        
    Correlation: Events within 180-second windows across different sources
    get correlated and receive +0.15 mission_score boost.
    """

    URGENCY_TERMS = {
        "critical": {
            "mayday", "active shooter", "gunfire", "shots fired", "officer down",
            "explosion", "hostage", "evac", "evacuate", "collapse", "fatal",
        },
        "high": {
            "weapon", "knife", "fire", "smoke", "intruder", "assault", "fight",
            "bleeding", "panic", "distress", "emergency", "urgent",
        },
        "medium": {
            "suspicious", "trespass", "crowd", "accident", "collision", "crash",
            "abandoned", "anomaly", "unusual", "loitering",
        },
    }

    def parse_query_intent(self, query: str) -> QueryIntent:
        q = (query or "").lower()
        tokens = [t for t in q.replace("_", " ").replace("-", " ").split() if t]

        urgency = 0.0
        priority_terms: List[str] = []

        for term in self.URGENCY_TERMS["critical"]:
            if term in q:
                urgency += 0.45
                priority_terms.append(term)

        for term in self.URGENCY_TERMS["high"]:
            if term in q:
                urgency += 0.25
                priority_terms.append(term)

        for term in self.URGENCY_TERMS["medium"]:
            if term in q:
                urgency += 0.12
                priority_terms.append(term)

        return QueryIntent(tokens=tokens, urgency_score=min(1.0, urgency), priority_terms=priority_terms)

    @staticmethod
    def _normalize_object_list(detected_objects: Any) -> List[str]:
        if not detected_objects:
            return []
        normalized: List[str] = []
        for obj in detected_objects:
            if isinstance(obj, str):
                normalized.append(obj.lower())
            elif isinstance(obj, dict) and obj.get("label"):
                normalized.append(str(obj["label"]).lower())
        return sorted(set(normalized))

    @staticmethod
    def _overlap_score(tokens: List[str], object_labels: List[str]) -> float:
        if not tokens or not object_labels:
            return 0.0
        matches = 0
        for t in tokens:
            if any((t == o or t in o or o in t) for o in object_labels):
                matches += 1
        return min(1.0, matches / max(1, len(tokens)))

    @staticmethod
    def _urgency_level(score: float) -> str:
        if score >= 0.8:
            return "critical"
        if score >= 0.6:
            return "high"
        if score >= 0.35:
            return "medium"
        return "low"

    def enrich_results(self, query: str, results: List[Dict[str, Any]], mode: str = "clip") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        intent = self.parse_query_intent(query)

        enriched: List[Dict[str, Any]] = []
        bucketed: Dict[int, List[int]] = defaultdict(list)

        for idx, r in enumerate(results):
            base_score = float(r.get("score", 0.0))
            object_labels = self._normalize_object_list(r.get("detected_objects"))
            object_overlap = self._overlap_score(intent.tokens, object_labels)

            urgency_reasons: List[str] = []
            urgency_score = intent.urgency_score

            if object_overlap > 0.35:
                urgency_score += 0.12
                urgency_reasons.append("query-object overlap")

            for lbl in object_labels:
                if lbl in {"person", "car", "truck", "bus", "motorcycle"}:
                    urgency_score += 0.03

            if r.get("source_type") == "live":
                urgency_score += 0.05
                urgency_reasons.append("live feed")

            urgency_score = min(1.0, urgency_score)

            correlation_window = int(r.get("timestamp", 0)) // 180
            bucketed[correlation_window].append(idx)

            if intent.priority_terms:
                urgency_reasons.extend([f"query:{p}" for p in intent.priority_terms[:3]])

            mission_score = (0.65 * base_score) + (0.20 * object_overlap) + (0.15 * urgency_score)

            if mode == "mission_ai":
                mission_score = (0.50 * base_score) + (0.25 * object_overlap) + (0.25 * urgency_score)

            e = r.copy()
            e["clip_score"] = e.get("clip_score", base_score)
            e["object_overlap_score"] = round(object_overlap, 4)
            e["urgency_score"] = round(urgency_score, 4)
            e["urgency_level"] = self._urgency_level(urgency_score)
            e["urgency_reasons"] = urgency_reasons[:6]
            e["mission_score"] = round(min(1.0, mission_score), 4)
            e["correlation_score"] = 0.0
            e["correlated_sources"] = []
            enriched.append(e)

        # Cross-source correlation boost for near-time events across different feeds
        for idxs in bucketed.values():
            if len(idxs) < 2:
                continue
            sources = {str(enriched[i].get("source_name", "")) for i in idxs}
            if len(sources) < 2:
                continue
            for i in idxs:
                enriched[i]["correlation_score"] = 0.15
                enriched[i]["correlated_sources"] = sorted(list(sources - {str(enriched[i].get("source_name", ""))}))[:5]
                enriched[i]["mission_score"] = round(min(1.0, enriched[i]["mission_score"] + 0.15), 4)

        # Re-rank by mission score for mission mode, else keep existing order by score-ish
        if mode == "mission_ai":
            enriched.sort(key=lambda x: x.get("mission_score", 0.0), reverse=True)

        alerts = [
            {
                "id": r.get("id"),
                "source_name": r.get("source_name"),
                "source_type": r.get("source_type"),
                "timestamp": r.get("timestamp"),
                "urgency_level": r.get("urgency_level"),
                "urgency_score": r.get("urgency_score"),
                "mission_score": r.get("mission_score"),
                "urgency_reasons": r.get("urgency_reasons", []),
                "detected_objects": r.get("detected_objects", []),
                "video_chunk_path": r.get("video_chunk_path"),
                "thumbnail_path": r.get("thumbnail_path"),
            }
            for r in enriched
            if r.get("urgency_level") in {"critical", "high"}
        ]

        alerts.sort(key=lambda x: (x.get("urgency_score", 0.0), x.get("mission_score", 0.0)), reverse=True)
        return enriched, alerts[:10]

    @staticmethod
    def build_incident_report(query: str, alerts: List[Dict[str, Any]]) -> str:
        if not alerts:
            return "No urgent incidents detected for this query."

        top = alerts[0]
        lines = [
            "MISSION INCIDENT REPORT",
            "=======================",
            f"Query: {query}",
            f"Priority: {str(top.get('urgency_level', 'low')).upper()}",
            f"Primary Source: {top.get('source_name', 'unknown')} ({top.get('source_type', 'unknown')})",
            f"Timestamp: {top.get('timestamp')}",
            f"AI Urgency Score: {top.get('urgency_score')}",
            f"Mission Score: {top.get('mission_score')}",
            "",
            "Reasoning:",
        ]

        for reason in top.get("urgency_reasons", [])[:5]:
            lines.append(f"- {reason}")

        objs = top.get("detected_objects", [])
        if objs:
            lines.append("")
            lines.append("Detected Objects:")
            for o in objs[:8]:
                if isinstance(o, dict):
                    lines.append(f"- {o.get('label')} ({o.get('confidence', 0):.2f})")
                else:
                    lines.append(f"- {o}")

        lines.extend([
            "",
            "Recommended Actions:",
            "- Validate with nearest available camera feed.",
            "- Notify command and relevant agencies based on SOP.",
            "- Preserve clip evidence and continue monitoring correlated sources.",
        ])

        return "\n".join(lines)
