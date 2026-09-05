"""
Integration Tests for Apache AGE Git Knowledge Graph Service
============================================================
"""

import time
import unittest
from backend.graph.age_client import AGEClient
from backend.git_graph.graph.git_graph_service import GitGraphService
from backend.git_graph.context.schemas import GitRepoContext, GitGraphEntity, GitGraphRelationship, GitProvenance

class TestGitAgeGraphService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use isolated graph for test run
        cls.test_graph_name = f"test_git_kg_{int(time.time()*1000)}"
        cls.age_client = AGEClient(graph_name=cls.test_graph_name)
        cls.service = GitGraphService(age_client=cls.age_client, graph_name=cls.test_graph_name)

    def test_vertex_and_edge_ingestion_with_provenance(self):
        prov = GitProvenance(
            repository_url="https://github.com/segmento/test-service.git",
            repository_name="test-service",
            branch="main",
            commit_sha="a1b2c3d4",
            file_path="src/service.py",
            start_line=10,
            end_line=25,
            source_snippet="class TestService:\n    pass",
            extraction_method="STRUCTURAL_AST"
        )

        repo_ent = GitGraphEntity(
            canonical_id="repo:test-service",
            name="test-service",
            entity_type="Repository",
            provenance=prov
        )

        file_ent = GitGraphEntity(
            canonical_id="repo:test-service:file:src/service.py",
            name="service.py",
            entity_type="File",
            properties={"line_count": 50},
            provenance=prov
        )

        class_ent = GitGraphEntity(
            canonical_id="repo:test-service:file:src/service.py:class:TestService",
            name="TestService",
            entity_type="Class",
            provenance=prov
        )

        rel1 = GitGraphRelationship(
            source_canonical_id="repo:test-service",
            target_canonical_id="repo:test-service:file:src/service.py",
            relationship_type="CONTAINS",
            provenance=prov
        )

        rel2 = GitGraphRelationship(
            source_canonical_id="repo:test-service:file:src/service.py",
            target_canonical_id="repo:test-service:file:src/service.py:class:TestService",
            relationship_type="DEFINES",
            provenance=prov
        )

        ctx = GitRepoContext(
            repository_name="test-service",
            repository_url="https://github.com/segmento/test-service.git",
            commit_sha="a1b2c3d4",
            entities=[repo_ent, file_ent, class_ent],
            relationships=[rel1, rel2]
        )

        # 1. First Ingestion
        summary1 = self.service.ingest_repo_context(ctx)
        self.assertGreaterEqual(summary1["nodes_created"], 3)
        self.assertGreaterEqual(summary1["edges_created"], 2)

        # 2. Verify Graph Query
        graph_data = self.service.get_repository_graph(repo_name="test-service")
        self.assertGreaterEqual(len(graph_data["nodes"]), 3)
        self.assertGreaterEqual(len(graph_data["edges"]), 2)

        # 3. Verify Entity Provenance Resolution
        prov_data = self.service.get_entity_provenance("TestService")
        self.assertEqual(prov_data["name"], "TestService")
        self.assertEqual(prov_data["repository_name"], "test-service")
        self.assertEqual(prov_data["file_path"], "src/service.py")
        self.assertEqual(prov_data["start_line"], 10)
        self.assertEqual(prov_data["commit_sha"], "a1b2c3d4")
        self.assertIn("class TestService", prov_data["source_snippet"])

        # 4. Test Idempotency (repeated ingestion must not create duplicate nodes or edges)
        summary2 = self.service.ingest_repo_context(ctx)
        self.assertEqual(summary2["nodes_created"], 0)
        self.assertEqual(summary2["edges_created"], 0)
        self.assertEqual(summary2["nodes_existing"], 3)
        self.assertEqual(summary2["edges_existing"], 2)

    def test_repository_listing_metadata(self):
        # Ingest repository context with distinct repo name to ensure test isolation
        prov = GitProvenance(
            repository_url="https://github.com/segmento/listing-test-service.git",
            repository_name="listing-test-service",
            branch="main",
            commit_sha="a1b2c3d4",
            file_path="src/service.py",
            start_line=1,
            end_line=1,
            extraction_method="REPOSITORY_METADATA"
        )
        repo_ent = GitGraphEntity(
            canonical_id="repo:listing-test-service",
            name="listing-test-service",
            entity_type="Repository",
            properties={
                "url": "https://github.com/segmento/listing-test-service.git",
                "repository_url": "https://github.com/segmento/listing-test-service.git",
                "total_files": 10,
                "total_lines": 500
            },
            provenance=prov
        )
        ctx = GitRepoContext(
            repository_name="listing-test-service",
            repository_url="https://github.com/segmento/listing-test-service.git",
            commit_sha="a1b2c3d4",
            entities=[repo_ent],
            relationships=[]
        )
        self.service.ingest_repo_context(ctx)

        # Verify Repository Listing returns canonical metadata
        repos = self.service.list_repositories()
        self.assertTrue(any(r["name"] == "listing-test-service" for r in repos))
        target = next(r for r in repos if r["name"] == "listing-test-service")
        self.assertEqual(target["repository_name"], "listing-test-service")
        self.assertEqual(target["url"], "https://github.com/segmento/listing-test-service.git")
        self.assertEqual(target["repository_url"], "https://github.com/segmento/listing-test-service.git")
        self.assertEqual(target["branch"], "main")
        self.assertEqual(target["commit_sha"], "a1b2c3d4")
        self.assertFalse(target["is_legacy_temp"])

if __name__ == "__main__":
    unittest.main()
