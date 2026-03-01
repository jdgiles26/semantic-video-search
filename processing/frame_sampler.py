"""
Frame Sampling and Video Segmentation Module
Handles RTSP streams, video URLs, and uploaded files.
"""
import cv2
import numpy as np
import os
import logging
from typing import Iterator, Tuple, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
import threading
import time
import subprocess
import tempfile

from thumbnail_generator import get_thumbnail_generator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Frame:
    """Represents a sampled frame with metadata."""
    data: np.ndarray  # RGB image array
    timestamp: float  # Timestamp in seconds from video start
    frame_number: int  # Frame number in original video
    source_name: str  # Source identifier


@dataclass
class ClipSegment:
    """Represents a 10-second video segment with sampled frames."""
    frames: List[Frame]
    start_offset: int  # Start time in seconds from video start
    end_offset: int    # End time in seconds from video start
    source_type: str   # "live", "url", or "upload"
    source_name: str   # Camera ID or filename
    chunk_path: str    # Path to saved video chunk
    thumbnail_paths: dict = None  # Dictionary of thumbnail paths by size


class FrameSampler:
    """
    Samples frames from video sources at 1 frame per second.
    Groups frames into 10-second clips for processing.
    """
    
    def __init__(self, sample_rate: int = 1, clip_duration: int = 10):
        """
        Initialize frame sampler.
        
        Args:
            sample_rate: Frames to sample per second (default 1)
            clip_duration: Duration of each clip in seconds (default 10)
        """
        self.sample_rate = sample_rate
        self.clip_duration = clip_duration
        self.frames_per_clip = sample_rate * clip_duration
        
    def _open_video(self, source: str, is_rtsp: bool = False) -> Tuple[cv2.VideoCapture, dict]:
        """
        Open video source with optimized settings.
        
        Args:
            source: Video source (file path, URL, or RTSP stream)
            is_rtsp: Whether source is an RTSP stream
            
        Returns:
            Tuple of (VideoCapture object, video properties dict)
        """
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            raise ValueError(f"Failed to open video source: {source}")
        
        # Set buffer size for RTSP to reduce latency
        if is_rtsp:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Get video properties
        props = {
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
        
        # Handle cases where FPS is not available or invalid
        if props['fps'] <= 0:
            props['fps'] = 30  # Default assumption
        
        logger.info(f"Opened video: {source}, Properties: {props}")
        return cap, props
    
    def sample_frames(
        self,
        source: str,
        source_type: str,
        source_name: str,
        is_rtsp: bool = False,
        max_duration: Optional[int] = None,
        motion_detector: Optional[Callable[[np.ndarray, np.ndarray], bool]] = None
    ) -> Iterator[ClipSegment]:
        """
        Sample frames from video source and yield 10-second clip segments.
        
        Args:
            source: Video source path/URL
            source_type: "live", "url", or "upload"
            source_name: Identifier for the source
            is_rtsp: Whether this is an RTSP stream
            max_duration: Maximum duration to process in seconds (None for unlimited)
            motion_detector: Optional function to detect motion between frames
            
        Yields:
            ClipSegment objects containing sampled frames
        """
        cap, props = self._open_video(source, is_rtsp)
        fps = props['fps']
        frame_interval = int(fps / self.sample_rate)  # Frames to skip between samples
        
        frames_buffer = []
        clip_start_offset = 0
        frame_number = 0
        last_sampled_frame = None
        last_sampled_frame_num = -frame_interval
        
        try:
            while True:
                ret, frame = cap.read()
                
                if not ret:
                    if is_rtsp:
                        # For RTSP, try to reconnect
                        logger.warning(f"Lost connection to RTSP stream: {source}")
                        time.sleep(1)
                        cap.release()
                        cap, _ = self._open_video(source, is_rtsp)
                        continue
                    else:
                        # End of file
                        break
                
                current_time = frame_number / fps
                
                # Check max duration
                if max_duration and current_time >= max_duration:
                    break
                
                # Sample frame at specified rate
                if frame_number - last_sampled_frame_num >= frame_interval:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Motion detection (optional)
                    if motion_detector and last_sampled_frame is not None:
                        if not motion_detector(last_sampled_frame, frame_rgb):
                            frame_number += 1
                            continue
                    
                    frame_obj = Frame(
                        data=frame_rgb,
                        timestamp=current_time,
                        frame_number=frame_number,
                        source_name=source_name
                    )
                    frames_buffer.append(frame_obj)
                    last_sampled_frame = frame_rgb
                    last_sampled_frame_num = frame_number
                    
                    # Check if we have a complete clip
                    if len(frames_buffer) >= self.frames_per_clip:
                        # Save video chunk
                        chunk_path = self._save_video_chunk(
                            source, clip_start_offset, self.clip_duration, source_name
                        )
                        
                        # Generate thumbnails from middle frame
                        thumb_gen = get_thumbnail_generator()
                        middle_frame_idx = len(frames_buffer) // 2
                        thumbnail_paths = thumb_gen.generate_from_frame(
                            frames_buffer[middle_frame_idx].data,
                            source_name,
                            clip_start_offset
                        )
                        
                        clip_segment = ClipSegment(
                            frames=frames_buffer.copy(),
                            start_offset=clip_start_offset,
                            end_offset=clip_start_offset + self.clip_duration,
                            source_type=source_type,
                            source_name=source_name,
                            chunk_path=chunk_path,
                            thumbnail_paths=thumbnail_paths
                        )
                        
                        yield clip_segment
                        
                        # Reset for next clip
                        frames_buffer = []
                        clip_start_offset += self.clip_duration
                
                frame_number += 1
                
        finally:
            cap.release()
            
            # Yield any remaining frames as final clip
            if frames_buffer:
                chunk_path = self._save_video_chunk(
                    source, clip_start_offset, self.clip_duration, source_name
                )
                
                # Generate thumbnails from middle frame
                thumb_gen = get_thumbnail_generator()
                middle_frame_idx = len(frames_buffer) // 2
                thumbnail_paths = thumb_gen.generate_from_frame(
                    frames_buffer[middle_frame_idx].data,
                    source_name,
                    clip_start_offset
                )
                
                clip_segment = ClipSegment(
                    frames=frames_buffer,
                    start_offset=clip_start_offset,
                    end_offset=clip_start_offset + len(frames_buffer) // self.sample_rate,
                    source_type=source_type,
                    source_name=source_name,
                    chunk_path=chunk_path,
                    thumbnail_paths=thumbnail_paths
                )
                yield clip_segment
    
    def _save_video_chunk(
        self,
        source: str,
        start_offset: int,
        duration: int,
        source_name: str
    ) -> str:
        """
        Extract and save a video chunk using FFmpeg.
        
        Args:
            source: Original video source
            start_offset: Start time in seconds
            duration: Duration in seconds
            source_name: Source identifier for naming
            
        Returns:
            Path to the saved chunk file
        """
        # Create chunks directory
        chunks_dir = os.path.join("/tmp/video_chunks", source_name)
        os.makedirs(chunks_dir, exist_ok=True)
        
        # Generate chunk filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chunk_filename = f"{source_name}_{timestamp}_{start_offset}_{start_offset + duration}.mp4"
        chunk_path = os.path.join(chunks_dir, chunk_filename)
        
        try:
            # Use FFmpeg to extract the segment
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-ss", str(start_offset),  # Start time
                "-t", str(duration),  # Duration
                "-i", source,  # Input
                "-c:v", "libx264",  # Video codec
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",  # Audio codec
                "-b:a", "128k",
                "-movflags", "+faststart",
                chunk_path
            ]
            
            subprocess.run(cmd, capture_output=True, check=True, timeout=60)
            logger.debug(f"Saved video chunk: {chunk_path}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr.decode()}")
            # Return a placeholder path if extraction fails
            chunk_path = f"placeholder://{source}#{start_offset}-{start_offset + duration}"
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for chunk at {start_offset}s")
            chunk_path = f"placeholder://{source}#{start_offset}-{start_offset + duration}"
        
        return chunk_path


class MotionDetector:
    """
    Simple motion detector to skip stagnant frames from RTSP feeds.
    """
    
    def __init__(self, threshold: float = 0.02, min_pixel_diff: int = 30):
        """
        Initialize motion detector.
        
        Args:
            threshold: Minimum fraction of pixels that must change
            min_pixel_diff: Minimum pixel value difference to count as changed
        """
        self.threshold = threshold
        self.min_pixel_diff = min_pixel_diff
    
    def detect(self, prev_frame: np.ndarray, curr_frame: np.ndarray) -> bool:
        """
        Detect if there is significant motion between two frames.
        
        Args:
            prev_frame: Previous frame (RGB)
            curr_frame: Current frame (RGB)
            
        Returns:
            True if motion detected, False otherwise
        """
        # Convert to grayscale for faster processing
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_RGB2GRAY)
        curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_RGB2GRAY)
        
        # Calculate absolute difference
        diff = cv2.absdiff(prev_gray, curr_gray)
        
        # Threshold the difference
        _, thresh = cv2.threshold(diff, self.min_pixel_diff, 255, cv2.THRESH_BINARY)
        
        # Calculate fraction of changed pixels
        changed_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.size
        change_ratio = changed_pixels / total_pixels
        
        return change_ratio > self.threshold


def create_frame_sampler(sample_rate: int = 1, clip_duration: int = 10) -> FrameSampler:
    """Factory function to create a frame sampler."""
    return FrameSampler(sample_rate=sample_rate, clip_duration=clip_duration)


def create_motion_detector(threshold: float = 0.02) -> MotionDetector:
    """Factory function to create a motion detector."""
    return MotionDetector(threshold=threshold)
