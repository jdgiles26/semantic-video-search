"""
Document processing service for text extraction.
"""
import logging
import subprocess
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports with fallbacks
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None


class DocumentService:
    """Service for extracting text from various document formats."""
    
    # File extension mappings
    TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".tsv", ".log", ".yaml", ".yml", ".xml", ".html", ".htm"}
    PDF_EXTENSIONS = {".pdf"}
    DOCX_EXTENSIONS = {".docx"}
    SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm"}
    PRESENTATION_EXTENSIONS = {".pptx"}
    LEGACY_EXTENSIONS = {".doc", ".rtf", ".odt", ".xls", ".ppt"}
    
    def __init__(self, max_chars: int = 1200):
        self.max_chars = max_chars
    
    def extract_text(self, file_path: str, filename: str) -> Optional[str]:
        """
        Extract text from a document based on its file type.
        
        Args:
            file_path: Path to the file
            filename: Original filename for extension detection
            
        Returns:
            Extracted text or None if extraction failed
        """
        ext = Path(filename).suffix.lower()
        
        try:
            if ext in self.TEXT_EXTENSIONS:
                return self._extract_text_file(file_path)
            elif ext in self.PDF_EXTENSIONS:
                return self._extract_pdf(file_path)
            elif ext in self.DOCX_EXTENSIONS:
                return self._extract_docx(file_path)
            elif ext in self.SPREADSHEET_EXTENSIONS:
                return self._extract_spreadsheet(file_path)
            elif ext in self.PRESENTATION_EXTENSIONS:
                return self._extract_presentation(file_path)
            elif ext in {".doc", ".rtf", ".odt"}:
                return self._extract_with_textutil(file_path)
            elif ext in {".xls", ".ppt"}:
                return self._extract_with_strings(file_path)
            else:
                # Try as text file as fallback
                return self._extract_text_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to extract text from {filename}: {e}")
            return None
    
    def _normalize_text(self, text: str) -> Optional[str]:
        """Normalize extracted text."""
        cleaned = " ".join((text or "").split())
        return cleaned[:self.max_chars] if cleaned else None
    
    def _extract_text_file(self, file_path: str) -> Optional[str]:
        """Extract text from a plain text file."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return self._normalize_text(f.read(self.max_chars * 4))
    
    def _extract_pdf(self, file_path: str) -> Optional[str]:
        """Extract text from PDF."""
        if PdfReader is None:
            return None
        
        reader = PdfReader(file_path)
        chunks = []
        for page in reader.pages[:25]:
            chunks.append(page.extract_text() or "")
            if sum(len(chunk) for chunk in chunks) >= self.max_chars * 2:
                break
        return self._normalize_text(" ".join(chunks))
    
    def _extract_docx(self, file_path: str) -> Optional[str]:
        """Extract text from DOCX."""
        if DocxDocument is None:
            return None
        
        doc = DocxDocument(file_path)
        text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
        return self._normalize_text(" ".join(text_parts))
    
    def _extract_spreadsheet(self, file_path: str) -> Optional[str]:
        """Extract text from Excel spreadsheet."""
        if load_workbook is None:
            return None
        
        workbook = load_workbook(file_path, read_only=True, data_only=True)
        rows: List[str] = []
        
        for sheet in workbook.worksheets[:5]:
            rows.append(f"Sheet {sheet.title}")
            for row in sheet.iter_rows(min_row=1, max_row=25, values_only=True):
                values = [str(cell).strip() for cell in row if cell not in {None, ""}]
                if values:
                    rows.append(" | ".join(values))
                if sum(len(item) for item in rows) >= self.max_chars * 2:
                    break
            if sum(len(item) for item in rows) >= self.max_chars * 2:
                break
        
        workbook.close()
        return self._normalize_text(" ".join(rows))
    
    def _extract_presentation(self, file_path: str) -> Optional[str]:
        """Extract text from PowerPoint presentation."""
        if Presentation is None:
            return None
        
        presentation = Presentation(file_path)
        parts: List[str] = []
        
        for slide in presentation.slides[:20]:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    parts.append(shape.text)
            if sum(len(item) for item in parts) >= self.max_chars * 2:
                break
        
        return self._normalize_text(" ".join(parts))
    
    def _extract_with_textutil(self, file_path: str) -> Optional[str]:
        """Extract text using macOS textutil command."""
        try:
            result = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", file_path],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            return self._normalize_text(result.stdout)
        except Exception:
            return None
    
    def _extract_with_strings(self, file_path: str) -> Optional[str]:
        """Extract text using Unix strings command."""
        try:
            result = subprocess.run(
                ["strings", "-n", "4", file_path],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return self._normalize_text(result.stdout)
        except Exception:
            return None
