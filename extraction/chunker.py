"""
Document Chunker
================
Splits extracted document pages into semantic chunks with sliding window overlap.
Ensures every chunk retains page number, document metadata, and text spans for strict provenance.
"""

import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from extraction.pdf_extractor import ExtractedDocument, ExtractedPage
from config import settings

class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    chunk_index: int
    text: str
    char_count: int
    word_count: int

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class DocumentChunker:
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_document(self, document: ExtractedDocument) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        for page in document.pages:
            page_text = page.text
            if not page_text.strip():
                continue

            # If page text is within chunk size, create a single chunk for the page
            if len(page_text) <= self.chunk_size:
                chunk_id = f"{document.document_id}_p{page.page_number}_c0"
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        document_name=document.document_name,
                        page_number=page.page_number,
                        chunk_index=global_chunk_idx,
                        text=page_text,
                        char_count=len(page_text),
                        word_count=len(page_text.split())
                    )
                )
                global_chunk_idx += 1
                continue

            # Page is larger than chunk size: split with sentence awareness and overlap
            page_chunks = self._split_text(page_text)
            for sub_idx, chunk_text in enumerate(page_chunks):
                chunk_id = f"{document.document_id}_p{page.page_number}_c{sub_idx}"
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        document_name=document.document_name,
                        page_number=page.page_number,
                        chunk_index=global_chunk_idx,
                        text=chunk_text,
                        char_count=len(chunk_text),
                        word_count=len(chunk_text.split())
                    )
                )
                global_chunk_idx += 1

        return chunks

    def _split_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks respecting sentence boundaries."""
        sentences = re.split(r'(?<=[.?!;:\n])\s+', text)
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if current_len + sent_len > self.chunk_size and current_chunk:
                chunk_str = " ".join(current_chunk).strip()
                if chunk_str:
                    chunks.append(chunk_str)
                
                # Compute overlap
                overlap_chunk: List[str] = []
                overlap_len = 0
                for s in reversed(current_chunk):
                    if overlap_len + len(s) < self.chunk_overlap:
                        overlap_chunk.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break
                current_chunk = overlap_chunk
                current_len = sum(len(s) for s in current_chunk)

            current_chunk.append(sent)
            current_len += sent_len

        if current_chunk:
            chunk_str = " ".join(current_chunk).strip()
            if chunk_str:
                chunks.append(chunk_str)

        return chunks
