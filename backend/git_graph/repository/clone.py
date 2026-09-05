"""
Git Repository Cloner and Commit Resolver
=========================================
Safely clones remote Git repositories into isolated temporary workspaces,
resolves exact HEAD commit SHAs, and manages automatic cleanup.
"""

import os
import re
import shutil
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Generator
from contextlib import contextmanager

from backend.git_graph.config import git_settings
from backend.git_graph.repository.models import RepoSource

logger = logging.getLogger("git_cloner")

class GitCloneError(Exception):
    """Raised when repository cloning or commit resolution fails."""
    pass

def validate_repository_url(url: str) -> bool:
    """Validate format of Git URL or local path."""
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if clean.startswith("file://") or (Path(clean).exists() and Path(clean).is_dir()):
        return True
    # HTTP/HTTPS, SSH, git protocol formats
    patterns = [
        r'^https?://[a-zA-Z0-9_\-\.]+(/[a-zA-Z0-9_\-\.]+)+(\.git)?/?$',
        r'^git@[a-zA-Z0-9_\-\.]+:[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+(\.git)?/?$',
        r'^git://[a-zA-Z0-9_\-\.]+(/[a-zA-Z0-9_\-\.]+)+(\.git)?/?$'
    ]
    return any(re.match(p, clean) for p in patterns)

def resolve_local_commit_sha(repo_dir: Path) -> str:
    """Resolve commit SHA for a local git directory if available, else generate fallback."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
        sha = res.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    return "local-head-00000000"

def get_git_commit_sha(repo_dir: Path) -> str:
    """Run `git rev-parse HEAD` in a repository directory."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
            check=True
        )
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitCloneError(f"Failed to resolve commit SHA: {e.stderr or e.stdout}")
    except Exception as e:
        raise GitCloneError(f"Error resolving commit SHA: {str(e)}")

@contextmanager
def clone_repository(
    repo_source: RepoSource,
    cleanup: bool = True
) -> Generator[Tuple[Path, str], None, None]:
    """
    Context manager that clones a repository into a temporary directory,
    resolves the exact commit SHA, and automatically deletes the temporary directory on exit.

    Yields:
        (workspace_path: Path, commit_sha: str)
    """
    url = repo_source.repository_url.strip()
    if not validate_repository_url(url):
        raise GitCloneError(f"Invalid repository URL or path: '{url}'")

    # If it is a local directory
    if repo_source.is_local:
        clean_path = url[7:] if url.startswith("file://") else url
        local_dir = Path(clean_path).resolve()
        if not local_dir.exists() or not local_dir.is_dir():
            raise GitCloneError(f"Local directory does not exist: '{local_dir}'")
        
        target_path = local_dir
        if repo_source.subdirectory:
            target_path = local_dir / repo_source.subdirectory
            if not target_path.exists() or not target_path.is_dir():
                raise GitCloneError(f"Subdirectory '{repo_source.subdirectory}' not found in '{local_dir}'")
        
        sha = repo_source.commit or resolve_local_commit_sha(local_dir)
        logger.info(f"Using local repository at {target_path} (commit: {sha})")
        yield target_path, sha
        return

    # Remote Git repository
    git_settings.TEMP_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix=f"git_graph_{repo_source.repo_name}_", dir=str(git_settings.TEMP_WORKSPACE_DIR))
    temp_path = Path(temp_dir).resolve()

    try:
        clone_cmd = ["git", "clone", "--depth", str(git_settings.GIT_CLONE_DEPTH)]
        if repo_source.branch:
            clone_cmd.extend(["--branch", repo_source.branch])
        clone_cmd.extend([url, str(temp_path)])

        logger.info(f"Cloning {url} (branch: {repo_source.branch}) into {temp_path}")
        
        res = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=git_settings.GIT_CLONE_TIMEOUT_SEC
        )
        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            # If shallow branch clone failed, retry without branch restriction
            if repo_source.branch and "not found" in err_msg.lower():
                logger.warning(f"Branch '{repo_source.branch}' not found. Retrying default branch clone...")
                shutil.rmtree(str(temp_path), ignore_errors=True)
                temp_path.mkdir(parents=True, exist_ok=True)
                retry_cmd = ["git", "clone", "--depth", str(git_settings.GIT_CLONE_DEPTH), url, str(temp_path)]
                res_retry = subprocess.run(
                    retry_cmd,
                    capture_output=True,
                    text=True,
                    timeout=git_settings.GIT_CLONE_TIMEOUT_SEC
                )
                if res_retry.returncode != 0:
                    raise GitCloneError(f"Git clone failed: {res_retry.stderr.strip() or res_retry.stdout.strip()}")
            else:
                raise GitCloneError(f"Git clone failed: {err_msg}")

        # If specific commit requested, checkout that commit
        if repo_source.commit:
            fetch_res = subprocess.run(
                ["git", "checkout", repo_source.commit],
                cwd=str(temp_path),
                capture_output=True,
                text=True,
                timeout=30
            )
            if fetch_res.returncode != 0:
                logger.warning(f"Could not checkout specific commit '{repo_source.commit}'. Using cloned HEAD.")

        # Resolve exact commit SHA
        commit_sha = get_git_commit_sha(temp_path)
        logger.info(f"Successfully cloned {url}. Resolved commit SHA: {commit_sha}")

        workspace_target = temp_path
        if repo_source.subdirectory:
            sub_path = temp_path / repo_source.subdirectory
            if not sub_path.exists() or not sub_path.is_dir():
                raise GitCloneError(f"Subdirectory '{repo_source.subdirectory}' not found in repository.")
            workspace_target = sub_path

        yield workspace_target, commit_sha

    finally:
        if cleanup and temp_path.exists():
            try:
                # Handle Windows readonly git files during deletion
                def handle_remove_readonly(func, path, exc):
                    import stat
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(str(temp_path), onerror=handle_remove_readonly)
                logger.info(f"Cleaned up temporary workspace: {temp_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanly delete temp workspace {temp_path}: {e}")
