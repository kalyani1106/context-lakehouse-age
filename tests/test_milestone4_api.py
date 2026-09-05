import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.api.app import app

class TestMilestone4API(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"]["status"], "connected")
        print(f"\n[Test API Health] System healthy. PostgreSQL version: {data['database']['postgres_version'][:30]}...")

    def test_02_upload_and_process_pdf(self):
        real_pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\Report on Building a Semantic Layer with Apache AGE.pdf")
        if not real_pdf_path.exists():
            self.skipTest(f"PDF not found at {real_pdf_path}")

        # 1. Upload PDF
        with open(real_pdf_path, "rb") as f:
            upload_resp = self.client.post(
                "/documents/upload",
                files={"file": ("Report on Building a Semantic Layer with Apache AGE.pdf", f, "application/pdf")}
            )
        self.assertEqual(upload_resp.status_code, 200)
        upload_data = upload_resp.json()
        doc_id = upload_data["document_id"]
        self.assertIsNotNone(doc_id)
        self.assertIn(upload_data["status"], ["UPLOADED", "COMPLETED"])
        print(f"\n[Test API Upload] Uploaded document ID: {doc_id} (Status: {upload_data['status']})")

        # 2. Get Metadata
        meta_resp = self.client.get(f"/documents/{doc_id}")
        self.assertEqual(meta_resp.status_code, 200)

        # 3. Process Document with reprocess=True
        proc_resp = self.client.post(f"/documents/{doc_id}/process?provider=heuristic&reprocess=true")
        self.assertEqual(proc_resp.status_code, 200)
        proc_data = proc_resp.json()
        self.assertEqual(proc_data["status"], "COMPLETED")
        self.assertGreater(proc_data["total_pages"], 0)
        self.assertGreater(proc_data["total_entities"], 0)
        print(f"[Test API Process] Processed {proc_data['total_pages']} pages, extracted {proc_data['total_entities']} entities & {proc_data['total_relationships']} relationships.")

        # 4. Get Extracted Pages
        pages_resp = self.client.get(f"/documents/{doc_id}/pages")
        self.assertEqual(pages_resp.status_code, 200)
        self.assertGreater(pages_resp.json()["total_pages"], 0)

        # 5. Get Chunks
        chunks_resp = self.client.get(f"/documents/{doc_id}/chunks")
        self.assertEqual(chunks_resp.status_code, 200)
        self.assertGreater(chunks_resp.json()["total_chunks"], 0)

        # 6. Get Context JSON Artifact
        ctx_resp = self.client.get(f"/documents/{doc_id}/context")
        self.assertEqual(ctx_resp.status_code, 200)
        ctx_data = ctx_resp.json()
        self.assertIn("entities", ctx_data)
        self.assertIn("relationships", ctx_data)
        print(f"[Test API Context Artifact] Context JSON artifact accessible directly via API.")

        # 7. Get Document Graph from AGE
        graph_resp = self.client.get(f"/documents/{doc_id}/graph")
        self.assertEqual(graph_resp.status_code, 200)
        graph_data = graph_resp.json()
        self.assertGreater(len(graph_data["nodes"]), 0)
        print(f"[Test API Document Graph] Document graph contains {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges.")

        # 8. Query AGE Cypher via API
        cypher_resp = self.client.post(
            "/graph/query",
            json={
                "query": "MATCH (n:Technology) RETURN n.name AS name LIMIT 5",
                "columns": ["name"]
            }
        )
        self.assertEqual(cypher_resp.status_code, 200)
        cypher_data = cypher_resp.json()
        print(f"[Test API Cypher Query] Result: {cypher_data['results']}")

        # 9. Query Entity Provenance
        prov_resp = self.client.get("/graph/provenance?entity_name=Apache AGE")
        self.assertEqual(prov_resp.status_code, 200)
        prov_data = prov_resp.json()
        self.assertEqual(prov_data["canonical_name"], "Apache AGE")
        print(f"[Test API Provenance] Entity 'Apache AGE' provenance retrieved successfully: {prov_data['document_name']}, page {prov_data['page_number']}.")

if __name__ == "__main__":
    unittest.main()
