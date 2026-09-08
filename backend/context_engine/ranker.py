"""
Context Ranker for Context Engine
=================================
Deterministic scoring, multi-factor weighting (Graph + Semantic + Provenance),
and candidate re-ranking with intent alignment.
"""

from typing import List, Optional
from .models import ContextItem, QueryAnalysisResult, QueryIntent, ContextType


class ContextRanker:
    """
    Ranks retrieved context items using linear combinations of graph connectivity,
    lexical/semantic similarity, provenance completeness, and query intent alignment.
    """

    def rank(
        self,
        items: List[ContextItem],
        analysis: QueryAnalysisResult,
        graph_weight: float = 0.5,
        semantic_weight: float = 0.3,
        provenance_weight: float = 0.2,
        top_k: int = 10,
    ) -> List[ContextItem]:
        """
        Score, boost, and sort candidate context items.
        """
        if not items:
            return []

        total_weight = graph_weight + semantic_weight + provenance_weight
        if total_weight <= 0:
            w_g, w_s, w_p = 0.5, 0.3, 0.2
            total_weight = 1.0
        else:
            w_g = graph_weight / total_weight
            w_s = semantic_weight / total_weight
            w_p = provenance_weight / total_weight

        ranked_items: List[ContextItem] = []

        for item in items:
            # 1. Fair multi-modal retrieval relevance
            if item.graph_score > 0 and item.semantic_score > 0:
                # Matched via both graph and vector
                match_relevance = ((w_g * item.graph_score) + (w_s * item.semantic_score)) / max(0.001, (w_g + w_s))
                match_relevance *= 1.15  # Hybrid cross-modal bonus
            elif item.graph_score > 0:
                match_relevance = item.graph_score
            elif item.semantic_score > 0:
                match_relevance = item.semantic_score
            else:
                match_relevance = 0.0

            # Combine match relevance with provenance completeness
            base_score = ((1.0 - w_p) * match_relevance) + (w_p * item.provenance_score)

            # 2. Intent alignment boost
            intent_boost = self._calculate_intent_boost(item, analysis.intent)

            # 3. Exact target / entity match boost
            target_boost = self._calculate_target_boost(item, analysis)

            # 4. Provenance quality boost
            prov_boost = self._calculate_provenance_boost(item)

            final_score = base_score * (1.0 + intent_boost + target_boost + prov_boost)
            item.score = round(final_score, 4)
            ranked_items.append(item)

        # Sort descending by final score
        ranked_items.sort(key=lambda x: x.score, reverse=True)
        return ranked_items[:top_k]

    def _calculate_intent_boost(self, item: ContextItem, intent: QueryIntent) -> float:
        """Boost items matching the specific query intent."""
        boost = 0.0
        content_lower = item.content.lower()
        title_lower = item.title.lower()

        if intent == QueryIntent.API_ROUTES:
            if "route" in title_lower or "endpoint" in title_lower or "fastapi" in content_lower or "router" in content_lower:
                boost += 0.20
        elif intent == QueryIntent.AUTHENTICATION:
            if any(k in content_lower for k in ["jwt", "auth", "token", "password", "bearer"]):
                boost += 0.20
        elif intent == QueryIntent.DEPENDENCY:
            if item.type == ContextType.RELATIONSHIP and any(k in content_lower for k in ["imports", "depends_on", "extends"]):
                boost += 0.25
        elif intent == QueryIntent.SCHEMA:
            if any(k in content_lower for k in ["column", "table", "sheet", "field", "schema", "datatype"]):
                boost += 0.20
        elif intent == QueryIntent.DATA_FLOW:
            if item.type == ContextType.RELATIONSHIP or "pipeline" in content_lower or "flow" in content_lower:
                boost += 0.15
        elif intent == QueryIntent.ARCHITECTURE:
            if item.type in (ContextType.SUBGRAPH, ContextType.ENTITY):
                boost += 0.10

        return boost

    def _calculate_target_boost(self, item: ContextItem, analysis: QueryAnalysisResult) -> float:
        """Boost items that directly match identified entity names or code targets."""
        boost = 0.0
        title_lower = item.title.lower()
        content_lower = item.content.lower()

        for ent in analysis.extracted_entities:
            ent_lower = ent.lower()
            if ent_lower in title_lower:
                boost += 0.15
            elif ent_lower in content_lower:
                boost += 0.08

        for target in analysis.detected_targets:
            target_lower = target.lower()
            if target_lower in title_lower:
                boost += 0.15
            elif target_lower in content_lower:
                boost += 0.08

        return min(boost, 0.30)

    def _calculate_provenance_boost(self, item: ContextItem) -> float:
        """Bonus for high-precision provenance with line numbers or chunk IDs."""
        if not item.provenance:
            return 0.0

        prov = item.provenance
        boost = 0.0
        if prov.start_line is not None and prov.start_line > 0:
            boost += 0.08
        if prov.page_number is not None and prov.page_number > 0:
            boost += 0.08
        if prov.commit_hash or prov.chunk_id:
            boost += 0.04

        return boost
