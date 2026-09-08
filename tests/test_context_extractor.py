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

    def test_excel_structural_entity_deduplication_and_no_orphan_concepts(self):
        """Verify Book1.xlsx produces connected structural graph and NO orphan Concept nodes."""
        import io
        import pandas as pd
        from backend.extraction.document_extractor import DocumentExtractor
        from backend.extraction.chunker import DocumentChunker

        df = pd.DataFrame({
            "ID": [101, 102],
            "Name": ["Ravi", "Anu"],
            "Department": ["Engineering", "HR"]
        })
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Sheet1")
        excel_bytes = buf.getvalue()

        extractor = DocumentExtractor()
        chunker = DocumentChunker()
        doc = extractor.extract_from_bytes(excel_bytes, "doc_book1", "Book1.xlsx")
        chunks = chunker.chunk_document(doc)
        context = self.extractor.extract_context(doc, chunks)

        # 1. Verify entity count and types
        self.assertEqual(len(context.entities), 5)
        entity_types = {e.canonical_name: e.type for e in context.entities}
        self.assertEqual(entity_types.get("Book1.xlsx"), "Workbook")
        self.assertEqual(entity_types.get("Book1.xlsx::Sheet1"), "Sheet")
        self.assertEqual(entity_types.get("Book1.xlsx::Sheet1.ID"), "Column")
        self.assertEqual(entity_types.get("Book1.xlsx::Sheet1.Name"), "Column")
        self.assertEqual(entity_types.get("Book1.xlsx::Sheet1.Department"), "Column")

        # 2. Verify display names
        display_names = {e.canonical_name: e.name for e in context.entities}
        self.assertEqual(display_names.get("Book1.xlsx::Sheet1.ID"), "Sheet1.ID")
        self.assertEqual(display_names.get("Book1.xlsx::Sheet1.Name"), "Sheet1.Name")
        self.assertEqual(display_names.get("Book1.xlsx::Sheet1.Department"), "Sheet1.Department")

        # 3. Verify NO orphan generic Concept nodes
        concept_names = [e.canonical_name for e in context.entities if e.type == "Concept"]
        self.assertEqual(concept_names, [], "Orphan Concept nodes detected for column headers!")

        # 4. Verify relationships
        self.assertEqual(len(context.relationships), 4)
        rel_pairs = {(r.source_entity, r.relationship_type, r.target_entity) for r in context.relationships}
        self.assertIn(("Book1.xlsx", "CONTAINS_SHEET", "Book1.xlsx::Sheet1"), rel_pairs)
        self.assertIn(("Book1.xlsx::Sheet1", "CONTAINS_COLUMN", "Book1.xlsx::Sheet1.ID"), rel_pairs)
        self.assertIn(("Book1.xlsx::Sheet1", "CONTAINS_COLUMN", "Book1.xlsx::Sheet1.Name"), rel_pairs)
        self.assertIn(("Book1.xlsx::Sheet1", "CONTAINS_COLUMN", "Book1.xlsx::Sheet1.Department"), rel_pairs)

    def test_multi_sheet_excel_scoped_column_entities(self):
        """Verify two sheets in the same workbook with identical column names do not collide."""
        import io
        import pandas as pd
        from backend.extraction.document_extractor import DocumentExtractor
        from backend.extraction.chunker import DocumentChunker

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]}).to_excel(writer, index=False, sheet_name="Sheet1")
            pd.DataFrame({"ID": [10, 20], "Name": ["X", "Y"], "Score": [99, 88]}).to_excel(writer, index=False, sheet_name="Sheet2")
        excel_bytes = buf.getvalue()

        extractor = DocumentExtractor()
        chunker = DocumentChunker()
        doc = extractor.extract_from_bytes(excel_bytes, "doc_multi_sheet", "MultiSheet.xlsx")
        chunks = chunker.chunk_document(doc)
        context = self.extractor.extract_context(doc, chunks)

        # 1 Workbook + 2 Sheets + 2 cols in Sheet1 + 3 cols in Sheet2 = 8 entities
        self.assertEqual(len(context.entities), 8)
        cnames = {e.canonical_name for e in context.entities}
        self.assertIn("MultiSheet.xlsx", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet1", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet2", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet1.ID", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet1.Name", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet2.ID", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet2.Name", cnames)
        self.assertIn("MultiSheet.xlsx::Sheet2.Score", cnames)

        # Verify distinct relationships per sheet
        rel_pairs = {(r.source_entity, r.relationship_type, r.target_entity) for r in context.relationships}
        self.assertIn(("MultiSheet.xlsx::Sheet1", "CONTAINS_COLUMN", "MultiSheet.xlsx::Sheet1.ID"), rel_pairs)
        self.assertIn(("MultiSheet.xlsx::Sheet2", "CONTAINS_COLUMN", "MultiSheet.xlsx::Sheet2.ID"), rel_pairs)

    def test_multi_workbook_excel_scoped_column_entities(self):
        """Verify two different Excel workbooks with the same column names do not collide."""
        import io
        import pandas as pd
        from backend.extraction.document_extractor import DocumentExtractor
        from backend.extraction.chunker import DocumentChunker

        df = pd.DataFrame({"ID": [1, 2], "Name": ["Alpha", "Beta"]})
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Sheet1")
        excel_bytes = buf.getvalue()

        extractor = DocumentExtractor()
        chunker = DocumentChunker()

        doc1 = extractor.extract_from_bytes(excel_bytes, "doc_wb1", "BookA.xlsx")
        context1 = self.extractor.extract_context(doc1, chunker.chunk_document(doc1))

        doc2 = extractor.extract_from_bytes(excel_bytes, "doc_wb2", "BookB.xlsx")
        context2 = self.extractor.extract_context(doc2, chunker.chunk_document(doc2))

        cnames1 = {e.canonical_name for e in context1.entities}
        cnames2 = {e.canonical_name for e in context2.entities}

        self.assertIn("BookA.xlsx::Sheet1.ID", cnames1)
        self.assertIn("BookB.xlsx::Sheet1.ID", cnames2)
        # Column identities must be distinct across workbooks
        self.assertTrue(cnames1.isdisjoint(cnames2))

    def test_excel_domain_concepts_in_cell_data_preserved(self):
        """Verify meaningful domain entities in cell content (e.g. Apache AGE, PostgreSQL) are still extracted."""
        import io
        import pandas as pd
        from backend.extraction.document_extractor import DocumentExtractor
        from backend.extraction.chunker import DocumentChunker

        df = pd.DataFrame({
            "ID": [101, 102],
            "Technology": ["Apache AGE", "PostgreSQL"],
            "Category": ["Graph Database", "Relational Database"]
        })
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Sheet1")
        excel_bytes = buf.getvalue()

        extractor = DocumentExtractor()
        chunker = DocumentChunker()
        doc = extractor.extract_from_bytes(excel_bytes, "doc_tech", "TechStack.xlsx")
        chunks = chunker.chunk_document(doc)
        context = self.extractor.extract_context(doc, chunks)

        cnames = {e.canonical_name for e in context.entities}
        # Structural columns are extracted
        self.assertIn("TechStack.xlsx::Sheet1.Technology", cnames)
        self.assertIn("TechStack.xlsx::Sheet1.Category", cnames)

        # Domain entities inside cells are ALSO extracted
        self.assertIn("Apache AGE", cnames)
        self.assertIn("PostgreSQL", cnames)
        self.assertIn("Graph Database", cnames)
        self.assertIn("Relational Database", cnames)

    def test_excel_version_update_column_stability(self):
        """Verify modifying row data preserves identical structural column identities."""
        import io
        import pandas as pd
        from backend.extraction.document_extractor import DocumentExtractor
        from backend.extraction.chunker import DocumentChunker

        # Version 1
        df_v1 = pd.DataFrame({
            "ID": [101, 102],
            "Name": ["Ravi", "Anu"],
            "Department": ["Engineering", "HR"]
        })
        buf_v1 = io.BytesIO()
        df_v1.to_excel(buf_v1, index=False, sheet_name="Sheet1")
        bytes_v1 = buf_v1.getvalue()

        # Version 2 (Data modified and row added)
        df_v2 = pd.DataFrame({
            "ID": [101, 102, 103],
            "Name": ["Ravi", "Anu", "Priya"],
            "Department": ["Data Engineering", "HR", "Marketing"]
        })
        buf_v2 = io.BytesIO()
        df_v2.to_excel(buf_v2, index=False, sheet_name="Sheet1")
        bytes_v2 = buf_v2.getvalue()

        extractor = DocumentExtractor()
        chunker = DocumentChunker()

        doc_v1 = extractor.extract_from_bytes(bytes_v1, "doc_v1", "Book1.xlsx")
        context_v1 = self.extractor.extract_context(doc_v1, chunker.chunk_document(doc_v1))

        doc_v2 = extractor.extract_from_bytes(bytes_v2, "doc_v2", "Book1.xlsx")
        context_v2 = self.extractor.extract_context(doc_v2, chunker.chunk_document(doc_v2))

        cols_v1 = {e.canonical_name for e in context_v1.entities if e.type == "Column"}
        cols_v2 = {e.canonical_name for e in context_v2.entities if e.type == "Column"}

        self.assertEqual(cols_v1, cols_v2, "Column identities changed between versions!")
        self.assertEqual(cols_v1, {"Book1.xlsx::Sheet1.ID", "Book1.xlsx::Sheet1.Name", "Book1.xlsx::Sheet1.Department"})

if __name__ == "__main__":
    unittest.main()
