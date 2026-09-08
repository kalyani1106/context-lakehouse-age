"""
Context Engine Data Models & Contracts
======================================
Structured schemas for query intent, retrieval modes, candidate context items,
rich citations, scoring, and assembled response payloads.
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    ARCHITECTURE = "ARCHITECTURE"
    AUTHENTICATION = "AUTHENTICATION"
    API_ROUTES = "API_ROUTES"
    DEPENDENCY = "DEPENDENCY"
    DATA_FLOW = "DATA_FLOW"
    SCHEMA = "SCHEMA"
    GENERAL = "GENERAL"


class RetrievalMode(str, Enum):
    HYBRID = "hybrid"
    GRAPH = "graph"
    SEMANTIC = "semantic"


class ContextType(str, Enum):
    ENTITY = "ENTITY"
    RELATIONSHIP = "RELATIONSHIP"
    SUBGRAPH = "SUBGRAPH"
    CHUNK = "CHUNK"
    FILE = "FILE"
    METADATA = "METADATA"


class ProvenanceCitation(BaseModel):
    source_type: str = "document"  # "document" or "git"
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    page_number: Optional[int] = None
    repo_name: Optional[str] = None
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    commit_hash: Optional[str] = None
    chunk_id: Optional[str] = None
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ContextItem(BaseModel):
    id: str
    type: ContextType
    title: str
    content: str
    score: float = 0.0
    graph_score: float = 0.0
    semantic_score: float = 0.0
    provenance_score: float = 0.0
    provenance: Optional[ProvenanceCitation] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class QueryAnalysisResult(BaseModel):
    raw_query: str
    intent: QueryIntent = QueryIntent.GENERAL
    extracted_entities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    detected_targets: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["intent"] = self.intent.value
        return data


class RetrievalStats(BaseModel):
    mode: str = "hybrid"
    nodes_retrieved: int = 0
    edges_retrieved: int = 0
    chunks_retrieved: int = 0
    total_candidates: int = 0
    final_items_count: int = 0
    total_tokens_estimated: int = 0
    retrieval_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ContextQueryRequest(BaseModel):
    query: str
    repo_name: Optional[str] = None
    doc_name: Optional[str] = None
    document_id: Optional[str] = None
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = 10
    max_context_tokens: int = 4000
    graph_weight: float = 0.5
    semantic_weight: float = 0.3
    provenance_weight: float = 0.2
    traversal_depth: int = 2
    include_raw_chunks: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["mode"] = self.mode.value
        return data


class ContextQueryResponse(BaseModel):
    query: str
    query_analysis: QueryAnalysisResult
    items: List[ContextItem] = Field(default_factory=list)
    assembled_context: str
    citations: List[ProvenanceCitation] = Field(default_factory=list)
    stats: RetrievalStats

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
