import unittest
from pathlib import Path
from extraction.pdf_extractor import PDFExtractor, PDFExtractionError
from extraction.chunker import DocumentChunker

class TestPDFExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = PDFExtractor()
        self.chunker = DocumentChunker(chunk_size=400, chunk_overlap=80)

    def test_clean_text(self):
        dirty = "Hello \x00\x08World!   \n\n\n  This is a test.  "
        cleaned = PDFExtractor.clean_text(dirty)
        self.assertEqual(cleaned, "Hello World!\n\nThis is a test.")

    def test_empty_bytes_raises(self):
        with self.assertRaises(PDFExtractionError):
            self.extractor.extract_from_bytes(b"", "doc_empty", "empty.pdf")

    def test_corrupted_pdf_raises(self):
        with self.assertRaises(PDFExtractionError):
            self.extractor.extract_from_bytes(b"Not a valid PDF header", "doc_bad", "bad.pdf")

    def test_real_pdf_extraction(self):
        pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\Report on Building a Semantic Layer with Apache AGE.pdf")
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")
        
        extracted = self.extractor.extract_from_path(pdf_path, "doc_age_report", "age_report.pdf")
        self.assertGreater(extracted.total_pages, 0)
        self.assertGreater(extracted.total_words, 100)
        
        chunks = self.chunker.chunk_document(extracted)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0].document_id, "doc_age_report")

if __name__ == "__main__":
    unittest.main()
