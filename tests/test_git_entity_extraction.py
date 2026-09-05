"""
Unit Tests for Entity & Relationship Extraction and Canonical Normalization
===========================================================================
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from backend.git_graph.repository.models import RepoSource
from backend.git_graph.repository.scanner import RepositoryScanner
from backend.git_graph.context.normalizer import EntityNormalizer
from backend.git_graph.context.schemas import GitGraphEntity, GitGraphRelationship, GitProvenance
from backend.git_graph.context.extractor import GitGraphExtractor

class TestGitEntityExtraction(unittest.TestCase):
    def setUp(self):
        self.normalizer = EntityNormalizer()
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_canonical_id_generation(self):
        self.assertEqual(self.normalizer.repo_id("my-repo"), "repo:my-repo")
        self.assertEqual(self.normalizer.dir_id("my-repo", "src/api"), "repo:my-repo:dir:src/api")
        self.assertEqual(self.normalizer.file_id("my-repo", "src/app.py"), "repo:my-repo:file:src/app.py")
        self.assertEqual(self.normalizer.class_id("my-repo", "src/app.py", "AppService"), "repo:my-repo:file:src/app.py:class:AppService")
        self.assertEqual(self.normalizer.method_id("my-repo", "src/app.py", "AppService", "start"), "repo:my-repo:file:src/app.py:class:AppService:method:start")
        self.assertEqual(self.normalizer.function_id("my-repo", "src/app.py", "main"), "repo:my-repo:file:src/app.py:func:main")
        self.assertEqual(self.normalizer.library_id("psycopg2-binary"), "lib:psycopg2")
        self.assertEqual(self.normalizer.technology_id("postgres"), "tech:PostgreSQL")
        self.assertEqual(self.normalizer.concept_id("Knowledge Graph"), "concept:Knowledge Graph")

    def test_entity_and_rel_deduplication(self):
        prov = GitProvenance(repository_url="https://github.com/test/repo", repository_name="repo", commit_sha="abc1234")
        
        ent1 = GitGraphEntity(canonical_id="lib:fastapi", name="FastAPI", entity_type="Library", aliases=["fastapi"], provenance=prov)
        ent2 = GitGraphEntity(canonical_id="lib:fastapi", name="fastapi", entity_type="Library", aliases=["fastapi-web"], provenance=prov)
        
        rel1 = GitGraphRelationship(source_canonical_id="repo:repo:file:app.py", target_canonical_id="lib:fastapi", relationship_type="IMPORTS", provenance=prov, weight=1.0)
        rel2 = GitGraphRelationship(source_canonical_id="repo:repo:file:app.py", target_canonical_id="lib:fastapi", relationship_type="IMPORTS", provenance=prov, weight=1.0)
        
        # Need file entity so relationship isn't pruned
        file_ent = GitGraphEntity(canonical_id="repo:repo:file:app.py", name="app.py", entity_type="File", provenance=prov)

        dedup_ents, dedup_rels = self.normalizer.deduplicate_and_normalize([ent1, ent2, file_ent], [rel1, rel2])
        
        self.assertEqual(len(dedup_ents), 2)
        fastapi_ent = next(e for e in dedup_ents if e.canonical_id == "lib:fastapi")
        self.assertIn("fastapi", fastapi_ent.aliases)
        self.assertIn("fastapi-web", fastapi_ent.aliases)

        self.assertEqual(len(dedup_rels), 1)
        self.assertEqual(dedup_rels[0].weight, 1.5)

    def test_full_workspace_extraction(self):
        # Create test project files
        (self.workspace / "api").mkdir()
        (self.workspace / "api" / "app.py").write_text("""
import os
import fastapi
from graph.service import GraphService

class WebApp:
    def run(self):
        pass

def create_app():
    return WebApp()
""", encoding="utf-8")
        
        (self.workspace / "requirements.txt").write_text("fastapi>=0.110.0\npsycopg2-binary>=2.9.9\n", encoding="utf-8")
        (self.workspace / "README.md").write_text("# Test Repo\nPowered by Apache AGE and PostgreSQL.\n## Architecture\nUses Knowledge Graph.\n", encoding="utf-8")

        repo_src = RepoSource(repository_url="https://github.com/segmento/test-repo.git")
        scanner = RepositoryScanner()
        inventory = scanner.scan(self.workspace, repo_src, "commit-sha-999")

        extractor = GitGraphExtractor()
        context = extractor.extract(self.workspace, inventory)

        self.assertEqual(context.repository_name, "test-repo")
        self.assertEqual(context.commit_sha, "commit-sha-999")
        
        # Check entities
        cids = {e.canonical_id: e for e in context.entities}
        self.assertIn("repo:test-repo", cids)
        self.assertIn("repo:test-repo:dir:api", cids)
        self.assertIn("repo:test-repo:file:api/app.py", cids)
        self.assertIn("repo:test-repo:file:api/app.py:class:WebApp", cids)
        self.assertIn("repo:test-repo:file:api/app.py:class:WebApp:method:run", cids)
        self.assertIn("repo:test-repo:file:api/app.py:func:create_app", cids)
        self.assertIn("lib:fastapi", cids)
        self.assertIn("lib:psycopg2", cids)
        self.assertIn("tech:Apache AGE", cids)
        self.assertIn("tech:PostgreSQL", cids)
        self.assertIn("concept:Knowledge Graph", cids)

        # Check relationships
        rel_signatures = {(r.source_canonical_id, r.relationship_type, r.target_canonical_id) for r in context.relationships}
        self.assertIn(("repo:test-repo", "CONTAINS", "repo:test-repo:dir:api"), rel_signatures)
        self.assertIn(("repo:test-repo:dir:api", "CONTAINS", "repo:test-repo:file:api/app.py"), rel_signatures)
        self.assertIn(("repo:test-repo:file:api/app.py", "DEFINES", "repo:test-repo:file:api/app.py:class:WebApp"), rel_signatures)
        self.assertIn(("repo:test-repo:file:api/app.py:class:WebApp", "CONTAINS", "repo:test-repo:file:api/app.py:class:WebApp:method:run"), rel_signatures)
        self.assertIn(("repo:test-repo:file:api/app.py", "IMPORTS", "lib:fastapi"), rel_signatures)
        self.assertIn(("repo:test-repo:file:README.md", "DESCRIBES", "repo:test-repo"), rel_signatures)
        self.assertIn(("repo:test-repo:file:README.md", "DESCRIBES", "concept:Knowledge Graph"), rel_signatures)

        # Verify 100% provenance retention
        for e in context.entities:
            self.assertEqual(e.provenance.repository_name, "test-repo")
            self.assertEqual(e.provenance.commit_sha, "commit-sha-999")
            self.assertTrue(e.provenance.extraction_method)

        for r in context.relationships:
            self.assertEqual(r.provenance.repository_name, "test-repo")
            self.assertEqual(r.provenance.commit_sha, "commit-sha-999")

if __name__ == "__main__":
    unittest.main()
