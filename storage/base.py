from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, BinaryIO
from pathlib import Path
from storage.models import DocumentMetadata, ProcessingStatus

class StorageService(ABC):
    """
    Abstract interface for Lakehouse document storage and metadata catalog.
    Enables pluggable lakehouse backends (Local DuckDB/Parquet, Delta Lake, Iceberg, S3/GCS).
    """

    @abstractmethod
    def upload_document(
        self,
        document_id: str,
        filename: str,
        file_bytes: bytes,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentMetadata:
        """Store original raw PDF in Lakehouse and register metadata with SHA-256 deduplication."""
        pass

    @abstractmethod
    def get_document_by_hash(self, sha256_hash: str) -> Optional[DocumentMetadata]:
        """Check if a document with identical SHA-256 hash exists in Lakehouse catalog."""
        pass

    @abstractmethod
    def get_document_path(self, document_id: str) -> Path:
        """Return local file system path for the raw PDF."""
        pass

    @abstractmethod
    def get_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        """Fetch metadata for a document."""
        pass

    @abstractmethod
    def list_documents(self) -> List[DocumentMetadata]:
        """List all documents in the Lakehouse catalog."""
        pass

    @abstractmethod
    def update_status(
        self,
        document_id: str,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
        **kwargs
    ) -> DocumentMetadata:
        """Update processing lifecycle status."""
        pass

    @abstractmethod
    def save_extracted_pages(self, document_id: str, pages_data: List[Dict[str, Any]]) -> None:
        """Store extracted page text in lakehouse extracted_pages tier."""
        pass

    @abstractmethod
    def get_extracted_pages(self, document_id: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve extracted pages for a document."""
        pass

    @abstractmethod
    def save_chunks(self, document_id: str, chunks_data: List[Dict[str, Any]]) -> None:
        """Store chunked passages in lakehouse chunks tier."""
        pass

    @abstractmethod
    def get_chunks(self, document_id: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve chunks for a document."""
        pass

    @abstractmethod
    def save_context(self, document_id: str, context_data: Dict[str, Any]) -> None:
        """Store structured context (entities & relationships) in lakehouse context tier."""
        pass

    @abstractmethod
    def get_context(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve structured context for a document."""
        pass

    @abstractmethod
    def delete_document(self, document_id: str) -> bool:
        """Delete raw document and all associated lakehouse tier artifacts."""
        pass
