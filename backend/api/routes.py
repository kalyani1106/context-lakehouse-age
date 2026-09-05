"""
REST API Router for PDF Context Lakehouse & Apache AGE Knowledge Graph
======================================================================
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from backend.pipeline import PDFContextPipeline
from backend.storage.models import DocumentMetadata, ProcessingStatus
from backend.graph.age_client import AGEClient
from backend.graph.graph_service import GraphService

router = APIRouter()
pipeline = PDFContextPipeline()

class CypherQueryRequest(BaseModel):
    query: str
    columns: Optional[List[str]] = None

class CypherQueryResponse(BaseModel):
    query: str
    graph_name: str
    result_count: int
    results: List[Dict[str, Any]]

@router.post("/documents/upload", response_model=DocumentMetadata, summary="Upload a PDF document to Lakehouse (SHA-256 deduplicated)")
async def upload_document(
    file: UploadFile = File(...)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted.")
    
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    try:
        metadata = pipeline.upload_pdf(
            filename=file.filename,
            file_bytes=file_bytes
        )
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/documents", response_model=List[DocumentMetadata], summary="List all documents in the Lakehouse")
def list_documents():
    return pipeline.storage.list_documents()

@router.get("/documents/{document_id}", response_model=DocumentMetadata, summary="Get metadata for a specific document")
def get_document_metadata(document_id: str):
    meta = pipeline.storage.get_metadata(document_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return meta

@router.post("/documents/{document_id}/process", summary="Execute PDF -> Context -> Apache AGE pipeline (Idempotent)")
def process_document(
    document_id: str,
    provider: Optional[str] = Query(default=None, description="LLM provider: 'openai', 'gemini', 'heuristic', or 'auto'"),
    reprocess: bool = Query(default=False, description="Force re-extraction and graph synchronization even if already COMPLETED")
):
    meta = pipeline.storage.get_metadata(document_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    try:
        result = pipeline.process_document(
            document_id=document_id,
            force_provider=provider,
            reprocess=reprocess
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/documents/{document_id}/pages", summary="Get extracted pages from Lakehouse")
def get_document_pages(document_id: str):
    pages = pipeline.storage.get_extracted_pages(document_id)
    if pages is None:
        raise HTTPException(status_code=404, detail=f"No extracted pages found for document {document_id}.")
    return {"document_id": document_id, "total_pages": len(pages), "pages": pages}

@router.get("/documents/{document_id}/chunks", summary="Get chunked passages from Lakehouse")
def get_document_chunks(document_id: str):
    chunks = pipeline.storage.get_chunks(document_id)
    if chunks is None:
        raise HTTPException(status_code=404, detail=f"No chunks found for document {document_id}.")
    return {"document_id": document_id, "total_chunks": len(chunks), "chunks": chunks}

@router.get("/documents/{document_id}/context", summary="Get structured context (entities & relationships) from Lakehouse")
def get_document_context(document_id: str):
    context = pipeline.storage.get_context(document_id)
    if context is None:
        raise HTTPException(status_code=404, detail=f"No context generated yet for document {document_id}.")
    return context

@router.get("/documents/{document_id}/graph", summary="Get document subgraph directly from Apache AGE")
def get_document_graph(document_id: str):
    meta = pipeline.storage.get_metadata(document_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return pipeline.graph_service.get_document_subgraph(document_id)

@router.delete("/documents/{document_id}", summary="Delete document from Lakehouse")
def delete_document(document_id: str):
    deleted = pipeline.storage.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return {"document_id": document_id, "deleted": True}

# ----------------- Apache AGE Knowledge Graph Endpoints -----------------

@router.get("/graph/entities", summary="Query entities from Apache AGE")
def get_graph_entities(
    entity_type: Optional[str] = Query(default=None, description="Filter by entity label (e.g. Technology, Concept, Organization)"),
    search: Optional[str] = Query(default=None, description="Search by name"),
    limit: int = Query(default=200, ge=1, le=1000)
):
    return pipeline.graph_service.get_all_entities(entity_type=entity_type, search=search, limit=limit)

@router.get("/graph/relationships", summary="Query relationships from Apache AGE")
def get_graph_relationships(
    relationship_type: Optional[str] = Query(default=None, description="Filter by relation type (e.g. EXTENDS, USES, PART_OF)"),
    limit: int = Query(default=200, ge=1, le=1000)
):
    return pipeline.graph_service.get_all_relationships(rel_type=relationship_type, limit=limit)

@router.get("/graph/full", summary="Get complete knowledge graph for visual rendering")
def get_full_knowledge_graph(
    limit: int = Query(default=300, ge=1, le=1000)
):
    return pipeline.graph_service.get_full_graph(limit=limit)

@router.post("/graph/query", response_model=CypherQueryResponse, summary="Execute raw Cypher query against Apache AGE")
def execute_cypher_query(req: CypherQueryRequest):
    try:
        results = pipeline.graph_service.age_client.execute_cypher(
            cypher_query=req.query,
            columns=req.columns,
            graph_name=pipeline.graph_service.graph_name
        )
        return CypherQueryResponse(
            query=req.query,
            graph_name=pipeline.graph_service.graph_name,
            result_count=len(results),
            results=results
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher execution failed: {str(e)}")

@router.get("/graph/provenance", summary="Get complete document provenance for an entity")
def get_entity_provenance(
    entity_name: str = Query(..., description="Canonical or exact name of the entity")
):
    prov = pipeline.graph_service.get_entity_provenance(entity_name)
    if "error" in prov:
        raise HTTPException(status_code=404, detail=prov["error"])
    return prov

@router.get("/graph/stats", summary="Get graph statistics from Apache AGE")
def get_graph_stats():
    return pipeline.graph_service.get_graph_stats()

@router.get("/health", summary="Check system health and AGE database status")
def health_check():
    db_health = pipeline.graph_service.age_client.test_connection()
    doc_count = len(pipeline.storage.list_documents())
    return {
        "status": "ok",
        "database": db_health,
        "lakehouse_documents": doc_count,
        "storage_root": str(pipeline.storage.root_dir)
    }
