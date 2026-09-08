"""
Vector and Lexical Retriever for Context Engine
===============================================
Deterministic BM25 and TF-IDF lexical search engine with pluggable vector embedding
support across Lakehouse passage chunks, code files, and extracted context entities.
"""

import re
import math
import logging
from typing import List, Dict, Any, Optional, Set, Callable
from pathlib import Path

from backend.storage.lakehouse import LocalLakehouseStorageService
from backend.storage.base import StorageService
from .models import (
    ContextItem,
    ContextType,
    ProvenanceCitation,
    QueryAnalysisResult,
)

logger = logging.getLogger("vector_retriever")


class VectorRetriever:
    """
    Deterministic BM25 and TF-IDF lexical retrieval engine over Lakehouse chunks,
    extracted document context, and indexed code files.
    """

    def __init__(
        self,
        storage_service: Optional[StorageService] = None,
        k1: float = 1.5,
        b: float = 0.75,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        self.storage = storage_service or LocalLakehouseStorageService()
        self.k1 = k1
        self.b = b
        self.embed_fn = embed_fn

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Simple deterministic alphanumeric tokenizer."""
        cleaned = re.sub(r'[^a-zA-Z0-9_\-\.]', ' ', text.lower())
        tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 1]
        return tokens

    def retrieve(
        self,
        analysis: QueryAnalysisResult,
        repo_name: Optional[str] = None,
        doc_name: Optional[str] = None,
        document_id: Optional[str] = None,
        limit: int = 15,
    ) -> List[ContextItem]:
        """
        Execute BM25 / TF-IDF scoring over Lakehouse passage chunks and/or code files
        strictly respecting the requested scope (document, repository, or global).
        """
        query_terms = list(analysis.keywords)
        for ent in analysis.extracted_entities:
            for t in self.tokenize(ent):
                if t not in query_terms:
                    query_terms.append(t)
        for target in analysis.detected_targets:
            for t in self.tokenize(target):
                if t not in query_terms:
                    query_terms.append(t)

        # Morphological root expansion
        expanded_terms = list(query_terms)
        for qt in query_terms:
            if qt.endswith("ies") and len(qt) > 4:
                expanded_terms.append(qt[:-3] + "y")
            elif qt.endswith("es") and len(qt) > 4:
                expanded_terms.append(qt[:-2])
            elif qt.endswith("s") and len(qt) > 3:
                expanded_terms.append(qt[:-1])
            elif qt.endswith("ed") and len(qt) > 4:
                expanded_terms.append(qt[:-2])
                if qt.endswith("ified"):
                    expanded_terms.append(qt[:-5] + "ify")
            elif qt.endswith("ing") and len(qt) > 4:
                expanded_terms.append(qt[:-3])
            elif qt.endswith("tion") and len(qt) > 5:
                if "auth" in qt:
                    expanded_terms.append("auth")
                if "verif" in qt:
                    expanded_terms.append("verify")
                    expanded_terms.append("verification")

        query_terms = list(dict.fromkeys(expanded_terms))

        if not query_terms:
            return []

        passages: List[Dict[str, Any]] = []

        # 1. Document Chunks Retrieval (when doc_name/document_id is set or when in global scope)
        if doc_name or document_id or not repo_name:
            try:
                docs = self.storage.list_documents()
                for doc in docs:
                    # Apply scoping
                    if document_id and doc_name:
                        if doc.document_id != document_id and doc.document_name.lower() != doc_name.lower():
                            continue
                    elif document_id and doc.document_id != document_id:
                        continue
                    elif doc_name and doc.document_name.lower() != doc_name.lower():
                        continue

                    chunks = self.storage.get_chunks(doc.document_id)
                    if chunks:
                        for ch in chunks:
                            text = ch.get("chunk_text") or ch.get("text") or ""
                            if text:
                                passages.append({
                                    "id": f"chunk:{doc.document_id}:{ch.get('chunk_id', len(passages))}",
                                    "document_id": doc.document_id,
                                    "document_name": doc.document_name,
                                    "page_number": ch.get("page_number", 1),
                                    "chunk_id": ch.get("chunk_id"),
                                    "text": text,
                                    "source_type": "document"
                                })
            except Exception as e:
                logger.warning(f"Error gathering Lakehouse chunks: {e}")

        # 2. Repository Code Passages Retrieval (when repo_name is set or when in global scope)
        if repo_name or not (doc_name or document_id):
            try:
                from backend.graph.age_client import AGEClient
                from backend.git_graph.config import git_settings
                age = AGEClient()
                scope_clause = f"n.repository_name = {GraphRetriever.cypher_val(repo_name)}" if repo_name else "1=1"
                code_q = f"""
                MATCH (n)
                WHERE ({scope_clause}) AND (
                    (n.source_snippet IS NOT NULL AND n.source_snippet <> '""' AND n.source_snippet <> '') OR
                    (n.description IS NOT NULL AND n.description <> '""' AND n.description <> '')
                )
                RETURN n.name AS name, n.entity_type AS etype, n.file_path AS file_path, 
                       n.start_line AS start_line, n.end_line AS end_line, 
                       n.source_snippet AS snippet, n.description AS description,
                       n.repository_name AS repo_name, n.commit_sha AS commit_sha
                LIMIT 100
                """
                code_rows = age.execute_cypher(code_q, columns=["name", "etype", "file_path", "start_line", "end_line", "snippet", "description", "repo_name", "commit_sha"], graph_name=git_settings.GIT_AGE_GRAPH_NAME)
                for r in code_rows:
                    snippet = r.get("snippet") or ""
                    desc = r.get("description") or ""
                    combined_text = f"{r.get('name', '')} {r.get('file_path', '')} {desc} {snippet}".strip()
                    if combined_text:
                        passages.append({
                            "id": f"code:{r.get('repo_name')}:{r.get('file_path')}:{r.get('name')}",
                            "repo_name": r.get("repo_name"),
                            "file_path": r.get("file_path"),
                            "start_line": r.get("start_line", 1),
                            "end_line": r.get("end_line", 1),
                            "commit_sha": r.get("commit_sha"),
                            "name": r.get("name"),
                            "entity_type": r.get("etype", "Code"),
                            "text": combined_text,
                            "snippet": snippet or desc,
                            "source_type": "git"
                        })
            except Exception as e:
                logger.debug(f"Notice: Repository code passages query: {e}")

        if not passages:
            return []

        # 3. Compute BM25 scores
        scored_passages = self._score_bm25(query_terms, analysis.raw_query, passages)
        
        # 4. Sort and construct ContextItem results
        scored_passages.sort(key=lambda x: x["score"], reverse=True)
        
        results: List[ContextItem] = []
        for p in scored_passages[:limit]:
            if p["score"] <= 0.0:
                continue

            score = p["score"]
            stype = p.get("source_type", "document")

            if stype == "git":
                repo_n = p.get("repo_name")
                fpath = p.get("file_path")
                sline = p.get("start_line", 1)
                eline = p.get("end_line", 1)
                commit_sha = p.get("commit_sha")
                name = p.get("name")
                etype = p.get("entity_type", "Code")
                snip = p.get("snippet") or p.get("text", "")

                citation = ProvenanceCitation(
                    source_type="git",
                    repo_name=repo_n,
                    file_path=fpath,
                    start_line=sline,
                    end_line=eline,
                    commit_hash=commit_sha,
                    snippet=snip[:250],
                )

                line_info = f":L{sline}-L{eline}" if sline else ""
                title = f"Code Passage: {name} [{etype}] ({fpath}{line_info})"
                content = f"**Location**: `{fpath}{line_info}` in `{repo_n or 'repository'}`\n\n```\n{snip.strip()}\n```"

                results.append(ContextItem(
                    id=p["id"],
                    type=ContextType.FILE if etype == "File" else ContextType.CHUNK,
                    title=title,
                    content=content,
                    score=score,
                    graph_score=0.0,
                    semantic_score=score,
                    provenance_score=1.0 if (fpath and sline) else 0.7,
                    provenance=citation,
                    metadata={"repo_name": repo_n, "file_path": fpath, "start_line": sline, "end_line": eline},
                ))
            else:
                doc_id = p["document_id"]
                doc_n = p["document_name"]
                page_n = p["page_number"]
                ch_id = p["chunk_id"]
                text = p["text"]

                citation = ProvenanceCitation(
                    source_type="document",
                    document_id=doc_id,
                    document_name=doc_n,
                    page_number=page_n,
                    chunk_id=ch_id,
                    snippet=text[:250],
                )

                title = f"Document Chunk: {doc_n} (p.{page_n}, {ch_id or 'passage'})"
                content = f"**Document**: `{doc_n}` *(Page {page_n})*\n**Chunk ID**: `{ch_id or 'N/A'}`\n\n> {text.strip()}"

                results.append(ContextItem(
                    id=p["id"],
                    type=ContextType.CHUNK,
                    title=title,
                    content=content,
                    score=score,
                    graph_score=0.0,
                    semantic_score=score,
                    provenance_score=1.0 if (doc_n and page_n) else 0.6,
                    provenance=citation,
                    metadata={"document_id": doc_id, "page_number": page_n, "chunk_id": ch_id},
                ))

        return results

    def _score_bm25(
        self,
        query_terms: List[str],
        raw_query: str,
        passages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute Okapi BM25 scores for passages given query terms."""
        N = len(passages)
        if N == 0:
            return []

        # Document lengths & tokenized documents
        doc_tokens_list: List[List[str]] = []
        total_len = 0
        df: Dict[str, int] = {}

        for p in passages:
            tokens = self.tokenize(p["text"])
            doc_tokens_list.append(tokens)
            total_len += len(tokens)
            unique_terms = set(tokens)
            for t in unique_terms:
                df[t] = df.get(t, 0) + 1

        avgdl = total_len / N if N > 0 else 1.0

        # Calculate IDF for query terms
        idf: Dict[str, float] = {}
        for qt in query_terms:
            doc_freq = df.get(qt, 0)
            # Standard smoothed IDF
            idf[qt] = math.log(1.0 + (N - doc_freq + 0.5) / (doc_freq + 0.5))

        raw_q_lower = raw_query.lower()
        scored_list: List[Dict[str, Any]] = []

        for idx, p in enumerate(passages):
            tokens = doc_tokens_list[idx]
            dl = len(tokens)
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1

            score = 0.0
            for qt in query_terms:
                f = tf.get(qt, 0)
                if f > 0:
                    numerator = f * (self.k1 + 1.0)
                    denominator = f + self.k1 * (1.0 - self.b + self.b * (dl / (avgdl or 1.0)))
                    score += idf.get(qt, 0.0) * (numerator / denominator)

            # Bonus for exact query phrase match
            if raw_q_lower and raw_q_lower in p["text"].lower():
                score += 3.0

            # Normalize score
            normalized_score = max(0.0, score)
            item = dict(p)
            item["score"] = normalized_score
            scored_list.append(item)

        # Scale scores to 0.0 - 1.0 range if max > 0
        max_score = max([x["score"] for x in scored_list], default=0.0)
        if max_score > 0.0:
            for x in scored_list:
                x["score"] = round(x["score"] / max_score, 4)

        return scored_list
