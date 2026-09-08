"""
File Type & Format Detector
===========================
Safe and robust file format, MIME type, and category detection using
file extensions and magic byte signatures.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Set

class FileCategory(str, Enum):
    DOCUMENT = "document"
    TABULAR = "tabular"
    SPREADSHEET = "spreadsheet"
    HIERARCHICAL = "hierarchical"
    ANALYTICS = "analytics"
    CODE = "code"

class SupportedFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    HTML = "html"
    XML = "xml"
    RTF = "rtf"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    JSONL = "jsonl"
    XLSX = "xlsx"
    XLS = "xls"
    PARQUET = "parquet"
    FEATHER = "feather"
    YAML = "yaml"
    SQL = "sql"

# Supported extension mapping to format
EXTENSION_MAP: Dict[str, SupportedFormat] = {
    ".pdf": SupportedFormat.PDF,
    ".docx": SupportedFormat.DOCX,
    ".txt": SupportedFormat.TXT,
    ".text": SupportedFormat.TXT,
    ".md": SupportedFormat.MARKDOWN,
    ".markdown": SupportedFormat.MARKDOWN,
    ".html": SupportedFormat.HTML,
    ".htm": SupportedFormat.HTML,
    ".xml": SupportedFormat.XML,
    ".rtf": SupportedFormat.RTF,
    ".csv": SupportedFormat.CSV,
    ".tsv": SupportedFormat.TSV,
    ".json": SupportedFormat.JSON,
    ".jsonl": SupportedFormat.JSONL,
    ".ndjson": SupportedFormat.JSONL,
    ".xlsx": SupportedFormat.XLSX,
    ".xls": SupportedFormat.XLS,
    ".parquet": SupportedFormat.PARQUET,
    ".pq": SupportedFormat.PARQUET,
    ".feather": SupportedFormat.FEATHER,
    ".arrow": SupportedFormat.FEATHER,
    ".yaml": SupportedFormat.YAML,
    ".yml": SupportedFormat.YAML,
    ".sql": SupportedFormat.SQL,
}

# Standard canonical MIME types
MIME_MAP: Dict[SupportedFormat, str] = {
    SupportedFormat.PDF: "application/pdf",
    SupportedFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    SupportedFormat.TXT: "text/plain",
    SupportedFormat.MARKDOWN: "text/markdown",
    SupportedFormat.HTML: "text/html",
    SupportedFormat.XML: "application/xml",
    SupportedFormat.RTF: "application/rtf",
    SupportedFormat.CSV: "text/csv",
    SupportedFormat.TSV: "text/tab-separated-values",
    SupportedFormat.JSON: "application/json",
    SupportedFormat.JSONL: "application/x-ndjson",
    SupportedFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    SupportedFormat.XLS: "application/vnd.ms-excel",
    SupportedFormat.PARQUET: "application/vnd.apache.parquet",
    SupportedFormat.FEATHER: "application/vnd.apache.arrow.feather",
    SupportedFormat.YAML: "application/x-yaml",
    SupportedFormat.SQL: "application/sql",
}

# Format category map
CATEGORY_MAP: Dict[SupportedFormat, FileCategory] = {
    SupportedFormat.PDF: FileCategory.DOCUMENT,
    SupportedFormat.DOCX: FileCategory.DOCUMENT,
    SupportedFormat.TXT: FileCategory.DOCUMENT,
    SupportedFormat.MARKDOWN: FileCategory.DOCUMENT,
    SupportedFormat.HTML: FileCategory.DOCUMENT,
    SupportedFormat.XML: FileCategory.HIERARCHICAL,
    SupportedFormat.RTF: FileCategory.DOCUMENT,
    SupportedFormat.CSV: FileCategory.TABULAR,
    SupportedFormat.TSV: FileCategory.TABULAR,
    SupportedFormat.JSON: FileCategory.HIERARCHICAL,
    SupportedFormat.JSONL: FileCategory.TABULAR,
    SupportedFormat.XLSX: FileCategory.SPREADSHEET,
    SupportedFormat.XLS: FileCategory.SPREADSHEET,
    SupportedFormat.PARQUET: FileCategory.ANALYTICS,
    SupportedFormat.FEATHER: FileCategory.ANALYTICS,
    SupportedFormat.YAML: FileCategory.HIERARCHICAL,
    SupportedFormat.SQL: FileCategory.CODE,
}

SUPPORTED_EXTENSIONS: Set[str] = set(EXTENSION_MAP.keys())

class FileDetectionError(Exception):
    """Raised when file type is invalid or unsupported."""
    pass

class FileDetector:
    """Detects and validates file format, category, and MIME type."""

    @classmethod
    def is_supported(cls, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in EXTENSION_MAP

    @classmethod
    def get_supported_extensions_display(cls) -> str:
        return "PDF, DOCX, TXT, MD, CSV, TSV, XLSX, XLS, JSON, JSONL, XML, HTML, Parquet, Feather, YAML, SQL, RTF"

    @classmethod
    def detect_format(cls, filename: str, file_bytes: Optional[bytes] = None) -> Tuple[SupportedFormat, str, FileCategory]:
        """
        Determines the supported format, canonical MIME type, and category.
        Inspects extension and magic byte signatures when available.
        """
        ext = Path(filename).suffix.lower()
        if not ext:
            # Try to detect purely by magic bytes if no extension
            if file_bytes:
                fmt = cls._detect_from_bytes(file_bytes)
                if fmt:
                    return fmt, MIME_MAP[fmt], CATEGORY_MAP[fmt]
            raise FileDetectionError(
                f"Unsupported file format. Supported formats: {cls.get_supported_extensions_display()}."
            )

        if ext not in EXTENSION_MAP:
            raise FileDetectionError(
                f"Unsupported file format. Supported formats: {cls.get_supported_extensions_display()}."
            )

        detected_fmt = EXTENSION_MAP[ext]

        # Verify magic bytes for binary formats if bytes are provided
        if file_bytes and len(file_bytes) > 0:
            cls._verify_magic_bytes(detected_fmt, file_bytes, filename)

        return detected_fmt, MIME_MAP[detected_fmt], CATEGORY_MAP[detected_fmt]

    @classmethod
    def _detect_from_bytes(cls, file_bytes: bytes) -> Optional[SupportedFormat]:
        if file_bytes.startswith(b"%PDF-"):
            return SupportedFormat.PDF
        elif file_bytes.startswith(b"PAR1"):
            return SupportedFormat.PARQUET
        elif file_bytes.startswith(b"ARROW1") or file_bytes.startswith(b"FEA1"):
            return SupportedFormat.FEATHER
        elif file_bytes.startswith(b"{\\rtf"):
            return SupportedFormat.RTF
        elif file_bytes.strip().startswith(b"<?xml") or file_bytes.strip().startswith(b"<html"):
            return SupportedFormat.HTML if b"<html" in file_bytes.lower() else SupportedFormat.XML
        elif file_bytes.strip().startswith(b"{") or file_bytes.strip().startswith(b"["):
            return SupportedFormat.JSON
        return None

    @classmethod
    def _verify_magic_bytes(cls, fmt: SupportedFormat, file_bytes: bytes, filename: str):
        """Sanity check magic bytes for formats with strict headers."""
        if fmt == SupportedFormat.PDF:
            if not file_bytes.startswith(b"%PDF-"):
                pass
        elif fmt == SupportedFormat.PARQUET:
            if not file_bytes.startswith(b"PAR1"):
                raise FileDetectionError(f"Corrupted or invalid Parquet file '{filename}': Missing PAR1 magic header.")
        elif fmt == SupportedFormat.FEATHER:
            if not (file_bytes.startswith(b"ARROW1") or file_bytes.startswith(b"FEA1") or file_bytes.endswith(b"ARROW1")):
                pass
        elif fmt == SupportedFormat.RTF:
            if not file_bytes.startswith(b"{\\rtf"):
                raise FileDetectionError(f"Invalid RTF file '{filename}': Missing {{\\rtf header.")
