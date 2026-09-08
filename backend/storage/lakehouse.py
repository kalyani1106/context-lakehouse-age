"""
Local Lakehouse Storage Service Implementation
==============================================
NOTE: This is a modular local/development Lakehouse implementation using structured directory tiers,
Parquet file tables, SHA-256 deduplication, and metadata cataloging. In production, this can be swapped
with Delta Lake, Apache Iceberg, or Cloud Storage (S3/GCS/BigLake) without altering the pipeline contracts.

Tier Architecture:
- backend/lakehouse_storage/
  ├── raw/               (Original unmodified PDF binaries)
  ├── metadata/          (Document catalog & lifecycle state tracking)
  ├── extracted_pages/   (Page-level texts & metadata as Parquet & JSON)
  ├── chunks/            (Passage chunks with token & char spans as Parquet & JSON)
  ├── context/           (Structured entities, relationships & provenance as Parquet & JSON)
  └── graph_sync/        (Ingestion logs and status to Apache AGE)
"""

import json
import hashlib
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import pandas as pd

from backend.storage.base import StorageService
from backend.storage.models import DocumentMetadata, ProcessingStatus, LakehouseLayer, ExtractionMethod
from backend.config import settings

class LocalLakehouseStorageService(StorageService):
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or settings.LAKEHOUSE_ROOT
        self._init_lakehouse_tiers()

    def _init_lakehouse_tiers(self):
        """Create explicit directories for every architectural lakehouse tier."""
        for layer in LakehouseLayer:
            layer_dir = self.root_dir / layer.value
            layer_dir.mkdir(parents=True, exist_ok=True)

    @property
    def raw_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.RAW.value

    @property
    def metadata_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.METADATA.value

    @property
    def extracted_pages_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.EXTRACTED_PAGES.value

    @property
    def chunks_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.CHUNKS.value

    @property
    def context_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.CONTEXT.value

    @property
    def graph_sync_dir(self) -> Path:
        return self.root_dir / LakehouseLayer.GRAPH_SYNC.value

    def get_document_by_hash(self, sha256_hash: str) -> Optional[DocumentMetadata]:
        """Search the metadata catalog for a document matching the SHA-256 hash."""
        for doc in self.list_documents():
            if getattr(doc, "sha256", None) == sha256_hash:
                return doc
        return None

    def upload_document(
        self,
        document_id: str,
        filename: str,
        file_bytes: bytes,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentMetadata:
        # Calculate SHA-256 hash of document bytes
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()

        # Check if identical document already exists in Lakehouse
        existing = self.get_document_by_hash(sha256_hash)
        if existing:
            # Document with identical content already exists, return existing record
            return existing

        # Determine extension and MIME type
        ext = Path(filename).suffix.lower() or ".bin"
        try:
            from backend.extraction.file_detector import FileDetector
            _, mime_type, _ = FileDetector.detect_format(filename, file_bytes)
        except Exception:
            mime_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"

        # 1. Store in RAW tier
        raw_path = self.raw_dir / f"{document_id}{ext}"
        with open(raw_path, "wb") as f:
            f.write(file_bytes)

        # 2. Build metadata record
        meta = DocumentMetadata(
            document_id=document_id,
            document_name=filename,
            file_type=mime_type,
            file_size_bytes=len(file_bytes),
            sha256=sha256_hash,
            status=ProcessingStatus.UPLOADED,
            uploaded_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            custom_metadata=custom_metadata or {}
        )

        # 3. Save to METADATA tier
        self._save_metadata(meta)
        return meta

    def get_document_path(self, document_id: str) -> Path:
        # First check if document_id.pdf exists (legacy or standard)
        pdf_path = self.raw_dir / f"{document_id}.pdf"
        if pdf_path.exists():
            return pdf_path

        # Next check using metadata document_name extension
        meta = self.get_metadata(document_id)
        if meta and meta.document_name:
            ext = Path(meta.document_name).suffix.lower()
            exact_path = self.raw_dir / f"{document_id}{ext}"
            if exact_path.exists():
                return exact_path

        # Search for any matching file document_id.* in raw dir
        matches = list(self.raw_dir.glob(f"{document_id}.*"))
        if matches:
            return matches[0]

        raise FileNotFoundError(f"Raw file for document {document_id} not found in Lakehouse raw tier.")

    def get_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        meta_path = self.metadata_dir / f"{document_id}.json"
        if not meta_path.exists():
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Backwards compatibility for sha256 if missing in old json
            if "sha256" not in data:
                data["sha256"] = "unknown_legacy"
            return DocumentMetadata(**data)

    def list_documents(self) -> List[DocumentMetadata]:
        docs = []
        for file in self.metadata_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "sha256" not in data:
                        data["sha256"] = "unknown_legacy"
                    docs.append(DocumentMetadata(**data))
            except Exception:
                continue
        # Sort newest first
        return sorted(docs, key=lambda d: d.uploaded_at, reverse=True)

    def update_status(
        self,
        document_id: str,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
        **kwargs
    ) -> DocumentMetadata:
        meta = self.get_metadata(document_id)
        if not meta:
            raise KeyError(f"Document {document_id} not found in Lakehouse catalog.")
        
        meta.status = status
        meta.updated_at = datetime.now(timezone.utc)
        if error_message:
            meta.error_message = error_message
        
        for k, v in kwargs.items():
            if hasattr(meta, k):
                setattr(meta, k, v)
            else:
                meta.custom_metadata[k] = v

        self._save_metadata(meta)
        return meta

    def save_extracted_pages(self, document_id: str, pages_data: List[Dict[str, Any]]) -> None:
        """Save extracted page text to EXTRACTED_PAGES tier as Parquet and JSON."""
        json_path = self.extracted_pages_dir / f"{document_id}.json"
        parquet_path = self.extracted_pages_dir / f"{document_id}.parquet"
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(pages_data, f, indent=2, ensure_ascii=False)
            
        df = pd.DataFrame(pages_data)
        df.to_parquet(parquet_path, index=False)

    def get_extracted_pages(self, document_id: str) -> Optional[List[Dict[str, Any]]]:
        json_path = self.extracted_pages_dir / f"{document_id}.json"
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_chunks(self, document_id: str, chunks_data: List[Dict[str, Any]]) -> None:
        """Save chunked passages to CHUNKS tier as Parquet and JSON."""
        json_path = self.chunks_dir / f"{document_id}.json"
        parquet_path = self.chunks_dir / f"{document_id}.parquet"
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f, indent=2, ensure_ascii=False)
            
        df = pd.DataFrame(chunks_data)
        df.to_parquet(parquet_path, index=False)

    def get_chunks(self, document_id: str) -> Optional[List[Dict[str, Any]]]:
        json_path = self.chunks_dir / f"{document_id}.json"
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_context(self, document_id: str, context_data: Dict[str, Any]) -> None:
        """Save structured context (entities & relationships) to CONTEXT tier as JSON and Parquet."""
        json_path = self.context_dir / f"{document_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(context_data, f, indent=2, ensure_ascii=False)
            
        entities = context_data.get("entities", [])
        relationships = context_data.get("relationships", [])
        
        if entities:
            ent_df = pd.json_normalize(entities)
            ent_df.to_parquet(self.context_dir / f"{document_id}_entities.parquet", index=False)
            
        if relationships:
            rel_df = pd.json_normalize(relationships)
            rel_df.to_parquet(self.context_dir / f"{document_id}_relationships.parquet", index=False)

    def get_context(self, document_id: str) -> Optional[Dict[str, Any]]:
        json_path = self.context_dir / f"{document_id}.json"
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def record_graph_sync(self, document_id: str, sync_info: Dict[str, Any]) -> None:
        """Record sync details and statistics into GRAPH_SYNC tier."""
        sync_path = self.graph_sync_dir / f"{document_id}.json"
        with open(sync_path, "w", encoding="utf-8") as f:
            json.dump(sync_info, f, indent=2, ensure_ascii=False)

    def delete_document(self, document_id: str) -> bool:
        """Clean up document across all lakehouse tiers."""
        deleted = False
        files_to_remove = [
            self.raw_dir / f"{document_id}.pdf",
            self.metadata_dir / f"{document_id}.json",
            self.extracted_pages_dir / f"{document_id}.json",
            self.extracted_pages_dir / f"{document_id}.parquet",
            self.chunks_dir / f"{document_id}.json",
            self.chunks_dir / f"{document_id}.parquet",
            self.context_dir / f"{document_id}.json",
            self.context_dir / f"{document_id}_entities.parquet",
            self.context_dir / f"{document_id}_relationships.parquet",
            self.graph_sync_dir / f"{document_id}.json",
        ]
        for p in files_to_remove:
            if p.exists():
                p.unlink()
                deleted = True
        return deleted

    def _save_metadata(self, meta: DocumentMetadata):
        meta_path = self.metadata_dir / f"{meta.document_id}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2, ensure_ascii=False)
