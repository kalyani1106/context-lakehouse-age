"""
End-to-End Integration Tests for GitGraphPipeline
=================================================
"""

import time
import unittest
import tempfile
import shutil
from pathlib import Path

from backend.graph.age_client import AGEClient
from backend.git_graph.graph.git_graph_service import GitGraphService
from backend.git_graph.pipeline import GitGraphPipeline

class TestGitPipelineE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_graph_name = f"test_git_e2e_kg_{int(time.time()*1000)}"
        cls.age_client = AGEClient(graph_name=cls.test_graph_name)
        cls.service = GitGraphService(age_client=cls.age_client, graph_name=cls.test_graph_name)
        cls.pipeline = GitGraphPipeline(graph_service=cls.service)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_git_graph_pipeline_execution(self):
        # 1. Setup mock repository files
        (self.workspace / "api").mkdir()
        (self.workspace / "api" / "routes.py").write_text("""\"\"\"API Router\"\"\"
from fastapi import APIRouter
import psycopg2

router = APIRouter()

@router.get("/health")
def health():
    \"\"\"Check system health.\"\"\"
    return {"status": "ok"}
""", encoding="utf-8")

        (self.workspace / "services").mkdir()
        (self.workspace / "services" / "data_service.py").write_text("""\"\"\"Data Service\"\"\"
class DataService:
    \"\"\"Handles database queries.\"\"\"
    def __init__(self):
        self.connected = True

    def query_all(self):
        return []
""", encoding="utf-8")

        (self.workspace / "requirements.txt").write_text("fastapi>=0.110.0\npsycopg2-binary>=2.9.9\n", encoding="utf-8")
        (self.workspace / "Dockerfile").write_text("FROM python:3.11\nEXPOSE 8000\n", encoding="utf-8")
        (self.workspace / "docker-compose.yml").write_text("""version: '3.8'
services:
  age-db:
    image: apache/age:latest
    ports:
      - "5455:5432"
""", encoding="utf-8")
        (self.workspace / "README.md").write_text("""# Sample Git Project
Built with FastAPI, Apache AGE, and PostgreSQL.
## Architecture
Implements Knowledge Graph analytics.
""", encoding="utf-8")

        # 2. Run Pipeline Analysis (First Run)
        res1 = self.pipeline.analyze(
            repository_url=str(self.workspace),
            branch="main"
        )

        self.assertEqual(res1.status, "COMPLETED")
        self.assertEqual(res1.files_scanned, 6)
        self.assertGreater(res1.entities_extracted, 10)
        self.assertGreater(res1.relationships_extracted, 10)
        self.assertGreater(res1.nodes_created, 10)
        self.assertGreater(res1.edges_created, 10)
        self.assertGreater(res1.duration_seconds, 0)

        # 3. Query Apache AGE for Graph Data
        graph_data = self.service.get_repository_graph(repo_name=res1.repository_name)
        self.assertGreaterEqual(len(graph_data["nodes"]), 10)
        self.assertGreaterEqual(len(graph_data["edges"]), 10)

        # 4. Verify Line-Level Provenance Traceability
        data_svc_prov = self.service.get_entity_provenance("DataService")
        self.assertEqual(data_svc_prov["name"], "DataService")
        self.assertEqual(data_svc_prov["entity_type"], "Class")
        self.assertEqual(data_svc_prov["file_path"], "services/data_service.py")
        self.assertEqual(data_svc_prov["start_line"], 2)
        self.assertIn("class DataService", data_svc_prov["source_snippet"])

        # 5. Test Idempotent Repeated Ingestion
        res2 = self.pipeline.analyze(
            repository_url=str(self.workspace),
            branch="main"
        )
        self.assertEqual(res2.nodes_created, 0) # No new duplicate nodes created!
        self.assertEqual(res2.edges_created, 0) # No new duplicate edges created!
        self.assertGreater(res2.nodes_existing, 10)
        self.assertGreater(res2.edges_existing, 10)

if __name__ == "__main__":
    unittest.main()
