"""
Context Assembler for Context Engine
====================================
Deduplicates, token-budgets, and formats retrieved knowledge graph and document
excerpts into structured markdown context with full citation traceability.
"""

from typing import List, Tuple, Dict, Set
from .models import ContextItem, ContextType, ProvenanceCitation, QueryAnalysisResult


class ContextAssembler:
    """
    Assembles prioritized context items into structured, token-budgeted markdown context.
    """

    CHARS_PER_TOKEN: float = 4.0

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count based on standard character heuristics."""
        if not text:
            return 0
        return max(1, int(len(text) / self.CHARS_PER_TOKEN))

    def assemble(
        self,
        query: str,
        analysis: QueryAnalysisResult,
        items: List[ContextItem],
        max_context_tokens: int = 4000,
    ) -> Tuple[str, List[ProvenanceCitation], int]:
        """
        Assemble items into structured markdown, respecting max_context_tokens.
        Returns: (assembled_markdown_text, citations_list, total_tokens_estimated)
        """
        if not items:
            empty_msg = f"# Context Retrieval: {query}\n\n*No relevant context items found in Knowledge Graph or Lakehouse for this query.*"
            return empty_msg, [], self.estimate_tokens(empty_msg)

        # 1. Deduplicate items by ID and title
        unique_items: List[ContextItem] = []
        seen_ids: Set[str] = set()
        seen_contents: Set[str] = set()

        for it in items:
            content_key = it.content.strip().lower()
            if it.id not in seen_ids and content_key not in seen_contents:
                seen_ids.add(it.id)
                seen_contents.add(content_key)
                unique_items.append(it)

        # 2. Categorize items into sections
        graph_entities: List[ContextItem] = []
        graph_relationships: List[ContextItem] = []
        document_chunks: List[ContextItem] = []
        code_files: List[ContextItem] = []

        for it in unique_items:
            if it.type == ContextType.ENTITY:
                graph_entities.append(it)
            elif it.type == ContextType.RELATIONSHIP:
                graph_relationships.append(it)
            elif it.type == ContextType.CHUNK:
                document_chunks.append(it)
            elif it.type == ContextType.FILE:
                code_files.append(it)
            else:
                graph_entities.append(it)

        # 3. Build Markdown Sections incrementally within token budget
        sections: List[str] = []
        citations: List[ProvenanceCitation] = []
        seen_citation_keys: Set[str] = set()

        # Header & Query Analysis
        header_lines = [
            f"# Context Retrieval: {query}",
            "",
            "## 🎯 Query Analysis",
            f"- **Intent**: `{analysis.intent.value}`",
        ]
        if analysis.extracted_entities:
            header_lines.append(f"- **Extracted Entities**: {', '.join([f'`{e}`' for e in analysis.extracted_entities])}")
        if analysis.detected_targets:
            header_lines.append(f"- **Target Symbols/Files**: {', '.join([f'`{t}`' for t in analysis.detected_targets])}")
        if analysis.keywords:
            header_lines.append(f"- **Keywords**: {', '.join(analysis.keywords[:8])}")
        header_lines.append("")
        
        current_text = "\n".join(header_lines)
        current_tokens = self.estimate_tokens(current_text)

        # Helper to safely add citation
        def add_citation(item: ContextItem):
            if item.provenance:
                prov = item.provenance
                key = f"{prov.source_type}:{prov.document_id or prov.repo_name}:{prov.file_path or prov.page_number}:{prov.start_line or prov.chunk_id}"
                if key not in seen_citation_keys:
                    seen_citation_keys.add(key)
                    citations.append(prov)

        # Section 1: Knowledge Graph Entities
        if graph_entities:
            sec_lines = ["## 🕸️ Knowledge Graph Entities & Nodes", ""]
            for ent in graph_entities:
                sec_lines.append(f"### {ent.title}")
                sec_lines.append(ent.content)
                sec_lines.append(f"*Relevance Score: {ent.score:.2f}*")
                sec_lines.append("")
                add_citation(ent)
            sec_text = "\n".join(sec_lines)
            sec_tokens = self.estimate_tokens(sec_text)
            if current_tokens + sec_tokens <= max_context_tokens:
                sections.append(sec_text)
                current_tokens += sec_tokens

        # Section 2: Knowledge Graph Relationships
        if graph_relationships:
            sec_lines = ["## 🔗 Graph Relationships & Linkages", ""]
            for rel in graph_relationships:
                sec_lines.append(f"- {rel.content} *(Score: {rel.score:.2f})*")
                add_citation(rel)
            sec_lines.append("")
            sec_text = "\n".join(sec_lines)
            sec_tokens = self.estimate_tokens(sec_text)
            if current_tokens + sec_tokens <= max_context_tokens:
                sections.append(sec_text)
                current_tokens += sec_tokens

        # Section 3: Document & Code Chunks
        all_chunks = document_chunks + code_files
        if all_chunks:
            sec_lines = ["## 📄 Lakehouse Document & Code Chunks", ""]
            for ch in all_chunks:
                chunk_block = f"### {ch.title}\n{ch.content}\n*Relevance Score: {ch.score:.2f}*\n\n"
                chunk_tokens = self.estimate_tokens(chunk_block)
                if current_tokens + chunk_tokens <= max_context_tokens:
                    sec_lines.append(chunk_block)
                    current_tokens += chunk_tokens
                    add_citation(ch)
                else:
                    # If budget almost full, attempt truncated block if budget allows
                    remaining_budget = max_context_tokens - current_tokens
                    if remaining_budget > 80:
                        max_chars = int(remaining_budget * self.CHARS_PER_TOKEN) - 100
                        truncated_content = ch.content[:max_chars] + "\n\n*[... truncated to fit token budget ...]*"
                        truncated_block = f"### {ch.title}\n{truncated_content}\n\n"
                        sec_lines.append(truncated_block)
                        current_tokens += self.estimate_tokens(truncated_block)
                        add_citation(ch)
                    break
            sec_text = "\n".join(sec_lines)
            sections.append(sec_text)

        # Section 4: Citations & Provenance Ledger
        if citations:
            cit_lines = ["## 🏷️ Provenance & Citation Ledger", ""]
            for idx, cit in enumerate(citations, 1):
                if cit.source_type == "git":
                    loc = f"`{cit.file_path}`"
                    if cit.start_line:
                        loc += f" (Lines {cit.start_line}-{cit.end_line or cit.start_line})"
                    commit = f" `[{cit.commit_hash[:7]}]`" if cit.commit_hash else ""
                    cit_lines.append(f"{idx}. **Git Repository**: `{cit.repo_name or 'repo'}` | {loc}{commit}")
                else:
                    page_str = f"Page {cit.page_number}" if cit.page_number else "Document Level"
                    chunk_str = f", Chunk: `{cit.chunk_id}`" if cit.chunk_id else ""
                    cit_lines.append(f"{idx}. **Document**: `{cit.document_name or cit.document_id}` | {page_str}{chunk_str}")
            cit_lines.append("")
            cit_text = "\n".join(cit_lines)
            sections.append(cit_text)

        assembled_full = current_text + "\n\n" + "\n\n".join(sections)
        total_tokens = self.estimate_tokens(assembled_full)
        return assembled_full, citations, total_tokens
