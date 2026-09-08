"""
Multi-Format Document Extractor
===============================
Unified extraction dispatcher that detects file format, validates content,
and routes to the appropriate format-specific extractor.
"""

from pathlib import Path
from typing import Optional, Dict, Any, Union

from backend.extraction.pdf_extractor import ExtractedDocument, PDFExtractor, PDFExtractionError
from backend.extraction.file_detector import FileDetector, SupportedFormat, FileDetectionError
from backend.extraction.format_extractors import (
    DocumentExtractionError,
    TextDocumentExtractor,
    DocxExtractor,
    HtmlExtractor,
    XmlExtractor,
    TabularExtractor,
    SpreadsheetExtractor,
    JsonExtractor,
    ParquetExtractor,
    YamlExtractor,
)

class DocumentExtractor:
    """
    Dispatcher for multi-format text, schema, and document extraction.
    Provides backward-compatible extract_from_path and extract_from_bytes.
    """

    def __init__(self):
        self.pdf_extractor = PDFExtractor()
        self.text_extractor = TextDocumentExtractor()
        self.docx_extractor = DocxExtractor()
        self.html_extractor = HtmlExtractor()
        self.xml_extractor = XmlExtractor()
        self.tabular_extractor = TabularExtractor()
        self.spreadsheet_extractor = SpreadsheetExtractor()
        self.json_extractor = JsonExtractor()
        self.parquet_extractor = ParquetExtractor()
        self.yaml_extractor = YamlExtractor()

    def extract_from_path(self, file_path: Path, document_id: str, document_name: str) -> ExtractedDocument:
        if not file_path.exists():
            raise DocumentExtractionError(f"File not found at {file_path}")

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            return self.extract_from_bytes(file_bytes, document_id, document_name)
        except (DocumentExtractionError, PDFExtractionError, FileDetectionError):
            raise
        except Exception as e:
            raise DocumentExtractionError(f"Failed extracting from {document_name}: {str(e)}")

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        detected_format: Optional[SupportedFormat] = None
    ) -> ExtractedDocument:
        if not file_bytes or len(file_bytes) == 0:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        if not detected_format:
            detected_format, _, _ = FileDetector.detect_format(document_name, file_bytes)

        # Dispatch based on detected format
        if detected_format == SupportedFormat.PDF:
            return self.pdf_extractor.extract_from_bytes(file_bytes, document_id, document_name)

        elif detected_format in (SupportedFormat.TXT, SupportedFormat.MARKDOWN, SupportedFormat.SQL, SupportedFormat.RTF):
            return self.text_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format == SupportedFormat.DOCX:
            return self.docx_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format == SupportedFormat.HTML:
            return self.html_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format == SupportedFormat.XML:
            return self.xml_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format in (SupportedFormat.CSV, SupportedFormat.TSV):
            return self.tabular_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format in (SupportedFormat.XLSX, SupportedFormat.XLS):
            return self.spreadsheet_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format in (SupportedFormat.JSON, SupportedFormat.JSONL):
            return self.json_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format in (SupportedFormat.PARQUET, SupportedFormat.FEATHER):
            return self.parquet_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        elif detected_format == SupportedFormat.YAML:
            return self.yaml_extractor.extract_from_bytes(file_bytes, document_id, document_name, detected_format)

        else:
            raise DocumentExtractionError(f"Unsupported extractor dispatch for format: {detected_format}")

# Alias for clear naming
MultiFormatDocumentExtractor = DocumentExtractor
