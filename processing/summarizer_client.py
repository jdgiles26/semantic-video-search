"""Client for the dedicated LLM summarizer service."""
from __future__ import annotations

from typing import Dict, List, Any, Optional
import os
import requests


class SitrepSummarizerClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or os.getenv("SUMMARIZER_SERVICE_URL", "http://llm-summarizer:8010")

    def generate_sitrep(
        self,
        query: str,
        alerts: List[Dict[str, Any]],
        policy: Dict[str, Any],
        commander_intent: str = "Protect life, coordinate multi-agency response, and preserve evidence.",
    ) -> str:
        payload = {
            "query": query,
            "alerts": alerts,
            "policy": policy,
            "commander_intent": commander_intent,
        }
        r = requests.post(f"{self.base_url}/summarize/sitrep", json=payload, timeout=12)
        r.raise_for_status()
        data = r.json()
        return str(data.get("sitrep", "")).strip()
