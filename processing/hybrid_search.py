"""
Hybrid Search Module - Combines CLIP semantic search with YOLO object detection
for improved video search accuracy.
"""
import os
import numpy as np
from typing import List, Dict, Any
from PIL import Image
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy import YOLO to avoid loading on startup
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("YOLO not available. Install with: pip install ultralytics")


class HybridScorer:
    """
    Combines CLIP semantic similarity with YOLO object detection for improved
    video search accuracy.
    """
    
    def __init__(self, model_size: str = 'n'):
        """
        Initialize the hybrid scorer.
        
        Args:
            model_size: YOLOv8 model size ('n'=nano, 's'=small, 'm'=medium, 'l'=large)
        """
        self.yolo = None
        self.model_size = model_size
        self._yolo_cache = {}  # Cache for frame-level detections
        
    def _load_yolo(self):
        """Lazy load YOLO model."""
        if self.yolo is None and YOLO_AVAILABLE:
            logger.info(f"Loading YOLOv8{self.model_size} model...")
            try:
                self.yolo = YOLO(f'yolov8{self.model_size}.pt')
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")
                self.yolo = None
    
    def detect_objects(self, frame_path: str) -> List[Dict[str, Any]]:
        """
        Detect objects in a frame using YOLO.
        
        Args:
            frame_path: Path to the frame image
            
        Returns:
            List of detected objects with labels and confidence scores
        """
        # Check cache
        if frame_path in self._yolo_cache:
            return self._yolo_cache[frame_path]
        
        self._load_yolo()
        
        if self.yolo is None or not os.path.exists(frame_path):
            return []
        
        try:
            results = self.yolo(frame_path, verbose=False)
            objects = []
            
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        cls_id = int(box.cls.item())
                        conf = float(box.conf.item())
                        label = result.names[cls_id]
                        objects.append({
                            'label': label,
                            'confidence': conf,
                            'class_id': cls_id
                        })
            
            # Cache results
            self._yolo_cache[frame_path] = objects
            
            # Limit cache size
            if len(self._yolo_cache) > 1000:
                self._yolo_cache.pop(next(iter(self._yolo_cache)))
            
            return objects
            
        except Exception as e:
            logger.error(f"YOLO detection failed for {frame_path}: {e}")
            return []
    
    def compute_object_match_score(self, query: str, detected_objects: List[Dict[str, Any]]) -> float:
        """
        Compute how well the detected objects match the query.
        
        Args:
            query: Search query string
            detected_objects: List of detected objects
            
        Returns:
            Match score between 0 and 1
        """
        if not detected_objects:
            return 0.0
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Common object categories and their synonyms
        object_categories = {
            'person': ['person', 'people', 'human', 'man', 'woman', 'child', 'individual', 'pedestrian'],
            'car': ['car', 'vehicle', 'automobile', 'sedan', 'suv', 'truck'],
            'truck': ['truck', 'lorry', 'pickup', 'van', 'vehicle'],
            'bus': ['bus', 'coach', 'vehicle'],
            'motorcycle': ['motorcycle', 'motorbike', 'bike', 'scooter'],
            'bicycle': ['bicycle', 'bike', 'cycle'],
            'dog': ['dog', 'puppy', 'canine', 'pet'],
            'cat': ['cat', 'kitten', 'feline', 'pet'],
            'bird': ['bird', 'avian'],
            'backpack': ['backpack', 'bag', 'rucksack'],
            'umbrella': ['umbrella', 'parasol'],
            'handbag': ['handbag', 'purse', 'bag'],
            'suitcase': ['suitcase', 'luggage', 'bag'],
            'chair': ['chair', 'seat', 'furniture'],
            'couch': ['couch', 'sofa', 'furniture'],
            'tv': ['tv', 'television', 'monitor', 'screen'],
            'laptop': ['laptop', 'computer', 'notebook'],
            'cell phone': ['cell phone', 'mobile', 'phone', 'smartphone'],
            'book': ['book', 'novel', 'textbook'],
            'clock': ['clock', 'watch', 'timepiece'],
        }
        
        score = 0.0
        max_score = 0.0
        
        for obj in detected_objects:
            label = obj['label'].lower()
            confidence = obj['confidence']
            
            # Direct match
            if label in query_lower:
                score += confidence * 1.0  # Full weight for exact match
            
            # Category match (e.g., "person" matches "man")
            for category, synonyms in object_categories.items():
                if label in synonyms or category == label:
                    for synonym in synonyms:
                        if synonym in query_lower:
                            score += confidence * 0.8  # Slightly less for category match
                            break
            
            # Word overlap
            label_words = set(label.split())
            overlap = query_words & label_words
            if overlap:
                score += confidence * 0.5 * (len(overlap) / len(label_words))
            
            max_score += confidence
        
        # Normalize
        if max_score > 0:
            return min(score / max_score, 1.0)
        return 0.0
    
    def compute_hybrid_score(
        self, 
        query: str, 
        clip_score: float, 
        detected_objects: List[Dict[str, Any]],
        frame_count: int = 1
    ) -> float:
        """
        Compute combined CLIP + YOLO score.
        
        Args:
            query: Search query
            clip_score: Original CLIP similarity score (0-1)
            detected_objects: Objects detected in the video clip
            frame_count: Number of frames in the clip
            
        Returns:
            Combined hybrid score (0-1)
        """
        # CLIP semantic score (0-1)
        semantic_score = clip_score
        
        # Object label match score
        object_score = self.compute_object_match_score(query, detected_objects)
        
        # Exact match boost
        exact_match_boost = 1.0
        query_lower = query.lower()
        for obj in detected_objects:
            if obj['label'].lower() in query_lower:
                exact_match_boost = 1.5  # 50% boost for exact matches
                break
        
        # Combined score with weighting
        # - CLIP provides semantic understanding
        # - YOLO provides concrete object verification
        combined = (0.6 * semantic_score + 0.4 * object_score) * exact_match_boost
        
        return min(combined, 1.0)  # Cap at 1.0


def enhance_search_results(
    query: str,
    results: List[Dict[str, Any]],
    hybrid_scorer: HybridScorer,
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Enhance search results using hybrid CLIP + YOLO scoring.
    
    Args:
        query: Original search query
        results: Initial CLIP search results
        hybrid_scorer: Initialized HybridScorer instance
        top_k: Number of top results to return
        
    Returns:
        Re-ranked results with hybrid scores
    """
    logger.info(f"Enhancing {len(results)} results with hybrid scoring")
    
    enhanced_results = []
    
    for result in results:
        clip_score = result.get('score', 0.0)
        
        # Try to find a representative frame for YOLO detection
        # Use thumbnail if available
        thumbnail_path = result.get('thumbnail_path')
        
        detected_objects = []
        if thumbnail_path and os.path.exists(thumbnail_path):
            detected_objects = hybrid_scorer.detect_objects(thumbnail_path)
        
        # Compute hybrid score
        hybrid_score = hybrid_scorer.compute_hybrid_score(
            query=query,
            clip_score=clip_score,
            detected_objects=detected_objects,
            frame_count=result.get('frame_count', 1)
        )
        
        # Update result with new score
        enhanced_result = result.copy()
        enhanced_result['score'] = hybrid_score
        enhanced_result['clip_score'] = clip_score  # Keep original
        enhanced_result['detected_objects'] = detected_objects
        
        enhanced_results.append(enhanced_result)
    
    # Sort by hybrid score (descending)
    enhanced_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Return top_k
    return enhanced_results[:top_k]
