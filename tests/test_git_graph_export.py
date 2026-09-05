"""
Unit and Integration Tests for Knowledge Graph Export Service and Endpoints
===========================================================================
"""

import io
import json
import zipfile
import unittest
import tempfile
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.git_graph.pipeline import GitGraphPipeline
from backend.git_graph.graph.graph_export import GraphExportService

class TestGitGraphExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.export_service = GraphExportService()

        # Ingest fixture repo
        cls.temp_dir = tempfile.mkdtemp()
        cls.workspace = Path(cls.temp_dir)
        (cls.workspace / "pkg").mkdir()

        (cls.workspace / "pkg" / "module.py").write_text("""\"\"\"Module Doc\"\"\"
import os

class ModelWorker:
    def execute(self):
        return 42

def runner():
    return ModelWorker().execute()
""", encoding="utf-8")

        (cls.workspace / "requirements.txt").write_text("numpy>=1.20.0\n", encoding="utf-8")
        (cls.workspace / "README.md").write_text("# Test Export Service\n", encoding="utf-8")

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

    def test_01_export_json(self):
        data = self.export_service.export_json(self.repo_name)
        self.assertIn("metadata", data)
        self.assertIn("vertices", data)
        self.assertIn("edges", data)
        self.assertEqual(data["metadata"]["repository_name"], self.repo_name)
        self.assertGreaterEqual(len(data["vertices"]), 4)
        self.assertGreaterEqual(len(data["edges"]), 3)

        # Check line-level provenance preservation
        worker_v = next((v for v in data["vertices"] if v.get("name") == "ModelWorker"), None)
        self.assertIsNotNone(worker_v)
        self.assertEqual(worker_v["provenance"]["file_path"], "pkg/module.py")
        self.assertGreaterEqual(worker_v["provenance"]["start_line"], 1)

    def test_02_export_csv_bundle(self):
        v_csv, e_csv = self.export_service.export_csv_bundle(self.repo_name)
        self.assertIn("id,canonical_id,label,name,entity_type", v_csv)
        self.assertIn("id,source_id,source_canonical_id,target_id,target_canonical_id", e_csv)
        self.assertIn("ModelWorker", v_csv)
        self.assertIn("pkg/module.py", v_csv)

    def test_03_export_zip(self):
        zip_bytes = self.export_service.export_zip(self.repo_name)
        self.assertIsInstance(zip_bytes, bytes)
        self.assertGreater(len(zip_bytes), 100)

        # Unpack and verify contents
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            files = zf.namelist()
            self.assertIn("knowledge_graph.json", files)
            self.assertIn("vertices.csv", files)
            self.assertIn("edges.csv", files)
            self.assertIn("README.md", files)

            json_content = json.loads(zf.read("knowledge_graph.json").decode("utf-8"))
            self.assertEqual(json_content["metadata"]["repository_name"], self.repo_name)

    def test_04_export_graphml(self):
        graphml_str = self.export_service.export_graphml(self.repo_name)
        self.assertTrue(graphml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("<graphml", graphml_str)
        self.assertIn("<graph", graphml_str)

        # Validate that it parses cleanly as XML
        root = ET.fromstring(graphml_str.replace('<?xml version="1.0" encoding="UTF-8"?>', "").strip())
        self.assertIsNotNone(root)
        self.assertTrue(len(root.findall(".//{http://graphml.graphdrawing.org/xmlns}node")) >= 4)
        self.assertTrue(len(root.findall(".//{http://graphml.graphdrawing.org/xmlns}edge")) >= 3)

    def test_05_api_export_json_endpoint(self):
        res = self.client.get(f"/repositories/{self.repo_name}/export", params={"format": "json"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["metadata"]["repository_name"], self.repo_name)

    def test_06_api_export_download_json_attachment(self):
        res = self.client.get(f"/repositories/{self.repo_name}/export", params={"format": "json", "download": "true"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/json")
        self.assertIn("attachment; filename=", res.headers["content-disposition"])

    def test_07_api_export_zip_endpoint(self):
        res = self.client.get(f"/repositories/{self.repo_name}/export", params={"format": "zip"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/zip")
        self.assertIn("attachment; filename=", res.headers["content-disposition"])

    def test_08_api_export_csv_endpoint(self):
        res = self.client.get(f"/repositories/{self.repo_name}/export", params={"format": "csv"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/zip")

    def test_09_api_export_graphml_endpoint(self):
        res = self.client.get(f"/repositories/{self.repo_name}/export", params={"format": "graphml"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/xml")
        self.assertIn("attachment; filename=", res.headers["content-disposition"])
        self.assertIn("<graphml", res.text)

if __name__ == "__main__":
    unittest.main()
