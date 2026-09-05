"""
End-to-End Git Repository Knowledge Graph Pipeline
==================================================
Orchestrates Git clone, repository file discovery, AST & config parsing,
canonical normalization, and idempotent Apache AGE graph ingestion.
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from backend.git_graph.config import git_settings
from backend.git_graph.repository.models import RepoSource, RepoInventory
from backend.git_graph.repository.clone import clone_repository, GitCloneError
from backend.git_graph.repository.scanner import RepositoryScanner
from backend.git_graph.context.extractor import GitGraphExtractor
from backend.git_graph.context.schemas import GitRepoContext
from backend.git_graph.graph.git_graph_service import GitGraphService

logger = logging.getLogger("git_graph_pipeline")

class GitAnalysisResult(BaseModel):
    repository_name: str
    repository_url: str
    branch: str = "main"
    commit_sha: str
    status: str = "COMPLETED"
    files_scanned: int = 0
    lines_scanned: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    nodes_created: int = 0
    nodes_existing: int = 0
    edges_created: int = 0
    edges_existing: int = 0
    graph_name: str
    duration_seconds: float = 0.0
    languages: Dict[str, int] = Field(default_factory=dict)
    file_types: Dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["analyzed_at"] = self.analyzed_at.isoformat()
        return data

class GitGraphPipeline:
    def __init__(
        self,
        graph_service: Optional[GitGraphService] = None,
        scanner: Optional[RepositoryScanner] = None,
        extractor: Optional[GitGraphExtractor] = None
    ):
        self.graph_service = graph_service or GitGraphService()
        self.scanner = scanner or RepositoryScanner()
        self.extractor = extractor or GitGraphExtractor()

    def analyze(
        self,
        repository_url: str,
        branch: Optional[str] = "main",
        commit: Optional[str] = None,
        subdirectory: Optional[str] = None,
        cleanup: bool = True,
        progress_callback: Optional[Any] = None
    ) -> GitAnalysisResult:
        """
        Execute full pipeline:
        Clone -> Scan -> Extract -> Ingest Apache AGE -> Return Summary.
        """
        start_time = time.time()
        repo_source = RepoSource(
            repository_url=repository_url,
            branch=branch or "main",
            commit=commit,
            subdirectory=subdirectory
        )

        logger.info(f"Starting Git Graphify analysis for: {repository_url} (branch: {branch})")
        warnings = []

        if progress_callback:
            progress_callback(1, "1. Cloning repository")

        try:
            with clone_repository(repo_source, cleanup=cleanup) as (workspace_path, commit_sha):
                logger.info(f"Workspace prepared at {workspace_path} (commit: {commit_sha})")
                
                # 1. Scan Repository
                if progress_callback:
                    progress_callback(2, "2. Scanning files")
                inventory = self.scanner.scan(workspace_path, repo_source, commit_sha)
                if inventory.total_files == 0:
                    warnings.append("No indexable source or configuration files discovered in repository.")

                # 2. Extract Entities and Relationships with Provenance
                if progress_callback:
                    progress_callback(3, "3. Parsing source code")
                if progress_callback:
                    progress_callback(4, "4. Extracting entities and relationships")
                if progress_callback:
                    progress_callback(5, "5. Normalizing entities")
                context = self.extractor.extract(workspace_path, inventory)

                # 3. Ingest into Apache AGE
                if progress_callback:
                    progress_callback(6, "6. Ingesting into Apache AGE")
                ingest_summary = self.graph_service.ingest_repo_context(context)

                if progress_callback:
                    progress_callback(7, "7. Loading graph")

                duration = round(time.time() - start_time, 3)
                logger.info(f"Analysis completed in {duration}s for {repo_source.repo_name}")

                return GitAnalysisResult(
                    repository_name=context.repository_name,
                    repository_url=context.repository_url,
                    branch=context.branch,
                    commit_sha=context.commit_sha,
                    status="COMPLETED",
                    files_scanned=inventory.total_files,
                    lines_scanned=inventory.total_lines,
                    entities_extracted=len(context.entities),
                    relationships_extracted=len(context.relationships),
                    nodes_created=ingest_summary["nodes_created"],
                    nodes_existing=ingest_summary["nodes_existing"],
                    edges_created=ingest_summary["edges_created"],
                    edges_existing=ingest_summary["edges_existing"],
                    graph_name=self.graph_service.graph_name,
                    duration_seconds=duration,
                    languages=inventory.languages,
                    file_types=inventory.file_types,
                    warnings=warnings
                )

        except GitCloneError as e:
            logger.error(f"Clone error during analysis: {e}")
            raise e
        except Exception as e:
            logger.error(f"Pipeline error during analysis: {e}")
            raise e
