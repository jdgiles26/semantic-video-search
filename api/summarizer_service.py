"""Dedicated LLM summarizer service for commander-intent SITREPs."""
from __future__ import annotations

from typing import Any, Dict, List
import json
import os

import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Mission Summarizer", version="1.0.0")


class SitrepRequest(BaseModel):
    query: str
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    policy: Dict[str, Any] = Field(default_factory=dict)
    commander_intent: str = "Protect life, coordinate multi-agency response, and preserve evidence."


class SitrepResponse(BaseModel):
    sitrep: str


AGENCY_TEMPLATES = {
    "law-enforcement": "Law enforcement focus: suspect/vehicle description, last known location, immediate perimeter recommendations.",
    "fire-rescue": "Fire/rescue focus: hazard type, spread indicators, evacuation routes, and staging recommendations.",
    "ems": "EMS focus: casualty indicators, triage urgency, access constraints, and handoff notes.",
    "maritime-ops": "Maritime ops focus: vessel/location context, navigational hazards, and cross-agency comms plan.",
    "aviation-ops": "Aviation ops focus: runway/airside impact, aircraft movement risk, and tower coordination actions.",
    "command-center": "Command center focus: multi-agency priorities, resource assignment, and 30-minute action plan.",
}


def _fallback_template(req: SitrepRequest) -> str:
    agencies = req.policy.get("agencies", []) if isinstance(req.policy, dict) else []
    template_lines = [AGENCY_TEMPLATES.get(a, "") for a in agencies if AGENCY_TEMPLATES.get(a)]
    top = req.alerts[0] if req.alerts else {}
    return "\n".join(
        [
            "MISSION SITREP",
            "============",
            f"Commander Intent: {req.commander_intent}",
            f"Query: {req.query}",
            f"Priority: {top.get('urgency_level', 'low')}",
            f"Primary Source: {top.get('source_name', 'unknown')}",
            f"Policy Route: agencies={', '.join(agencies) if agencies else 'command-center'} channels={', '.join(req.policy.get('channels', ['redis'])) if isinstance(req.policy, dict) else 'redis'}",
            "",
            "Agency Guidance:",
            *(template_lines or ["- Coordinate command-center validation and escalation."]),
            "",
            "Immediate Actions (0-30 min):",
            "1. Validate top event against nearest correlated feed.",
            "2. Notify routed agencies and assign incident lead.",
            "3. Preserve and distribute clip evidence with timestamps.",
        ]
    )


def _llm_generate(req: SitrepRequest) -> str:
    # OpenAI-compatible HTTP API
    base = os.getenv("LLM_API_BASE", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = os.getenv("LLM_API_KEY", "")

    if not base:
        return _fallback_template(req)

    agencies = req.policy.get("agencies", []) if isinstance(req.policy, dict) else []
    guidance = [AGENCY_TEMPLATES.get(a, "") for a in agencies if AGENCY_TEMPLATES.get(a)]

    system_prompt = (
        "You generate concise, operational SITREPs for multi-agency commanders. "
        "Output plain text with sections: Situation, Assessment, Recommended Actions, Routing Notes, Confidence."
    )

    user_prompt = {
        "commander_intent": req.commander_intent,
        "query": req.query,
        "alerts": req.alerts[:5],
        "policy": req.policy,
        "agency_guidance": guidance,
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt)},
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(f"{base.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
        return _fallback_template(req)


@app.get("/")
def health():
    return {"status": "ok", "service": "mission-summarizer"}


@app.post("/summarize/sitrep", response_model=SitrepResponse)
def summarize(req: SitrepRequest):
    sitrep = _llm_generate(req)
    return SitrepResponse(sitrep=sitrep)
