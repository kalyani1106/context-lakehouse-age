import io
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import pypdf

class ExtractedPage(BaseModel):
    document_id: str
    document_name: str
    page_number: int # 1-indexed
    text: str
    char_count: int
    word_count: int

class ExtractedDocument(BaseModel):
    document_id: str
    document_name: str
    total_pages: int
    total_characters: int
    total_words: int
    pages: List[ExtractedPage]

class PDFExtractionError(Exception):
    """Custom exception raised when PDF extraction fails."""
    pass

class PDFExtractor:
    """
    Robust PDF text extraction using pypdf.
    Preserves page-level provenance, character counts, and handles Unicode text cleanly.
    """

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        # Replace non-printable/control chars except newlines and tabs
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        # Normalize horizontal whitespaces
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        # Clean whitespaces adjacent to newlines
        cleaned = re.sub(r' *(\n+) *', r'\1', cleaned)
        # Normalize multiple newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def extract_from_path(self, file_path: Path, document_id: str, document_name: str) -> ExtractedDocument:
        if not file_path.exists():
            raise PDFExtractionError(f"PDF file not found at {file_path}")
        
        try:
            with open(file_path, "rb") as f:
                return self.extract_from_bytes(f.read(), document_id, document_name)
        except PDFExtractionError:
            raise
        except Exception as e:
            raise PDFExtractionError(f"Failed reading PDF {document_name}: {str(e)}")

    def extract_from_bytes(self, file_bytes: bytes, document_id: str, document_name: str) -> ExtractedDocument:
        if not file_bytes or len(file_bytes) == 0:
            raise PDFExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except Exception as e:
            raise PDFExtractionError(f"Invalid or corrupted PDF file {document_name}: {str(e)}")

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise PDFExtractionError(f"PDF {document_name} has 0 pages.")

        pages: List[ExtractedPage] = []
        total_chars = 0
        total_words = 0

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                raw_text = page.extract_text() or ""
            except Exception as e:
                raw_text = f"[Extraction warning on page {page_num}: {str(e)}]"

            cleaned = self.clean_text(raw_text)
            char_count = len(cleaned)
            word_count = len(cleaned.split()) if cleaned else 0

            pages.append(
                ExtractedPage(
                    document_id=document_id,
                    document_name=document_name,
                    page_number=page_num,
                    text=cleaned,
                    char_count=char_count,
                    word_count=word_count
                )
            )
            total_chars += char_count
            total_words += word_count

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=num_pages,
            total_characters=total_chars,
            total_words=total_words,
            pages=pages
        )
