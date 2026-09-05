"""
Unit Tests for Repository Management: Clone and Scanner
========================================================
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from backend.git_graph.repository.models import RepoSource, FileInfo, RepoInventory
from backend.git_graph.repository.clone import validate_repository_url, clone_repository, GitCloneError
from backend.git_graph.repository.scanner import RepositoryScanner

class TestGitCloneAndScanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_repository_url_validation(self):
        self.assertTrue(validate_repository_url("https://github.com/apache/age"))
        self.assertTrue(validate_repository_url("https://github.com/apache/age.git"))
        self.assertTrue(validate_repository_url("git@github.com:apache/age.git"))
        self.assertTrue(validate_repository_url(str(self.workspace)))
        self.assertFalse(validate_repository_url(""))
        self.assertFalse(validate_repository_url("not_a_valid_url"))

    def test_repo_source_properties(self):
        src1 = RepoSource(repository_url="https://github.com/segmento/context-lakehouse.git")
        self.assertEqual(src1.repo_name, "context-lakehouse")
        self.assertEqual(src1.owner, "segmento")
        self.assertFalse(src1.is_local)

        src2 = RepoSource(repository_url=str(self.workspace))
        self.assertTrue(src2.is_local)

    def test_github_url_identity_and_preservation(self):
        urls = [
            ("https://github.com/kalyani1106/context-lakehouse-age", "context-lakehouse-age", "kalyani1106"),
            ("https://github.com/kalyani1106/context-lakehouse-age.git", "context-lakehouse-age", "kalyani1106"),
            ("https://github.com/kalyani1106/context-lakehouse-age/", "context-lakehouse-age", "kalyani1106"),
            ("git@github.com:kalyani1106/context-lakehouse-age.git", "context-lakehouse-age", "kalyani1106"),
            ("https://gitlab.com/group/subgroup/context-lakehouse-age.git", "context-lakehouse-age", "subgroup")
        ]
        for url, expected_name, expected_owner in urls:
            src = RepoSource(repository_url=url)
            self.assertEqual(src.repo_name, expected_name)
            self.assertEqual(src.owner, expected_owner)
            self.assertEqual(src.repository_url, url)
            self.assertFalse(src.is_local)
            # Ensure temporary clone directory is never part of repo_name
            self.assertFalse(src.repo_name.startswith("tmp"))

    def test_local_clone_and_scan(self):
        # Create dummy project structure
        (self.workspace / "api").mkdir()
        (self.workspace / "api" / "app.py").write_text("print('hello world')\n", encoding="utf-8")
        (self.workspace / "requirements.txt").write_text("fastapi>=0.110.0\npsycopg2-binary>=2.9.9\n", encoding="utf-8")
        (self.workspace / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
        (self.workspace / "docker-compose.yml").write_text("version: '3.8'\nservices:\n  db:\n    image: postgres\n", encoding="utf-8")
        (self.workspace / "README.md").write_text("# Project Title\nA sample project for testing.\n", encoding="utf-8")
        
        # Ignored directory
        (self.workspace / "__pycache__").mkdir()
        (self.workspace / "__pycache__" / "app.cpython-314.pyc").write_bytes(b"\x00\x01\x02")

        repo_source = RepoSource(repository_url=str(self.workspace))
        
        with clone_repository(repo_source) as (ws_path, commit_sha):
            self.assertEqual(str(ws_path), str(self.workspace))
            self.assertTrue(commit_sha)

            scanner = RepositoryScanner()
            inventory = scanner.scan(ws_path, repo_source, commit_sha)

            self.assertEqual(inventory.total_files, 5) # app.py, requirements.txt, Dockerfile, docker-compose.yml, README.md
            self.assertIn("Python", inventory.languages)
            self.assertIn("Requirements", inventory.languages)
            self.assertIn("Dockerfile", inventory.languages)
            self.assertIn("DockerCompose", inventory.languages)
            self.assertIn("Markdown", inventory.languages)

            py_file = next(f for f in inventory.files if f.filename == "app.py")
            self.assertEqual(py_file.file_type, "SOURCE_CODE")
            self.assertEqual(py_file.line_count, 1)

if __name__ == "__main__":
    unittest.main()
