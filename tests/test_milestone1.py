import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.lakehouse import LocalLakehouseStorageService
from backend.storage.models import ProcessingStatus
from backend.extraction.pdf_extractor import PDFExtractor
from backend.graph.age_client import AGEClient

class TestMilestone1(unittest.TestCase):
    def setUp(self):
        self.storage = LocalLakehouseStorageService(root_dir=Path(__file__).parent.parent / "backend" / "test_lakehouse_storage")
        self.extractor = PDFExtractor()
        self.age_client = AGEClient()

    def test_01_lakehouse_storage(self):
        doc_id = "doc_test_123"
        dummy_pdf_bytes = b"%PDF-1.4 dummy content for testing lakehouse"
        meta = self.storage.upload_document(
            document_id=doc_id,
            filename="dummy_test.pdf",
            file_bytes=dummy_pdf_bytes,
            custom_metadata={"test": True}
        )
        self.assertEqual(meta.document_id, doc_id)
        self.assertEqual(meta.status, ProcessingStatus.UPLOADED)
        
        # Verify status update
        updated_meta = self.storage.update_status(doc_id, ProcessingStatus.EXTRACTING)
        self.assertEqual(updated_meta.status, ProcessingStatus.EXTRACTING)
        
        # Verify retrieved metadata
        retrieved = self.storage.get_metadata(doc_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.document_name, "dummy_test.pdf")
        
        # Clean up
        self.storage.delete_document(doc_id)

    def test_02_pdf_extraction_real_file(self):
        real_pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if real_pdf_path.exists():
            extracted = self.extractor.extract_from_path(
                file_path=real_pdf_path,
                document_id="doc_real_report",
                document_name="A Report on Context Lakehouse.pdf"
            )
            self.assertGreater(extracted.total_pages, 0)
            self.assertGreater(extracted.total_characters, 100)
            self.assertEqual(extracted.pages[0].page_number, 1)
            print(f"\n[Test PDF Extraction] Extracted {extracted.total_pages} pages, {extracted.total_words} words from real PDF.")
        else:
            self.skipTest(f"Sample PDF not found at {real_pdf_path}")

    def test_03_age_client_connection(self):
        health = self.age_client.test_connection()
        self.assertEqual(health["status"], "connected")
        print(f"\n[Test AGE Connection] Connected to PostgreSQL: {health['postgres_version'][:30]}... Graphs: {health['available_graphs']}")
        
        # Ensure knowledge_graph exists
        self.age_client.ensure_graph_exists("knowledge_graph")
        
        # Simple test query
        res = self.age_client.execute_cypher("MATCH (n) RETURN count(n) AS cnt", columns=["cnt"])
        self.assertIsInstance(res, list)
        print(f"[Test AGE Query] Graph query executed successfully. Node count: {res[0].get('cnt')}")

if __name__ == "__main__":
    unittest.main()
