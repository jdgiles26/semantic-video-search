"""
OPORD (Operations Order) parsing and activation routes.
"""
import logging
import uuid
from typing import Optional
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, HTTPException, File, UploadFile, BackgroundTasks
import redis
import os

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from api.models import OpordParseRequest, OpordParseResponse
from processing.opord_parser import parse_opord_document, get_opord_parser
from processing.watchlist_manager import WatchlistManager
from processing.ai_provider import get_ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/opord", tags=["opord"])

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)


def _extract_text_from_file(content: bytes, filename: str, mime_type: str) -> str:
    """Extract text from uploaded file."""
    text = ""
    
    if mime_type == "text/plain" or filename.endswith('.txt'):
        text = content.decode('utf-8', errors='ignore')
    
    elif mime_type == "application/pdf" or filename.endswith('.pdf'):
        if not PDF_AVAILABLE:
            raise HTTPException(status_code=400, detail="PDF parsing not available. Install pypdf.")
        reader = PdfReader(BytesIO(content))
        text = " ".join(page.extract_text() or "" for page in reader.pages[:25])
    
    elif filename.endswith('.docx'):
        if not DOCX_AVAILABLE:
            raise HTTPException(status_code=400, detail="DOCX parsing not available. Install python-docx.")
        doc = DocxDocument(BytesIO(content))
        text = " ".join(p.text for p in doc.paragraphs if p.text)
    
    else:
        # Try as text
        text = content.decode('utf-8', errors='ignore')
    
    return text.strip()


@router.post("/parse", response_model=OpordParseResponse)
async def parse_opord(request: OpordParseRequest):
    """
    Parse an OPORD document using NLP.
    Extracts watch phrases, entities, topics, keywords, and priority.
    """
    try:
        parsed = parse_opord_document(
            text=request.text,
            source_filename=request.source_filename,
            mime_type=request.mime_type
        )
        
        return OpordParseResponse(
            watch_phrase=parsed.watch_phrase,
            watch_labels=parsed.watch_labels,
            priority=parsed.priority,
            topics=parsed.topics,
            keywords=parsed.keywords,
            entities=parsed.entities,
            persons=parsed.persons,
            locations=parsed.locations,
            excerpt=parsed.excerpt,
            parser_used=parsed.parser_used,
            confidence=parsed.confidence
        )
    except Exception as e:
        logger.error(f"OPORD parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.post("/upload-and-activate")
async def upload_and_activate_opord(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload an OPORD document, parse it with NLP, and activate a watch alert.
    Supports: PDF, DOCX, TXT, and other text formats.
    """
    try:
        # Read file
        content = await file.read()
        mime_type = file.content_type or "application/octet-stream"
        
        # Extract text
        text = _extract_text_from_file(content, file.filename, mime_type)
        
        if not text:
            raise HTTPException(status_code=400, detail="No text content extracted from file")
        
        # Parse with NLP
        parsed = parse_opord_document(
            text=text,
            source_filename=file.filename,
            mime_type=mime_type
        )
        
        # Create and activate watch alert
        alert_payload = parsed.to_alert_payload()
        alert_payload["alert_id"] = str(uuid.uuid4())
        alert_payload["status"] = "active"
        alert_payload["created_at"] = int(datetime.now().timestamp())
        alert_payload["source_filename"] = file.filename
        alert_payload["mime_type"] = mime_type
        alert_payload["banner_message"] = f"OPORD watch active: prioritizing '{parsed.watch_phrase}' detections."
        
        manager = WatchlistManager(redis_client)
        manager.activate_alert(alert_payload)
        
        return {
            "status": "activated",
            "alert": alert_payload,
            "parsed": {
                "watch_phrase": parsed.watch_phrase,
                "priority": parsed.priority,
                "topics": parsed.topics,
                "keywords": parsed.keywords,
                "persons": parsed.persons,
                "locations": parsed.locations,
                "parser_used": parsed.parser_used,
                "confidence": parsed.confidence
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OPORD upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/parser/status")
async def get_parser_status():
    """Get OPORD parser status and available backends."""
    parser = get_opord_parser()
    return parser.get_status()
