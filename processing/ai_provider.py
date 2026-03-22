"""Unified AI provider service supporting Ollama, OpenAI, and WebGPU backends."""
from __future__ import annotations

import json
import os
import logging
import time
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AI_CONFIG_PATH = os.getenv("AI_CONFIG_PATH", "/tmp/video_search_ai_config.json")


class AIProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    WEBGPU = "webgpu"


@dataclass
class AIConfig:
    """
    Configuration for multi-provider AI backends.
    
    Provider Priority: Ollama (local) → OpenAI (cloud) → WebGPU (browser)
    
    Environment Variables:
        AI_PROVIDER: ollama|openai|webgpu
        OLLAMA_BASE_URL: http://localhost:11434
        OLLAMA_MODEL: llava:7b (vision model required)
        OPENAI_API_KEY: sk-...
        OPENAI_MODEL: gpt-4o-mini
        WEBGPU_ENABLED: false (frontend-only)
    """
    provider: AIProvider = AIProvider.OLLAMA
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llava:7b"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    webgpu_enabled: bool = False
    temperature: float = 0.3
    max_tokens: int = 2048


@dataclass
class ProviderStatus:
    provider: str
    available: bool
    configured: bool = True
    model: str = ""
    detail: str = ""
    error: str = ""
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "available": self.available,
            "configured": self.configured,
            "model": self.model,
            "detail": self.detail,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "actions": self.actions,
        }


@dataclass
class AnalysisResult:
    summary: str
    threat_level: str = "low"
    threat_score: float = 0.0
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    predictions: List[str] = field(default_factory=list)
    correlations: List[Dict[str, Any]] = field(default_factory=list)
    priorities: List[Dict[str, Any]] = field(default_factory=list)
    trends: List[str] = field(default_factory=list)
    detected_themes: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    watch_assessment: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    provider_used: str = ""
    model_used: str = ""
    confidence: float = 0.0
    analysis_factors: List[Dict[str, Any]] = field(default_factory=list)


class BaseAIBackend(ABC):
    @abstractmethod
    def analyze(self, prompt: str, context: Dict[str, Any]) -> AnalysisResult:
        pass

    @abstractmethod
    def generate_report(self, data: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    def get_status(self) -> ProviderStatus:
        available = self.is_available()
        return ProviderStatus(
            provider="unknown",
            available=available,
            detail="Provider status not implemented",
        )


class OllamaBackend(BaseAIBackend):
    VISION_MODEL_HINTS = (
        "llava",
        "bakllava",
        "vision",
        "minicpm-v",
        "moondream",
        "qwen2.5vl",
        "qwen2-vl",
        "gemma3",
        "phi4-mini",
        "qwen",
    )

    def __init__(self, config: AIConfig):
        self.base_url = config.ollama_base_url
        self.model = config.ollama_model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self._cached_models: Optional[List[Dict]] = None
        self._cache_time: float = 0

    def is_available(self) -> bool:
        return self.get_status().available

    def _is_vision_model(self, model_name: str) -> bool:
        normalized = (model_name or "").lower()
        return any(hint in normalized for hint in self.VISION_MODEL_HINTS)

    def _fetch_tags(self, timeout: int = 5) -> Dict[str, Any]:
        """Fetch models from Ollama with better error handling."""
        urls_to_try = self._candidate_base_urls()

        last_error = None
        for url in urls_to_try:
            try:
                response = requests.get(f"{url}/api/tags", timeout=timeout)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and "models" in payload:
                    # Update base URL if this one worked
                    if url != self.base_url:
                        logger.info(f"Ollama found at {url} instead of {self.base_url}")
                        self.base_url = url
                    return payload
            except Exception as e:
                last_error = e
                continue
        
        if last_error:
            raise last_error
        return {"models": []}

    def _candidate_base_urls(self) -> List[str]:
        urls_to_try = [self.base_url]

        localhost_variants = {
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://host.docker.internal:11434",
        }
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url or "host.docker.internal" in self.base_url:
            urls_to_try.extend(sorted(localhost_variants))

        deduped: List[str] = []
        seen = set()
        for url in urls_to_try:
            normalized = str(url or "").rstrip("/")
            if not normalized or normalized in seen:
                continue
            deduped.append(normalized)
            seen.add(normalized)
        return deduped

    def discover_models(self, timeout: int = 5, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Discover Ollama models with caching."""
        # Use cache if valid (cache for 30 seconds)
        if use_cache and self._cached_models and (time.perf_counter() - self._cache_time) < 30:
            return self._cached_models
        
        try:
            payload = self._fetch_tags(timeout=timeout)
        except Exception as exc:
            logger.warning(f"Failed to discover Ollama models: {exc}")
            return self._cached_models or []

        models: List[Dict[str, Any]] = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue
            
            # Handle both old and new Ollama API formats
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            
            details = item.get("details") or {}
            
            # Parse size (could be int or string)
            size = item.get("size")
            if isinstance(size, str):
                try:
                    size = int(size)
                except ValueError:
                    size = 0
            
            models.append({
                "name": name,
                "size": size,
                "modified_at": item.get("modified_at") or item.get("modified"),
                "digest": item.get("digest"),
                "family": details.get("family"),
                "families": details.get("families"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
                "format": details.get("format"),
                "vision_capable": self._is_vision_model(name),
            })
        
        # Update cache
        self._cached_models = models
        self._cache_time = time.perf_counter()
        
        return models

    def get_status(self) -> ProviderStatus:
        configured = bool(self.base_url)
        if not configured:
            return ProviderStatus(
                provider=AIProvider.OLLAMA.value,
                available=False,
                configured=False,
                model=self.model,
                detail="Ollama base URL is not configured",
                actions=["Set OLLAMA_BASE_URL or save an Ollama base URL in settings"],
            )

        started = time.perf_counter()
        try:
            models = self.discover_models(timeout=5, use_cache=False)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception as exc:
            error_message = str(exc)
            return ProviderStatus(
                provider=AIProvider.OLLAMA.value,
                available=False,
                configured=True,
                model=self.model,
                detail="Failed to reach Ollama",
                error=error_message,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                actions=[
                    "Verify Ollama Desktop is running",
                    "Run 'ollama serve' in terminal",
                    "Check if Ollama is accessible at http://localhost:11434",
                    "For Docker: ensure host.docker.internal:11434 is reachable",
                ],
            )

        installed_models = {model["name"] for model in models}
        
        # Check for model with or without tag
        selected_model_present = self.model in installed_models
        if not selected_model_present:
            # Try matching without tag
            model_base = self.model.split(":")[0]
            for installed in installed_models:
                if installed.startswith(model_base + ":"):
                    selected_model_present = True
                    self.model = installed  # Update to full name
                    break
        
        selected_model_is_vision = self._is_vision_model(self.model)

        if not models:
            return ProviderStatus(
                provider=AIProvider.OLLAMA.value,
                available=False,
                configured=True,
                model=self.model,
                detail="Ollama is reachable but no local models were found",
                latency_ms=latency_ms,
                metadata={"models": [], "model_count": 0, "vision_capable": False},
                actions=[
                    "Pull a local model with `ollama pull <model>`",
                    "Select an installed model after it becomes available",
                ],
            )

        if not selected_model_present:
            return ProviderStatus(
                provider=AIProvider.OLLAMA.value,
                available=False,
                configured=True,
                model=self.model,
                detail="Configured Ollama model is not installed locally",
                latency_ms=latency_ms,
                metadata={
                    "models": models,
                    "model_count": len(models),
                    "vision_capable": False,
                },
                actions=[
                    f"Pull `{self.model}` with Ollama or choose one of the discovered models",
                ],
            )

        detail = "Ollama is reachable and the selected model is installed"
        actions: List[str] = []
        if not selected_model_is_vision:
            detail = "Ollama is reachable, but the selected model may not support vision review"
            actions.append("Choose a vision-capable Ollama model for clip/image review")

        return ProviderStatus(
            provider=AIProvider.OLLAMA.value,
            available=True,
            configured=True,
            model=self.model,
            detail=detail,
            latency_ms=latency_ms,
            metadata={
                "models": models,
                "model_count": len(models),
                "vision_capable": selected_model_is_vision,
                "base_url": self.base_url,
            },
            actions=actions,
        )

    def _call_api(self, prompt: str, system: str = "", image_paths: Optional[List[str]] = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
        if image_paths:
            payload["images"] = self._encode_images(image_paths)

        last_error: Optional[Exception] = None
        for url in self._candidate_base_urls():
            try:
                resp = requests.post(
                    f"{url}/api/generate",
                    json=payload,
                    timeout=60
                )
                resp.raise_for_status()
                if url != self.base_url:
                    logger.info("Ollama request succeeded via %s instead of %s", url, self.base_url)
                    self.base_url = url
                return resp.json().get("response", "")
            except requests.HTTPError as e:
                last_error = e
                response_text = ""
                if e.response is not None:
                    response_text = e.response.text[:300]
                logger.error(f"Ollama API error: {e} {response_text}")
                break
            except Exception as e:
                last_error = e
                continue

        if last_error:
            logger.error(f"Ollama API error: {last_error}")
        return ""

    def _encode_images(self, image_paths: List[str]) -> List[str]:
        encoded: List[str] = []
        for image_path in image_paths[:4]:
            if not image_path or not os.path.exists(image_path):
                continue
            try:
                with open(image_path, "rb") as handle:
                    encoded.append(base64.b64encode(handle.read()).decode("utf-8"))
            except Exception as exc:
                logger.warning("Failed to encode Ollama review image %s: %s", image_path, exc)
        return encoded

    def analyze(self, prompt: str, context: Dict[str, Any]) -> AnalysisResult:
        system_prompt = """Return compact JSON for surveillance review:
{
  "summary": "brief analysis summary",
  "threat_level": "low|medium|high|critical",
  "threat_score": 0.0-1.0,
  "alerts": [{"title": "alert", "priority": "low|medium|high|critical", "basis": "why"}],
  "predictions": ["prediction1", "prediction2"],
  "correlations": [{"source": "name", "relationship": "description"}],
  "priorities": [{"item": "focus area", "priority": "high", "reason": "why"}],
  "trends": ["trend1", "trend2"],
  "detected_themes": ["theme1", "theme2"],
  "recommendations": ["action1", "action2"],
  "watch_assessment": {"suspicious": false, "risk_factor": "low", "activity": "", "location": "", "companions": "", "military_or_uniform": "unknown", "weapons": "unknown", "friendly_force": "unknown"},
  "confidence": 0.0-1.0,
  "analysis_factors": [{"factor": "name", "weight": 0.0-1.0, "description": "why"}]
}"""
        full_prompt = f"Context: {json.dumps(context)}\n\nAnalysis request: {prompt}"
        raw = self._call_api(full_prompt, system_prompt)
        return self._parse_analysis(raw, "ollama", self.model)

    def generate_report(self, data: Dict[str, Any]) -> str:
        system_prompt = """Generate a detailed incident report with sections:
- SITUATION OVERVIEW
- THREAT ASSESSMENT
- DETECTED ENTITIES
- CORRELATION ANALYSIS
- PREDICTED DEVELOPMENTS
- RECOMMENDED ACTIONS
- CONFIDENCE ASSESSMENT"""
        prompt = f"Generate report for: {json.dumps(data)}"
        return self._call_api(prompt, system_prompt) or self._fallback_report(data)

    def review_mission_context(self, context: Dict[str, Any]) -> AnalysisResult:
        image_paths: List[str] = []
        for clip in context.get("clips", [])[:6]:
            thumbnail_path = clip.get("thumbnail_path")
            if thumbnail_path:
                image_paths.append(thumbnail_path)
        for asset in context.get("assets", [])[:6]:
            thumbnail_path = asset.get("thumbnail_path")
            if thumbnail_path:
                image_paths.append(thumbnail_path)

        system_prompt = """Return compact JSON for maritime/emergency review:
{
  "summary": "brief analysis summary",
  "threat_level": "low|medium|high|critical",
  "threat_score": 0.0-1.0,
  "alerts": [{"title": "alert", "priority": "critical", "basis": "why"}],
  "predictions": ["prediction1", "prediction2"],
  "correlations": [{"source": "name", "relationship": "description"}],
  "priorities": [{"item": "focus area", "priority": "high", "reason": "why"}],
  "trends": ["trend1", "trend2"],
  "detected_themes": ["maritime", "fire", "evacuation"],
  "recommendations": ["action1", "action2"],
  "confidence": 0.0-1.0,
  "analysis_factors": [{"factor": "name", "weight": 0.0-1.0, "description": "why"}]
}"""
        prompt = (
            "Review the attached thumbnails with the structured evidence. "
            "Flag maritime hazards, emergency wording/scenes, high-priority alerts, trends, and recommended actions. "
            f"Context: {json.dumps(context)}"
        )
        raw = self._call_api(prompt, system_prompt, image_paths=image_paths)
        return self._parse_analysis(raw, "ollama", self.model)

    def review_watch_target(self, context: Dict[str, Any], image_paths: Optional[List[str]] = None) -> AnalysisResult:
        system_prompt = """Return compact JSON for a watchlist-trigger review:
{
  "summary": "brief finding summary",
  "threat_level": "low|medium|high|critical",
  "threat_score": 0.0-1.0,
  "alerts": [{"title": "alert", "priority": "high", "basis": "why"}],
  "recommendations": ["action1", "action2"],
  "watch_assessment": {"suspicious": false, "risk_factor": "low", "activity": "", "location": "", "companions": "", "military_or_uniform": "unknown", "weapons": "unknown", "friendly_force": "unknown"},
  "confidence": 0.0-1.0,
  "analysis_factors": [{"factor": "name", "weight": 0.0-1.0, "description": "why"}]
}"""
        prompt = (
            "A watchlist item was triggered by YOLO/object detection. "
            "Assess whether the subject is suspicious, what they are doing, where they appear to be, "
            "whether they have companions, whether they look military or friendly, and whether weapons are visible. "
            f"Context: {json.dumps(context)}"
        )
        raw = self._call_api(prompt, system_prompt, image_paths=image_paths)
        return self._parse_analysis(raw, "ollama", self.model)

    def _parse_analysis(self, raw: str, provider: str, model: str) -> AnalysisResult:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                return AnalysisResult(
                    summary=parsed.get("summary", "Analysis completed"),
                    threat_level=parsed.get("threat_level", "low"),
                    threat_score=float(parsed.get("threat_score", 0.0)),
                    alerts=parsed.get("alerts", []),
                    predictions=parsed.get("predictions", []),
                    correlations=parsed.get("correlations", []),
                    priorities=parsed.get("priorities", []),
                    trends=parsed.get("trends", []),
                    detected_themes=parsed.get("detected_themes", []),
                    recommendations=parsed.get("recommendations", []),
                    watch_assessment=parsed.get("watch_assessment", {}),
                    raw_response=raw,
                    provider_used=provider,
                    model_used=model,
                    confidence=float(parsed.get("confidence", 0.5)),
                    analysis_factors=parsed.get("analysis_factors", [])
                )
        except Exception as e:
            logger.warning(f"Failed to parse AI response: {e}")
        return AnalysisResult(
            summary=raw[:500] if raw else "Analysis unavailable",
            raw_response=raw,
            provider_used=provider,
            model_used=model
        )

    def _fallback_report(self, data: Dict[str, Any]) -> str:
        return f"""INCIDENT REPORT
===============
Generated via: Ollama ({self.model})

SITUATION: {data.get('query', 'Unknown query')}
PRIORITY: {data.get('urgency_level', 'low').upper()}
SOURCE: {data.get('source_name', 'Unknown')}

Unable to generate detailed AI report. Please review raw data."""


class OpenAIBackend(BaseAIBackend):
    def __init__(self, config: AIConfig):
        self.api_key = config.openai_api_key
        self.base_url = config.openai_base_url
        self.model = config.openai_model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_status(self) -> ProviderStatus:
        configured = bool(self.api_key)
        detail = "OpenAI API key configured" if configured else "OpenAI API key is not configured"
        actions: List[str] = []
        if not configured:
            actions.append("Set OPENAI_API_KEY or save the API key in settings")
        return ProviderStatus(
            provider=AIProvider.OPENAI.value,
            available=configured,
            configured=configured,
            model=self.model,
            detail=detail,
            metadata={"base_url": self.base_url},
            actions=actions,
        )

    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            return ""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return ""

    def analyze(self, prompt: str, context: Dict[str, Any]) -> AnalysisResult:
        messages = [
            {"role": "system", "content": """You are an expert video surveillance analyst. Return JSON:
{
  "summary": "analysis summary",
  "threat_level": "low|medium|high|critical",
  "threat_score": 0.0-1.0,
  "alerts": [{"title": "alert", "priority": "high", "basis": "why"}],
  "predictions": ["prediction1"],
  "correlations": [{"source": "name", "relationship": "desc"}],
  "priorities": [{"item": "focus area", "priority": "high", "reason": "why"}],
  "trends": ["trend1"],
  "detected_themes": ["theme1"],
  "recommendations": ["action1"],
  "watch_assessment": {"suspicious": false, "risk_factor": "low", "activity": "", "location": "", "companions": "", "military_or_uniform": "unknown", "weapons": "unknown", "friendly_force": "unknown"},
  "confidence": 0.0-1.0,
  "analysis_factors": [{"factor": "name", "weight": 0.5, "description": "why"}]
}"""},
            {"role": "user", "content": f"Context: {json.dumps(context)}\n\nRequest: {prompt}"}
        ]
        raw = self._call_api(messages)
        return self._parse_analysis(raw, "openai", self.model)

    def generate_report(self, data: Dict[str, Any]) -> str:
        messages = [
            {"role": "system", "content": "Generate detailed operational incident reports."},
            {"role": "user", "content": f"Generate SITREP for: {json.dumps(data)}"}
        ]
        return self._call_api(messages) or self._fallback_report(data)

    def _parse_analysis(self, raw: str, provider: str, model: str) -> AnalysisResult:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                return AnalysisResult(
                    summary=parsed.get("summary", ""),
                    threat_level=parsed.get("threat_level", "low"),
                    threat_score=float(parsed.get("threat_score", 0.0)),
                    alerts=parsed.get("alerts", []),
                    predictions=parsed.get("predictions", []),
                    correlations=parsed.get("correlations", []),
                    priorities=parsed.get("priorities", []),
                    trends=parsed.get("trends", []),
                    detected_themes=parsed.get("detected_themes", []),
                    recommendations=parsed.get("recommendations", []),
                    watch_assessment=parsed.get("watch_assessment", {}),
                    raw_response=raw,
                    provider_used=provider,
                    model_used=model,
                    confidence=float(parsed.get("confidence", 0.5)),
                    analysis_factors=parsed.get("analysis_factors", [])
                )
        except Exception:
            pass
        return AnalysisResult(summary=raw[:500], raw_response=raw, provider_used=provider, model_used=model)

    def _fallback_report(self, data: Dict[str, Any]) -> str:
        return f"OpenAI report generation failed for: {data.get('query', 'unknown')}"


class WebGPUBackend(BaseAIBackend):
    """WebGPU backend - analysis delegated to browser client via WebSocket/API."""

    def __init__(self, config: AIConfig):
        self.enabled = config.webgpu_enabled

    def is_available(self) -> bool:
        return self.enabled

    def get_status(self) -> ProviderStatus:
        detail = (
            "WebGPU browser inference is enabled and must be verified from the client"
            if self.enabled
            else "WebGPU browser inference is disabled"
        )
        actions: List[str] = []
        if self.enabled:
            actions.append("Use the dashboard status check to verify browser GPU support")
        else:
            actions.append("Enable WebGPU in settings to use browser-local inference")
        return ProviderStatus(
            provider=AIProvider.WEBGPU.value,
            available=self.enabled,
            configured=self.enabled,
            model="LFM2.5-1.2B-Thinking-WebGPU",
            detail=detail,
            metadata={"client_side": True},
            actions=actions,
        )

    def analyze(self, prompt: str, context: Dict[str, Any]) -> AnalysisResult:
        return AnalysisResult(
            summary="WebGPU analysis runs in-browser. Use the client-side model.",
            provider_used="webgpu",
            model_used="LFM2.5-1.2B-Thinking",
            recommendations=["Run the review from the browser to validate local WebGPU support."],
            analysis_factors=[{
                "factor": "browser_inference",
                "weight": 1.0,
                "description": "Model runs locally in browser via WebGPU"
            }]
        )

    def generate_report(self, data: Dict[str, Any]) -> str:
        return "WebGPU reports generated client-side in browser."


class AIProviderService:
    """Unified service that selects best available AI provider."""

    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or self._load_config()
        self.backends: Dict[AIProvider, BaseAIBackend] = {
            AIProvider.OLLAMA: OllamaBackend(self.config),
            AIProvider.OPENAI: OpenAIBackend(self.config),
            AIProvider.WEBGPU: WebGPUBackend(self.config),
        }

    @staticmethod
    def _read_persisted_config() -> Dict[str, Any]:
        if not os.path.exists(AI_CONFIG_PATH):
            return {}
        try:
            with open(AI_CONFIG_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning(f"Failed to read persisted AI config: {exc}")
        return {}

    @staticmethod
    def _persist_config(config: AIConfig) -> None:
        payload = {
            "provider": config.provider.value,
            "ollama_base_url": config.ollama_base_url,
            "ollama_model": config.ollama_model,
            "openai_api_key": config.openai_api_key,
            "openai_base_url": config.openai_base_url,
            "openai_model": config.openai_model,
            "webgpu_enabled": config.webgpu_enabled,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        try:
            with open(AI_CONFIG_PATH, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        except Exception as exc:
            logger.warning(f"Failed to persist AI config: {exc}")

    def _load_config(self) -> AIConfig:
        persisted = self._read_persisted_config()
        return AIConfig(
            provider=AIProvider(str(persisted.get("provider") or os.getenv("AI_PROVIDER", "ollama"))),
            ollama_base_url=str(persisted.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
            ollama_model=str(persisted.get("ollama_model") or os.getenv("OLLAMA_MODEL", "llava:7b")),
            openai_api_key=str(persisted.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")),
            openai_base_url=str(persisted.get("openai_base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            openai_model=str(persisted.get("openai_model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
            webgpu_enabled=bool(
                persisted.get("webgpu_enabled")
                if "webgpu_enabled" in persisted
                else os.getenv("WEBGPU_ENABLED", "false").lower() == "true"
            ),
            temperature=float(persisted.get("temperature") or os.getenv("AI_TEMPERATURE", "0.3")),
            max_tokens=int(persisted.get("max_tokens") or os.getenv("AI_MAX_TOKENS", "2048"))
        )

    def get_available_providers(self) -> List[Dict[str, Any]]:
        providers: List[Dict[str, Any]] = []
        for provider in AIProvider:
            status = self.backends[provider].get_status().to_dict()
            status.setdefault("model", self._get_model_name(provider))
            providers.append(status)
        return providers

    def get_provider_statuses(self) -> List[Dict[str, Any]]:
        return self.get_available_providers()

    def get_ollama_models(self) -> List[Dict[str, Any]]:
        backend = self.backends.get(AIProvider.OLLAMA)
        if isinstance(backend, OllamaBackend):
            return backend.discover_models()
        return []

    def _get_model_name(self, provider: AIProvider) -> str:
        if provider == AIProvider.OLLAMA:
            return self.config.ollama_model
        elif provider == AIProvider.OPENAI:
            return self.config.openai_model
        return "LFM2.5-1.2B-Thinking-WebGPU"

    def _get_best_backend(self) -> BaseAIBackend:
        preferred = self.backends.get(self.config.provider)
        if preferred and preferred.is_available():
            return preferred
        for p in [AIProvider.OPENAI, AIProvider.OLLAMA]:
            if self.backends[p].is_available():
                return self.backends[p]
        return self.backends[AIProvider.OLLAMA]

    def analyze(self, prompt: str, context: Dict[str, Any]) -> AnalysisResult:
        backend = self._get_best_backend()
        return backend.analyze(prompt, context)

    def generate_report(self, data: Dict[str, Any]) -> str:
        backend = self._get_best_backend()
        return backend.generate_report(data)

    def analyze_threat(self, events: List[Dict[str, Any]], query: str = "") -> AnalysisResult:
        context = {
            "events": events[:10],
            "query": query,
            "event_count": len(events),
            "analysis_type": "threat_assessment"
        }
        prompt = f"""Analyze these surveillance events for threat level:
- Identify patterns indicating escalation
- Assess immediate risk to safety
- Consider temporal correlations
- Evaluate object detection confidence"""
        return self.analyze(prompt, context)

    def predict_risk(self, predictions: List[Dict[str, Any]], historical: List[Dict[str, Any]] = None) -> AnalysisResult:
        context = {
            "current_predictions": predictions,
            "historical_events": (historical or [])[:20],
            "analysis_type": "risk_prediction"
        }
        prompt = """Based on current risk predictions and historical patterns:
- Project 30-minute risk trajectory
- Identify sources likely to escalate
- Recommend preemptive actions
- Assess prediction confidence"""
        return self.analyze(prompt, context)

    def correlate_sources(self, events: List[Dict[str, Any]]) -> AnalysisResult:
        context = {
            "events": events,
            "analysis_type": "source_correlation"
        }
        prompt = """Analyze cross-source correlations:
- Identify events occurring within same time window
- Find object/entity matches across cameras
- Detect movement patterns between sources
- Assess correlation confidence"""
        return self.analyze(prompt, context)

    def review_mission_context(self, context: Dict[str, Any]) -> AnalysisResult:
        review_context = {
            "clips": context.get("clips", [])[:10],
            "assets": context.get("assets", [])[:10],
            "events": context.get("events", [])[:20],
            "predictions": context.get("predictions", [])[:10],
            "alerts": context.get("alerts", [])[:10],
            "live_streams": context.get("live_streams", [])[:10],
            "query": context.get("query", ""),
            "analysis_type": "mission_vision_review",
        }
        backend = self._get_best_backend()
        if isinstance(backend, OllamaBackend):
            return backend.review_mission_context(review_context)
        prompt = """Review clips, uploaded assets, documents, and live detections.
- Flag maritime and emergency indicators
- Rank immediate alerts
- Summarize threats, predictions, correlations, priorities, and trends
- Return structured JSON"""
        return self.analyze(prompt, review_context)

    def review_watch_target(self, context: Dict[str, Any]) -> AnalysisResult:
        backend = self._get_best_backend()
        image_paths = []
        thumbnail_path = context.get("thumbnail_path")
        if thumbnail_path:
            image_paths.append(thumbnail_path)
        if isinstance(backend, OllamaBackend):
            return backend.review_watch_target(context, image_paths=image_paths)
        prompt = """Review a watchlist-triggered detection.
- Assess suspiciousness, actions, location, companions, military/friendly status, and visible weapons
- Return structured JSON"""
        return self.analyze(prompt, context)

    def generate_overview(self, stats: Dict[str, Any], alerts: List[Dict[str, Any]], predictions: List[Dict[str, Any]]) -> str:
        data = {
            "system_stats": stats,
            "active_alerts": alerts[:5],
            "risk_predictions": predictions[:5],
            "report_type": "operational_overview"
        }
        return self.generate_report(data)


_ai_service: Optional[AIProviderService] = None


def get_ai_service() -> AIProviderService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIProviderService()
    return _ai_service


def update_ai_config(config: AIConfig) -> AIProviderService:
    global _ai_service
    AIProviderService._persist_config(config)
    _ai_service = AIProviderService(config)
    return _ai_service
