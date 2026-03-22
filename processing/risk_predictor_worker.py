"""Background predictor worker for proactive risk forecasting from mission events."""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List

import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskPredictorWorker:
    """
    Proactive risk forecasting worker that polls mission events from Redis.
    
    Risk Formula:
        risk_score = 0.55 × min(1, signal_60m / 5) + 0.45 × min(1, trend)
        
    Where:
        signal_60m = weighted sum of (urgency × mission_score) over 60 minutes
        signal_15m = weighted sum over 15 minutes (recent activity)
        trend = signal_15m / signal_60m (acceleration indicator)
        
    Output: JSON predictions sorted by risk_score, stored in Redis key "risk:predictions"
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.poll_interval = int(os.getenv("PREDICTOR_POLL_SECONDS", "15"))

    @staticmethod
    def _parse_event(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            return {}

    @staticmethod
    def _urgency_weight(level: str) -> float:
        return {
            "critical": 1.0,
            "high": 0.7,
            "medium": 0.4,
            "low": 0.1,
        }.get((level or "low").lower(), 0.1)

    def _compute_predictions(self, events: List[Dict[str, Any]], now_ts: int) -> List[Dict[str, Any]]:
        per_source_15 = defaultdict(float)
        per_source_60 = defaultdict(float)
        object_graph = defaultdict(set)

        for e in events:
            ts = int(e.get("timestamp") or e.get("created_at") or 0)
            if ts <= 0:
                continue
            source = str(e.get("source_name", "unknown"))
            urgency = self._urgency_weight(str(e.get("urgency_level", "low")))
            mission = float(e.get("mission_score", 0.0))
            weight = max(0.05, 0.5 * urgency + 0.5 * mission)

            age = now_ts - ts
            if age <= 15 * 60:
                per_source_15[source] += weight
            if age <= 60 * 60:
                per_source_60[source] += weight

            labels = []
            for obj in e.get("detected_objects", []) or []:
                if isinstance(obj, dict) and obj.get("label"):
                    labels.append(str(obj["label"]).lower())
                elif isinstance(obj, str):
                    labels.append(obj.lower())
            for i in range(len(labels)):
                for j in range(i + 1, len(labels)):
                    a, b = sorted([labels[i], labels[j]])
                    object_graph[a].add(b)

        predictions = []
        for source, score_60 in per_source_60.items():
            score_15 = per_source_15.get(source, 0.0)
            trend = score_15 / max(0.1, score_60)
            forecast = min(1.0, 0.55 * min(1.0, score_60 / 5.0) + 0.45 * min(1.0, trend))
            predictions.append(
                {
                    "source_name": source,
                    "risk_score": round(forecast, 4),
                    "recent_signal_15m": round(score_15, 4),
                    "recent_signal_60m": round(score_60, 4),
                    "trend": round(trend, 4),
                    "forecast_horizon_minutes": 30,
                    "risk_level": "critical" if forecast >= 0.8 else "high" if forecast >= 0.6 else "medium" if forecast >= 0.35 else "low",
                }
            )

        predictions.sort(key=lambda x: x["risk_score"], reverse=True)

        graph_edges = []
        for a, bs in object_graph.items():
            for b in sorted(bs):
                graph_edges.append({"from": a, "to": b})

        self.redis.set("risk:event_graph", json.dumps(graph_edges[:300]))
        return predictions[:50]

    def run(self):
        logger.info("Risk predictor worker started")
        while True:
            try:
                raw_events = self.redis.lrange("mission:events", 0, 1000)
                events = [self._parse_event(e) for e in raw_events]
                now_ts = int(time.time())
                predictions = self._compute_predictions(events, now_ts)
                self.redis.set("risk:predictions", json.dumps({"generated_at": now_ts, "items": predictions}))
                time.sleep(self.poll_interval)
            except Exception as exc:
                logger.error("Risk predictor loop error: %s", exc)
                time.sleep(3)


def main():
    worker = RiskPredictorWorker(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
    )
    worker.run()


if __name__ == "__main__":
    main()
