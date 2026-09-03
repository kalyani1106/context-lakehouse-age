import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.pdf_extractor import PDFExtractor
from extraction.chunker import DocumentChunker
from context.extractor import ContextExtractor
from context.schemas import DocumentContext

class TestMilestone2(unittest.TestCase):
    def setUp(self):
        self.extractor = PDFExtractor()
        self.chunker = DocumentChunker(chunk_size=600, chunk_overlap=100)
        self.context_extractor = ContextExtractor()

    def test_01_chunking_and_provenance(self):
        real_pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if not real_pdf_path.exists():
            self.skipTest(f"PDF not found at {real_pdf_path}")

        extracted_doc = self.extractor.extract_from_path(
            file_path=real_pdf_path,
            document_id="doc_report_ctx",
            document_name="A Report on Context Lakehouse.pdf"
        )
        chunks = self.chunker.chunk_document(extracted_doc)
        self.assertGreater(len(chunks), 0)
        
        # Verify first chunk provenance
        first_chunk = chunks[0]
        self.assertEqual(first_chunk.document_id, "doc_report_ctx")
        self.assertEqual(first_chunk.page_number, 1)
        self.assertIsNotNone(first_chunk.chunk_id)
        print(f"\n[Test Chunker] Created {len(chunks)} chunks from {extracted_doc.total_pages} pages.")

    def test_02_context_extraction_real_doc(self):
        real_pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if not real_pdf_path.exists():
            self.skipTest(f"PDF not found at {real_pdf_path}")

        extracted_doc = self.extractor.extract_from_path(
            file_path=real_pdf_path,
            document_id="doc_report_ctx",
            document_name="A Report on Context Lakehouse.pdf"
        )
        chunks = self.chunker.chunk_document(extracted_doc)
        
        # Extract structured context
        context: DocumentContext = self.context_extractor.extract_context(
            document=extracted_doc,
            chunks=chunks,
            force_provider="heuristic"
        )

        self.assertIsInstance(context, DocumentContext)
        self.assertGreater(len(context.entities), 0)
        self.assertGreater(len(context.relationships), 0)
        
        print(f"\n[Test Context Extraction] Extracted {len(context.entities)} unique canonical entities and {len(context.relationships)} relationships.")
        print("Sample Entities:")
        for ent in context.entities[:5]:
            print(f"  - [{ent.type}] {ent.canonical_name} (aliases: {ent.aliases}) (Source: p.{ent.source.page_number})")
            
        print("Sample Relationships:")
        for rel in context.relationships[:5]:
            print(f"  - {rel.source_entity} -[:{rel.relationship_type}]-> {rel.target_entity} (p.{rel.source.page_number})")

if __name__ == "__main__":
    unittest.main()
