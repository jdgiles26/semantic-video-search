"""
URL and Upload Worker - Processes video URLs and uploaded files
Uses yt-dlp for URL streaming and handles file uploads.
"""
import os
import sys
import time
import logging
import tempfile
import shutil
from typing import Optional, Dict
import redis
import json
import requests
import yt_dlp

from frame_sampler import FrameSampler
from embedding import get_embedder
from vector_store import get_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class URLUploadWorker:
    """
    Worker that processes video URLs (using yt-dlp) and uploaded files,
    samples frames, generates embeddings, and stores them in the vector database.
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        milvus_host: str = "localhost",
        milvus_port: str = "19530",
        storage_path: str = "/tmp/video_uploads"
    ):
        """
        Initialize the URL/Upload worker.
        
        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            milvus_host: Milvus server host
            milvus_port: Milvus server port
            storage_path: Path to store uploaded files and chunks
        """
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.embedder = get_embedder()
        self.vector_store = get_vector_store(host=milvus_host, port=milvus_port,
                                              embedding_dim=self.embedder.embedding_dim)
        self.storage_path = storage_path
        
        # Ensure storage directory exists
        os.makedirs(storage_path, exist_ok=True)
    
    def download_from_url(self, url: str, task_id: str) -> Optional[str]:
        """
        Download video from URL using yt-dlp.
        
        Args:
            url: Video URL (YouTube, Vimeo, etc.)
            task_id: Task identifier for organizing downloads
            
        Returns:
            Path to downloaded file or None if failed
        """
        download_dir = os.path.join(self.storage_path, "downloads", task_id)
        os.makedirs(download_dir, exist_ok=True)
        
        ydl_opts = {
            'format': 'best[height<=720]/best',  # Prefer 720p or lower for processing speed
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                logger.info(f"Downloaded video from URL: {filename}")
                return filename
        except Exception as e:
            logger.error(f"Failed to download from URL {url}: {e}")
            return None
    
    def process_video_file(
        self,
        file_path: str,
        source_type: str,
        source_name: str,
        task_id: str,
        max_duration: Optional[int] = None
    ) -> Dict:
        """
        Process a video file - sample frames, generate embeddings, store in vector DB.
        
        Args:
            file_path: Path to video file
            source_type: "url" or "upload"
            source_name: Original URL or filename
            task_id: Task identifier
            max_duration: Maximum duration to process
            
        Returns:
            Processing result statistics
        """
        logger.info(f"Processing video file: {file_path}")
        
        sampler = FrameSampler(sample_rate=1, clip_duration=10)
        
        clips_processed = 0
        frames_processed = 0
        errors = []
        
        try:
            for clip_segment in sampler.sample_frames(
                source=file_path,
                source_type=source_type,
                source_name=source_name,
                is_rtsp=False,
                max_duration=max_duration
            ):
                try:
                    # Generate clip embedding
                    frame_arrays = [f.data for f in clip_segment.frames]
                    clip_embedding = self.embedder.compute_clip_embedding(frame_arrays)
                    
                    # Get timestamp
                    timestamp = int(time.time())
                    
                    # Get thumbnail path (medium size)
                    thumbnail_path = ""
                    if clip_segment.thumbnail_paths:
                        thumbnail_path = clip_segment.thumbnail_paths.get('medium', '')
                    
                    # Store in vector database
                    clip_id = self.vector_store.insert_clip(
                        vector=clip_embedding,
                        source_type=source_type,
                        source_name=source_name,
                        timestamp=timestamp,
                        video_chunk_path=clip_segment.chunk_path,
                        start_offset=clip_segment.start_offset,
                        end_offset=clip_segment.end_offset,
                        frame_count=len(clip_segment.frames),
                        thumbnail_path=thumbnail_path
                    )
                    
                    clips_processed += 1
                    frames_processed += len(clip_segment.frames)
                    
                    # Update progress in Redis
                    self.redis_client.hset(f"task:{task_id}", mapping={
                        "clips_processed": clips_processed,
                        "frames_processed": frames_processed,
                        "status": "processing"
                    })
                    
                    logger.info(f"Processed clip {clips_processed} from {source_name}: "
                               f"offset {clip_segment.start_offset}s, frames: {len(clip_segment.frames)}")
                    
                except Exception as e:
                    error_msg = f"Error processing clip at offset {clip_segment.start_offset}s: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    continue
            
            result = {
                "status": "completed" if not errors else "completed_with_errors",
                "clips_processed": clips_processed,
                "frames_processed": frames_processed,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Failed to process video {file_path}: {e}")
            result = {
                "status": "failed",
                "error": str(e)
            }
        
        return result
    
    def process_url_task(self, task_id: str, url: str, max_duration: Optional[int] = None):
        """
        Process a video URL task.
        
        Args:
            task_id: Task identifier
            url: Video URL
            max_duration: Maximum duration to process
        """
        logger.info(f"Starting URL task: {task_id} -> {url}")
        
        self.redis_client.hset(f"task:{task_id}", mapping={
            "url": url,
            "status": "downloading",
            "type": "url"
        })
        
        # Download video
        file_path = self.download_from_url(url, task_id)
        
        if not file_path:
            self.redis_client.hset(f"task:{task_id}", mapping={
                "status": "failed",
                "error": "Download failed"
            })
            return
        
        # Process the downloaded file
        self.redis_client.hset(f"task:{task_id}", "status", "processing")
        result = self.process_video_file(
            file_path=file_path,
            source_type="url",
            source_name=url,
            task_id=task_id,
            max_duration=max_duration
        )
        
        # Update final status
        self.redis_client.hset(f"task:{task_id}", mapping={
            "status": result["status"],
            "clips_processed": result.get("clips_processed", 0),
            "frames_processed": result.get("frames_processed", 0),
            "errors": json.dumps(result.get("errors", []))
        })
        
        # Clean up downloaded file (optional - keep for now)
        # shutil.rmtree(os.path.dirname(file_path), ignore_errors=True)
        
        logger.info(f"Completed URL task: {task_id}")
    
    def process_upload_task(self, task_id: str, file_path: str, original_filename: str):
        """
        Process an uploaded file task.
        
        Args:
            task_id: Task identifier
            file_path: Path to uploaded file
            original_filename: Original filename
        """
        logger.info(f"Starting upload task: {task_id} -> {original_filename}")
        
        self.redis_client.hset(f"task:{task_id}", mapping={
            "filename": original_filename,
            "status": "processing",
            "type": "upload"
        })
        
        # Process the file
        result = self.process_video_file(
            file_path=file_path,
            source_type="upload",
            source_name=original_filename,
            task_id=task_id
        )
        
        # Update final status
        self.redis_client.hset(f"task:{task_id}", mapping={
            "status": result["status"],
            "clips_processed": result.get("clips_processed", 0),
            "frames_processed": result.get("frames_processed", 0),
            "errors": json.dumps(result.get("errors", []))
        })
        
        logger.info(f"Completed upload task: {task_id}")
    
    def run(self):
        """Main worker loop - listens for URL/upload tasks from Redis."""
        logger.info("URL/Upload Worker started, listening for tasks...")
        
        while True:
            try:
                # Check for new tasks in Redis queue
                task = self.redis_client.blpop("video_tasks", timeout=5)
                
                if task:
                    _, task_data = task
                    task_info = json.loads(task_data)
                    
                    task_id = task_info.get("task_id")
                    task_type = task_info.get("type")
                    
                    if task_type == "url":
                        self.process_url_task(
                            task_id=task_id,
                            url=task_info.get("url"),
                            max_duration=task_info.get("max_duration")
                        )
                    elif task_type == "upload":
                        self.process_upload_task(
                            task_id=task_id,
                            file_path=task_info.get("file_path"),
                            original_filename=task_info.get("original_filename")
                        )
                    else:
                        logger.warning(f"Unknown task type: {task_type}")
                        
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(1)


def main():
    """Entry point for the URL/Upload worker."""
    # Get configuration from environment
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    milvus_host = os.getenv("MILVUS_HOST", "localhost")
    milvus_port = os.getenv("MILVUS_PORT", "19530")
    storage_path = os.getenv("STORAGE_PATH", "/tmp/video_uploads")
    
    worker = URLUploadWorker(
        redis_host=redis_host,
        redis_port=redis_port,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        storage_path=storage_path
    )
    
    worker.run()


if __name__ == "__main__":
    main()
