"""
YOLO Object Detection for Video Frames
Extracts object labels to enhance semantic search with detected objects.
"""
import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    """Represents a detected object in a frame."""
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2


class ObjectDetector:
    """
    YOLO-based object detector for extracting objects from video frames.
    Uses YOLOv8 for fast and accurate object detection.
    """
    
    # COCO dataset classes that YOLOv8 can detect
    COCO_CLASSES = [
        'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
        'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
        'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
        'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
        'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
        'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
        'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
        'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
        'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
        'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
    ]
    
    def __init__(self, model_size: str = 'n', confidence_threshold: float = 0.3):
        """
        Initialize YOLO object detector.
        
        Args:
            model_size: YOLOv8 model size ('n'=nano, 's'=small, 'm'=medium, 'l'=large)
            confidence_threshold: Minimum confidence for object detection
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.model_size = model_size
        
        try:
            # Try to import ultralytics
            from ultralytics import YOLO
            
            # Download/load model
            model_name = f'yolov8{model_size}.pt'
            self.model = YOLO(model_name)
            logger.info(f"Loaded YOLOv8 model: {model_name}")
            
        except ImportError:
            logger.warning("ultralytics not installed. YOLO detection disabled. "
                          "Install with: pip install ultralytics")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
    
    def detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """
        Detect objects in a frame.
        
        Args:
            frame: RGB frame array
            
        Returns:
            List of detected objects
        """
        if self.model is None:
            return []
        
        try:
            # YOLO expects BGR format
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Run inference
            results = self.model(frame_bgr, verbose=False)
            
            # Parse results
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                    
                for box in boxes:
                    confidence = float(box.conf[0])
                    if confidence < self.confidence_threshold:
                        continue
                    
                    # Get class label
                    class_id = int(box.cls[0])
                    label = self.COCO_CLASSES[class_id] if class_id < len(self.COCO_CLASSES) else f'class_{class_id}'
                    
                    # Get bounding box
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    detections.append(DetectedObject(
                        label=label,
                        confidence=confidence,
                        bbox=(x1, y1, x2, y2)
                    ))
            
            return detections
            
        except Exception as e:
            logger.error(f"Error in object detection: {e}")
            return []
    
    def detect_batch(self, frames: List[np.ndarray]) -> Dict[str, float]:
        """
        Detect objects in multiple frames and aggregate results.
        
        Args:
            frames: List of RGB frame arrays
            
        Returns:
            Dictionary mapping object labels to their max confidence scores
        """
        object_scores = {}
        
        for frame in frames:
            detections = self.detect(frame)
            for det in detections:
                # Keep the highest confidence for each object type
                if det.label not in object_scores or det.confidence > object_scores[det.label]:
                    object_scores[det.label] = det.confidence
        
        return object_scores
    
    def get_object_labels(self, frames: List[np.ndarray], top_k: int = 10) -> List[str]:
        """
        Get top object labels from frames.
        
        Args:
            frames: List of RGB frame arrays
            top_k: Number of top objects to return
            
        Returns:
            List of object label strings
        """
        object_scores = self.detect_batch(frames)
        
        # Sort by confidence and get top k
        sorted_objects = sorted(object_scores.items(), key=lambda x: x[1], reverse=True)
        return [label for label, _ in sorted_objects[:top_k]]


# Singleton instance
_object_detector = None


def get_object_detector() -> ObjectDetector:
    """Get or create the singleton object detector instance."""
    global _object_detector
    if _object_detector is None:
        _object_detector = ObjectDetector()
    return _object_detector
