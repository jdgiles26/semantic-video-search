"""
Milvus Vector Database Integration for Video Embeddings
"""
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VideoVectorStore:
    """
    Manages video clip embeddings in Milvus vector database.
    
    Schema:
        - id: Primary key (auto-generated)
        - vector: 512-D float array (CLIP embedding)
        - source_type: Enum ("live", "url", "upload")
        - source_name: Camera ID or filename
        - timestamp: Epoch timestamp
        - video_chunk_path: Path to the 10s clip file
        - start_offset: Start time offset in seconds within source video
        - end_offset: End time offset in seconds within source video
        - frame_count: Number of frames in the clip
    """
    
    COLLECTION_NAME = "video_clips"
    
    def __init__(self, host: str = "localhost", port: str = "19530", embedding_dim: int = 512):
        """
        Initialize connection to Milvus.
        
        Args:
            host: Milvus server host
            port: Milvus server port
            embedding_dim: Dimension of embedding vectors (512 for ViT-B-32, 768 for ViT-L-14)
        """
        self.host = host
        self.port = port
        self.embedding_dim = embedding_dim
        self.collection = None
        
        # Connect to Milvus
        connections.connect(alias="default", host=host, port=port)
        logger.info(f"Connected to Milvus at {host}:{port}")
        
        # Initialize collection
        self._init_collection()
    
    def _init_collection(self):
        """Initialize the video clips collection if it doesn't exist."""
        if utility.has_collection(self.COLLECTION_NAME):
            self.collection = Collection(self.COLLECTION_NAME)
            logger.info(f"Loaded existing collection: {self.COLLECTION_NAME}")
        else:
            # Define schema
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
                FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=20),
                FieldSchema(name="source_name", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="timestamp", dtype=DataType.INT64),
                FieldSchema(name="video_chunk_path", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="thumbnail_path", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="start_offset", dtype=DataType.INT64),
                FieldSchema(name="end_offset", dtype=DataType.INT64),
                FieldSchema(name="frame_count", dtype=DataType.INT64),
            ]
            
            schema = CollectionSchema(fields, description="Video clip embeddings for semantic search")
            self.collection = Collection(self.COLLECTION_NAME, schema)
            
            # Create index for vector search
            index_params = {
                "metric_type": "IP",  # Inner Product (cosine similarity for normalized vectors)
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            self.collection.create_index(field_name="vector", index_params=index_params)
            logger.info(f"Created new collection: {self.COLLECTION_NAME}")
        
        self.collection.load()
    
    def insert_clip(
        self,
        vector: np.ndarray,
        source_type: str,
        source_name: str,
        timestamp: int,
        video_chunk_path: str,
        start_offset: int,
        end_offset: int,
        frame_count: int,
        thumbnail_path: str = ""
    ) -> int:
        """
        Insert a video clip embedding into the database.
        
        Args:
            vector: Embedding vector (512-D or 768-D)
            source_type: "live", "url", or "upload"
            source_name: Camera ID or filename
            timestamp: Epoch timestamp
            video_chunk_path: Path to the 10s clip file
            start_offset: Start time offset in seconds
            end_offset: End time offset in seconds
            frame_count: Number of frames sampled
            thumbnail_path: Path to the thumbnail image
            
        Returns:
            The auto-generated ID of the inserted record
        """
        entities = [
            [vector.tolist()],  # vector
            [source_type],      # source_type
            [source_name],      # source_name
            [timestamp],        # timestamp
            [video_chunk_path], # video_chunk_path
            [thumbnail_path],   # thumbnail_path
            [start_offset],     # start_offset
            [end_offset],       # end_offset
            [frame_count],      # frame_count
        ]
        
        insert_result = self.collection.insert(entities)
        self.collection.flush()
        
        logger.debug(f"Inserted clip: {source_name} at offset {start_offset}s")
        return insert_result.primary_keys[0]
    
    def insert_clips_batch(self, clips: List[Dict]) -> List[int]:
        """
        Insert multiple video clips in batch.
        
        Args:
            clips: List of clip dictionaries with keys matching insert_clip parameters
            
        Returns:
            List of auto-generated IDs
        """
        if not clips:
            return []
        
        entities = [
            [clip["vector"].tolist() for clip in clips],
            [clip["source_type"] for clip in clips],
            [clip["source_name"] for clip in clips],
            [clip["timestamp"] for clip in clips],
            [clip["video_chunk_path"] for clip in clips],
            [clip["start_offset"] for clip in clips],
            [clip["end_offset"] for clip in clips],
            [clip["frame_count"] for clip in clips],
        ]
        
        insert_result = self.collection.insert(entities)
        self.collection.flush()
        
        logger.info(f"Batch inserted {len(clips)} clips")
        return insert_result.primary_keys
    
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        source_type: Optional[str] = None,
        source_name: Optional[str] = None,
        min_timestamp: Optional[int] = None,
        max_timestamp: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for similar video clips using vector similarity.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            source_type: Filter by source type
            source_name: Filter by source name
            min_timestamp: Filter by minimum timestamp
            max_timestamp: Filter by maximum timestamp
            
        Returns:
            List of matching clips with similarity scores
        """
        # Build expression for filtering
        expr_parts = []
        if source_type:
            expr_parts.append(f'source_type == "{source_type}"')
        if source_name:
            expr_parts.append(f'source_name == "{source_name}"')
        if min_timestamp is not None:
            expr_parts.append(f'timestamp >= {min_timestamp}')
        if max_timestamp is not None:
            expr_parts.append(f'timestamp <= {max_timestamp}')
        
        expr = " and ".join(expr_parts) if expr_parts else None
        
        # Search parameters
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        
        results = self.collection.search(
            data=[query_vector.tolist()],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["source_type", "source_name", "timestamp", "video_chunk_path",
                          "thumbnail_path", "start_offset", "end_offset", "frame_count"]
        )
        
        # Format results
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.id,
                    "score": float(hit.score),
                    "source_type": hit.entity.get("source_type"),
                    "source_name": hit.entity.get("source_name"),
                    "timestamp": hit.entity.get("timestamp"),
                    "video_chunk_path": hit.entity.get("video_chunk_path"),
                    "thumbnail_path": hit.entity.get("thumbnail_path"),
                    "start_offset": hit.entity.get("start_offset"),
                    "end_offset": hit.entity.get("end_offset"),
                    "frame_count": hit.entity.get("frame_count"),
                })
        
        return formatted_results
    
    def get_clip_by_id(self, clip_id: int) -> Optional[Dict]:
        """Retrieve a specific clip by ID."""
        results = self.collection.query(
            expr=f"id == {clip_id}",
            output_fields=["source_type", "source_name", "timestamp", "video_chunk_path",
                          "thumbnail_path", "start_offset", "end_offset", "frame_count"]
        )
        return results[0] if results else None
    
    def delete_clips_by_source(self, source_name: str) -> int:
        """Delete all clips from a specific source."""
        expr = f'source_name == "{source_name}"'
        result = self.collection.delete(expr)
        logger.info(f"Deleted clips from source: {source_name}")
        return result.delete_count
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection."""
        self.collection.flush()
        stats = self.collection.num_entities
        return {
            "total_clips": stats,
            "collection_name": self.COLLECTION_NAME,
            "embedding_dim": self.embedding_dim
        }
    
    def close(self):
        """Close the Milvus connection."""
        connections.disconnect("default")
        logger.info("Disconnected from Milvus")


# Singleton instance
_vector_store = None


def get_vector_store(host: str = "localhost", port: str = "19530", embedding_dim: int = 512) -> VideoVectorStore:
    """Get or create the singleton vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VideoVectorStore(host, port, embedding_dim)
    return _vector_store
