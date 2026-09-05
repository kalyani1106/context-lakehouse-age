"""
Integration Tests for FastAPI Git Graph Endpoints
=================================================
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from backend.api.app import app

class TestGitAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_git_api_analyze_and_query_flow(self):
        # Create minimal repository structure
        (self.workspace / "api").mkdir()
        (self.workspace / "api" / "app.py").write_text("""\"\"\"API File\"\"\"
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
def get_items():
    return [1, 2, 3]
""", encoding="utf-8")
        (self.workspace / "requirements.txt").write_text("fastapi>=0.110.0\n", encoding="utf-8")
        (self.workspace / "README.md").write_text("# API Service\nBuilt with FastAPI.\n", encoding="utf-8")

        # 1. Test POST /repositories/analyze
        res = self.client.post("/repositories/analyze", json={
            "repository_url": str(self.workspace),
            "branch": "main"
        })
        self.assertEqual(res.status_code, 200, msg=res.text)
        data = res.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertGreaterEqual(data["files_scanned"], 3)
        self.assertGreaterEqual(data["entities_extracted"], 5)
        repo_name = data["repository_name"]

        # 2. Test GET /repositories
        list_res = self.client.get("/repositories")
        self.assertEqual(list_res.status_code, 200)
        repos = list_res.json()
        self.assertTrue(any(r.get("name") == repo_name for r in repos))
        target_repo = next(r for r in repos if r.get("name") == repo_name)
        self.assertTrue(target_repo.get("url") or target_repo.get("repository_url"))
        self.assertIn("branch", target_repo)
        self.assertIn("commit_sha", target_repo)

        # 3. Test GET /repositories/{repo_name}/graph
        graph_res = self.client.get(f"/repositories/{repo_name}/graph")
        self.assertEqual(graph_res.status_code, 200)
        gdata = graph_res.json()
        self.assertGreaterEqual(len(gdata["nodes"]), 5)
        self.assertGreaterEqual(len(gdata["edges"]), 4)

        # 4. Test GET /repositories/provenance
        prov_res = self.client.get("/repositories/provenance", params={"entity_name": "get_items"})
        self.assertEqual(prov_res.status_code, 200)
        pdata = prov_res.json()
        self.assertEqual(pdata["name"], "get_items")
        self.assertEqual(pdata["file_path"], "api/app.py")

        # 5. Test POST /repositories/query
        cypher_res = self.client.post("/repositories/query", json={
            "query": "MATCH (f:File) RETURN f LIMIT 10",
            "columns": ["f"]
        })
        self.assertEqual(cypher_res.status_code, 200)
        cdata = cypher_res.json()
        self.assertGreaterEqual(cdata["result_count"], 1)

        # 6. Test GET /repositories/stats
        stats_res = self.client.get("/repositories/stats")
        self.assertEqual(stats_res.status_code, 200)
        sdata = stats_res.json()
        self.assertGreaterEqual(sdata["total_nodes"], 1)

        # 7. Verify Health endpoint (backward compatibility)
        health_res = self.client.get("/health")
        self.assertEqual(health_res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
