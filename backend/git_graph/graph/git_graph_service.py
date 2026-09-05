"""
Apache AGE Git Knowledge Graph Service
======================================
Manages idempotent vertex and edge persistence for Git repository entities,
cypher queries, provenance resolution, and subgraphs using Apache AGE in PostgreSQL.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone

from backend.config import settings
from backend.git_graph.config import git_settings
from backend.graph.age_client import AGEClient
from backend.git_graph.context.schemas import GitRepoContext, GitGraphEntity, GitGraphRelationship

logger = logging.getLogger("git_graph_service")

class GitGraphService:
    def __init__(self, age_client: Optional[AGEClient] = None, graph_name: Optional[str] = None):
        self.age_client = age_client or AGEClient()
        self.graph_name = graph_name or git_settings.GIT_AGE_GRAPH_NAME
        self.age_client.ensure_graph_exists(self.graph_name)

    @staticmethod
    def sanitize_label(label: str) -> str:
        """Sanitize graph vertex/edge label to valid Cypher alphanumeric/underscore."""
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', label.strip())
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        return cleaned if cleaned else "Concept"

    @staticmethod
    def cypher_val(val: Any) -> str:
        """Safe double-quoted Cypher string literal using JSON escaping."""
        if val is None:
            return '""'
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, bool):
            return "true" if val else "false"
        s = str(val).replace("\r", " ").replace("\n", " ").strip()
        return json.dumps(s)

    def ingest_repo_context(self, context: GitRepoContext) -> Dict[str, Any]:
        """
        Ingest GitRepoContext entities as vertices and relationships as edges into Apache AGE.
        Idempotent: prevents duplicate vertices with the same canonical_id.
        """
        self.age_client.ensure_graph_exists(self.graph_name)

        nodes_created = 0
        nodes_existing = 0
        edges_created = 0
        edges_existing = 0

        # 1. Batch check existing vertices by canonical_id
        existing_cids: Set[str] = set()
        all_cids = [ent.canonical_id for ent in context.entities if ent.canonical_id]

        if all_cids:
            for i in range(0, len(all_cids), 50):
                chunk_cids = all_cids[i:i+50]
                in_clause = ", ".join([self.cypher_val(cid) for cid in chunk_cids])
                try:
                    res = self.age_client.execute_cypher(
                        f"MATCH (n) WHERE n.canonical_id IN [{in_clause}] RETURN n.canonical_id AS cid",
                        columns=["cid"],
                        graph_name=self.graph_name
                    )
                    for r in res:
                        if r.get("cid"):
                            existing_cids.add(r["cid"])
                except Exception as e:
                    logger.warning(f"Batch vertex check warning: {e}")
                    for cid in chunk_cids:
                        try:
                            chk = self.age_client.execute_cypher(
                                f"MATCH (n) WHERE n.canonical_id = {self.cypher_val(cid)} RETURN n.canonical_id AS cid LIMIT 1",
                                columns=["cid"],
                                graph_name=self.graph_name
                            )
                            if chk:
                                existing_cids.add(cid)
                        except Exception:
                            pass

        # 2. Ingest Vertices
        seen_in_batch: Set[str] = set()
        for ent in context.entities:
            cid = ent.canonical_id
            if not cid or cid in seen_in_batch:
                continue
            seen_in_batch.add(cid)

            label = self.sanitize_label(ent.entity_type)
            prov = ent.provenance
            desc = ent.description or ""
            snippet = (prov.source_snippet or "")[:400]
            aliases_str = ", ".join(ent.aliases) if isinstance(ent.aliases, list) else str(ent.aliases or "")

            if cid in existing_cids:
                nodes_existing += 1
                if ent.entity_type == "Repository":
                    url_val = ent.properties.get("url") or prov.repository_url or ent.properties.get("repository_url") or ""
                    repo_name_val = ent.name or prov.repository_name or ent.properties.get("repository_name") or ""
                    files_cnt = ent.properties.get("total_files", 0)
                    lines_cnt = ent.properties.get("total_lines", 0)
                    update_q = f"""
                    MATCH (n:Repository {{canonical_id: {self.cypher_val(cid)}}})
                    SET n.url = {self.cypher_val(url_val)},
                        n.repository_url = {self.cypher_val(url_val)},
                        n.repository_name = {self.cypher_val(repo_name_val)},
                        n.name = {self.cypher_val(repo_name_val)},
                        n.total_files = {files_cnt},
                        n.total_lines = {lines_cnt},
                        n.branch = {self.cypher_val(prov.branch)},
                        n.commit_sha = {self.cypher_val(prov.commit_sha)}
                    RETURN n
                    """
                    try:
                        self.age_client.execute_cypher(update_q, columns=["n"], graph_name=self.graph_name)
                    except Exception as e:
                        logger.warning(f"Failed to update existing repository vertex for {cid}: {e}")
            else:
                if ent.entity_type == "Repository":
                    url_val = ent.properties.get("url") or prov.repository_url or ent.properties.get("repository_url") or ""
                    repo_name_val = ent.name or prov.repository_name or ent.properties.get("repository_name") or ""
                    files_cnt = ent.properties.get("total_files", 0)
                    lines_cnt = ent.properties.get("total_lines", 0)
                    create_q = f"""
                    CREATE (n:{label} {{
                        canonical_id: {self.cypher_val(cid)},
                        name: {self.cypher_val(repo_name_val)},
                        entity_type: {self.cypher_val(label)},
                        description: {self.cypher_val(desc)},
                        aliases: {self.cypher_val(aliases_str)},
                        repository_name: {self.cypher_val(repo_name_val)},
                        repository_url: {self.cypher_val(url_val)},
                        url: {self.cypher_val(url_val)},
                        branch: {self.cypher_val(prov.branch)},
                        commit_sha: {self.cypher_val(prov.commit_sha)},
                        total_files: {files_cnt},
                        total_lines: {lines_cnt},
                        file_path: {self.cypher_val(prov.file_path or "")},
                        start_line: {prov.start_line if prov.start_line is not None else 1},
                        end_line: {prov.end_line if prov.end_line is not None else 1},
                        source_snippet: {self.cypher_val(snippet)},
                        extraction_method: {self.cypher_val(prov.extraction_method)},
                        confidence: {ent.confidence},
                        created_at: {self.cypher_val(datetime.now(timezone.utc).isoformat())}
                    }})
                    RETURN n
                    """
                else:
                    create_q = f"""
                    CREATE (n:{label} {{
                        canonical_id: {self.cypher_val(cid)},
                        name: {self.cypher_val(ent.name)},
                        entity_type: {self.cypher_val(label)},
                        description: {self.cypher_val(desc)},
                        aliases: {self.cypher_val(aliases_str)},
                        repository_name: {self.cypher_val(prov.repository_name)},
                        repository_url: {self.cypher_val(prov.repository_url)},
                        branch: {self.cypher_val(prov.branch)},
                        commit_sha: {self.cypher_val(prov.commit_sha)},
                        file_path: {self.cypher_val(prov.file_path or "")},
                        start_line: {prov.start_line if prov.start_line is not None else 1},
                        end_line: {prov.end_line if prov.end_line is not None else 1},
                        source_snippet: {self.cypher_val(snippet)},
                        extraction_method: {self.cypher_val(prov.extraction_method)},
                        confidence: {ent.confidence},
                        created_at: {self.cypher_val(datetime.now(timezone.utc).isoformat())}
                    }})
                    RETURN n
                    """
                try:
                    self.age_client.execute_cypher(create_q, columns=["n"], graph_name=self.graph_name)
                    nodes_created += 1
                    existing_cids.add(cid)
                except Exception as e:
                    logger.error(f"Failed to create vertex for {cid}: {e}")

        # 3. Ingest Relationships (Edges)
        seen_edges_in_batch: Set[Tuple[str, str, str]] = set()
        for rel in context.relationships:
            src_cid = rel.source_canonical_id
            tgt_cid = rel.target_canonical_id
            rel_label = self.sanitize_label(rel.relationship_type).upper()

            if not src_cid or not tgt_cid or src_cid == tgt_cid:
                continue

            edge_key = (src_cid, rel_label, tgt_cid)
            if edge_key in seen_edges_in_batch:
                continue
            seen_edges_in_batch.add(edge_key)

            # Check if edge already exists
            check_edge_q = f"""
            MATCH (a {{canonical_id: {self.cypher_val(src_cid)}}})-[r:{rel_label}]->(b {{canonical_id: {self.cypher_val(tgt_cid)}}})
            RETURN r LIMIT 1
            """
            try:
                existing_edge = self.age_client.execute_cypher(check_edge_q, columns=["r"], graph_name=self.graph_name)
            except Exception:
                existing_edge = []

            if existing_edge:
                edges_existing += 1
            else:
                prov = rel.provenance
                snippet = (prov.source_snippet or "")[:400]
                desc = rel.description or ""

                create_edge_q = f"""
                MATCH (a {{canonical_id: {self.cypher_val(src_cid)}}}), (b {{canonical_id: {self.cypher_val(tgt_cid)}}})
                CREATE (a)-[r:{rel_label} {{
                    relationship_type: {self.cypher_val(rel_label)},
                    repository_name: {self.cypher_val(prov.repository_name)},
                    commit_sha: {self.cypher_val(prov.commit_sha)},
                    file_path: {self.cypher_val(prov.file_path or "")},
                    start_line: {prov.start_line if prov.start_line is not None else 1},
                    end_line: {prov.end_line if prov.end_line is not None else 1},
                    source_snippet: {self.cypher_val(snippet)},
                    extraction_method: {self.cypher_val(prov.extraction_method)},
                    description: {self.cypher_val(desc)},
                    weight: {rel.weight},
                    created_at: {self.cypher_val(datetime.now(timezone.utc).isoformat())}
                }}]->(b)
                RETURN r
                """
                try:
                    res = self.age_client.execute_cypher(create_edge_q, columns=["r"], graph_name=self.graph_name)
                    if res:
                        edges_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create edge {src_cid} -[:{rel_label}]-> {tgt_cid}: {e}")

        summary = {
            "graph_name": self.graph_name,
            "repository_name": context.repository_name,
            "commit_sha": context.commit_sha,
            "nodes_created": nodes_created,
            "nodes_existing": nodes_existing,
            "edges_created": edges_created,
            "edges_existing": edges_existing,
            "total_entities_processed": len(context.entities),
            "total_relationships_processed": len(context.relationships)
        }
        logger.info(f"Git graph ingestion completed for {context.repository_name}: {summary}")
        return summary

    def get_repository_graph(self, repo_name: Optional[str] = None, limit: int = 300) -> Dict[str, Any]:
        """Fetch vertices and edges for visual exploration."""
        if repo_name:
            edge_q = f"""
            MATCH (a)-[r]->(b)
            WHERE a.repository_name = {self.cypher_val(repo_name)} OR r.repository_name = {self.cypher_val(repo_name)}
            RETURN a, r, b
            LIMIT {limit}
            """
        else:
            edge_q = f"MATCH (a)-[r]->(b) RETURN a, r, b LIMIT {limit}"

        rows = self.age_client.execute_cypher(edge_q, columns=["a", "r", "b"], graph_name=self.graph_name)
        
        nodes_map = {}
        edges = []

        for row in rows:
            a = row.get("a", {})
            r = row.get("r", {})
            b = row.get("b", {})

            for node_obj in (a, b):
                if isinstance(node_obj, dict) and node_obj.get("id"):
                    nid = node_obj["id"]
                    if nid not in nodes_map:
                        props = node_obj.get("properties", {})
                        nodes_map[nid] = {
                            "id": nid,
                            "label": node_obj.get("label", "Concept"),
                            "name": props.get("name", "Unnamed"),
                            "canonical_id": props.get("canonical_id", ""),
                            "entity_type": props.get("entity_type") or node_obj.get("label"),
                            "repository_name": props.get("repository_name", ""),
                            "file_path": props.get("file_path", ""),
                            "start_line": props.get("start_line", 1),
                            "end_line": props.get("end_line", 1),
                            "source_snippet": props.get("source_snippet", ""),
                            "extraction_method": props.get("extraction_method", ""),
                            "properties": props
                        }

            if isinstance(r, dict):
                r_props = r.get("properties", {})
                edges.append({
                    "id": r.get("id"),
                    "label": r.get("label", "RELATED_TO"),
                    "relationship_type": r.get("label", "RELATED_TO"),
                    "source": a.get("id") if isinstance(a, dict) else None,
                    "target": b.get("id") if isinstance(b, dict) else None,
                    "repository_name": r_props.get("repository_name", ""),
                    "file_path": r_props.get("file_path", ""),
                    "start_line": r_props.get("start_line", 1),
                    "end_line": r_props.get("end_line", 1),
                    "source_snippet": r_props.get("source_snippet", ""),
                    "properties": r_props
                })

        # If isolated nodes exist
        if len(nodes_map) < limit:
            iso_q = f"MATCH (n) WHERE n.repository_name = {self.cypher_val(repo_name)} RETURN n LIMIT {limit}" if repo_name else f"MATCH (n) RETURN n LIMIT {limit}"
            iso_rows = self.age_client.execute_cypher(iso_q, columns=["n"], graph_name=self.graph_name)
            for row in iso_rows:
                n = row.get("n")
                if isinstance(n, dict) and n.get("id"):
                    nid = n["id"]
                    if nid not in nodes_map:
                        props = n.get("properties", {})
                        nodes_map[nid] = {
                            "id": nid,
                            "label": n.get("label", "Concept"),
                            "name": props.get("name", "Unnamed"),
                            "canonical_id": props.get("canonical_id", ""),
                            "entity_type": props.get("entity_type") or n.get("label"),
                            "repository_name": props.get("repository_name", ""),
                            "file_path": props.get("file_path", ""),
                            "start_line": props.get("start_line", 1),
                            "end_line": props.get("end_line", 1),
                            "source_snippet": props.get("source_snippet", ""),
                            "extraction_method": props.get("extraction_method", ""),
                            "properties": props
                        }

        return {
            "graph_name": self.graph_name,
            "repository_name": repo_name,
            "nodes": list(nodes_map.values()),
            "edges": edges
        }

    def get_entity_provenance(self, canonical_id_or_name: str) -> Dict[str, Any]:
        """Fetch full provenance traceback and connected neighborhood for an entity."""
        cypher = f"""
        MATCH (n)
        WHERE n.canonical_id = {self.cypher_val(canonical_id_or_name)} OR n.name = {self.cypher_val(canonical_id_or_name)}
        RETURN n
        LIMIT 1
        """
        results = self.age_client.execute_cypher(cypher, columns=["n"], graph_name=self.graph_name)
        if not results:
            return {"error": f"Entity '{canonical_id_or_name}' not found in Git knowledge graph."}

        node_data = results[0]["n"]
        props = node_data.get("properties", {})

        # Fetch connected relationships
        cid = props.get("canonical_id") or canonical_id_or_name
        rel_cypher = f"""
        MATCH (n {{canonical_id: {self.cypher_val(cid)}}})-[r]-(target)
        RETURN r, target
        LIMIT 50
        """
        rel_results = self.age_client.execute_cypher(rel_cypher, columns=["r", "target"], graph_name=self.graph_name)

        connections = []
        for r_row in rel_results:
            r = r_row.get("r", {})
            tgt = r_row.get("target", {})
            tgt_props = tgt.get("properties", {}) if isinstance(tgt, dict) else {}
            r_props = r.get("properties", {}) if isinstance(r, dict) else {}

            connections.append({
                "relationship_type": r.get("label", "RELATED_TO"),
                "connected_entity": tgt_props.get("name") or tgt_props.get("canonical_id"),
                "connected_type": tgt_props.get("entity_type") or tgt.get("label"),
                "connected_canonical_id": tgt_props.get("canonical_id"),
                "file_path": r_props.get("file_path"),
                "start_line": r_props.get("start_line"),
                "end_line": r_props.get("end_line"),
                "source_snippet": r_props.get("source_snippet")
            })

        return {
            "canonical_id": props.get("canonical_id"),
            "name": props.get("name"),
            "entity_type": props.get("entity_type") or node_data.get("label"),
            "repository_name": props.get("repository_name"),
            "repository_url": props.get("repository_url"),
            "branch": props.get("branch"),
            "commit_sha": props.get("commit_sha"),
            "file_path": props.get("file_path"),
            "start_line": props.get("start_line"),
            "end_line": props.get("end_line"),
            "source_snippet": props.get("source_snippet"),
            "extraction_method": props.get("extraction_method"),
            "description": props.get("description"),
            "properties": props,
            "connections": connections
        }

    def list_repositories(self) -> List[Dict[str, Any]]:
        """List all analyzed repositories in the Apache AGE graph."""
        cypher = "MATCH (r:Repository) RETURN r"
        try:
            results = self.age_client.execute_cypher(cypher, columns=["r"], graph_name=self.graph_name)
            repos = []
            seen = set()
            for row in results:
                r = row.get("r", {})
                if isinstance(r, dict):
                    props = r.get("properties", {})
                    name = props.get("name") or props.get("repository_name") or "Unnamed"
                    url = props.get("url") or props.get("repository_url") or ""
                    cid = props.get("canonical_id") or f"repo:{name}"
                    
                    if cid in seen:
                        continue
                    seen.add(cid)

                    is_legacy = bool(
                        name.startswith("tmp") or
                        name == "." or
                        "AppData" in url or
                        "\\Temp\\" in url or
                        "/tmp/" in url
                    )

                    repo_entry = {
                        "name": name,
                        "repository_name": name,
                        "url": url,
                        "repository_url": url,
                        "branch": props.get("branch", "main"),
                        "commit_sha": props.get("commit_sha", ""),
                        "total_files": props.get("total_files", "-"),
                        "total_lines": props.get("total_lines", "-"),
                        "canonical_id": cid,
                        "is_legacy_temp": is_legacy,
                        "created_at": props.get("created_at", "")
                    }
                    repos.append(repo_entry)
            
            # Sort: Canonical repos first, then legacy repos, preserving alphabetical order
            repos.sort(key=lambda x: (1 if x["is_legacy_temp"] else 0, x["name"].lower()))
            return repos
        except Exception as e:
            logger.error(f"Error listing repositories: {e}")
            return []

    def get_graph_stats(self) -> Dict[str, Any]:
        """Return total counts of vertices, edges, and entity types."""
        try:
            node_res = self.age_client.execute_cypher("MATCH (n) RETURN count(n) AS cnt", columns=["cnt"], graph_name=self.graph_name)
            edge_res = self.age_client.execute_cypher("MATCH ()-[r]->() RETURN count(r) AS cnt", columns=["cnt"], graph_name=self.graph_name)

            total_nodes = node_res[0].get("cnt", 0) if node_res else 0
            total_edges = edge_res[0].get("cnt", 0) if edge_res else 0

            type_cypher = "MATCH (n) RETURN label(n) AS label, count(n) AS cnt"
            type_res = self.age_client.execute_cypher(type_cypher, columns=["label", "cnt"], graph_name=self.graph_name)
            type_counts = {r["label"]: r["cnt"] for r in type_res if "label" in r}

            return {
                "graph_name": self.graph_name,
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "entity_types": type_counts
            }
        except Exception as e:
            logger.error(f"Error fetching Git graph stats: {e}")
            return {"graph_name": self.graph_name, "total_nodes": 0, "total_edges": 0, "entity_types": {}}
