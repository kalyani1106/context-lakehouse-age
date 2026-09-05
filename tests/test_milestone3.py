import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.extraction.pdf_extractor import PDFExtractor
from backend.extraction.chunker import DocumentChunker
from backend.context.extractor import ContextExtractor
from backend.graph.age_client import AGEClient
from backend.graph.graph_service import GraphService

class TestMilestone3(unittest.TestCase):
    def setUp(self):
        self.age_client = AGEClient()
        self.test_graph_name = "test_e2e_kg"
        self.age_client.ensure_graph_exists(self.test_graph_name)
        self.graph_service = GraphService(age_client=self.age_client, graph_name=self.test_graph_name)
        self.extractor = PDFExtractor()
        self.chunker = DocumentChunker(chunk_size=800, chunk_overlap=150)
        self.context_extractor = ContextExtractor()

    def tearDown(self):
        # Drop test graph after testing
        conn = self.age_client.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT drop_graph('{self.test_graph_name}', true);")
            conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            conn.close()

    def test_01_ingest_and_query_real_pdf(self):
        real_pdf_path = Path(r"c:\Users\varshini\OneDrive\文件\Segemento Internship\A Report on Context Lakehouse.pdf")
        if not real_pdf_path.exists():
            self.skipTest(f"PDF not found at {real_pdf_path}")

        # 1. Extract PDF
        doc_id = "doc_test_context_lakehouse"
        doc_name = "A Report on Context Lakehouse.pdf"
        extracted_doc = self.extractor.extract_from_path(real_pdf_path, doc_id, doc_name)
        
        # 2. Chunk
        chunks = self.chunker.chunk_document(extracted_doc)
        
        # 3. Context Generation
        context = self.context_extractor.extract_context(extracted_doc, chunks, force_provider="heuristic")
        self.assertGreater(len(context.entities), 0)
        
        # 4. Ingest into Apache AGE
        ingest_res = self.graph_service.ingest_context(context)
        print(f"\n[Test Graph Ingestion] Summary: {ingest_res}")
        self.assertGreater(ingest_res["nodes_created"], 0)

        # 5. Verify Cypher queries
        # Find all nodes
        nodes = self.graph_service.get_all_entities(limit=20)
        self.assertGreater(len(nodes), 0)
        print(f"[Test AGE Cypher] Queried {len(nodes)} sample nodes from AGE.")

        # Find relationships
        edges = self.graph_service.get_all_relationships(limit=20)
        print(f"[Test AGE Cypher] Queried {len(edges)} sample edges from AGE.")
        if edges:
            first_edge = edges[0]
            print(f"Sample Edge: {first_edge['source_name']} -[:{first_edge['relationship_type']}]-> {first_edge['target_name']}")
            print(f"Edge Provenance: Doc '{first_edge['document_name']}', Page {first_edge['page_number']}")

        # Provenance check
        prov = self.graph_service.get_entity_provenance("Context Lakehouse")
        self.assertNotIn("error", prov)
        self.assertEqual(prov["document_id"], doc_id)
        print(f"[Test Provenance Traceback] Entity 'Context Lakehouse' traceable to: {prov['document_name']}, page {prov['page_number']}")
        print(f"Source snippet: {prov['source_text'][:120]}...")

        # Document Subgraph
        subgraph = self.graph_service.get_document_subgraph(doc_id)
        self.assertEqual(subgraph["document_id"], doc_id)
        self.assertGreater(len(subgraph["nodes"]), 0)
        print(f"[Test Subgraph] Subgraph for {doc_id} contains {len(subgraph['nodes'])} nodes and {len(subgraph['edges'])} edges.")

if __name__ == "__main__":
    unittest.main()
