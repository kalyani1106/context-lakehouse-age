import unittest
import shutil
from pathlib import Path
from backend.storage.lakehouse import LocalLakehouseStorageService
from backend.storage.models import ProcessingStatus, DocumentMetadata, LakehouseLayer

class TestStorage(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(__file__).parent.parent / "backend" / "test_storage_tier"
        self.storage = LocalLakehouseStorageService(root_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_lakehouse_tier_creation(self):
        for layer in LakehouseLayer:
            layer_path = self.test_dir / layer.value
            self.assertTrue(layer_path.exists(), f"Layer {layer.value} directory should exist.")

    def test_document_lifecycle(self):
        doc_id = "doc_test_unit"
        dummy_content = b"%PDF-1.5 test raw file content"
        
        # Upload
        meta = self.storage.upload_document(
            document_id=doc_id,
            filename="unit_test.pdf",
            file_bytes=dummy_content
        )
        self.assertEqual(meta.document_id, doc_id)
        self.assertEqual(meta.status, ProcessingStatus.UPLOADED)
        
        # Save pages
        pages = [{"page_number": 1, "text": "Hello page 1", "char_count": 12, "word_count": 3}]
        self.storage.save_extracted_pages(doc_id, pages)
        retrieved_pages = self.storage.get_extracted_pages(doc_id)
        self.assertEqual(len(retrieved_pages), 1)

        # Save chunks
        chunks = [{"chunk_id": "c1", "page_number": 1, "text": "Hello page 1"}]
        self.storage.save_chunks(doc_id, chunks)
        retrieved_chunks = self.storage.get_chunks(doc_id)
        self.assertEqual(len(retrieved_chunks), 1)

        # Save context
        context = {"summary": "Unit test summary", "entities": [{"name": "TestEntity"}], "relationships": []}
        self.storage.save_context(doc_id, context)
        retrieved_ctx = self.storage.get_context(doc_id)
        self.assertEqual(retrieved_ctx["summary"], "Unit test summary")

        # Delete
        self.storage.delete_document(doc_id)
        self.assertIsNone(self.storage.get_metadata(doc_id))

if __name__ == "__main__":
    unittest.main()
