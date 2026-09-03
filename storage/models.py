from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ProcessingStatus(str, Enum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    GENERATING_CONTEXT = "GENERATING_CONTEXT"
    BUILDING_GRAPH = "BUILDING_GRAPH"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ExtractionMethod(str, Enum):
    OPENAI = "OPENAI"
    GEMINI = "GEMINI"
    HEURISTIC_NLP = "HEURISTIC_NLP"
    MOCK = "MOCK"

class DocumentMetadata(BaseModel):
    document_id: str
    document_name: str
    file_type: str = "application/pdf"
    file_size_bytes: int
    sha256: str
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    total_entities: Optional[int] = None
    total_relationships: Optional[int] = None
    status: ProcessingStatus = ProcessingStatus.UPLOADED
    extraction_method: Optional[ExtractionMethod] = None
    processing_time_sec: Optional[float] = None
    nodes_added: Optional[int] = None
    edges_added: Optional[int] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["uploaded_at"] = self.uploaded_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        data["status"] = self.status.value
        if self.extraction_method:
            data["extraction_method"] = self.extraction_method.value
        return data

class LakehouseLayer(str, Enum):
    """
    Explicit architectural lakehouse tiers:
    - RAW: Unmodified binary assets (PDFs)
    - METADATA: Catalog and lifecycle tracking
    - EXTRACTED_PAGES: Cleaned page-level text extraction
    - CHUNKS: Token/character bounded passage chunks with provenance
    - CONTEXT: Structured semantic context (entities & relationships)
    - GRAPH_SYNC: Sync logs with Apache AGE graph database
    """
    RAW = "raw"
    METADATA = "metadata"
    EXTRACTED_PAGES = "extracted_pages"
    CHUNKS = "chunks"
    CONTEXT = "context"
    GRAPH_SYNC = "graph_sync"
