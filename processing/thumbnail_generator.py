"""
Thumbnail Generator for Video Clips
Generates visual thumbnails from video chunks for display in the dashboard.
"""
import cv2
import numpy as np
import os
import logging
from typing import Optional, Tuple
from PIL import Image
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """
    Generates thumbnails from video files or frame data.
    Creates multiple sizes for different use cases.
    """
    
    # Thumbnail sizes
    SIZES = {
        'small': (160, 90),      # For lists
        'medium': (320, 180),    # For grid (default)
        'large': (640, 360),     # For detail view
    }
    
    def __init__(self, output_dir: str = "/tmp/video_thumbnails"):
        """
        Initialize thumbnail generator.
        
        Args:
            output_dir: Directory to save thumbnails
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_from_video(
        self, 
        video_path: str, 
        source_name: str,
        start_offset: int = 0,
        time_position: float = 0.5  # 0.0 = start, 0.5 = middle, 1.0 = end
    ) -> dict:
        """
        Generate thumbnails from a video file.
        
        Args:
            video_path: Path to video file
            source_name: Source identifier for naming
            start_offset: Start time offset in seconds
            time_position: Position in video to extract frame (0-1)
            
        Returns:
            Dictionary mapping size names to thumbnail paths
        """
        # Handle placeholder paths (RTSP streams that failed to save)
        if video_path.startswith("placeholder://"):
            return self._generate_placeholder_thumbnails(source_name, start_offset)
        
        # Check if video exists
        if not os.path.exists(video_path):
            logger.warning(f"Video not found for thumbnail: {video_path}")
            return self._generate_placeholder_thumbnails(source_name, start_offset)
        
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Cannot open video: {video_path}")
                return self._generate_placeholder_thumbnails(source_name, start_offset)
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            if total_frames == 0 or fps == 0:
                logger.warning(f"Invalid video properties: {video_path}")
                cap.release()
                return self._generate_placeholder_thumbnails(source_name, start_offset)
            
            # Calculate frame position
            target_frame = int(total_frames * time_position)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            # Read frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                logger.warning(f"Could not read frame from: {video_path}")
                return self._generate_placeholder_thumbnails(source_name, start_offset)
            
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Generate thumbnails
            return self._save_thumbnails(frame_rgb, source_name, start_offset)
            
        except Exception as e:
            logger.error(f"Error generating thumbnail for {video_path}: {e}")
            return self._generate_placeholder_thumbnails(source_name, start_offset)
    
    def generate_from_frame(
        self, 
        frame: np.ndarray, 
        source_name: str,
        start_offset: int = 0
    ) -> dict:
        """
        Generate thumbnails from a frame array.
        
        Args:
            frame: RGB frame array
            source_name: Source identifier for naming
            start_offset: Start time offset in seconds
            
        Returns:
            Dictionary mapping size names to thumbnail paths
        """
        try:
            return self._save_thumbnails(frame, source_name, start_offset)
        except Exception as e:
            logger.error(f"Error generating thumbnail from frame: {e}")
            return self._generate_placeholder_thumbnails(source_name, start_offset)
    
    def _save_thumbnails(
        self, 
        frame: np.ndarray, 
        source_name: str,
        start_offset: int
    ) -> dict:
        """
        Save frame as thumbnails in multiple sizes.
        
        Args:
            frame: RGB frame array
            source_name: Source identifier
            start_offset: Start time offset
            
        Returns:
            Dictionary mapping size names to thumbnail paths
        """
        # Create source directory
        source_dir = os.path.join(self.output_dir, source_name)
        os.makedirs(source_dir, exist_ok=True)
        
        # Generate unique filename base
        import time
        timestamp = int(time.time())
        base_name = f"{source_name}_{start_offset}_{timestamp}"
        
        thumbnail_paths = {}
        
        for size_name, (width, height) in self.SIZES.items():
            # Resize frame
            resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LANCZOS4)
            
            # Convert RGB to BGR for OpenCV
            resized_bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
            
            # Save thumbnail
            thumb_path = os.path.join(source_dir, f"{base_name}_{size_name}.jpg")
            cv2.imwrite(thumb_path, resized_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            thumbnail_paths[size_name] = thumb_path
            logger.debug(f"Saved {size_name} thumbnail: {thumb_path}")
        
        return thumbnail_paths
    
    def _generate_placeholder_thumbnails(
        self, 
        source_name: str,
        start_offset: int
    ) -> dict:
        """
        Generate placeholder thumbnails when video is not available.
        Creates colored placeholder images with source info.
        
        Args:
            source_name: Source identifier
            start_offset: Start time offset
            
        Returns:
            Dictionary mapping size names to placeholder paths
        """
        # Create source directory
        source_dir = os.path.join(self.output_dir, source_name)
        os.makedirs(source_dir, exist_ok=True)
        
        import time
        timestamp = int(time.time())
        base_name = f"{source_name}_{start_offset}_{timestamp}_placeholder"
        
        # Generate deterministic color based on source name
        import hashlib
        hash_val = int(hashlib.md5(source_name.encode()).hexdigest(), 16)
        hue = (hash_val % 360) / 360.0
        
        # Convert HSV to RGB for placeholder color
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(hue, 0.6, 0.3)
        color = (int(r * 255), int(g * 255), int(b * 255))
        
        thumbnail_paths = {}
        
        for size_name, (width, height) in self.SIZES.items():
            # Create placeholder image
            img = np.full((height, width, 3), color, dtype=np.uint8)
            
            # Add text
            font = cv2.FONT_HERSHEY_SIMPLEX
            text = source_name[:15]  # Limit text length
            font_scale = max(0.3, min(width / 400, 0.8))
            thickness = max(1, int(width / 200))
            
            # Get text size
            (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
            
            # Center text
            text_x = (width - text_width) // 2
            text_y = (height + text_height) // 2
            
            # Draw text with outline
            cv2.putText(img, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness + 2)
            cv2.putText(img, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)
            
            # Save
            thumb_path = os.path.join(source_dir, f"{base_name}_{size_name}.jpg")
            cv2.imwrite(thumb_path, img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            thumbnail_paths[size_name] = thumb_path
        
        logger.debug(f"Generated placeholder thumbnails for {source_name}")
        return thumbnail_paths
    
    def get_thumbnail_url(self, thumbnail_path: str) -> str:
        """
        Convert a local thumbnail path to a URL.
        
        Args:
            thumbnail_path: Local filesystem path
            
        Returns:
            URL path for accessing the thumbnail
        """
        if not thumbnail_path:
            return ""
        
        # Extract relative path from output_dir
        if thumbnail_path.startswith(self.output_dir):
            rel_path = thumbnail_path[len(self.output_dir):].lstrip("/")
            return f"/thumbnails/{rel_path}"
        
        return thumbnail_path


# Singleton instance
_thumbnail_generator = None


def get_thumbnail_generator() -> ThumbnailGenerator:
    """Get or create the singleton thumbnail generator instance."""
    global _thumbnail_generator
    if _thumbnail_generator is None:
        _thumbnail_generator = ThumbnailGenerator()
    return _thumbnail_generator
