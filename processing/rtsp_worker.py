"""
RTSP Stream Worker - Processes live RTSP camera feeds
"""
import os
import sys
import time
import logging
import signal
import threading
from typing import Dict, List
import redis
import json

from frame_sampler import FrameSampler, create_motion_detector
from embedding import get_embedder
from vector_store import get_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RTSPWorker:
    """
    Worker that processes RTSP streams, samples frames, generates embeddings,
    and stores them in the vector database.
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        milvus_host: str = "localhost",
        milvus_port: str = "19530"
    ):
        """
        Initialize the RTSP worker.
        
        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            milvus_host: Milvus server host
            milvus_port: Milvus server port
        """
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.embedder = get_embedder()
        self.vector_store = get_vector_store(host=milvus_host, port=milvus_port, 
                                              embedding_dim=self.embedder.embedding_dim)
        self.motion_detector = create_motion_detector(threshold=0.02)
        
        self.active_streams: Dict[str, threading.Thread] = {}
        self.running = False
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal, stopping worker...")
        self.running = False
    
    def process_stream(self, camera_id: str, rtsp_url: str):
        """
        Process a single RTSP stream.
        
        Args:
            camera_id: Unique identifier for the camera
            rtsp_url: RTSP stream URL
        """
        logger.info(f"Starting to process RTSP stream: {camera_id} -> {rtsp_url}")
        
        sampler = FrameSampler(sample_rate=1, clip_duration=10)
        
        try:
            for clip_segment in sampler.sample_frames(
                source=rtsp_url,
                source_type="live",
                source_name=camera_id,
                is_rtsp=True,
                motion_detector=self.motion_detector.detect
            ):
                if not self.running:
                    break
                
                try:
                    # Generate clip embedding by averaging frame embeddings
                    frame_arrays = [f.data for f in clip_segment.frames]
                    clip_embedding = self.embedder.compute_clip_embedding(frame_arrays)
                    
                    # Get current timestamp
                    timestamp = int(time.time())
                    
                    # Get thumbnail path (medium size)
                    thumbnail_path = ""
                    if clip_segment.thumbnail_paths:
                        thumbnail_path = clip_segment.thumbnail_paths.get('medium', '')
                    
                    # Store in vector database
                    clip_id = self.vector_store.insert_clip(
                        vector=clip_embedding,
                        source_type="live",
                        source_name=camera_id,
                        timestamp=timestamp,
                        video_chunk_path=clip_segment.chunk_path,
                        start_offset=clip_segment.start_offset,
                        end_offset=clip_segment.end_offset,
                        frame_count=len(clip_segment.frames),
                        thumbnail_path=thumbnail_path
                    )
                    
                    # Update Redis with latest camera status
                    self.redis_client.hset(f"camera:{camera_id}", mapping={
                        "last_update": timestamp,
                        "last_clip_id": clip_id,
                        "status": "active"
                    })
                    
                    logger.info(f"Processed clip from {camera_id}: offset {clip_segment.start_offset}s, "
                               f"frames: {len(clip_segment.frames)}, clip_id: {clip_id}")
                    
                except Exception as e:
                    logger.error(f"Error processing clip from {camera_id}: {e}")
                    continue
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in stream processing for {camera_id}: {error_msg}")
            # Update status to error with message
            self.redis_client.hset(f"camera:{camera_id}", mapping={
                "status": "error",
                "error": error_msg[:200]  # Limit error message length
            })
        finally:
            # Only set to inactive if not already set to error
            current_status = self.redis_client.hget(f"camera:{camera_id}", "status")
            if current_status not in ["error", "stopped"]:
                self.redis_client.hset(f"camera:{camera_id}", "status", "inactive")
            logger.info(f"Stopped processing RTSP stream: {camera_id}")
    
    def start_stream(self, camera_id: str, rtsp_url: str):
        """
        Start processing a new RTSP stream in a background thread.
        
        Args:
            camera_id: Unique identifier for the camera
            rtsp_url: RTSP stream URL
        """
        if camera_id in self.active_streams:
            logger.warning(f"Stream {camera_id} is already active")
            return
        
        # Store stream config in Redis
        self.redis_client.hset(f"camera:{camera_id}", mapping={
            "rtsp_url": rtsp_url,
            "status": "starting"
        })
        
        # Start processing thread
        thread = threading.Thread(
            target=self.process_stream,
            args=(camera_id, rtsp_url),
            daemon=True
        )
        thread.start()
        
        self.active_streams[camera_id] = thread
        logger.info(f"Started stream thread for {camera_id}")
    
    def stop_stream(self, camera_id: str):
        """Stop processing a specific stream."""
        if camera_id in self.active_streams:
            # Note: Thread will exit on next iteration due to running flag
            del self.active_streams[camera_id]
            self.redis_client.hset(f"camera:{camera_id}", "status", "stopped")
            logger.info(f"Stopped stream: {camera_id}")
    
    def get_active_cameras(self) -> List[Dict]:
        """Get list of all registered cameras and their status."""
        cameras = []
        for key in self.redis_client.scan_iter(match="camera:*"):
            camera_id = key.split(":")[1]
            info = self.redis_client.hgetall(key)
            cameras.append({
                "camera_id": camera_id,
                **info
            })
        return cameras
    
    def run(self):
        """Main worker loop - listens for new stream tasks from Redis."""
        logger.info("RTSP Worker started, listening for tasks...")
        self.running = True
        
        # Restore any previously configured streams
        for key in self.redis_client.scan_iter(match="camera:*"):
            camera_id = key.split(":")[1]
            info = self.redis_client.hgetall(key)
            if info.get("rtsp_url") and info.get("status") != "stopped":
                logger.info(f"Restoring stream: {camera_id}")
                self.start_stream(camera_id, info["rtsp_url"])
        
        # Main loop - listen for new tasks
        while self.running:
            try:
                # Check for new stream tasks in Redis queue
                task = self.redis_client.blpop("rtsp_tasks", timeout=5)
                
                if task:
                    _, task_data = task
                    task_info = json.loads(task_data)
                    
                    action = task_info.get("action")
                    camera_id = task_info.get("camera_id")
                    rtsp_url = task_info.get("rtsp_url")
                    
                    if action == "start" and camera_id and rtsp_url:
                        self.start_stream(camera_id, rtsp_url)
                    elif action == "stop" and camera_id:
                        self.stop_stream(camera_id)
                
                # Clean up finished threads
                for camera_id in list(self.active_streams.keys()):
                    if not self.active_streams[camera_id].is_alive():
                        del self.active_streams[camera_id]
                        
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(1)
        
        logger.info("RTSP Worker stopped")


def main():
    """Entry point for the RTSP worker."""
    # Get configuration from environment
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    milvus_host = os.getenv("MILVUS_HOST", "localhost")
    milvus_port = os.getenv("MILVUS_PORT", "19530")
    
    worker = RTSPWorker(
        redis_host=redis_host,
        redis_port=redis_port,
        milvus_host=milvus_host,
        milvus_port=milvus_port
    )
    
    worker.run()


if __name__ == "__main__":
    main()
