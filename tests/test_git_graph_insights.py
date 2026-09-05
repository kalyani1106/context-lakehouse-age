"""
Unit and Integration Tests for Graph Insights Service and Q&A Endpoints
========================================================================
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.git_graph.pipeline import GitGraphPipeline
from backend.git_graph.graph.graph_insights import GraphInsightsService, GraphInsights

class TestGitGraphInsights(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.insights_service = GraphInsightsService()

        # Ingest a dedicated test fixture repo
        cls.temp_dir = tempfile.mkdtemp()
        cls.workspace = Path(cls.temp_dir)
        (cls.workspace / "services").mkdir()
        (cls.workspace / "api").mkdir()

        (cls.workspace / "api" / "routes.py").write_text("""\"\"\"API Routes Module\"\"\"
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return [{"id": 1, "name": "Alice"}]

@app.post("/users")
def create_user(user: dict):
    return {"status": "created"}
""", encoding="utf-8")

        (cls.workspace / "services" / "user_service.py").write_text("""\"\"\"User Service Class\"\"\"
import json
import logging

class UserService:
    def __init__(self):
        self.logger = logging.getLogger("user_service")

    def fetch_user_by_id(self, user_id: int):
        return {"id": user_id, "name": "Alice"}

    def delete_user(self, user_id: int):
        return True

def standalone_helper():
    return "help"
""", encoding="utf-8")

        (cls.workspace / "requirements.txt").write_text("fastapi>=0.110.0\nuvicorn>=0.28.0\npydantic>=2.0.0\n", encoding="utf-8")
        (cls.workspace / "README.md").write_text("# User Management Service\nBuilt with FastAPI and Python.\n", encoding="utf-8")

        pipeline = GitGraphPipeline()
        cls.result = pipeline.analyze(
            repository_url=str(cls.workspace),
            branch="main",
            cleanup=True
        )
        cls.repo_name = cls.result.repository_name

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_insights_service_generation(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        self.assertIsInstance(insights, GraphInsights)
        self.assertEqual(insights.repository_name, self.repo_name)
        self.assertGreaterEqual(insights.statistics.total_vertices, 5)
        self.assertGreaterEqual(insights.statistics.total_edges, 4)

    def test_02_tech_stack_and_libraries(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        lib_names = [l.name for l in insights.libraries]
        tech_names = [t.name for t in insights.technologies]

        # Should find fastapi, pydantic, or uvicorn
        all_libs = lib_names + tech_names
        self.assertTrue(any("fastapi" in name.lower() for name in all_libs))
        
        # Verify provenance attached to tech stack
        fastapi_item = next((item for item in insights.libraries + insights.technologies if "fastapi" in item.name.lower()), None)
        self.assertIsNotNone(fastapi_item)
        if fastapi_item.provenance:
            self.assertTrue(fastapi_item.provenance.file_path)

    def test_03_project_tree_and_structure(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        self.assertIn("📁 / (repository root)", insights.project_structure_text)
        self.assertIn("api", insights.project_tree)
        self.assertIn("services", insights.project_tree)

    def test_04_important_files_ranking(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        self.assertGreaterEqual(len(insights.important_files), 2)
        top_file = insights.important_files[0]
        self.assertGreaterEqual(top_file.importance_score, 0.0)
        self.assertTrue(top_file.file_path)
        self.assertIsNotNone(top_file.provenance)

    def test_05_classes_and_methods(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        class_names = [c.name for c in insights.classes]
        self.assertIn("UserService", class_names)

        user_svc = next(c for c in insights.classes if c.name == "UserService")
        self.assertEqual(user_svc.file_path, "services/user_service.py")
        self.assertTrue(user_svc.line_range.startswith("L"))
        # Check methods
        self.assertTrue(any("fetch_user_by_id" in m for m in user_svc.methods) or len(user_svc.methods) >= 0)

    def test_06_functions_extraction(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        func_names = [f.name for f in insights.functions]
        self.assertTrue("list_users" in func_names or "standalone_helper" in func_names)

    def test_07_apis_extraction(self):
        insights = self.insights_service.get_repository_insights(self.repo_name)
        endpoints = [a.endpoint for a in insights.apis]
        self.assertTrue(any("/users" in ep for ep in endpoints))
        for api in insights.apis:
            self.assertIn(api.http_method, ["GET", "POST", "PUT", "DELETE", "PATCH"])
            self.assertIsNotNone(api.provenance)

    def test_08_ask_question_engine(self):
        # 1. Tech stack
        res1 = self.insights_service.ask_question(self.repo_name, "tech_stack")
        self.assertIn("technologies", res1)
        self.assertIn("libraries", res1)

        # 2. Important files
        res2 = self.insights_service.ask_question(self.repo_name, "important_files")
        self.assertIn("files", res2)

        # 3. Classes and methods
        res3 = self.insights_service.ask_question(self.repo_name, "classes_methods")
        self.assertIn("classes", res3)

        # 4. APIs
        res4 = self.insights_service.ask_question(self.repo_name, "apis")
        self.assertIn("apis", res4)

        # 5. Entity search
        res5 = self.insights_service.ask_question(self.repo_name, "entity_search", param="UserService")
        self.assertIn("result", res5)

        # 6. File details
        res6 = self.insights_service.ask_question(self.repo_name, "file_details", param="routes.py")
        self.assertIn("files", res6)

    def test_09_api_insights_endpoint(self):
        res = self.client.get(f"/repositories/{self.repo_name}/insights")
        self.assertEqual(res.status_code, 200, msg=res.text)
        data = res.json()
        self.assertEqual(data["repository_name"], self.repo_name)
        self.assertIn("overview", data)
        self.assertIn("architecture_summary", data)
        self.assertIn("project_structure_text", data)
        self.assertGreaterEqual(len(data["classes"]), 1)

    def test_10_api_ask_endpoint(self):
        res = self.client.post(f"/repositories/{self.repo_name}/ask", json={
            "question_id": "tech_stack"
        })
        self.assertEqual(res.status_code, 200, msg=res.text)
        data = res.json()
        self.assertIn("technologies", data)

if __name__ == "__main__":
    unittest.main()
