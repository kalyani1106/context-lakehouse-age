"""
Format-Specific Document and Data Extractors
============================================
Extracts structured text, pages, schemas, and metadata from a wide variety of
file formats (Text, Markdown, DOCX, HTML, XML, CSV, TSV, XLSX, XLS, JSON, JSONL,
Parquet, Feather, YAML, SQL, RTF) into normalized ExtractedDocument representation.
"""

import io
import re
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pypdf
from backend.extraction.pdf_extractor import ExtractedDocument, ExtractedPage, PDFExtractor
from backend.extraction.file_detector import SupportedFormat

class DocumentExtractionError(Exception):
    """Custom exception raised when multi-format extraction fails."""
    pass

class BaseFormatExtractor:
    """Base class for all format extractors."""
    
    @staticmethod
    def clean_text(text: str) -> str:
        return PDFExtractor.clean_text(text)

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        raise NotImplementedError

# -----------------------------------------------------------------------------
# 1. Text, Markdown, SQL, RTF Extractor
# -----------------------------------------------------------------------------
class TextDocumentExtractor(BaseFormatExtractor):
    """Extracts text from TXT, Markdown, SQL, and RTF documents."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        # Safe decoding with fallback encodings
        text = self._decode_bytes(file_bytes, document_name)

        if format_type == SupportedFormat.RTF:
            text = self._strip_rtf(text)

        cleaned = self.clean_text(text)
        if not cleaned:
            raise DocumentExtractionError(f"Document {document_name} contains no readable text.")

        # Chunk text into page-sized logical units (e.g. ~3000 chars or by major section headers)
        pages = self._paginate_text(cleaned, document_id, document_name)
        total_chars = sum(p.char_count for p in pages)
        total_words = sum(p.word_count for p in pages)

        metadata = {
            "format": format_type.value,
            "line_count": len(cleaned.splitlines()),
        }

        if format_type == SupportedFormat.SQL:
            statements = [s.strip() for s in re.split(r';\s*', cleaned) if s.strip()]
            metadata["sql_statement_count"] = len(statements)

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=len(pages),
            total_characters=total_chars,
            total_words=total_words,
            pages=pages,
            metadata=metadata
        )

    def _decode_bytes(self, b: bytes, filename: str) -> str:
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode("utf-8", errors="replace")

    def _strip_rtf(self, rtf_text: str) -> str:
        """Strip basic RTF control sequences into readable plain text."""
        # Remove RTF control words (\word or \word123)
        stripped = re.sub(r'\\[a-zA-Z]+(-?\d+)? ?', '', rtf_text)
        # Remove RTF groups { ... }
        stripped = re.sub(r'[{}]', '', stripped)
        return stripped.strip()

    def _paginate_text(self, text: str, document_id: str, document_name: str, page_size: int = 3000) -> List[ExtractedPage]:
        lines = text.splitlines(keepends=True)
        pages: List[ExtractedPage] = []
        current_page_lines: List[str] = []
        current_len = 0
        page_num = 1

        for line in lines:
            line_len = len(line)
            if current_len + line_len > page_size and current_page_lines:
                page_text = "".join(current_page_lines).strip()
                if page_text:
                    pages.append(ExtractedPage(
                        document_id=document_id,
                        document_name=document_name,
                        page_number=page_num,
                        text=page_text,
                        char_count=len(page_text),
                        word_count=len(page_text.split())
                    ))
                    page_num += 1
                current_page_lines = [line]
                current_len = line_len
            else:
                current_page_lines.append(line)
                current_len += line_len

        if current_page_lines:
            page_text = "".join(current_page_lines).strip()
            if page_text:
                pages.append(ExtractedPage(
                    document_id=document_id,
                    document_name=document_name,
                    page_number=page_num,
                    text=page_text,
                    char_count=len(page_text),
                    word_count=len(page_text.split())
                ))

        return pages or [ExtractedPage(
            document_id=document_id,
            document_name=document_name,
            page_number=1,
            text=text,
            char_count=len(text),
            word_count=len(text.split())
        )]

# -----------------------------------------------------------------------------
# 2. DOCX Extractor
# -----------------------------------------------------------------------------
class DocxExtractor(BaseFormatExtractor):
    """Extracts text, headings, and tables from DOCX documents."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            sections_text: List[str] = []

            for p in doc.paragraphs:
                p_text = p.text.strip()
                if p_text:
                    if p.style and p.style.name.startswith("Heading"):
                        sections_text.append(f"\n## {p_text}\n")
                    else:
                        sections_text.append(p_text)

            for table in doc.tables:
                table_rows = []
                for row in table.rows:
                    row_cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                    table_rows.append(" | ".join(row_cells))
                if table_rows:
                    sections_text.append("\n[Table]\n" + "\n".join(table_rows) + "\n")

            full_text = "\n\n".join(sections_text)

        except Exception as e:
            # Fallback to direct OOXML zip extraction if docx fails
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    text_nodes = tree.findall(".//w:t", ns)
                    full_text = " ".join([t.text for t in text_nodes if t.text])
            except Exception as zip_e:
                raise DocumentExtractionError(f"Invalid or corrupted DOCX file {document_name}: {str(e)}")

        cleaned = self.clean_text(full_text)
        if not cleaned:
            raise DocumentExtractionError(f"DOCX document {document_name} has no text content.")

        text_extractor = TextDocumentExtractor()
        pages = text_extractor._paginate_text(cleaned, document_id, document_name)

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=len(pages),
            total_characters=sum(p.char_count for p in pages),
            total_words=sum(p.word_count for p in pages),
            pages=pages,
            metadata={"format": "docx"}
        )

# -----------------------------------------------------------------------------
# 3. HTML Extractor
# -----------------------------------------------------------------------------
class HtmlExtractor(BaseFormatExtractor):
    """Extracts structured text and headers from HTML documents."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            from bs4 import BeautifulSoup
            html_str = file_bytes.decode("utf-8", errors="replace")
            soup = BeautifulSoup(html_str, "html.parser")

            # Remove script and style elements
            for tag in soup(["script", "style", "meta", "noscript", "svg"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            body_text = soup.get_text(separator="\n", strip=True)
            full_text = f"# {title}\n\n{body_text}" if title else body_text

        except Exception as e:
            # Fallback regex extraction if bs4 fails
            html_str = file_bytes.decode("utf-8", errors="replace")
            clean_html = re.sub(r'<script.*?</script>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<style.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            full_text = re.sub(r'<[^>]+>', ' ', clean_html)

        cleaned = self.clean_text(full_text)
        if not cleaned:
            raise DocumentExtractionError(f"HTML document {document_name} has no text content.")

        text_extractor = TextDocumentExtractor()
        pages = text_extractor._paginate_text(cleaned, document_id, document_name)

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=len(pages),
            total_characters=sum(p.char_count for p in pages),
            total_words=sum(p.word_count for p in pages),
            pages=pages,
            metadata={"format": "html"}
        )

# -----------------------------------------------------------------------------
# 4. XML Extractor
# -----------------------------------------------------------------------------
class XmlExtractor(BaseFormatExtractor):
    """Extracts elements, attributes, hierarchy, and text from XML documents."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(file_bytes)
        except Exception as e:
            raise DocumentExtractionError(f"Invalid or corrupted XML in {document_name}: {str(e)}")

        element_hierarchy: List[Dict[str, Any]] = []
        text_lines: List[str] = [f"XML Document: {document_name}", f"Root Element: <{root.tag}>\n"]
        total_elements = 0

        def traverse(element: ET.Element, path: str = "", depth: int = 0):
            nonlocal total_elements
            total_elements += 1
            current_path = f"{path}/{element.tag}" if path else element.tag
            indent = "  " * depth

            attrs_str = ", ".join([f"{k}='{v}'" for k, v in element.attrib.items()]) if element.attrib else ""
            attr_display = f" [{attrs_str}]" if attrs_str else ""
            elem_text = (element.text or "").strip()

            line = f"{indent}<{element.tag}>{attr_display}"
            if elem_text:
                line += f": {elem_text}"
            text_lines.append(line)

            element_hierarchy.append({
                "tag": element.tag,
                "path": current_path,
                "depth": depth,
                "attributes": element.attrib,
                "text": elem_text
            })

            for child in element:
                traverse(child, current_path, depth + 1)

        traverse(root)
        full_text = "\n".join(text_lines)
        cleaned = self.clean_text(full_text)

        text_extractor = TextDocumentExtractor()
        pages = text_extractor._paginate_text(cleaned, document_id, document_name)

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=len(pages),
            total_characters=sum(p.char_count for p in pages),
            total_words=sum(p.word_count for p in pages),
            pages=pages,
            metadata={
                "format": "xml",
                "root_tag": root.tag,
                "element_count": total_elements,
                "hierarchy": element_hierarchy[:100]
            }
        )

# -----------------------------------------------------------------------------
# 5. Tabular Extractor (CSV & TSV)
# -----------------------------------------------------------------------------
class TabularExtractor(BaseFormatExtractor):
    """Extracts schema, columns, rows, and structured representations from CSV & TSV."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        text_extractor = TextDocumentExtractor()
        raw_text = text_extractor._decode_bytes(file_bytes, document_name)
        delimiter = "\t" if format_type == SupportedFormat.TSV or document_name.lower().endswith(".tsv") else ","

        try:
            reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
            rows = [r for r in reader if r]
        except Exception as e:
            raise DocumentExtractionError(f"Error parsing tabular data in {document_name}: {str(e)}")

        if not rows:
            raise DocumentExtractionError(f"Tabular file {document_name} contains no records.")

        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
        record_count = len(data_rows)

        # Infer column types from sample data
        column_types = self._infer_column_types(headers, data_rows[:100])

        # Generate structured text representation
        lines = [
            f"Dataset: {document_name}",
            f"Type: Tabular ({format_type.value.upper()})",
            f"Total Records: {record_count}",
            f"Total Columns: {len(headers)}",
            "\nColumns Schema:",
        ]
        for col, ctype in column_types.items():
            lines.append(f"  - Column: `{col}` (Type: {ctype})")

        lines.append("\nSample Records:")
        for idx, r in enumerate(data_rows[:25]):
            row_dict = dict(zip(headers, r))
            row_items = ", ".join([f"{k}: {v}" for k, v in row_dict.items() if v.strip()])
            lines.append(f"  Record #{idx + 1}: {row_items}")

        full_text = "\n".join(lines)
        cleaned = self.clean_text(full_text)

        pages = [ExtractedPage(
            document_id=document_id,
            document_name=document_name,
            page_number=1,
            text=cleaned,
            char_count=len(cleaned),
            word_count=len(cleaned.split())
        )]

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=1,
            total_characters=len(cleaned),
            total_words=len(cleaned.split()),
            pages=pages,
            metadata={
                "format": format_type.value,
                "table_name": Path(document_name).stem,
                "record_count": record_count,
                "column_count": len(headers),
                "columns": headers,
                "column_types": column_types,
                "sample_rows": [dict(zip(headers, r)) for r in data_rows[:10]]
            }
        )

    def _infer_column_types(self, headers: List[str], sample_rows: List[List[str]]) -> Dict[str, str]:
        types: Dict[str, str] = {}
        for idx, col in enumerate(headers):
            values = [r[idx].strip() for r in sample_rows if idx < len(r) and r[idx].strip()]
            if not values:
                types[col] = "String"
                continue

            is_int = all(re.match(r'^-?\d+$', v) for v in values)
            is_float = all(re.match(r'^-?\d+(\.\d+)?$', v) for v in values)
            is_bool = all(v.lower() in ("true", "false", "yes", "no", "0", "1") for v in values)

            if is_int:
                types[col] = "Integer"
            elif is_float:
                types[col] = "Float"
            elif is_bool:
                types[col] = "Boolean"
            else:
                types[col] = "String"
        return types

# -----------------------------------------------------------------------------
# 6. Spreadsheet Extractor (XLSX & XLS)
# -----------------------------------------------------------------------------
class SpreadsheetExtractor(BaseFormatExtractor):
    """Extracts sheets, columns, and records from Excel workbooks."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet_names = wb.sheetnames
        except Exception as e:
            try:
                import pandas as pd
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
                sheet_names = excel_file.sheet_names
            except Exception as pd_e:
                raise DocumentExtractionError(f"Invalid or corrupted Excel file {document_name}: {str(e)}")

        pages: List[ExtractedPage] = []
        sheets_metadata: List[Dict[str, Any]] = []
        total_records = 0

        for page_idx, sheet_name in enumerate(sheet_names):
            try:
                import pandas as pd
                df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
                headers = [str(c) for c in df.columns]
                num_rows = len(df)
                total_records += num_rows

                lines = [
                    f"Workbook: {document_name}",
                    f"Sheet: {sheet_name}",
                    f"Total Rows: {num_rows}",
                    f"Columns: {', '.join(headers)}",
                    "\nColumns & Types:",
                ]
                for col in df.columns:
                    lines.append(f"  - Column `{col}` (Type: {df[col].dtype})")

                lines.append("\nSample Records:")
                for r_idx, row in df.head(15).iterrows():
                    row_items = ", ".join([f"{k}: {v}" for k, v in row.to_dict().items() if pd.notna(v)])
                    lines.append(f"  Row #{r_idx + 1}: {row_items}")

                sheet_text = self.clean_text("\n".join(lines))
                pages.append(ExtractedPage(
                    document_id=document_id,
                    document_name=document_name,
                    page_number=page_idx + 1,
                    text=sheet_text,
                    char_count=len(sheet_text),
                    word_count=len(sheet_text.split())
                ))

                sheets_metadata.append({
                    "sheet_name": sheet_name,
                    "row_count": num_rows,
                    "column_count": len(headers),
                    "columns": headers
                })
            except Exception:
                continue

        if not pages:
            raise DocumentExtractionError(f"No readable sheets found in {document_name}")

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=len(pages),
            total_characters=sum(p.char_count for p in pages),
            total_words=sum(p.word_count for p in pages),
            pages=pages,
            metadata={
                "format": format_type.value,
                "sheet_count": len(sheets_metadata),
                "record_count": total_records,
                "sheets": sheets_metadata
            }
        )

# -----------------------------------------------------------------------------
# 7. JSON & JSONL Extractor
# -----------------------------------------------------------------------------
class JsonExtractor(BaseFormatExtractor):
    """Extracts structured JSON objects, schema keys, and JSONL records."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        text_extractor = TextDocumentExtractor()
        raw_text = text_extractor._decode_bytes(file_bytes, document_name)

        if format_type == SupportedFormat.JSONL or document_name.lower().endswith((".jsonl", ".ndjson")):
            records = []
            for line in raw_text.splitlines():
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except Exception as e:
                        raise DocumentExtractionError(f"Invalid JSONL in {document_name}: {str(e)}")
            parsed_data = records
            is_jsonl = True
        else:
            try:
                parsed_data = json.loads(raw_text)
                is_jsonl = False
            except Exception as e:
                raise DocumentExtractionError(f"Invalid or malformed JSON in {document_name}: {str(e)}")

        # Build structured representation
        lines = [f"JSON Dataset: {document_name}"]
        schema_keys: List[str] = []
        nested_fields: List[Dict[str, Any]] = []

        if isinstance(parsed_data, list):
            record_count = len(parsed_data)
            lines.append(f"Structure: Array of {record_count} records")
            if parsed_data and isinstance(parsed_data[0], dict):
                schema_keys = list(parsed_data[0].keys())
                lines.append(f"Item Keys: {', '.join(schema_keys)}")
                lines.append("\nSample Records:")
                for idx, item in enumerate(parsed_data[:20]):
                    lines.append(f"  Item #{idx + 1}: {json.dumps(item)}")
        elif isinstance(parsed_data, dict):
            record_count = len(parsed_data)
            schema_keys = list(parsed_data.keys())
            lines.append(f"Structure: Object with {record_count} top-level keys: {', '.join(schema_keys)}")
            lines.append("\nKey-Value Details:")
            for k, v in list(parsed_data.items())[:30]:
                if isinstance(v, (dict, list)):
                    lines.append(f"  - Key `{k}`: {type(v).__name__} (length {len(v)})")
                    nested_fields.append({"key": k, "type": type(v).__name__, "value_preview": str(v)[:100]})
                else:
                    lines.append(f"  - Key `{k}`: {v}")
                    nested_fields.append({"key": k, "type": type(v).__name__, "value": v})
        else:
            record_count = 1
            lines.append(f"Primitive Value: {parsed_data}")

        full_text = self.clean_text("\n".join(lines))
        pages = [ExtractedPage(
            document_id=document_id,
            document_name=document_name,
            page_number=1,
            text=full_text,
            char_count=len(full_text),
            word_count=len(full_text.split())
        )]

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=1,
            total_characters=len(full_text),
            total_words=len(full_text.split()),
            pages=pages,
            metadata={
                "format": "jsonl" if is_jsonl else "json",
                "record_count": record_count,
                "schema_keys": schema_keys,
                "nested_fields": nested_fields
            }
        )

# -----------------------------------------------------------------------------
# 8. Parquet & Feather Extractor
# -----------------------------------------------------------------------------
class ParquetExtractor(BaseFormatExtractor):
    """Extracts schema, column types, record counts, and data from Parquet & Feather files."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        try:
            import pyarrow.parquet as pq
            import pyarrow.feather as feather

            if format_type == SupportedFormat.FEATHER or document_name.lower().endswith((".feather", ".arrow")):
                table = feather.read_table(io.BytesIO(file_bytes))
            else:
                table = pq.read_table(io.BytesIO(file_bytes))

            schema = table.schema
            column_names = schema.names
            record_count = table.num_rows
            column_types = {name: str(schema.field(name).type) for name in column_names}

            # Convert head to pandas for display
            df_sample = table.slice(0, 20).to_pandas()

        except Exception as e:
            raise DocumentExtractionError(f"Invalid or corrupted Parquet/Feather file {document_name}: {str(e)}")

        lines = [
            f"Analytics Dataset: {document_name}",
            f"Format: {format_type.value.upper()}",
            f"Total Rows: {record_count}",
            f"Total Columns: {len(column_names)}",
            "\nColumns & Arrow Types:",
        ]
        for col, ctype in column_types.items():
            lines.append(f"  - Column `{col}` (Type: {ctype})")

        lines.append("\nSample Records:")
        for idx, row in df_sample.iterrows():
            row_items = ", ".join([f"{k}: {v}" for k, v in row.to_dict().items()])
            lines.append(f"  Row #{idx + 1}: {row_items}")

        full_text = self.clean_text("\n".join(lines))
        pages = [ExtractedPage(
            document_id=document_id,
            document_name=document_name,
            page_number=1,
            text=full_text,
            char_count=len(full_text),
            word_count=len(full_text.split())
        )]

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=1,
            total_characters=len(full_text),
            total_words=len(full_text.split()),
            pages=pages,
            metadata={
                "format": format_type.value,
                "table_name": Path(document_name).stem,
                "record_count": record_count,
                "column_count": len(column_names),
                "columns": column_names,
                "column_types": column_types
            }
        )

# -----------------------------------------------------------------------------
# 9. YAML Extractor
# -----------------------------------------------------------------------------
class YamlExtractor(BaseFormatExtractor):
    """Extracts structured configuration mappings and keys from YAML files."""

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        document_name: str,
        format_type: SupportedFormat
    ) -> ExtractedDocument:
        if not file_bytes:
            raise DocumentExtractionError(f"Cannot extract from empty file (0 bytes) for {document_name}")

        text_extractor = TextDocumentExtractor()
        raw_text = text_extractor._decode_bytes(file_bytes, document_name)

        try:
            import yaml
            parsed_yaml = yaml.safe_load(raw_text)
        except Exception as e:
            raise DocumentExtractionError(f"Invalid or malformed YAML in {document_name}: {str(e)}")

        lines = [f"YAML Configuration: {document_name}"]
        top_keys: List[str] = []

        def format_yaml_node(node: Any, depth: int = 0) -> List[str]:
            res: List[str] = []
            indent = "  " * depth
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, (dict, list)):
                        res.append(f"{indent}- `{k}`:")
                        res.extend(format_yaml_node(v, depth + 1))
                    else:
                        res.append(f"{indent}- `{k}`: {v}")
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        res.extend(format_yaml_node(item, depth + 1))
                    else:
                        res.append(f"{indent}  * {item}")
            else:
                res.append(f"{indent}{node}")
            return res

        if isinstance(parsed_yaml, dict):
            top_keys = list(parsed_yaml.keys())
            lines.append(f"Top-level Keys: {', '.join(top_keys)}")
            lines.append("\nConfiguration Tree:")
            lines.extend(format_yaml_node(parsed_yaml))
        elif isinstance(parsed_yaml, list):
            lines.append(f"List with {len(parsed_yaml)} items")
            lines.extend(format_yaml_node(parsed_yaml))
        else:
            lines.append(f"Value: {parsed_yaml}")

        full_text = self.clean_text("\n".join(lines))
        pages = [ExtractedPage(
            document_id=document_id,
            document_name=document_name,
            page_number=1,
            text=full_text,
            char_count=len(full_text),
            word_count=len(full_text.split())
        )]

        return ExtractedDocument(
            document_id=document_id,
            document_name=document_name,
            total_pages=1,
            total_characters=len(full_text),
            total_words=len(full_text.split()),
            pages=pages,
            metadata={
                "format": "yaml",
                "top_keys": top_keys,
                "parsed_data": parsed_yaml if isinstance(parsed_yaml, dict) else {}
            }
        )
