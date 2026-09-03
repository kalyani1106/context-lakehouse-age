import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import PDFContextPipeline
from storage.models import ProcessingStatus

class TestDataQualityAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.pipeline = PDFContextPipeline()

    def test_01_duplicate_pdf_detection_via_sha256(self):
        pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # First upload
        meta1 = self.pipeline.upload_pdf("A Report on Context Lakehouse.pdf", pdf_bytes)
        self.assertIsNotNone(meta1.document_id)
        self.assertIsNotNone(meta1.sha256)

        # Second upload of the exact same content (even if filename was different)
        meta2 = self.pipeline.upload_pdf("duplicate_copy.pdf", pdf_bytes)

        # Must map to the exact same document ID and SHA-256
        self.assertEqual(meta1.document_id, meta2.document_id)
        self.assertEqual(meta1.sha256, meta2.sha256)
        print(f"\n[Test Duplicate Detection] Verified: Duplicate upload mapped to existing doc ID {meta1.document_id} (SHA-256: {meta1.sha256[:16]}...)")

    def test_02_idempotent_processing(self):
        pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\Report on Building a Semantic Layer with Apache AGE.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        meta = self.pipeline.upload_pdf("Report on Building a Semantic Layer with Apache AGE.pdf", pdf_bytes)
        doc_id = meta.document_id

        # First run
        res1 = self.pipeline.process_document(doc_id, force_provider="heuristic", reprocess=True)
        self.assertEqual(res1["status"], ProcessingStatus.COMPLETED.value)
        self.assertFalse(res1["already_processed"])
        
        # Count initial AGE nodes
        nodes_before = len(self.pipeline.graph_service.get_all_entities(limit=500))

        # Second run without reprocess
        res2 = self.pipeline.process_document(doc_id, force_provider="heuristic", reprocess=False)
        self.assertEqual(res2["status"], ProcessingStatus.COMPLETED.value)
        self.assertTrue(res2["already_processed"])

        # Count AGE nodes after: MUST be identical (no duplicate vertices created)
        nodes_after = len(self.pipeline.graph_service.get_all_entities(limit=500))
        self.assertEqual(nodes_before, nodes_after)
        print(f"[Test Idempotent Processing] Repeated processing without reprocess returned instantly without duplicating graph nodes ({nodes_before} nodes).")

    def test_03_high_precision_extraction_on_resume(self):
        resume_path = Path(r"C:\Users\varshini\Downloads\Rowthu_Kalyani_Final_Resume.pdf")
        if not resume_path.exists():
            self.skipTest("Resume PDF not found")

        with open(resume_path, "rb") as f:
            pdf_bytes = f.read()

        meta = self.pipeline.upload_pdf("Rowthu_Kalyani_Final_Resume.pdf", pdf_bytes)
        res = self.pipeline.process_document(meta.document_id, force_provider="heuristic", reprocess=True)

        # Assert no entity explosion on 1-page resume: entities should be under 25, relationships under 15
        self.assertLessEqual(res["total_entities"], 25)
        self.assertLessEqual(res["total_relationships"], 15)
        self.assertGreater(res["total_entities"], 5)
        self.assertGreater(res["total_relationships"], 2)

        # Check that noise words were excluded
        ctx = self.pipeline.storage.get_context(meta.document_id)
        extracted_names = [e["canonical_name"].upper() for e in ctx["entities"]]
        self.assertNotIn("EDUCATION", extracted_names)
        self.assertNotIn("EXPERIENCE", extracted_names)
        self.assertNotIn("SKILLS", extracted_names)
        self.assertNotIn("SUMMARY", extracted_names)
        self.assertNotIn("PHONE", extracted_names)
        self.assertNotIn("EMAIL", extracted_names)

        # Check Person and Key Tech were extracted
        self.assertIn("ROWTHU KALYANI", extracted_names)
        self.assertIn("PYTHON", extracted_names)
        self.assertIn("SQL", extracted_names)
        self.assertIn("POWER BI", extracted_names)

        print(f"\n[Test Resume High-Precision Extraction]")
        print(f"Total Pages: {res['total_pages']}")
        print(f"Entities Extracted: {res['total_entities']} (was 66 before)")
        print(f"Relationships Extracted: {res['total_relationships']} (was 103 before)")
        print(f"Processing Time: {res['processing_time_sec']}s")

    def test_04_provenance_validation(self):
        resume_path = Path(r"C:\Users\varshini\Downloads\Rowthu_Kalyani_Final_Resume.pdf")
        if not resume_path.exists():
            self.skipTest("Resume PDF not found")

        with open(resume_path, "rb") as f:
            file_hash = __import__("hashlib").sha256(f.read()).hexdigest()
        meta = self.pipeline.storage.get_document_by_hash(file_hash)
        if not meta:
            self.skipTest("Resume not yet uploaded in test")

        context = self.pipeline.storage.get_context(meta.document_id)
        self.assertIsNotNone(context)

        for ent in context["entities"]:
            src = ent["source"]
            self.assertEqual(src["document_id"], meta.document_id)
            self.assertEqual(src["page_number"], 1)
            self.assertGreater(len(src["source_text"]), 0)

        for rel in context["relationships"]:
            src = rel["source"]
            self.assertEqual(src["document_id"], meta.document_id)
            self.assertEqual(src["page_number"], 1)
            self.assertGreater(len(src["source_text"]), 0)

        print(f"[Test Provenance] Verified: 100% of entities and relationships retain document_id, page_number, and source_text.")

if __name__ == "__main__":
    unittest.main()
