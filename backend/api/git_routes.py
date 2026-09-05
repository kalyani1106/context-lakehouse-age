"""
REST API Router for Git Repository Knowledge Graph Pipeline
===========================================================
"""

import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from backend.git_graph.pipeline import GitGraphPipeline, GitAnalysisResult
from backend.git_graph.repository.clone import GitCloneError
from backend.git_graph.graph.graph_insights import GraphInsightsService, GraphInsights
from backend.git_graph.graph.graph_export import GraphExportService

git_router = APIRouter(prefix="/repositories", tags=["Git Knowledge Graph"])
pipeline = GitGraphPipeline()
insights_service = GraphInsightsService()
export_service = GraphExportService()

class AnalyzeRepoRequest(BaseModel):
    repository_url: str = Field(..., description="GitHub repository URL or local path (e.g. https://github.com/apache/age)")
    branch: Optional[str] = Field(default="main", description="Target branch name")
    commit: Optional[str] = Field(default=None, description="Optional commit SHA or tag")
    subdirectory: Optional[str] = Field(default=None, description="Optional subdirectory to restrict analysis")

class GitCypherQueryRequest(BaseModel):
    query: str
    columns: Optional[List[str]] = None

class GitCypherQueryResponse(BaseModel):
    query: str
    graph_name: str
    result_count: int
    results: List[Dict[str, Any]]

class AskQuestionRequest(BaseModel):
    question_id: str = Field(..., description="Question template ID (e.g. tech_stack, important_files, classes_methods, apis, entity_search, file_details, code_flows)")
    param: Optional[str] = Field(default=None, description="Optional parameter such as entity name or file path")

@git_router.post("/analyze", response_model=GitAnalysisResult, summary="Analyze Git repository and ingest into Apache AGE")
def analyze_repository(req: AnalyzeRepoRequest):
    """
    Clones/reads repository, discovers files, parses AST code & docs,
    extracts canonical entities/relationships with line-level provenance,
    and ingests property graph into Apache AGE idempotently.
    """
    try:
        result = pipeline.analyze(
            repository_url=req.repository_url,
            branch=req.branch,
            commit=req.commit,
            subdirectory=req.subdirectory,
            cleanup=True
        )
        return result
    except GitCloneError as e:
        raise HTTPException(status_code=400, detail=f"Git clone error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Repository analysis failed: {str(e)}")

@git_router.get("", summary="List all analyzed repositories in Apache AGE")
def list_repositories():
    """Retrieve all Repository nodes currently in the Git Knowledge Graph."""
    return pipeline.graph_service.list_repositories()

@git_router.get("/{repository_name}/graph", summary="Get knowledge graph for a repository")
def get_repository_graph(
    repository_name: str,
    limit: int = Query(default=300, ge=1, le=1000)
):
    """Retrieve vertices and edges for a specific repository from Apache AGE."""
    return pipeline.graph_service.get_repository_graph(repo_name=repository_name, limit=limit)

@git_router.get("/{repository_name}/insights", response_model=GraphInsights, summary="Get human-readable insights for a repository")
def get_repository_insights(repository_name: str):
    """
    Generate comprehensive, deterministic architectural insights, technology stack,
    ranked important files, class and function breakdowns, APIs, and execution flows.
    """
    try:
        return insights_service.get_repository_insights(repo_name=repository_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {str(e)}")

@git_router.post("/{repository_name}/ask", summary="Ask a structured architectural question about the knowledge graph")
def ask_repository_graph(repository_name: str, req: AskQuestionRequest):
    """
    Answers architectural and dependency queries directly against Apache AGE graph structures.
    """
    try:
        return insights_service.ask_question(
            repo_name=repository_name,
            question_id=req.question_id,
            param=req.param
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process graph question: {str(e)}")

@git_router.get("/{repository_name}/export", summary="Export knowledge graph in JSON, CSV, ZIP, or GraphML format")
def export_repository_graph(
    repository_name: str,
    format: str = Query(default="json", pattern="^(json|csv|zip|graphml)$", description="Export format: json, csv, zip, or graphml"),
    download: bool = Query(default=False, description="Set to true to trigger browser attachment download")
):
    """
    Export the repository's Apache AGE knowledge graph with full line-level provenance.
    """
    try:
        clean_name = repository_name.replace(" ", "_").replace("/", "_")
        if format == "json":
            data = export_service.export_json(repo_name=repository_name)
            if download:
                content = json.dumps(data, indent=2)
                return Response(
                    content=content,
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{clean_name}_knowledge_graph.json"'}
                )
            return data

        elif format == "csv":
            # Return ZIP containing both vertices.csv and edges.csv
            zip_bytes = export_service.export_zip(repo_name=repository_name)
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{clean_name}_csv_bundle.zip"'}
            )

        elif format == "zip":
            zip_bytes = export_service.export_zip(repo_name=repository_name)
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{clean_name}_knowledge_graph.zip"'}
            )

        elif format == "graphml":
            graphml_str = export_service.export_graphml(repo_name=repository_name)
            return Response(
                content=graphml_str,
                media_type="application/xml",
                headers={"Content-Disposition": f'attachment; filename="{clean_name}_knowledge_graph.graphml"'}
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export knowledge graph: {str(e)}")

@git_router.get("/provenance", summary="Get full line-level source code provenance for an entity")
def get_entity_provenance(
    entity_name: str = Query(..., description="Canonical ID or display name of the entity")
):
    """Fetch exact file, line number, commit SHA, and source code snippet from Apache AGE."""
    prov = pipeline.graph_service.get_entity_provenance(entity_name)
    if "error" in prov:
        raise HTTPException(status_code=404, detail=prov["error"])
    return prov

@git_router.post("/query", response_model=GitCypherQueryResponse, summary="Execute openCypher query against Git Knowledge Graph")
def execute_git_cypher_query(req: GitCypherQueryRequest):
    """Execute raw openCypher query against Apache AGE for the Git Knowledge Graph."""
    try:
        results = pipeline.graph_service.age_client.execute_cypher(
            cypher_query=req.query,
            columns=req.columns,
            graph_name=pipeline.graph_service.graph_name
        )
        return GitCypherQueryResponse(
            query=req.query,
            graph_name=pipeline.graph_service.graph_name,
            result_count=len(results),
            results=results
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher execution failed: {str(e)}")

@git_router.get("/stats", summary="Get Git Knowledge Graph statistics")
def get_git_graph_stats():
    """Return total node count, edge count, and label breakdown from Apache AGE."""
    return pipeline.graph_service.get_graph_stats()
