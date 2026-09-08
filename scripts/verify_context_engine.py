"""
Live Verification Script for Context Engine
===========================================
Executes real hybrid, graph, and semantic queries across Apache AGE
and Context Lakehouse storage.
"""

import sys
from pathlib import Path

# Set utf-8 encoding for Windows terminal
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.context_engine import (
    ContextEngine,
    ContextQueryRequest,
    RetrievalMode,
    QueryIntent,
)

def test_live_context_engine():
    print("==================================================================")
    print("   CONTEXT ENGINE LIVE VERIFICATION")
    print("==================================================================")

    engine = ContextEngine()

    test_queries = [
        ("Architecture & Components", "What is the high-level architecture, main components, and layer design?", RetrievalMode.HYBRID),
        ("Authentication Flow", "How does authentication, login, JWT tokens, and user verification work?", RetrievalMode.HYBRID),
        ("REST API Routes", "What are the REST API endpoints and routes in FastAPI?", RetrievalMode.GRAPH),
        ("Lakehouse Storage & Chunks", "Explain how passage chunking and Lakehouse tiers store documents.", RetrievalMode.SEMANTIC),
    ]

    for title, query, mode in test_queries:
        print(f"\n--- Testing Query: {title} [{mode.value.upper()}] ---")
        print(f"Query: \"{query}\"")
        req = ContextQueryRequest(
            query=query,
            mode=mode,
            top_k=8,
            max_context_tokens=3000,
        )
        resp = engine.query_context(req)

        print(f"Intent Classified: {resp.query_analysis.intent.value}")
        print(f"Extracted Entities: {resp.query_analysis.extracted_entities}")
        print(f"Target Keywords: {resp.query_analysis.keywords[:6]}")
        print(f"Stats: Latency={resp.stats.retrieval_time_ms:.1f}ms | Nodes={resp.stats.nodes_retrieved} | Edges={resp.stats.edges_retrieved} | Chunks={resp.stats.chunks_retrieved} | Tokens={resp.stats.total_tokens_estimated}")
        print(f"Top Ranked Context Items: {len(resp.items)}")
        for idx, item in enumerate(resp.items[:3], 1):
            print(f"  {idx}. [{item.type.value}] {item.title} (Score: {item.score:.3f})")
        print(f"Citations Extracted: {len(resp.citations)}")
        for c in resp.citations[:2]:
            print(f"  - Citation: {c.source_type.upper()} | {c.file_path or c.document_name} | {c.start_line or c.page_number}")

        assert resp.stats.retrieval_time_ms >= 0
        assert len(resp.assembled_context) > 50

    print("\n>>> ALL CONTEXT ENGINE LIVE VERIFICATION CHECKS PASSED 100%!")

if __name__ == "__main__":
    test_live_context_engine()
