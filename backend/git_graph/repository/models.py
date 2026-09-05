"""
Repository Data Models
======================
Pydantic contracts for repository source definitions, file metadata, and inventory.
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class RepoSource(BaseModel):
    repository_url: str
    branch: Optional[str] = "main"
    commit: Optional[str] = None
    subdirectory: Optional[str] = None

    @property
    def is_local(self) -> bool:
        """Check if repository_url points to a local directory."""
        clean = self.repository_url.strip()
        if clean.startswith("file://"):
            return True
        p = Path(clean)
        return p.exists() and p.is_dir()

    @property
    def repo_name(self) -> str:
        """Extract sanitized repository name from URL or local directory path."""
        clean = self.repository_url.strip().split("?")[0].rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        
        # Match github/gitlab/bitbucket style: https://github.com/owner/repo or git@github.com:owner/repo
        match = re.search(r'[:/]([^/:]+)/([^/:]+)$', clean)
        if match:
            name = match.group(2).strip()
            if name:
                return name
        
        # If it's a local path like "." or relative path
        if self.is_local or clean in {".", "./", ".\\"}:
            try:
                resolved_name = Path(clean).resolve().name
                if resolved_name and resolved_name not in {".", "", "/"}:
                    return resolved_name
            except Exception:
                pass

        # Fallback to last path component
        parts = clean.replace("\\", "/").split("/")
        candidate = parts[-1] if parts[-1] else "repository"
        if candidate in {".", "..", ""}:
            try:
                candidate = Path(clean).resolve().name or "repository"
            except Exception:
                candidate = "repository"
        return candidate

    @property
    def owner(self) -> Optional[str]:
        """Extract repository owner if available."""
        clean = self.repository_url.strip().split("?")[0].rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        match = re.search(r'[:/]([^/:]+)/([^/:]+)$', clean)
        if match:
            owner_candidate = match.group(1).split(":")[-1]
            return owner_candidate if owner_candidate else None
        return None

class FileInfo(BaseModel):
    relative_path: str
    filename: str
    extension: str
    file_type: str # SOURCE_CODE, CONFIG, DOCUMENTATION, DOCKER, DATABASE_SCHEMA, DATA, OTHER
    language: Optional[str] = None # Python, JavaScript, TypeScript, Markdown, JSON, YAML, TOML, SQL, Dockerfile, DockerCompose, etc.
    size_bytes: int = 0
    line_count: Optional[int] = 0
    is_test_file: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class RepoInventory(BaseModel):
    repo_source: RepoSource
    commit_sha: str
    workspace_path: str
    total_files: int = 0
    total_lines: int = 0
    total_size_bytes: int = 0
    languages: Dict[str, int] = Field(default_factory=dict)
    file_types: Dict[str, int] = Field(default_factory=dict)
    files: List[FileInfo] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["scanned_at"] = self.scanned_at.isoformat()
        return data
