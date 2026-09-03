import unittest
from pathlib import Path
from pipeline import PDFContextPipeline
from storage.models import ProcessingStatus

class TestPipelineE2E(unittest.TestCase):
    def setUp(self):
        self.pipeline = PDFContextPipeline()

    def test_e2e_pipeline_with_real_pdf_context_lakehouse(self):
        pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Step 1: Upload (or return existing deduplicated document)
        meta = self.pipeline.upload_pdf("A Report on Context Lakehouse.pdf", pdf_bytes)
        self.assertIn(meta.status, [ProcessingStatus.UPLOADED, ProcessingStatus.COMPLETED])
        doc_id = meta.document_id

        # Step 2: Execute full pipeline (with reprocess=True to verify pipeline execution)
        res = self.pipeline.process_document(doc_id, force_provider="heuristic", reprocess=True)
        self.assertEqual(res["status"], ProcessingStatus.COMPLETED.value)
        self.assertGreater(res["total_pages"], 0)
        self.assertGreater(res["total_entities"], 0)
        self.assertGreater(res["total_relationships"], 0)

        # Step 3: Verify Lakehouse Tiers
        pages = self.pipeline.storage.get_extracted_pages(doc_id)
        self.assertIsNotNone(pages)
        self.assertEqual(len(pages), res["total_pages"])

        chunks = self.pipeline.storage.get_chunks(doc_id)
        self.assertIsNotNone(chunks)
        self.assertEqual(len(chunks), res["total_chunks"])

        context = self.pipeline.storage.get_context(doc_id)
        self.assertIsNotNone(context)
        self.assertEqual(len(context["entities"]), res["total_entities"])

        # Step 4: Verify Apache AGE Knowledge Graph
        subgraph = self.pipeline.graph_service.get_document_subgraph(doc_id)
        self.assertGreater(len(subgraph["nodes"]), 0)

        print(f"\n[E2E Verification Success]")
        print(f"Document: {res['document_name']}")
        print(f"Pages: {res['total_pages']}, Chunks: {res['total_chunks']}")
        print(f"Entities in AGE: {res['total_entities']}, Relationships: {res['total_relationships']}")

    def test_e2e_pipeline_with_real_pdf_apache_age(self):
        pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\Report on Building a Semantic Layer with Apache AGE.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        meta = self.pipeline.upload_pdf("Report on Building a Semantic Layer with Apache AGE.pdf", pdf_bytes)
        doc_id = meta.document_id

        res = self.pipeline.process_document(doc_id, force_provider="heuristic")
        self.assertEqual(res["status"], ProcessingStatus.COMPLETED.value)
        self.assertGreater(res["total_pages"], 0)
        self.assertGreater(res["total_entities"], 0)

        # Verify Provenance
        prov = self.pipeline.graph_service.get_entity_provenance("Apache AGE")
        self.assertNotIn("error", prov)
        self.assertEqual(prov["canonical_name"], "Apache AGE")

if __name__ == "__main__":
    unittest.main()
