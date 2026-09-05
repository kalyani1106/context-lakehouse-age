"""
Git Graph Configuration Settings
================================
"""

import os
from pathlib import Path
from typing import Set
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class GitGraphSettings(BaseModel):
    # Apache AGE Graph Name for Git Knowledge Graph
    GIT_AGE_GRAPH_NAME: str = Field(default_factory=lambda: os.getenv("GIT_AGE_GRAPH_NAME", "git_knowledge_graph"))
    
    # Temporary Cloned Workspaces Root
    TEMP_WORKSPACE_DIR: Path = Field(default_factory=lambda: Path(os.getenv("GIT_TEMP_DIR", "./.git_workspaces")).resolve())
    
    # Git Clone Defaults
    GIT_CLONE_DEPTH: int = Field(default=1)
    GIT_CLONE_TIMEOUT_SEC: int = Field(default=120)
    MAX_FILE_SIZE_BYTES: int = Field(default=2 * 1024 * 1024) # 2 MB limit per file
    
    # Excluded directories during repository scan
    EXCLUDED_DIRS: Set[str] = {
        ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
        "dist", "build", "target", "coverage", ".pytest_cache", ".mypy_cache",
        ".idea", ".vscode", ".tox", "site-packages", "egg-info"
    }

git_settings = GitGraphSettings()
