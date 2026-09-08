"""
Context Engine Unit & Integration Tests
=======================================
Comprehensive test suite validating QueryAnalyzer, VectorRetriever, GraphRetriever,
ContextRanker, ContextAssembler, ContextEngine facade, and FastAPI /context/query routes.
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.context_engine.models import (
    QueryIntent,
    RetrievalMode,
    ContextType,
    ProvenanceCitation,
    ContextItem,
    ContextQueryRequest,
    ContextQueryResponse,
    QueryAnalysisResult,
)
from backend.context_engine.query_analyzer import QueryAnalyzer
from backend.context_engine.vector_retriever import VectorRetriever
from backend.context_engine.graph_retriever import GraphRetriever
from backend.context_engine.ranker import ContextRanker
from backend.context_engine.assembler import ContextAssembler
from backend.context_engine.context_engine import ContextEngine
from backend.storage.models import DocumentMetadata, ProcessingStatus


class TestQueryAnalyzer(unittest.TestCase):
    """Test deterministic NLP and intent parsing rules."""

    def setUp(self):
        self.analyzer = QueryAnalyzer()

    def test_intent_classification(self):
        test_cases = [
            ("How does user authentication, JWT tokens, and login verification work?", QueryIntent.AUTHENTICATION),
            ("What are the available FastAPI REST routes and API endpoints?", QueryIntent.API_ROUTES),
            ("Which modules import age_client and what classes inherit from BaseStorage?", QueryIntent.DEPENDENCY),
            ("Explain the data flow and ETL pipeline from raw PDF to Apache AGE", QueryIntent.DATA_FLOW),
            ("Show me the Excel sheet schema, columns, and table structure", QueryIntent.SCHEMA),
            ("Give me an architectural overview of the lakehouse layers and components", QueryIntent.ARCHITECTURE),
            ("What is this project about?", QueryIntent.GENERAL),
        ]

        for query, expected_intent in test_cases:
            result = self.analyzer.analyze(query)
            self.assertEqual(result.intent, expected_intent, f"Failed on query: {query}")

    def test_entity_and_symbol_extraction(self):
        query = 'Explain how "Apache AGE" and `AgeClient` interact with backend/pipeline.py and get_chunks()'
        result = self.analyzer.analyze(query)

        self.assertIn("Apache AGE", result.extracted_entities)
        self.assertIn("AgeClient", result.extracted_entities)
        self.assertIn("backend/pipeline.py", result.detected_targets)
        self.assertIn("get_chunks", result.detected_targets)

    def test_empty_query(self):
        result = self.analyzer.analyze("")
        self.assertEqual(result.intent, QueryIntent.GENERAL)
        self.assertEqual(len(result.keywords), 0)


class TestVectorRetriever(unittest.TestCase):
    """Test BM25 lexical search and chunk retrieval."""

    def setUp(self):
        self.mock_storage = MagicMock()
        self.retriever = VectorRetriever(storage_service=self.mock_storage)

    def test_bm25_retrieval(self):
        # Mock document metadata
        doc = DocumentMetadata(
            document_id="doc_123",
            document_name="architecture_report.pdf",
            file_type="application/pdf",
            file_size_bytes=1024,
            sha256="abc123hash",
            status=ProcessingStatus.COMPLETED
        )
        self.mock_storage.list_documents.return_value = [doc]

        # Mock passage chunks
        chunks = [
            {
                "chunk_id": "c1",
                "page_number": 1,
                "chunk_text": "The Apache AGE knowledge graph stores semantic relationships and vertex nodes."
            },
            {
                "chunk_id": "c2",
                "page_number": 2,
                "chunk_text": "FastAPI provides REST API endpoints for querying data."
            },
            {
                "chunk_id": "c3",
                "page_number": 3,
                "chunk_text": "PostgreSQL database configuration and storage settings."
            }
        ]
        self.mock_storage.get_chunks.return_value = chunks

        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze("Apache AGE knowledge graph relationships")

        items = self.retriever.retrieve(analysis, limit=5)
        self.assertGreater(len(items), 0)
        # First item should be chunk 1 with highest score
        self.assertEqual(items[0].metadata["chunk_id"], "c1")
        self.assertIn("Apache AGE", items[0].content)
        self.assertIsNotNone(items[0].provenance)
        self.assertEqual(items[0].provenance.document_name, "architecture_report.pdf")

    def test_scoping_by_document(self):
        doc1 = DocumentMetadata(document_id="doc_1", document_name="doc1.pdf", file_type="pdf", file_size_bytes=100, sha256="h1")
        doc2 = DocumentMetadata(document_id="doc_2", document_name="doc2.pdf", file_type="pdf", file_size_bytes=100, sha256="h2")
        self.mock_storage.list_documents.return_value = [doc1, doc2]

        self.mock_storage.get_chunks.side_effect = lambda doc_id: [
            {"chunk_id": f"{doc_id}_c1", "page_number": 1, "chunk_text": f"Content for {doc_id} with keywords"}
        ]

        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze("keywords")

        # Scope to doc_2
        items = self.retriever.retrieve(analysis, document_id="doc_2")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].metadata["document_id"], "doc_2")


class TestGraphRetriever(unittest.TestCase):
    """Test Apache AGE graph retrieval formatting and bounds."""

    def setUp(self):
        self.mock_age = MagicMock()
        self.retriever = GraphRetriever(age_client=self.mock_age)

    def test_git_node_conversion(self):
        node = {
            "id": 101,
            "label": "Class",
            "properties": {
                "name": "ContextEngine",
                "canonical_id": "repo:context-lakehouse:backend/context_engine.py:ContextEngine",
                "file_path": "backend/context_engine.py",
                "start_line": 25,
                "end_line": 150,
                "source_snippet": "class ContextEngine:\n    pass",
                "repository_name": "context-lakehouse",
                "commit_sha": "a1b2c3d4",
            }
        }
        item = self.retriever._git_node_to_context_item(node, seed_score=1.0)
        self.assertEqual(item.type, ContextType.ENTITY)
        self.assertIn("ContextEngine", item.title)
        self.assertEqual(item.provenance.file_path, "backend/context_engine.py")
        self.assertEqual(item.provenance.start_line, 25)

    def test_git_edge_conversion(self):
        src = {"id": 1, "label": "Module", "properties": {"name": "app.py", "file_path": "app.py"}}
        rel = {"id": 10, "label": "IMPORTS", "properties": {"file_path": "app.py", "start_line": 5}}
        tgt = {"id": 2, "label": "Class", "properties": {"name": "ContextEngine", "file_path": "engine.py"}}

        edge_item = self.retriever._git_edge_to_context_item(src, rel, tgt, depth_score=0.85)
        self.assertEqual(edge_item.type, ContextType.RELATIONSHIP)
        self.assertIn("--[:IMPORTS]-->", edge_item.content)
        self.assertEqual(edge_item.provenance.start_line, 5)


class TestContextRanker(unittest.TestCase):
    """Test composite multi-factor ranking."""

    def setUp(self):
        self.ranker = ContextRanker()

    def test_ranking_weights_and_boosts(self):
        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze("How does authentication and token checking work?")

        item_auth = ContextItem(
            id="item_auth",
            type=ContextType.CHUNK,
            title="Auth Module",
            content="Handles JWT auth and bearer tokens securely.",
            graph_score=0.0,
            semantic_score=0.8,
            provenance_score=1.0,
            provenance=ProvenanceCitation(source_type="git", file_path="auth.py", start_line=10)
        )

        item_unrelated = ContextItem(
            id="item_unrelated",
            type=ContextType.CHUNK,
            title="Unrelated Logging",
            content="Logs system heartbeat periodically.",
            graph_score=0.0,
            semantic_score=0.3,
            provenance_score=0.5,
            provenance=ProvenanceCitation(source_type="git", file_path="logger.py", start_line=1)
        )

        ranked = self.ranker.rank([item_unrelated, item_auth], analysis, top_k=2)
        self.assertEqual(ranked[0].id, "item_auth")
        self.assertGreater(ranked[0].score, ranked[1].score)


class TestContextAssembler(unittest.TestCase):
    """Test token budgeting, deduplication, and markdown assembly."""

    def setUp(self):
        self.assembler = ContextAssembler()

    def test_token_budget_enforcement(self):
        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze("Architecture of Context Lakehouse")

        items = [
            ContextItem(
                id=f"item_{i}",
                type=ContextType.CHUNK,
                title=f"Chunk {i}",
                content=f"Long detailed content paragraph about layer {i} " * 50,
                score=1.0 - (i * 0.1),
                graph_score=0.5,
                semantic_score=0.8,
                provenance_score=1.0,
                provenance=ProvenanceCitation(source_type="document", document_name="doc.pdf", page_number=i)
            )
            for i in range(10)
        ]

        # Assemble with strict token budget (e.g. 500 tokens)
        assembled, citations, token_count = self.assembler.assemble(
            query="Architecture of Context Lakehouse",
            analysis=analysis,
            items=items,
            max_context_tokens=500
        )

        self.assertLessEqual(token_count, 650)
        self.assertIn("# Context Retrieval:", assembled)
        self.assertIn("## 🎯 Query Analysis", assembled)
        self.assertGreater(len(citations), 0)

    def test_deduplication(self):
        analyzer = QueryAnalyzer()
        analysis = analyzer.analyze("Query")

        item1 = ContextItem(id="item_1", type=ContextType.ENTITY, title="Node A", content="Identical text", score=0.9)
        item2 = ContextItem(id="item_1", type=ContextType.ENTITY, title="Node A", content="Identical text", score=0.9)

        assembled, citations, _ = self.assembler.assemble("Query", analysis, [item1, item2])
        self.assertEqual(assembled.count("### Node A"), 1)


class TestContextEngineFacade(unittest.TestCase):
    """Test end-to-end ContextEngine execution."""

    def test_hybrid_pipeline(self):
        engine = ContextEngine()
        req = ContextQueryRequest(
            query="How does authentication and token verification work in FastAPI routes?",
            mode=RetrievalMode.HYBRID,
            top_k=5,
            max_context_tokens=2000,
        )

        resp = engine.query_context(req)
        self.assertIsInstance(resp, ContextQueryResponse)
        self.assertEqual(resp.query_analysis.intent, QueryIntent.AUTHENTICATION)
        self.assertIsNotNone(resp.assembled_context)
        self.assertIsNotNone(resp.stats)
        self.assertGreaterEqual(resp.stats.retrieval_time_ms, 0.0)

    def test_regex_builder_and_word_boundaries(self):
        retriever = GraphRetriever()
        # Word boundary for standard word
        reg_word = retriever._build_cypher_regex("space")
        self.assertEqual(reg_word, "(?i).*\\\\yspace\\\\y.*")
        
        # Safe punctuation for filename with dots
        reg_file = retriever._build_cypher_regex("age_client.py")
        self.assertEqual(reg_file, "(?i).*age_client.py.*")

    def test_search_token_morphological_expansion(self):
        retriever = GraphRetriever()
        analyzer = QueryAnalyzer()
        
        # Test plural and verb suffix expansion
        analysis = analyzer.analyze("How are tokens verified and dependencies checked?")
        tokens = retriever._expand_search_tokens(analysis)
        self.assertIn("token", tokens)
        self.assertIn("verify", tokens)
        self.assertIn("dependency", tokens)

    def test_out_of_domain_unrelated_query_clean_zero(self):
        engine = ContextEngine()
        req = ContextQueryRequest(
            query="Quantum teleportation in outer space astrophysics",
            mode=RetrievalMode.HYBRID,
            top_k=5,
        )
        resp = engine.query_context(req)
        self.assertEqual(len(resp.items), 0)
        self.assertEqual(resp.stats.nodes_retrieved, 0)
        self.assertEqual(resp.stats.edges_retrieved, 0)
        self.assertEqual(resp.stats.chunks_retrieved, 0)
        self.assertIn("No relevant context items found", resp.assembled_context)


class TestContextAPI(unittest.TestCase):
    """Test FastAPI /context endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_context_status_endpoint(self):
        response = self.client.get("/context/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["context_engine_ready"])

    def test_context_query_endpoint(self):
        payload = {
            "query": "What are the REST API endpoints in FastAPI?",
            "mode": "hybrid",
            "top_k": 5,
            "max_context_tokens": 2500
        }
        response = self.client.post("/context/query", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("query_analysis", data)
        self.assertEqual(data["query_analysis"]["intent"], "API_ROUTES")
        self.assertIn("assembled_context", data)
        self.assertIn("stats", data)

    def test_context_query_empty_error(self):
        payload = {"query": "   "}
        response = self.client.post("/context/query", json=payload)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

