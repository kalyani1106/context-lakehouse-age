"""
Context Engine Facade
=====================
Unified intelligence and context retrieval layer coordinating query analysis,
hybrid graph + lexical retrieval, deterministic ranking, token-budgeted assembly,
and provenance citations.
"""

import time
import logging
from typing import Optional, Dict, Any, List

from .models import (
    ContextQueryRequest,
    ContextQueryResponse,
    QueryAnalysisResult,
    RetrievalStats,
    RetrievalMode,
    ContextItem,
    ContextType,
)
from .query_analyzer import QueryAnalyzer
from .graph_retriever import GraphRetriever
from .vector_retriever import VectorRetriever
from .ranker import ContextRanker
from .assembler import ContextAssembler

logger = logging.getLogger("context_engine")


class ContextEngine:
    """
    Central Context Engine facade providing end-to-end intelligent context retrieval
    for downstream LLMs, RAG applications, and conversational agents.
    """

    def __init__(
        self,
        query_analyzer: Optional[QueryAnalyzer] = None,
        graph_retriever: Optional[GraphRetriever] = None,
        vector_retriever: Optional[VectorRetriever] = None,
        ranker: Optional[ContextRanker] = None,
        assembler: Optional[ContextAssembler] = None,
    ):
        self.query_analyzer = query_analyzer or QueryAnalyzer()
        self.graph_retriever = graph_retriever or GraphRetriever()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.ranker = ranker or ContextRanker()
        self.assembler = assembler or ContextAssembler()

    def query_context(self, request: ContextQueryRequest) -> ContextQueryResponse:
        """
        Execute full context retrieval pipeline:
        1. Query Analysis
        2. Graph / Vector / Hybrid Retrieval
        3. Multi-Factor Context Ranking
        4. Token-Budgeted Context Assembly
        5. Rich Citation Formatting
        """
        start_time = time.perf_counter()

        # 1. Query Analysis
        analysis: QueryAnalysisResult = self.query_analyzer.analyze(
            query=request.query,
            default_filters={
                "repo_name": request.repo_name,
                "doc_name": request.doc_name,
                "document_id": request.document_id,
            }
        )

        candidates: List[ContextItem] = []
        nodes_count = 0
        edges_count = 0
        chunks_count = 0

        # 2. Retrieval according to mode
        mode = request.mode

        if mode in (RetrievalMode.HYBRID, RetrievalMode.GRAPH):
            try:
                graph_items = self.graph_retriever.retrieve(
                    analysis=analysis,
                    repo_name=request.repo_name,
                    doc_name=request.doc_name,
                    document_id=request.document_id,
                    traversal_depth=request.traversal_depth,
                    limit=request.top_k * 2,
                )
                for it in graph_items:
                    if it.type == ContextType.ENTITY:
                        nodes_count += 1
                    elif it.type == ContextType.RELATIONSHIP:
                        edges_count += 1
                candidates.extend(graph_items)
            except Exception as e:
                logger.warning(f"Graph retrieval error in ContextEngine: {e}")

        if mode in (RetrievalMode.HYBRID, RetrievalMode.SEMANTIC) and request.include_raw_chunks:
            try:
                vector_items = self.vector_retriever.retrieve(
                    analysis=analysis,
                    repo_name=request.repo_name,
                    doc_name=request.doc_name,
                    document_id=request.document_id,
                    limit=request.top_k * 2,
                )
                for it in vector_items:
                    if it.type in (ContextType.CHUNK, ContextType.FILE):
                        chunks_count += 1
                candidates.extend(vector_items)
            except Exception as e:
                logger.warning(f"Vector retrieval error in ContextEngine: {e}")

        # 3. Deterministic Ranking
        ranked_items = self.ranker.rank(
            items=candidates,
            analysis=analysis,
            graph_weight=request.graph_weight,
            semantic_weight=request.semantic_weight,
            provenance_weight=request.provenance_weight,
            top_k=request.top_k,
        )

        # 4. Assembly & Token Budgeting
        assembled_context, citations, total_tokens = self.assembler.assemble(
            query=request.query,
            analysis=analysis,
            items=ranked_items,
            max_context_tokens=request.max_context_tokens,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        stats = RetrievalStats(
            mode=mode.value,
            nodes_retrieved=nodes_count,
            edges_retrieved=edges_count,
            chunks_retrieved=chunks_count,
            total_candidates=len(candidates),
            final_items_count=len(ranked_items),
            total_tokens_estimated=total_tokens,
            retrieval_time_ms=elapsed_ms,
        )

        return ContextQueryResponse(
            query=request.query,
            query_analysis=analysis,
            items=ranked_items,
            assembled_context=assembled_context,
            citations=citations,
            stats=stats,
        )
