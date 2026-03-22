"""
OPORD Parser - Advanced NLP parsing for Operation Orders using Hugging Face Transformers.

Supports multiple backends:
- Local Hugging Face models (BERT, LayoutLM, etc.)
- Hugging Face Inference API (with optional API key)
- Ollama local LLM fallback
- OpenAI API fallback

Extracts structured intelligence:
- Watch phrases and targets
- Named entities (persons, locations, organizations)
- Topics and keywords
- Temporal information
- Priority/urgency indicators
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default HF Inference API endpoint
HF_API_BASE = "https://api-inference.huggingface.co"

# Default models for different parsing tasks
DEFAULT_MODELS = {
    "ner": "dslim/bert-base-NER",  # Named Entity Recognition
    "classification": "facebook/bart-large-mnli",  # Zero-shot classification
    "summarization": "facebook/bart-large-cnn",  # Text summarization
    "keywords": "yanekyuk/bert-keyword-extractor",  # Keyword extraction
    "layout": "microsoft/layoutlm-base-uncased",  # Layout understanding (for PDFs)
}

# OPORD-specific watch phrases and threat indicators
WATCH_PHRASES = {
    "critical": [
        "suspicious person", "armed person", "active shooter", "hostage",
        "explosive", "bomb", "terrorist", "threat", "weapon", "gunfire",
        "casualty", "casualties", "mass casualty", "chemical", "biological",
        "radiological", "nuclear", "cbrn", "imminent threat", "clear and present danger"
    ],
    "high": [
        "suspicious vehicle", "unauthorized entry", "perimeter breach",
        "surveillance", "reconnaissance", "loitering", "abandoned package",
        "suspicious package", "protest", "demonstration", "civil disturbance",
        "medical emergency", "fire", "hazmat"
    ],
    "medium": [
        "suspicious activity", "unusual behavior", "after hours",
        "unattended bag", "vehicle parked", "door propped", "tailgating"
    ]
}

# Entity types relevant to security operations
SECURITY_ENTITY_TYPES = {
    "PER": "person",  # Person names
    "ORG": "organization",  # Organizations
    "LOC": "location",  # Locations
    "FAC": "facility",  # Facilities
    "GPE": "geo_political_entity",  # Countries, cities, states
    "VEH": "vehicle",  # Vehicles
    "WEA": "weapon",  # Weapons
}


@dataclass
class ParsedOpord:
    """Structured representation of a parsed OPORD document."""
    
    # Document metadata
    source_filename: str = ""
    mime_type: str = ""
    parsed_at: int = 0
    
    # Extracted intelligence
    watch_phrase: str = ""
    watch_labels: List[str] = field(default_factory=list)
    priority: str = "medium"
    
    # Named entities
    entities: List[Dict[str, Any]] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    organizations: List[str] = field(default_factory=list)
    
    # Topics and keywords
    topics: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # Temporal information
    temporal_refs: List[str] = field(default_factory=list)
    
    # Full text
    raw_text: str = ""
    excerpt: str = ""
    
    # Processing metadata
    parser_used: str = ""
    confidence: float = 0.0
    
    def to_alert_payload(self) -> Dict[str, Any]:
        """Convert to watch alert payload format."""
        return {
            "watch_phrase": self.watch_phrase,
            "watch_labels": self.watch_labels,
            "watch_label": self.watch_labels[0] if self.watch_labels else "person",
            "priority": self.priority,
            "topics": self.topics,
            "entities": [e.get("text", "") for e in self.entities],
            "keywords": self.keywords,
            "opord_excerpt": self.excerpt,
            "persons_of_interest": self.persons,
            "locations_of_interest": self.locations,
        }


class OpordParser:
    """
    Advanced OPORD parser using Hugging Face Transformers.
    
    Supports:
    - Local models (free, no API key)
    - Hugging Face Inference API (optional HF_API_KEY)
    - Ollama/OpenAI fallbacks
    """
    
    def __init__(
        self,
        hf_api_key: Optional[str] = None,
        use_local_models: bool = True,
        ollama_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.hf_api_key = hf_api_key or os.getenv("HF_API_KEY") or os.getenv("HUGGINGFACE_API_KEY")
        self.use_local_models = use_local_models
        self.ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        # Local model cache
        self._local_pipelines = {}
        self._local_models_available = {}
        
        # Check which backends are available
        self._check_backends()
    
    def _check_backends(self):
        """Check which parsing backends are available."""
        self.backends = {
            "hf_local": False,
            "hf_api": bool(self.hf_api_key),
            "ollama": False,
            "openai": bool(self.openai_api_key),
        }
        
        # Check local HF transformers
        if self.use_local_models:
            try:
                import transformers
                self.backends["hf_local"] = True
                logger.info("Hugging Face Transformers available for local inference")
            except ImportError:
                logger.warning("transformers not installed. Local HF models unavailable. "
                             "Install with: pip install transformers torch")
        
        # Check Ollama
        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                self.backends["ollama"] = True
                logger.info("Ollama available for OPORD parsing")
        except Exception:
            logger.warning("Ollama not available for OPORD parsing")
    
    def _get_local_pipeline(self, task: str, model_name: Optional[str] = None):
        """Get or create a local Hugging Face pipeline."""
        if not self.backends["hf_local"]:
            return None
        
        cache_key = f"{task}:{model_name or DEFAULT_MODELS.get(task, 'default')}"
        
        if cache_key not in self._local_pipelines:
            try:
                from transformers import pipeline
                
                model = model_name or DEFAULT_MODELS.get(task)
                if not model:
                    return None
                
                logger.info(f"Loading local HF model: {model} for task: {task}")
                
                # Use GPU if available
                device = -1  # CPU default
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = 0
                except ImportError:
                    pass
                
                self._local_pipelines[cache_key] = pipeline(
                    task,
                    model=model,
                    device=device,
                    truncation=True,
                )
                self._local_models_available[task] = True
                
            except Exception as e:
                logger.warning(f"Failed to load local model {model_name}: {e}")
                self._local_models_available[task] = False
                return None
        
        return self._local_pipelines.get(cache_key)
    
    def _call_hf_api(self, model: str, inputs: Any, parameters: Optional[Dict] = None) -> Any:
        """Call Hugging Face Inference API."""
        if not self.hf_api_key:
            return None
        
        headers = {"Authorization": f"Bearer {self.hf_api_key}"}
        payload = {"inputs": inputs}
        if parameters:
            payload["parameters"] = parameters
        
        try:
            response = requests.post(
                f"{HF_API_BASE}/models/{model}",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"HF API call failed for {model}: {e}")
            return None
    
    def _extract_named_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract named entities using NER model."""
        # Truncate text for NER
        text_chunk = text[:2000]
        
        # Try local model first
        if self.backends["hf_local"]:
            pipeline = self._get_local_pipeline("ner", DEFAULT_MODELS["ner"])
            if pipeline:
                try:
                    results = pipeline(text_chunk)
                    # Aggregate subword tokens
                    entities = []
                    current_entity = None
                    
                    for item in results:
                        word = item.get("word", "")
                        entity = item.get("entity", "")
                        score = item.get("score", 0)
                        
                        # Handle B- and I- prefixes
                        if entity.startswith("B-"):
                            if current_entity:
                                entities.append(current_entity)
                            current_entity = {
                                "text": word.replace("##", ""),
                                "type": entity[2:],
                                "score": score,
                                "start": item.get("start", 0),
                                "end": item.get("end", 0),
                            }
                        elif entity.startswith("I-") and current_entity:
                            current_entity["text"] += word.replace("##", "").replace("_", " ")
                            current_entity["end"] = item.get("end", 0)
                            current_entity["score"] = max(current_entity["score"], score)
                        else:
                            if current_entity:
                                entities.append(current_entity)
                                current_entity = None
                    
                    if current_entity:
                        entities.append(current_entity)
                    
                    return entities
                except Exception as e:
                    logger.warning(f"Local NER failed: {e}")
        
        # Try HF API
        if self.backends["hf_api"]:
            result = self._call_hf_api(DEFAULT_MODELS["ner"], text_chunk)
            if result and isinstance(result, list):
                return [{"text": r.get("word", ""), "type": r.get("entity", ""), 
                        "score": r.get("score", 0)} for r in result]
        
        return []
    
    def _classify_text(self, text: str, candidate_labels: List[str]) -> Dict[str, float]:
        """Zero-shot classification of text."""
        text_chunk = text[:1500]
        
        # Try local model
        if self.backends["hf_local"]:
            pipeline = self._get_local_pipeline("zero-shot-classification", DEFAULT_MODELS["classification"])
            if pipeline:
                try:
                    result = pipeline(text_chunk, candidate_labels)
                    return dict(zip(result.get("labels", []), result.get("scores", [])))
                except Exception as e:
                    logger.warning(f"Local classification failed: {e}")
        
        # Try HF API
        if self.backends["hf_api"]:
            result = self._call_hf_api(
                DEFAULT_MODELS["classification"],
                text_chunk,
                {"candidate_labels": candidate_labels}
            )
            if result and isinstance(result, dict):
                return dict(zip(result.get("labels", []), result.get("scores", [])))
        
        return {}
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        text_chunk = text[:2000]
        
        # Try local model
        if self.backends["hf_local"]:
            pipeline = self._get_local_pipeline("token-classification", DEFAULT_MODELS["keywords"])
            if pipeline:
                try:
                    results = pipeline(text_chunk)
                    keywords = list(set([r.get("word", "").strip() for r in results 
                                       if r.get("score", 0) > 0.5]))
                    return keywords[:15]
                except Exception as e:
                    logger.warning(f"Local keyword extraction failed: {e}")
        
        # Fallback: simple keyword extraction
        return self._extract_keywords_fallback(text)
    
    def _extract_keywords_fallback(self, text: str) -> List[str]:
        """Fallback keyword extraction using frequency analysis."""
        # Remove common stop words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "dare", "ought", "used", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into",
            "through", "during", "before", "after", "above", "below",
            "between", "under", "and", "but", "or", "yet", "so", "if",
            "because", "although", "though", "while", "where", "when",
            "that", "which", "who", "whom", "whose", "what", "this",
            "these", "those", "i", "you", "he", "she", "it", "we", "they"
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        word_freq = {}
        
        for word in words:
            if word not in stop_words and not word.isdigit():
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Get top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:15]]
    
    def _summarize_text(self, text: str, max_length: int = 200) -> str:
        """Summarize text using summarization model."""
        if len(text) < max_length * 2:
            return text[:max_length]
        
        # Try local model
        if self.backends["hf_local"]:
            pipeline = self._get_local_pipeline("summarization", DEFAULT_MODELS["summarization"])
            if pipeline:
                try:
                    result = pipeline(text[:3000], max_length=max_length, min_length=50)
                    if result and len(result) > 0:
                        return result[0].get("summary_text", text[:max_length])
                except Exception as e:
                    logger.warning(f"Local summarization failed: {e}")
        
        # Try HF API
        if self.backends["hf_api"]:
            result = self._call_hf_api(
                DEFAULT_MODELS["summarization"],
                text[:3000],
                {"max_length": max_length, "min_length": 50}
            )
            if result and isinstance(result, list) and len(result) > 0:
                return result[0].get("summary_text", text[:max_length])
        
        # Fallback: first sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        summary = ""
        for sent in sentences:
            if len(summary) + len(sent) < max_length:
                summary += sent + " "
            else:
                break
        return summary.strip() or text[:max_length]
    
    def _detect_watch_phrases(self, text: str) -> Tuple[str, str, List[str]]:
        """
        Detect watch phrases and determine priority.
        Returns: (watch_phrase, priority, watch_labels)
        """
        text_lower = text.lower()
        
        # Check for critical phrases
        for phrase in WATCH_PHRASES["critical"]:
            if phrase in text_lower:
                return phrase, "critical", ["person"]
        
        # Check for high priority phrases
        for phrase in WATCH_PHRASES["high"]:
            if phrase in text_lower:
                return phrase, "high", ["car", "truck", "bus", "motorcycle"] if "vehicle" in phrase else ["person"]
        
        # Check for medium priority phrases
        for phrase in WATCH_PHRASES["medium"]:
            if phrase in text_lower:
                return phrase, "medium", ["person"]
        
        # Default: try to infer from content
        if "boat" in text_lower or "vessel" in text_lower or "maritime" in text_lower:
            return "boat", "high", ["boat"]
        
        if "person" in text_lower or "individual" in text_lower or "suspect" in text_lower:
            return "suspicious person", "high", ["person"]
        
        if "vehicle" in text_lower or "car" in text_lower or "truck" in text_lower:
            return "suspicious vehicle", "medium", ["car", "truck"]
        
        return "suspicious activity", "medium", ["person"]
    
    def _extract_temporal_refs(self, text: str) -> List[str]:
        """Extract temporal references from text."""
        # Pattern for time references
        time_patterns = [
            r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s+\d{4})?\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b(?:today|tomorrow|yesterday|tonight|this morning|this afternoon|this evening)\b',
            r'\b(?:\d+\s*(?:hours?|hrs?|minutes?|mins?|days?|weeks?))\b',
        ]
        
        temporal_refs = []
        text_lower = text.lower()
        
        for pattern in time_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            temporal_refs.extend(matches)
        
        return list(set(temporal_refs))[:10]
    
    def _call_ollama_for_parsing(self, text: str) -> Dict[str, Any]:
        """Use Ollama as fallback for OPORD parsing."""
        if not self.backends["ollama"]:
            return {}
        
        system_prompt = """You are an intelligence analyst parsing an OPORD (Operation Order).
Extract structured information and return ONLY valid JSON:
{
  "watch_phrase": "primary watch target (e.g., 'suspicious person', 'armed individual')",
  "priority": "critical|high|medium|low",
  "watch_labels": ["person", "car", etc],
  "topics": ["topic1", "topic2"],
  "keywords": ["keyword1", "keyword2"],
  "entities": {"persons": [], "locations": [], "organizations": []},
  "temporal_refs": [],
  "summary": "brief summary"
}"""
        
        prompt = f"Parse this OPORD document:\n\n{text[:4000]}"
        
        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            raw_text = result.get("response", "")
            
            # Extract JSON
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw_text[start:end])
        except Exception as e:
            logger.warning(f"Ollama parsing failed: {e}")
        
        return {}
    
    def parse(self, text: str, source_filename: str = "", mime_type: str = "") -> ParsedOpord:
        """
        Parse an OPORD document and extract structured intelligence.
        
        Args:
            text: Raw text content of the document
            source_filename: Original filename
            mime_type: MIME type of the document
            
        Returns:
            ParsedOpord with extracted intelligence
        """
        parsed = ParsedOpord(
            source_filename=source_filename,
            mime_type=mime_type,
            parsed_at=int(time.time()),
            raw_text=text,
            excerpt=" ".join(text.split())[:1200]
        )
        
        # Track which parser was used
        parsers_used = []
        
        # Step 1: Detect watch phrases and priority
        watch_phrase, priority, watch_labels = self._detect_watch_phrases(text)
        parsed.watch_phrase = watch_phrase
        parsed.priority = priority
        parsed.watch_labels = watch_labels
        parsers_used.append("rule_based")
        
        # Step 2: Extract named entities
        try:
            entities = self._extract_named_entities(text)
            parsed.entities = entities
            
            # Categorize entities
            for entity in entities:
                entity_type = entity.get("type", "").upper()
                entity_text = entity.get("text", "")
                
                if entity_type in ("PER", "PERSON"):
                    parsed.persons.append(entity_text)
                elif entity_type in ("LOC", "LOCATION", "GPE", "FAC"):
                    parsed.locations.append(entity_text)
                elif entity_type in ("ORG", "ORGANIZATION"):
                    parsed.organizations.append(entity_text)
            
            if entities:
                parsers_used.append("hf_ner")
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")
        
        # Step 3: Extract keywords
        try:
            keywords = self._extract_keywords(text)
            parsed.keywords = keywords
            if keywords:
                parsers_used.append("hf_keywords")
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
        
        # Step 4: Classify for topics
        try:
            topic_labels = [
                "security", "surveillance", "perimeter", "access control",
                "maritime", "aviation", "transportation", "crowd control",
                "emergency response", "medical", "fire", "hazmat",
                "vip protection", "event security", "border control"
            ]
            topic_scores = self._classify_text(text, topic_labels)
            parsed.topics = [label for label, score in topic_scores.items() if score > 0.5]
            if parsed.topics:
                parsers_used.append("hf_classification")
        except Exception as e:
            logger.warning(f"Topic classification failed: {e}")
        
        # Step 5: Extract temporal references
        parsed.temporal_refs = self._extract_temporal_refs(text)
        
        # Step 6: Try Ollama for enhanced parsing if available
        if self.backends["ollama"]:
            try:
                ollama_result = self._call_ollama_for_parsing(text)
                if ollama_result:
                    # Merge Ollama results (don't override watch_phrase if already found)
                    if not parsed.watch_phrase and ollama_result.get("watch_phrase"):
                        parsed.watch_phrase = ollama_result["watch_phrase"]
                    if ollama_result.get("priority"):
                        parsed.priority = ollama_result["priority"]
                    if ollama_result.get("watch_labels"):
                        parsed.watch_labels = ollama_result["watch_labels"]
                    if ollama_result.get("topics"):
                        parsed.topics = list(set(parsed.topics + ollama_result["topics"]))
                    if ollama_result.get("keywords"):
                        parsed.keywords = list(set(parsed.keywords + ollama_result["keywords"]))
                    if ollama_result.get("entities", {}).get("persons"):
                        parsed.persons = list(set(parsed.persons + ollama_result["entities"]["persons"]))
                    if ollama_result.get("entities", {}).get("locations"):
                        parsed.locations = list(set(parsed.locations + ollama_result["entities"]["locations"]))
                    parsers_used.append("ollama")
            except Exception as e:
                logger.warning(f"Ollama enhancement failed: {e}")
        
        # Set parser metadata
        parsed.parser_used = "+".join(parsers_used)
        parsed.confidence = 0.7 if "hf_ner" in parsers_used else 0.5
        
        return parsed
    
    def get_status(self) -> Dict[str, Any]:
        """Get parser status and available backends."""
        return {
            "backends": self.backends,
            "local_models_loaded": list(self._local_pipelines.keys()),
            "default_models": DEFAULT_MODELS,
            "api_key_configured": bool(self.hf_api_key),
        }


# Singleton instance
_parser_instance: Optional[OpordParser] = None


def get_opord_parser(
    hf_api_key: Optional[str] = None,
    use_local_models: bool = True
) -> OpordParser:
    """Get or create the singleton OPORD parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = OpordParser(
            hf_api_key=hf_api_key,
            use_local_models=use_local_models
        )
    return _parser_instance


def parse_opord_document(
    text: str,
    source_filename: str = "",
    mime_type: str = ""
) -> ParsedOpord:
    """
    Convenience function to parse an OPORD document.
    
    Args:
        text: Raw text content
        source_filename: Original filename
        mime_type: MIME type
        
    Returns:
        ParsedOpord with extracted intelligence
    """
    parser = get_opord_parser()
    return parser.parse(text, source_filename, mime_type)
