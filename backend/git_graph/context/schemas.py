"""
Git Graph Semantic Schemas and Provenance Contracts
====================================================
Structured data contracts defining entities, directed relationships,
line-level source code provenance, and repository context.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class GitProvenance(BaseModel):
    repository_url: str
    repository_name: str
    branch: str = "main"
    commit_sha: str
    file_path: Optional[str] = None # Relative path in repository (e.g. "graph/age_client.py")
    start_line: Optional[int] = None # 1-indexed start line
    end_line: Optional[int] = None # 1-indexed end line
    source_snippet: Optional[str] = None # Raw source code snippet (up to 400 chars)
    extraction_method: str = "STRUCTURAL_AST" # STRUCTURAL_AST, CONFIG_PARSER, DOCS_PARSER, LLM_SEMANTIC

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class GitGraphEntity(BaseModel):
    canonical_id: str # Stable identifier (e.g. repo:name:file:path:class:ClassName)
    name: str # Display name
    entity_type: str # Repository, Directory, File, Module, Class, Function, Method, Library, Technology, API, Service, Table, Concept
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: GitProvenance
    aliases: List[str] = Field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class GitGraphRelationship(BaseModel):
    source_canonical_id: str
    target_canonical_id: str
    relationship_type: str # CONTAINS, DEFINES, IMPORTS, DEPENDS_ON, CALLS, IMPLEMENTED_BY, CONNECTS_TO, USES, DESCRIBES, EXTENDS
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: GitProvenance
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class GitRepoContext(BaseModel):
    repository_name: str
    repository_url: str
    branch: str = "main"
    commit_sha: str
    entities: List[GitGraphEntity] = Field(default_factory=list)
    relationships: List[GitGraphRelationship] = Field(default_factory=list)
    inventory_summary: Dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["extracted_at"] = self.extracted_at.isoformat()
        return data
