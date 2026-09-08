"""
PDF to Context to Apache AGE Knowledge Graph Pipeline Orchestrator
==================================================================
Explicit end-to-end execution with SHA-256 deduplication and idempotent graph ingestion:
PDF (Upload) -> Lakehouse (Raw & Metadata) -> Text Extraction -> Chunks
-> Context Extraction (Entities & Relations) -> Deduplication -> Apache AGE Ingestion -> Knowledge Graph
"""

import time
import logging
import uuid
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.config import settings
from backend.storage.base import StorageService
from backend.storage.lakehouse import LocalLakehouseStorageService
from backend.storage.models import DocumentMetadata, ProcessingStatus, ExtractionMethod
from backend.extraction.pdf_extractor import PDFExtractor, ExtractedDocument
from backend.extraction.document_extractor import DocumentExtractor
from backend.extraction.chunker import DocumentChunker, DocumentChunk
from backend.context.extractor import ContextExtractor
from backend.context.schemas import DocumentContext
from backend.graph.graph_service import GraphService

logger = logging.getLogger("pipeline")

class PDFContextPipeline:
    def __init__(
        self,
        storage: Optional[StorageService] = None,
        extractor: Optional[Any] = None,
        chunker: Optional[DocumentChunker] = None,
        context_extractor: Optional[ContextExtractor] = None,
        graph_service: Optional[GraphService] = None
    ):
        self.storage = storage or LocalLakehouseStorageService()
        self.extractor = extractor or DocumentExtractor()
        self.chunker = chunker or DocumentChunker()
        self.context_extractor = context_extractor or ContextExtractor()
        self.graph_service = graph_service or GraphService()

    def upload_document(
        self,
        filename: str,
        file_bytes: bytes,
        document_id: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentMetadata:
        """
        Store any supported document or data file in Lakehouse raw tier with SHA-256 content deduplication.
        If identical document content already exists, returns the existing document record.
        """
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        existing = self.storage.get_document_by_hash(sha256_hash)
        if existing:
            logger.info(f"Duplicate document detected (SHA-256: {sha256_hash[:12]}...). Returning existing document ID: '{existing.document_id}'")
            return existing

        doc_id = document_id or f"doc_{uuid.uuid4().hex[:10]}"
        logger.info(f"Uploading new document '{filename}' to Lakehouse with doc ID '{doc_id}' (SHA-256: {sha256_hash[:12]}...)")
        return self.storage.upload_document(
            document_id=doc_id,
            filename=filename,
            file_bytes=file_bytes,
            custom_metadata=custom_metadata
        )

    def upload_pdf(
        self,
        filename: str,
        file_bytes: bytes,
        document_id: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentMetadata:
        """
        Store PDF in Lakehouse raw tier with SHA-256 content deduplication (legacy wrapper).
        """
        return self.upload_document(
            filename=filename,
            file_bytes=file_bytes,
            document_id=document_id,
            custom_metadata=custom_metadata
        )

    def process_document(
        self,
        document_id: str,
        force_provider: Optional[str] = None,
        reprocess: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the full explicit pipeline:
        PDF -> Lakehouse -> Extraction -> Chunking -> Context -> Apache AGE -> Graph

        Idempotency: If document is already COMPLETED and reprocess=False, returns existing context
        and graph metrics without re-running ingestion or creating duplicate nodes/edges.
        """
        meta = self.storage.get_metadata(document_id)
        if not meta:
            raise KeyError(f"Document {document_id} not found in Lakehouse.")

        # Idempotency check
        if not reprocess and meta.status == ProcessingStatus.COMPLETED:
            logger.info(f"Document {document_id} is already COMPLETED. Returning existing Lakehouse context.")
            existing_ctx = self.storage.get_context(document_id) or {}
            existing_pages = self.storage.get_extracted_pages(document_id) or []
            existing_chunks = self.storage.get_chunks(document_id) or []
            
            return {
                "document_id": document_id,
                "document_name": meta.document_name,
                "status": ProcessingStatus.COMPLETED.value,
                "extraction_method": meta.extraction_method.value if meta.extraction_method else "HEURISTIC_NLP",
                "total_pages": len(existing_pages),
                "total_chunks": len(existing_chunks),
                "total_entities": meta.total_entities or len(existing_ctx.get("entities", [])),
                "total_relationships": meta.total_relationships or len(existing_ctx.get("relationships", [])),
                "processing_time_sec": meta.processing_time_sec or 0.0,
                "nodes_added": meta.nodes_added or 0,
                "edges_added": meta.edges_added or 0,
                "already_processed": True
            }

        logger.info(f"Starting pipeline processing for document: {meta.document_name} ({document_id}) [reprocess={reprocess}]")
        start_time = time.perf_counter()

        try:
            # 1. State: EXTRACTING
            self.storage.update_status(document_id, ProcessingStatus.EXTRACTING)
            raw_pdf_path = self.storage.get_document_path(document_id)

            # 2. PDF Text Extraction
            logger.info(f"Extracting page-level text from {meta.document_name}")
            extracted_doc = self.extractor.extract_from_path(
                file_path=raw_pdf_path,
                document_id=document_id,
                document_name=meta.document_name
            )

            # Save extracted pages to Lakehouse extracted_pages tier
            pages_data = [
                {
                    "document_id": p.document_id,
                    "document_name": p.document_name,
                    "page_number": p.page_number,
                    "text": p.text,
                    "char_count": p.char_count,
                    "word_count": p.word_count
                }
                for p in extracted_doc.pages
            ]
            self.storage.save_extracted_pages(document_id, pages_data)
            self.storage.update_status(
                document_id,
                ProcessingStatus.EXTRACTED,
                total_pages=extracted_doc.total_pages
            )

            # 3. State: GENERATING_CONTEXT
            self.storage.update_status(document_id, ProcessingStatus.GENERATING_CONTEXT)

            # Chunking with provenance tracking
            logger.info(f"Chunking text into passages with sliding window overlap")
            chunks = self.chunker.chunk_document(extracted_doc)
            chunks_data = [c.to_dict() for c in chunks]
            self.storage.save_chunks(document_id, chunks_data)

            # Context Extraction (Entities + Relationships + Summary + Provenance)
            logger.info(f"Extracting high-precision structured entities and relationships from {len(chunks)} chunks")
            context: DocumentContext = self.context_extractor.extract_context(
                document=extracted_doc,
                chunks=chunks,
                force_provider=force_provider
            )

            # Save structured context to Lakehouse context tier
            self.storage.save_context(document_id, context.to_dict())

            # 4. State: BUILDING_GRAPH
            self.storage.update_status(document_id, ProcessingStatus.BUILDING_GRAPH)

            # Apache AGE Ingestion
            logger.info(f"Ingesting {len(context.entities)} vertices and {len(context.relationships)} edges into Apache AGE")
            graph_summary = self.graph_service.ingest_context(context)

            # Save graph sync record to Lakehouse graph_sync tier
            self.storage.record_graph_sync(document_id, graph_summary)

            elapsed_sec = round(time.perf_counter() - start_time, 3)

            # 5. State: COMPLETED
            updated_meta = self.storage.update_status(
                document_id,
                ProcessingStatus.COMPLETED,
                total_chunks=len(chunks),
                total_entities=len(context.entities),
                total_relationships=len(context.relationships),
                extraction_method=ExtractionMethod(context.extraction_method),
                processing_time_sec=elapsed_sec,
                nodes_added=graph_summary.get("nodes_created", 0),
                edges_added=graph_summary.get("edges_created", 0)
            )

            logger.info(f"Pipeline completed successfully for document {document_id} in {elapsed_sec}s")
            return {
                "document_id": document_id,
                "document_name": meta.document_name,
                "status": ProcessingStatus.COMPLETED.value,
                "extraction_method": context.extraction_method,
                "total_pages": extracted_doc.total_pages,
                "total_chunks": len(chunks),
                "total_entities": len(context.entities),
                "total_relationships": len(context.relationships),
                "processing_time_sec": elapsed_sec,
                "nodes_added": graph_summary.get("nodes_created", 0),
                "edges_added": graph_summary.get("edges_created", 0),
                "graph_ingestion": graph_summary,
                "already_processed": False
            }

        except Exception as e:
            logger.error(f"Pipeline execution failed for {document_id}: {str(e)}", exc_info=True)
            self.storage.update_status(
                document_id,
                ProcessingStatus.FAILED,
                error_message=str(e)
            )
            raise e
