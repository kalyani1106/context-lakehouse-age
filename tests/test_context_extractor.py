import unittest
from backend.context.schemas import Entity, Relationship, Provenance, DocumentContext
from backend.context.normalizer import EntityNormalizer
from backend.context.extractor import ContextExtractor

class TestContextExtractor(unittest.TestCase):
    def setUp(self):
        self.normalizer = EntityNormalizer()
        self.extractor = ContextExtractor()

    def test_entity_deduplication_and_canonicalization(self):
        prov = Provenance(document_id="doc_1", document_name="doc.pdf", page_number=1, source_text="Apache AGE extends Postgres")
        
        raw_entities = [
            Entity(name="Apache AGE", canonical_name="Apache AGE", type="Technology", aliases=["AGE"], source=prov),
            Entity(name="apache age", canonical_name="apache age", type="Technology", aliases=[], source=prov),
            Entity(name="Postgres", canonical_name="Postgres", type="Technology", aliases=[], source=prov),
            Entity(name="PostgreSQL", canonical_name="PostgreSQL", type="Technology", aliases=["PG"], source=prov)
        ]

        raw_relationships = [
            Relationship(source_entity="Apache AGE", target_entity="Postgres", relationship_type="EXTENDS", source=prov),
            Relationship(source_entity="apache age", target_entity="PostgreSQL", relationship_type="EXTENDS", source=prov),
        ]

        merged_ents, merged_rels = self.normalizer.deduplicate_and_normalize(raw_entities, raw_relationships)
        
        # Verify merged entities count
        cnames = {e.canonical_name for e in merged_ents}
        self.assertIn("Apache AGE", cnames)
        self.assertIn("PostgreSQL", cnames)
        self.assertEqual(len(merged_ents), 2)

        # Verify merged relationships
        self.assertEqual(len(merged_rels), 1)
        rel = merged_rels[0]
        self.assertEqual(rel.source_entity, "Apache AGE")
        self.assertEqual(rel.target_entity, "PostgreSQL")
        self.assertEqual(rel.relationship_type, "EXTENDS")

if __name__ == "__main__":
    unittest.main()
