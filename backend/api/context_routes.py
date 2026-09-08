"""
Context Engine API Routes
=========================
FastAPI routes exposing intelligent hybrid context retrieval, query analysis,
and citation tracebacks for downstream LLMs and frontends.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status

from backend.context_engine.models import (
    ContextQueryRequest,
    ContextQueryResponse,
)
from backend.context_engine.context_engine import ContextEngine
from backend.storage.lakehouse import LocalLakehouseStorageService
from backend.git_graph.graph.git_graph_service import GitGraphService

logger = logging.getLogger("context_routes")

context_router = APIRouter(prefix="/context", tags=["Context Engine"])
context_engine_instance = ContextEngine()


@context_router.post(
    "/query",
    response_model=ContextQueryResponse,
    summary="Query Intelligent Context Engine",
    description="Analyze natural language query, execute hybrid graph + semantic retrieval, rank items, and return token-budgeted assembled context with citations."
)
async def query_context_endpoint(request: ContextQueryRequest) -> ContextQueryResponse:
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter cannot be empty."
            )
        response = context_engine_instance.query_context(request)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /context/query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context engine retrieval failed: {str(e)}"
        )


@context_router.get(
    "/status",
    summary="Get Context Engine Status",
    description="Returns current status, indexed document count, and graph configurations."
)
async def get_context_engine_status() -> Dict[str, Any]:
    try:
        storage = LocalLakehouseStorageService()
        docs = storage.list_documents()
        
        git_service = GitGraphService()
        repos = git_service.list_repositories()

        return {
            "status": "healthy",
            "context_engine_ready": True,
            "indexed_documents_count": len(docs),
            "indexed_repositories_count": len(repos),
            "repositories": repos,
            "git_graph_name": git_service.graph_name,
            "doc_graph_name": storage.root_dir.name,
        }
    except Exception as e:
        logger.error(f"Error in /context/status: {e}")
        return {
            "status": "degraded",
            "context_engine_ready": True,
            "error": str(e)
        }
