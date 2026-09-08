"""
Context, Entity, Relationship, and Provenance Schemas
=====================================================
Structured data contracts defining the semantic representation extracted from documents.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class Provenance(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    chunk_id: Optional[str] = None
    source_text: str

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class Entity(BaseModel):
    name: str
    canonical_name: str
    type: str = "Concept" # Technology, Concept, Organization, Person, Dataset, Algorithm, ResearchPaper, Framework, Layer
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    source: Provenance
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class Relationship(BaseModel):
    source_entity: str # Canonical name of source entity
    target_entity: str # Canonical name of target entity
    relationship_type: str # EXTENDS, USES, AUTHORED_BY, RELATED_TO, PART_OF, DEPENDS_ON, IMPLEMENTS, CREATES, MENTIONS, INTEGRATES_WITH
    description: Optional[str] = None
    source: Provenance
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class DocumentContext(BaseModel):
    document_id: str
    document_name: str
    extraction_method: str # OPENAI, GEMINI, HEURISTIC_NLP, MOCK
    summary: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["extracted_at"] = self.extracted_at.isoformat()
        return data
