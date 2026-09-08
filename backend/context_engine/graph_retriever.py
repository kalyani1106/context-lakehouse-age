"""
Graph Retriever for Context Engine
==================================
Executes parameterized, bounded openCypher queries against Apache AGE graphs
(git_knowledge_graph and knowledge_graph), expanding subgraphs and extracting
line-level code and document provenance.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone

from backend.config import settings
from backend.git_graph.config import git_settings
from backend.graph.age_client import AGEClient
from .models import (
    ContextItem,
    ContextType,
    ProvenanceCitation,
    QueryAnalysisResult,
)

logger = logging.getLogger("graph_retriever")


class GraphRetriever:
    """
    Retrieves entity vertices, relationship edges, and k-hop neighborhood subgraphs
    from Apache AGE for codebases and documents.
    """

    def __init__(
        self,
        age_client: Optional[AGEClient] = None,
        git_graph_name: Optional[str] = None,
        doc_graph_name: Optional[str] = None,
    ):
        self.age_client = age_client or AGEClient()
        self.git_graph_name = git_graph_name or git_settings.GIT_AGE_GRAPH_NAME
        self.doc_graph_name = doc_graph_name or settings.AGE_GRAPH_NAME

    @staticmethod
    def cypher_val(val: Any) -> str:
        """Safe double-quoted Cypher string literal."""
        if val is None:
            return '""'
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, bool):
            return "true" if val else "false"
        s = str(val).replace("\r", " ").replace("\n", " ").strip()
        return json.dumps(s)

    @staticmethod
    def _build_cypher_regex(token: str) -> str:
        """
        Build safe case-insensitive POSIX regex for Apache AGE openCypher queries.
        Uses word boundaries (\\y) for standard identifiers/words to prevent false-positive substring matches
        (e.g., 'space' matching 'workspace'), while safely handling filenames and punctuation.
        """
        clean = token.replace("'", "").replace('"', "").replace("\\", "").strip()
        if not clean or len(clean) < 2:
            return ""
        if clean.isalnum() or clean.replace("_", "").isalnum():
            return f"(?i).*\\\\y{clean}\\\\y.*"
        else:
            safe_str = "".join([c if (c.isalnum() or c in "_-") else "." for c in clean])
            return f"(?i).*{safe_str}.*"

    def _expand_search_tokens(self, analysis: QueryAnalysisResult) -> List[str]:
        """
        Extract base tokens from entities, detected targets, and keywords,
        expanding with morphological roots/lemmas and intent-specific vocabulary.
        """
        from .models import QueryIntent
        token_set: Set[str] = set()
        raw_tokens = list(analysis.extracted_entities) + list(analysis.detected_targets) + list(analysis.keywords)

        for raw in raw_tokens:
            if not raw or len(raw.strip()) < 2:
                continue
            cleaned = raw.strip()
            token_set.add(cleaned)
            c_lower = cleaned.lower()
            token_set.add(c_lower)

            # Plural and suffix root stripping
            if c_lower.endswith("ies") and len(c_lower) > 4:
                token_set.add(c_lower[:-3] + "y")  # dependencies -> dependency
            elif c_lower.endswith("es") and len(c_lower) > 4:
                token_set.add(c_lower[:-2])
            elif c_lower.endswith("s") and len(c_lower) > 3:
                token_set.add(c_lower[:-1])  # tokens -> token
            elif c_lower.endswith("ed") and len(c_lower) > 4:
                token_set.add(c_lower[:-2])
                token_set.add(c_lower[:-1])
                if c_lower.endswith("ified"):
                    token_set.add(c_lower[:-5] + "ify")  # verified -> verify
            elif c_lower.endswith("ing") and len(c_lower) > 4:
                token_set.add(c_lower[:-3])
                token_set.add(c_lower[:-3] + "e")
            elif c_lower.endswith("tion") and len(c_lower) > 5:
                if "auth" in c_lower:
                    token_set.add("auth")
                if "verif" in c_lower:
                    token_set.add("verify")
                    token_set.add("verification")

        # Intent-guided contextual expansions
        intent = analysis.intent
        if intent == QueryIntent.AUTHENTICATION:
            token_set.update(["auth", "token", "jwt", "bearer", "login", "credential", "verify"])
        elif intent == QueryIntent.DEPENDENCY:
            token_set.update(["dependency", "dependencies", "import", "library", "package", "depends_on", "imports", "requirements"])
        elif intent == QueryIntent.API_ROUTES:
            token_set.update(["route", "endpoint", "api", "router", "http", "get", "post"])
        elif intent == QueryIntent.SCHEMA:
            token_set.update(["schema", "table", "column", "sheet", "model", "database", "field"])
        elif intent == QueryIntent.DATA_FLOW:
            token_set.update(["pipeline", "flow", "etl", "ingest", "process", "lakehouse"])

        return [t for t in token_set if len(t) >= 2]

    def retrieve(
        self,
        analysis: QueryAnalysisResult,
        repo_name: Optional[str] = None,
        doc_name: Optional[str] = None,
        document_id: Optional[str] = None,
        traversal_depth: int = 2,
        limit: int = 25,
    ) -> List[ContextItem]:
        """
        Execute graph retrieval across git and document knowledge graphs.
        Depth is bounded between 1 and 3.
        """
        depth = max(1, min(int(traversal_depth), 3))
        items: List[ContextItem] = []
        seen_keys: Set[str] = set()

        search_tokens = self._expand_search_tokens(analysis)

        # 1. Retrieve from Git Knowledge Graph (if repo_name is specified or doc_name is None)
        if repo_name or not (doc_name or document_id):
            try:
                git_items = self._retrieve_git_graph(
                    search_tokens=search_tokens,
                    repo_name=repo_name,
                    depth=depth,
                    limit=limit,
                )
                for item in git_items:
                    if item.id not in seen_keys:
                        seen_keys.add(item.id)
                        items.append(item)
            except Exception as e:
                logger.warning(f"Git graph retrieval notice: {e}")

        # 2. Retrieve from Document Knowledge Graph (if doc_name/doc_id is specified or repo_name is None)
        if doc_name or document_id or not repo_name:
            try:
                doc_items = self._retrieve_doc_graph(
                    search_tokens=search_tokens,
                    doc_name=doc_name,
                    document_id=document_id,
                    depth=depth,
                    limit=limit,
                )
                for item in doc_items:
                    if item.id not in seen_keys:
                        seen_keys.add(item.id)
                        items.append(item)
            except Exception as e:
                logger.warning(f"Doc graph retrieval notice: {e}")

        return items

    def _retrieve_git_graph(
        self,
        search_tokens: List[str],
        repo_name: Optional[str] = None,
        depth: int = 2,
        limit: int = 25,
    ) -> List[ContextItem]:
        """Query Git Knowledge Graph for entities and neighborhood relationships."""
        items: List[ContextItem] = []
        
        # Build query clauses
        scope_clause = f"a.repository_name = {self.cypher_val(repo_name)}" if repo_name else "1=1"
        
        # Match seed nodes across multiple properties
        matched_node_ids: Set[Any] = set()
        
        for token in search_tokens:
            reg = self._build_cypher_regex(token)
            if not reg:
                continue
            
            match_q = f"""
            MATCH (a)
            WHERE ({scope_clause}) AND (
                a.name =~ '{reg}' OR 
                a.canonical_id =~ '{reg}' OR
                a.file_path =~ '{reg}' OR
                a.entity_type =~ '{reg}' OR
                a.description =~ '{reg}' OR
                a.source_snippet =~ '{reg}' OR
                a.aliases =~ '{reg}'
            )
            RETURN a LIMIT {limit}
            """
            try:
                rows = self.age_client.execute_cypher(match_q, columns=["a"], graph_name=self.git_graph_name)
                for r in rows:
                    node = r.get("a")
                    if isinstance(node, dict) and node.get("id"):
                        matched_node_ids.add(node["id"])
                        item = self._git_node_to_context_item(node, seed_score=1.0)
                        items.append(item)
            except Exception as e:
                logger.debug(f"Git node match failed for {token}: {e}")

        # Expand neighbor edges for matched nodes
        if matched_node_ids:
            id_list_str = ", ".join([str(nid) for nid in list(matched_node_ids)[:20]])
            edge_q = f"""
            MATCH (a)-[r]->(b)
            WHERE id(a) IN [{id_list_str}] OR id(b) IN [{id_list_str}]
            RETURN a, r, b
            LIMIT {limit * 2}
            """
            try:
                edge_rows = self.age_client.execute_cypher(edge_q, columns=["a", "r", "b"], graph_name=self.git_graph_name)
                for row in edge_rows:
                    a, r, b = row.get("a"), row.get("r"), row.get("b")
                    if isinstance(r, dict) and isinstance(a, dict) and isinstance(b, dict):
                        rel_item = self._git_edge_to_context_item(a, r, b, depth_score=0.85)
                        items.append(rel_item)
            except Exception as e:
                logger.debug(f"Git edge traversal failed: {e}")
        else:
            # Check for direct relationship matches on edge properties
            for token in search_tokens:
                reg = self._build_cypher_regex(token)
                if not reg:
                    continue
                edge_scope = f"r.repository_name = {self.cypher_val(repo_name)}" if repo_name else "1=1"
                direct_edge_q = f"""
                MATCH (a)-[r]->(b)
                WHERE ({edge_scope}) AND (
                    r.relationship_type =~ '{reg}' OR
                    r.description =~ '{reg}' OR
                    r.source_snippet =~ '{reg}'
                )
                RETURN a, r, b
                LIMIT {limit}
                """
                try:
                    edge_rows = self.age_client.execute_cypher(direct_edge_q, columns=["a", "r", "b"], graph_name=self.git_graph_name)
                    for row in edge_rows:
                        a, r, b = row.get("a"), row.get("r"), row.get("b")
                        if isinstance(r, dict) and isinstance(a, dict) and isinstance(b, dict):
                            items.append(self._git_edge_to_context_item(a, r, b, depth_score=0.9))
                except Exception as e:
                    logger.debug(f"Git direct edge query failed: {e}")

        return items

    def _retrieve_doc_graph(
        self,
        search_tokens: List[str],
        doc_name: Optional[str] = None,
        document_id: Optional[str] = None,
        depth: int = 2,
        limit: int = 25,
    ) -> List[ContextItem]:
        """Query Document Knowledge Graph for entities and neighborhood relationships."""
        items: List[ContextItem] = []
        
        # Robust Scoping: handle matching either document_id or document_name
        if document_id and doc_name:
            scope_clause = f"(a.document_id = {self.cypher_val(document_id)} OR a.document_name = {self.cypher_val(doc_name)})"
        elif document_id:
            scope_clause = f"a.document_id = {self.cypher_val(document_id)}"
        elif doc_name:
            scope_clause = f"a.document_name = {self.cypher_val(doc_name)}"
        else:
            scope_clause = "1=1"

        matched_node_ids: Set[Any] = set()

        for token in search_tokens:
            reg = self._build_cypher_regex(token)
            if not reg:
                continue
            match_q = f"""
            MATCH (a)
            WHERE ({scope_clause}) AND (
                a.name =~ '{reg}' OR 
                a.canonical_name =~ '{reg}' OR
                a.entity_type =~ '{reg}' OR
                a.description =~ '{reg}' OR
                a.source_text =~ '{reg}' OR
                a.aliases =~ '{reg}'
            )
            RETURN a LIMIT {limit}
            """
            try:
                rows = self.age_client.execute_cypher(match_q, columns=["a"], graph_name=self.doc_graph_name)
                for r in rows:
                    node = r.get("a")
                    if isinstance(node, dict) and node.get("id"):
                        matched_node_ids.add(node["id"])
                        items.append(self._doc_node_to_context_item(node, seed_score=1.0))
            except Exception as e:
                logger.debug(f"Doc node match failed for {token}: {e}")

        # Expand edges
        if matched_node_ids:
            id_list_str = ", ".join([str(nid) for nid in list(matched_node_ids)[:20]])
            edge_q = f"""
            MATCH (a)-[r]->(b)
            WHERE id(a) IN [{id_list_str}] OR id(b) IN [{id_list_str}]
            RETURN a, r, b
            LIMIT {limit * 2}
            """
            try:
                edge_rows = self.age_client.execute_cypher(edge_q, columns=["a", "r", "b"], graph_name=self.doc_graph_name)
                for row in edge_rows:
                    a, r, b = row.get("a"), row.get("r"), row.get("b")
                    if isinstance(r, dict) and isinstance(a, dict) and isinstance(b, dict):
                        items.append(self._doc_edge_to_context_item(a, r, b, depth_score=0.85))
            except Exception as e:
                logger.debug(f"Doc edge traversal failed: {e}")
        else:
            # Direct edge match on relationship properties
            for token in search_tokens:
                reg = self._build_cypher_regex(token)
                if not reg:
                    continue
                if document_id and doc_name:
                    edge_scope = f"(r.document_id = {self.cypher_val(document_id)} OR r.document_name = {self.cypher_val(doc_name)})"
                elif document_id:
                    edge_scope = f"r.document_id = {self.cypher_val(document_id)}"
                elif doc_name:
                    edge_scope = f"r.document_name = {self.cypher_val(doc_name)}"
                else:
                    edge_scope = "1=1"
                direct_doc_edge_q = f"""
                MATCH (a)-[r]->(b)
                WHERE ({edge_scope}) AND (
                    r.relationship_type =~ '{reg}' OR
                    r.source_text =~ '{reg}'
                )
                RETURN a, r, b
                LIMIT {limit}
                """
                try:
                    edge_rows = self.age_client.execute_cypher(direct_doc_edge_q, columns=["a", "r", "b"], graph_name=self.doc_graph_name)
                    for row in edge_rows:
                        a, r, b = row.get("a"), row.get("r"), row.get("b")
                        if isinstance(r, dict) and isinstance(a, dict) and isinstance(b, dict):
                            items.append(self._doc_edge_to_context_item(a, r, b, depth_score=0.9))
                except Exception as e:
                    logger.debug(f"Doc direct edge query failed: {e}")

        return items

    def _git_node_to_context_item(self, node: Dict[str, Any], seed_score: float) -> ContextItem:
        """Convert a Git AGE vertex to a ContextItem."""
        props = node.get("properties", {})
        label = node.get("label", "Concept")
        name = props.get("name", "Unnamed")
        canonical_id = props.get("canonical_id", str(node.get("id")))
        
        file_path = props.get("file_path")
        start_line = props.get("start_line")
        end_line = props.get("end_line")
        snippet = props.get("source_snippet")
        repo_name = props.get("repository_name")
        commit_sha = props.get("commit_sha")

        citation = ProvenanceCitation(
            source_type="git",
            repo_name=repo_name,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            commit_hash=commit_sha,
            snippet=snippet,
        )

        content_parts = [
            f"**Symbol**: `{name}` ({label})",
            f"**Canonical ID**: `{canonical_id}`",
        ]
        if file_path:
            line_str = f":L{start_line}-L{end_line}" if start_line else ""
            content_parts.append(f"**Location**: `{file_path}{line_str}` in `{repo_name or 'repository'}`")
        if snippet:
            content_parts.append(f"```\n{snippet.strip()}\n```")

        return ContextItem(
            id=f"git:node:{canonical_id}",
            type=ContextType.ENTITY,
            title=f"Code Entity: {name} [{label}]",
            content="\n".join(content_parts),
            score=seed_score,
            graph_score=seed_score,
            semantic_score=0.0,
            provenance_score=1.0 if (file_path and start_line) else 0.5,
            provenance=citation,
            metadata={"node_id": node.get("id"), "label": label, "properties": props},
        )

    def _git_edge_to_context_item(
        self,
        src: Dict[str, Any],
        rel: Dict[str, Any],
        tgt: Dict[str, Any],
        depth_score: float,
    ) -> ContextItem:
        """Convert a Git AGE relationship edge to a ContextItem."""
        src_props = src.get("properties", {})
        tgt_props = tgt.get("properties", {})
        rel_props = rel.get("properties", {})

        src_name = src_props.get("name") or src_props.get("canonical_id") or "Source"
        tgt_name = tgt_props.get("name") or tgt_props.get("canonical_id") or "Target"
        rel_type = rel.get("label", "RELATED_TO")

        file_path = rel_props.get("file_path") or src_props.get("file_path")
        start_line = rel_props.get("start_line") or src_props.get("start_line")
        end_line = rel_props.get("end_line") or src_props.get("end_line")
        snippet = rel_props.get("source_snippet") or src_props.get("source_snippet")
        repo_name = rel_props.get("repository_name") or src_props.get("repository_name")

        citation = ProvenanceCitation(
            source_type="git",
            repo_name=repo_name,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            commit_hash=rel_props.get("commit_sha"),
            snippet=snippet,
        )

        content = f"`{src_name}` --[:{rel_type}]--> `{tgt_name}`"
        if file_path:
            content += f" *(defined in `{file_path}`)*"

        edge_id = rel.get("id") or f"{src.get('id')}_{rel_type}_{tgt.get('id')}"

        return ContextItem(
            id=f"git:edge:{edge_id}",
            type=ContextType.RELATIONSHIP,
            title=f"Relationship: {src_name} → {rel_type} → {tgt_name}",
            content=content,
            score=depth_score,
            graph_score=depth_score,
            semantic_score=0.0,
            provenance_score=0.9 if file_path else 0.4,
            provenance=citation,
            metadata={
                "source": src_name,
                "target": tgt_name,
                "relationship_type": rel_type,
                "properties": rel_props,
            },
        )

    def _doc_node_to_context_item(self, node: Dict[str, Any], seed_score: float) -> ContextItem:
        """Convert a Document AGE vertex to a ContextItem."""
        props = node.get("properties", {})
        label = node.get("label", "Concept")
        name = props.get("name", "Unnamed")
        cname = props.get("canonical_name", name)
        doc_name = props.get("document_name")
        doc_id = props.get("document_id")
        page_num = props.get("page_number")
        source_text = props.get("source_text")

        citation = ProvenanceCitation(
            source_type="document",
            document_id=doc_id,
            document_name=doc_name,
            page_number=page_num,
            snippet=source_text,
        )

        content_parts = [
            f"**Entity**: `{name}` ({label})",
            f"**Canonical Name**: `{cname}`",
        ]
        if doc_name:
            page_str = f", Page {page_num}" if page_num else ""
            content_parts.append(f"**Source Document**: `{doc_name}`{page_str}")
        if source_text:
            content_parts.append(f"> \"{source_text.strip()}\"")

        return ContextItem(
            id=f"doc:node:{cname}",
            type=ContextType.ENTITY,
            title=f"Document Entity: {name} [{label}]",
            content="\n".join(content_parts),
            score=seed_score,
            graph_score=seed_score,
            semantic_score=0.0,
            provenance_score=1.0 if doc_name else 0.5,
            provenance=citation,
            metadata={"node_id": node.get("id"), "label": label, "properties": props},
        )

    def _doc_edge_to_context_item(
        self,
        src: Dict[str, Any],
        rel: Dict[str, Any],
        tgt: Dict[str, Any],
        depth_score: float,
    ) -> ContextItem:
        """Convert a Document AGE relationship edge to a ContextItem."""
        src_props = src.get("properties", {})
        tgt_props = tgt.get("properties", {})
        rel_props = rel.get("properties", {})

        src_name = src_props.get("name") or src_props.get("canonical_name") or "Source"
        tgt_name = tgt_props.get("name") or tgt_props.get("canonical_name") or "Target"
        rel_type = rel.get("label", "RELATED_TO")

        doc_name = rel_props.get("document_name") or src_props.get("document_name")
        doc_id = rel_props.get("document_id") or src_props.get("document_id")
        page_num = rel_props.get("page_number") or src_props.get("page_number")
        source_text = rel_props.get("source_text")

        citation = ProvenanceCitation(
            source_type="document",
            document_id=doc_id,
            document_name=doc_name,
            page_number=page_num,
            snippet=source_text,
        )

        content = f"`{src_name}` --[:{rel_type}]--> `{tgt_name}`"
        if doc_name:
            content += f" *(from `{doc_name}`, p.{page_num or 1})*"
        if source_text:
            content += f"\n> \"{source_text.strip()}\""

        edge_id = rel.get("id") or f"{src.get('id')}_{rel_type}_{tgt.get('id')}"

        return ContextItem(
            id=f"doc:edge:{edge_id}",
            type=ContextType.RELATIONSHIP,
            title=f"Document Relation: {src_name} → {rel_type} → {tgt_name}",
            content=content,
            score=depth_score,
            graph_score=depth_score,
            semantic_score=0.0,
            provenance_score=0.9 if doc_name else 0.4,
            provenance=citation,
            metadata={
                "source": src_name,
                "target": tgt_name,
                "relationship_type": rel_type,
                "properties": rel_props,
            },
        )
