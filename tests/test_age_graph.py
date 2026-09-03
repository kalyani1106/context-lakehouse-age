import unittest
from graph.age_client import AGEClient
from graph.graph_service import GraphService
from graph.agtype_parser import parse_agtype
from context.schemas import DocumentContext, Entity, Relationship, Provenance

class TestAGEGraph(unittest.TestCase):
    def setUp(self):
        self.client = AGEClient()
        self.graph_name = "test_unit_age_graph"
        self.client.ensure_graph_exists(self.graph_name)
        self.service = GraphService(age_client=self.client, graph_name=self.graph_name)

    def tearDown(self):
        conn = self.client.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT drop_graph('{self.graph_name}', true);")
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    def test_agtype_parser(self):
        raw_vertex = '{"id": 123, "label": "Technology", "properties": {"name": "AGE"}}::vertex'
        parsed = parse_agtype(raw_vertex)
        self.assertEqual(parsed["id"], 123)
        self.assertEqual(parsed["label"], "Technology")
        self.assertEqual(parsed["properties"]["name"], "AGE")

    def test_graph_ingestion_and_queries(self):
        prov = Provenance(document_id="doc_unit", document_name="doc.pdf", page_number=2, source_text="Apache AGE extends PostgreSQL")
        context = DocumentContext(
            document_id="doc_unit",
            document_name="doc.pdf",
            extraction_method="UNIT_TEST",
            summary="Test graph context",
            entities=[
                Entity(name="Apache AGE", canonical_name="Apache AGE", type="Technology", source=prov),
                Entity(name="PostgreSQL", canonical_name="PostgreSQL", type="Technology", source=prov)
            ],
            relationships=[
                Relationship(source_entity="Apache AGE", target_entity="PostgreSQL", relationship_type="EXTENDS", source=prov)
            ]
        )

        res = self.service.ingest_context(context)
        self.assertEqual(res["nodes_created"], 2)
        self.assertEqual(res["edges_created"], 1)

        # Query all
        nodes = self.service.get_all_entities()
        self.assertEqual(len(nodes), 2)

        edges = self.service.get_all_relationships()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["relationship_type"], "EXTENDS")

if __name__ == "__main__":
    unittest.main()
