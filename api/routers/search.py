"""
Search API routes.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from api.models import SearchResponse
from processing.embedding import get_embedder
from processing.vector_store import get_vector_store
from processing.hybrid_search import HybridScorer, enhance_search_results
from processing.mission_intelligence import MissionIntelligenceEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["search"])

# Lazy initialization
def get_embedder_instance(model_key: str = 'standard'):
    """Get embedder for specified model key."""
    if not hasattr(get_embedder_instance, '_embedders'):
        get_embedder_instance._embedders = {}
    if model_key not in get_embedder_instance._embedders:
        logger.info(f"Lazy loading embedder for model: {model_key}")
        get_embedder_instance._embedders[model_key] = get_embedder(model_key)
    return get_embedder_instance._embedders[model_key]


def get_vector_store_instance(embedding_dim: int = 512):
    """Get vector store instance."""
    if not hasattr(get_vector_store_instance, '_instance'):
        from processing.vector_store import get_vector_store
        import os
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        logger.info("Lazy loading vector store...")
        get_vector_store_instance._instance = get_vector_store(
            host=milvus_host, port=milvus_port, embedding_dim=embedding_dim
        )
    return get_vector_store_instance._instance


def get_hybrid_scorer():
    """Get hybrid scorer instance."""
    if not hasattr(get_hybrid_scorer, '_instance'):
        logger.info("Lazy loading hybrid scorer...")
        get_hybrid_scorer._instance = HybridScorer()
    return get_hybrid_scorer._instance


def get_mission_engine():
    """Get mission intelligence engine."""
    if not hasattr(get_mission_engine, '_instance'):
        get_mission_engine._instance = MissionIntelligenceEngine()
    return get_mission_engine._instance


@router.get("", response_model=SearchResponse)
async def search_videos(
    query: str = Query(..., min_length=1, description="Natural language search query"),
    top_k: int = Query(10, ge=1, le=100, description="Number of results to return"),
    source_type: Optional[str] = Query(None, description="Filter by source type: live, url, upload"),
    source_name: Optional[str] = Query(None, description="Filter by source name/camera ID"),
    min_timestamp: Optional[int] = Query(None, description="Filter by minimum timestamp"),
    max_timestamp: Optional[int] = Query(None, description="Filter by maximum timestamp"),
    mode: str = Query('clip', description="Search mode: clip, yolo_hybrid, advanced_clip, mission_ai")
):
    """
    Search for video clips using natural language.
    
    Search modes:
    - clip: Standard CLIP semantic search (fast, good accuracy)
    - yolo_hybrid: CLIP + YOLO object detection for improved accuracy
    - advanced_clip: Larger CLIP model (ViT-L-14) for better semantic understanding
    """
    try:
        # Determine embedder based on mode
        embedder_key = 'advanced' if mode == 'advanced_clip' else 'standard'
        embedder = get_embedder_instance(embedder_key)
        
        # Get vector store
        vector_store = get_vector_store_instance(embedding_dim=embedder.embedding_dim)
        
        # Generate query embedding
        query_embedding = embedder.encode_text(query)
        
        # Search with expanded results for hybrid re-ranking
        search_top_k = top_k * 3 if mode in {'yolo_hybrid', 'mission_ai'} else top_k
        
        try:
            results = vector_store.search(
                query_vector=query_embedding,
                top_k=search_top_k,
                source_type=source_type,
                source_name=source_name,
                min_timestamp=min_timestamp,
                max_timestamp=max_timestamp
            )
        except Exception as search_err:
            # Fall back to standard model on dimension mismatch
            error_str = str(search_err).lower()
            if mode == 'advanced_clip' and ('dimension mismatch' in error_str or 'vector dimension' in error_str):
                logger.warning("Advanced CLIP dimension mismatch, falling back to standard CLIP")
                embedder = get_embedder_instance('standard')
                vector_store = get_vector_store_instance(embedding_dim=embedder.embedding_dim)
                query_embedding = embedder.encode_text(query)
                results = vector_store.search(
                    query_vector=query_embedding,
                    top_k=search_top_k,
                    source_type=source_type,
                    source_name=source_name,
                    min_timestamp=min_timestamp,
                    max_timestamp=max_timestamp
                )
            else:
                raise
        
        # Apply hybrid scoring if requested
        if mode in {'yolo_hybrid', 'mission_ai'}:
            hybrid_scorer = get_hybrid_scorer()
            results = enhance_search_results(query, results, hybrid_scorer, top_k=top_k)
        
        # Enrich results with metadata
        from api.services import CacheService
        import redis
        import os
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True
        )
        cache = CacheService(redis_client)
        
        enriched_results = []
        for result in results:
            clip_id = int(result.get("id"))
            meta = cache.get_clip_metadata(clip_id)
            merged = result.copy()
            if meta:
                for field in ["detected_objects", "clip_tags", "object_scores",
                             "urgency_score", "urgency_level", "urgency_reasons",
                             "mission_score", "watch_phrase", "watch_summary", "watch_assessment"]:
                    if meta.get(field) and not merged.get(field):
                        merged[field] = meta.get(field)
            enriched_results.append(merged)
        
        # Apply mission intelligence
        mission_engine = get_mission_engine()
        enriched_results, alerts = mission_engine.enrich_results(
            query, enriched_results, mode=mode
        )
        report_preview = mission_engine.build_incident_report(query, alerts) if alerts else None
        
        # Keep top_k after reranking
        enriched_results = enriched_results[:top_k]
        
        from api.models import SearchResult, UrgentAlert
        return SearchResponse(
            query=query,
            results=[SearchResult(**r) for r in enriched_results],
            total_count=len(enriched_results),
            alerts=[UrgentAlert(**a) for a in alerts],
            report_preview=report_preview
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
