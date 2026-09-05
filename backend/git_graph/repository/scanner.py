"""
Repository File Scanner and Inventory Builder
=============================================
Recursively scans repository workspaces, ignores build artifacts and dependencies,
classifies file types and programming languages, and compiles structured inventories.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from backend.git_graph.config import git_settings
from backend.git_graph.repository.models import RepoSource, FileInfo, RepoInventory

logger = logging.getLogger("repo_scanner")

LANGUAGE_EXTENSION_MAP: Dict[str, Tuple[str, str]] = {
    # extension -> (Language, FileType)
    ".py": ("Python", "SOURCE_CODE"),
    ".pyi": ("Python", "SOURCE_CODE"),
    ".js": ("JavaScript", "SOURCE_CODE"),
    ".jsx": ("JavaScript", "SOURCE_CODE"),
    ".mjs": ("JavaScript", "SOURCE_CODE"),
    ".cjs": ("JavaScript", "SOURCE_CODE"),
    ".ts": ("TypeScript", "SOURCE_CODE"),
    ".tsx": ("TypeScript", "SOURCE_CODE"),
    ".mts": ("TypeScript", "SOURCE_CODE"),
    ".cts": ("TypeScript", "SOURCE_CODE"),
    ".java": ("Java", "SOURCE_CODE"),
    ".go": ("Go", "SOURCE_CODE"),
    ".rs": ("Rust", "SOURCE_CODE"),
    ".cpp": ("C++", "SOURCE_CODE"),
    ".c": ("C", "SOURCE_CODE"),
    ".h": ("C/C++ Header", "SOURCE_CODE"),
    ".cs": ("C#", "SOURCE_CODE"),
    ".rb": ("Ruby", "SOURCE_CODE"),
    ".php": ("PHP", "SOURCE_CODE"),
    ".sql": ("SQL", "DATABASE_SCHEMA"),
    ".md": ("Markdown", "DOCUMENTATION"),
    ".markdown": ("Markdown", "DOCUMENTATION"),
    ".rst": ("reStructuredText", "DOCUMENTATION"),
    ".json": ("JSON", "CONFIG"),
    ".yaml": ("YAML", "CONFIG"),
    ".yml": ("YAML", "CONFIG"),
    ".toml": ("TOML", "CONFIG"),
    ".ini": ("INI", "CONFIG"),
    ".cfg": ("Config", "CONFIG"),
    ".conf": ("Config", "CONFIG"),
    ".env": ("Environment", "CONFIG"),
    ".sh": ("Shell", "SCRIPT"),
    ".bash": ("Shell", "SCRIPT"),
    ".ps1": ("PowerShell", "SCRIPT"),
    ".bat": ("Batch", "SCRIPT"),
    ".html": ("HTML", "DOCUMENTATION"),
    ".csv": ("CSV", "DATA"),
    ".tsv": ("TSV", "DATA"),
}

SPECIAL_FILENAMES: Dict[str, Tuple[str, str]] = {
    "dockerfile": ("Dockerfile", "DOCKER"),
    "docker-compose.yml": ("DockerCompose", "DOCKER"),
    "docker-compose.yaml": ("DockerCompose", "DOCKER"),
    "compose.yml": ("DockerCompose", "DOCKER"),
    "compose.yaml": ("DockerCompose", "DOCKER"),
    "requirements.txt": ("Requirements", "CONFIG"),
    "package.json": ("PackageJSON", "CONFIG"),
    "pyproject.toml": ("PyProjectTOML", "CONFIG"),
    "setup.py": ("SetupPy", "CONFIG"),
    "makefile": ("Makefile", "CONFIG"),
    ".gitignore": ("GitIgnore", "CONFIG"),
    ".dockerignore": ("DockerIgnore", "CONFIG"),
    "readme.md": ("Markdown", "DOCUMENTATION"),
    "readme": ("Text", "DOCUMENTATION"),
}

class RepositoryScanner:
    def __init__(self, excluded_dirs: Optional[set[str]] = None, max_file_size: Optional[int] = None):
        self.excluded_dirs = excluded_dirs or git_settings.EXCLUDED_DIRS
        self.max_file_size = max_file_size or git_settings.MAX_FILE_SIZE_BYTES

    def should_ignore_dir(self, dir_name: str) -> bool:
        """Check if directory name matches ignore criteria."""
        lower = dir_name.lower().strip()
        if lower.startswith(".") and lower not in {".github"}:
            return True
        return lower in self.excluded_dirs

    def classify_file(self, file_path: Path, relative_str: str) -> Tuple[str, str, bool]:
        """
        Classify language, file_type, and is_test_file for a given file.
        Returns: (language, file_type, is_test_file)
        """
        filename = file_path.name.lower()
        ext = file_path.suffix.lower()

        # Check special exact filenames first
        if filename in SPECIAL_FILENAMES:
            lang, ftype = SPECIAL_FILENAMES[filename]
        elif filename.startswith("dockerfile"):
            lang, ftype = ("Dockerfile", "DOCKER")
        elif "docker-compose" in filename or "compose." in filename:
            lang, ftype = ("DockerCompose", "DOCKER")
        elif filename.startswith("requirements") and ext == ".txt":
            lang, ftype = ("Requirements", "CONFIG")
        elif ext in LANGUAGE_EXTENSION_MAP:
            lang, ftype = LANGUAGE_EXTENSION_MAP[ext]
        else:
            lang, ftype = ("Unknown", "OTHER")

        # Check if test file
        rel_lower = relative_str.lower().replace("\\", "/")
        is_test = (
            filename.startswith("test_") or
            filename.endswith("_test.py") or
            filename.endswith(".test.js") or
            filename.endswith(".spec.js") or
            filename.endswith(".test.ts") or
            filename.endswith(".spec.ts") or
            "/tests/" in f"/{rel_lower}" or
            "/test/" in f"/{rel_lower}"
        )

        return lang, ftype, is_test

    def count_file_lines(self, file_path: Path) -> int:
        """Safely count lines in a text file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def scan(self, workspace_path: Path, repo_source: RepoSource, commit_sha: str) -> RepoInventory:
        """
        Walk workspace directory and compile comprehensive RepoInventory.
        """
        workspace = Path(workspace_path).resolve()
        files: List[FileInfo] = []
        languages: Dict[str, int] = {}
        file_types: Dict[str, int] = {}
        total_size = 0
        total_lines = 0

        for root, dirs, filenames in os.walk(workspace):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if not self.should_ignore_dir(d)]

            for fname in filenames:
                full_path = Path(root) / fname
                try:
                    rel_path = full_path.relative_to(workspace).as_posix()
                except ValueError:
                    rel_path = str(full_path)

                try:
                    size = full_path.stat().st_size
                except Exception:
                    size = 0

                # Skip files exceeding size limit
                if size > self.max_file_size:
                    logger.debug(f"Skipping oversized file ({size} bytes): {rel_path}")
                    continue

                lang, ftype, is_test = self.classify_file(full_path, rel_path)
                lines = self.count_file_lines(full_path) if ftype in {"SOURCE_CODE", "CONFIG", "DOCUMENTATION", "DOCKER", "DATABASE_SCHEMA", "SCRIPT"} else 0

                info = FileInfo(
                    relative_path=rel_path,
                    filename=fname,
                    extension=full_path.suffix.lower(),
                    file_type=ftype,
                    language=lang,
                    size_bytes=size,
                    line_count=lines,
                    is_test_file=is_test
                )
                files.append(info)

                languages[lang] = languages.get(lang, 0) + 1
                file_types[ftype] = file_types.get(ftype, 0) + 1
                total_size += size
                total_lines += lines

        inventory = RepoInventory(
            repo_source=repo_source,
            commit_sha=commit_sha,
            workspace_path=str(workspace),
            total_files=len(files),
            total_lines=total_lines,
            total_size_bytes=total_size,
            languages=languages,
            file_types=file_types,
            files=files
        )
        logger.info(f"Scanned {len(files)} files ({total_lines} lines) in {workspace}")
        return inventory
