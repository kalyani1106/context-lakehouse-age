"""
Apache AGE Knowledge Graph Service
==================================
Handles ingestion of entities and relationships from DocumentContext into Apache AGE,
idempotent vertex and edge management, and rich graph queries with provenance resolution.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone

from config import settings
from graph.age_client import AGEClient
from context.schemas import DocumentContext, Entity, Relationship, Provenance

logger = logging.getLogger("graph_service")

class GraphService:
    def __init__(self, age_client: Optional[AGEClient] = None, graph_name: Optional[str] = None):
        self.age_client = age_client or AGEClient()
        self.graph_name = graph_name or settings.AGE_GRAPH_NAME
        self.age_client.ensure_graph_exists(self.graph_name)

    @staticmethod
    def sanitize_label(label: str) -> str:
        """Sanitize graph vertex/edge label to valid Cypher alphanumeric/underscore."""
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', label.strip())
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        return cleaned if cleaned else "Concept"

    @staticmethod
    def cypher_val(val: Any) -> str:
        """
        Return a safe double-quoted Cypher string literal using JSON escaping.
        Handles single quotes, double quotes, backslashes, and special characters cleanly.
        """
        if val is None:
            return '""'
        s = str(val).replace("\r", " ").replace("\n", " ").strip()
        return json.dumps(s)

    def escape_str(self, val: Any) -> str:
        """Legacy helper returning raw escaped string."""
        if val is None:
            return ""
        s = str(val).replace("\\", "\\\\").replace("'", "\\'")
        return s.replace("\n", " ").replace("\r", " ").strip()

    def ingest_context(self, context: DocumentContext) -> Dict[str, Any]:
        """
        Ingest extracted document entities as vertices and relationships as edges into Apache AGE.
        Guarantees idempotency and prevents duplicate vertices with the same canonical name.
        """
        self.age_client.ensure_graph_exists(self.graph_name)

        nodes_created = 0
        nodes_existing = 0
        edges_created = 0
        edges_existing = 0

        # 1. Batch-check existing nodes using double-quoted Cypher literals
        existing_names: Set[str] = set()
        all_cnames = [ent.canonical_name or ent.name for ent in context.entities if (ent.canonical_name or ent.name)]
        
        if all_cnames:
            # Check in chunks of 50
            for i in range(0, len(all_cnames), 50):
                chunk_names = all_cnames[i:i+50]
                in_clause = ", ".join([self.cypher_val(name) for name in chunk_names])
                try:
                    res = self.age_client.execute_cypher(
                        f"MATCH (n) WHERE n.canonical_name IN [{in_clause}] RETURN n.canonical_name AS cname",
                        columns=["cname"],
                        graph_name=self.graph_name
                    )
                    for r in res:
                        if r.get("cname"):
                            existing_names.add(r["cname"])
                except Exception as e:
                    logger.warning(f"Batch check warning: {e}")
                    # Fallback to individual checks if batch check fails
                    for name in chunk_names:
                        try:
                            chk = self.age_client.execute_cypher(
                                f"MATCH (n) WHERE n.canonical_name = {self.cypher_val(name)} RETURN n.canonical_name AS cname LIMIT 1",
                                columns=["cname"],
                                graph_name=self.graph_name
                            )
                            if chk:
                                existing_names.add(name)
                        except Exception:
                            pass

        # Ingest Vertices
        seen_in_batch: Set[str] = set()
        for ent in context.entities:
            cname = ent.canonical_name or ent.name
            if not cname or cname in seen_in_batch:
                continue
            seen_in_batch.add(cname)

            label = self.sanitize_label(ent.type)

            if cname in existing_names:
                nodes_existing += 1
            else:
                desc = ent.description or ""
                doc_name = ent.source.document_name
                src_text = ent.source.source_text[:300]
                aliases_str = ", ".join(ent.aliases) if isinstance(ent.aliases, list) else str(ent.aliases or "")

                create_q = f"""
                CREATE (n:{label} {{
                    name: {self.cypher_val(cname)},
                    canonical_name: {self.cypher_val(cname)},
                    entity_type: {self.cypher_val(label)},
                    description: {self.cypher_val(desc)},
                    aliases: {self.cypher_val(aliases_str)},
                    document_id: {self.cypher_val(ent.source.document_id)},
                    document_name: {self.cypher_val(doc_name)},
                    page_number: {ent.source.page_number},
                    source_text: {self.cypher_val(src_text)},
                    created_at: {self.cypher_val(datetime.now(timezone.utc).isoformat())}
                }})
                RETURN n
                """
                try:
                    self.age_client.execute_cypher(create_q, columns=["n"], graph_name=self.graph_name)
                    nodes_created += 1
                    existing_names.add(cname)
                except Exception as e:
                    logger.error(f"Failed to create vertex for {cname}: {e}")

        # 2. Ingest Relationships (Edges)
        seen_edges_in_batch: Set[Tuple[str, str, str]] = set()
        for rel in context.relationships:
            src_name = rel.source_entity
            tgt_name = rel.target_entity
            rel_label = self.sanitize_label(rel.relationship_type).upper()

            if not src_name or not tgt_name or src_name == tgt_name:
                continue

            edge_key = (src_name, rel_label, tgt_name)
            if edge_key in seen_edges_in_batch:
                continue
            seen_edges_in_batch.add(edge_key)

            # Check if edge already exists between these 2 nodes
            check_edge_q = f"""
            MATCH (a {{canonical_name: {self.cypher_val(src_name)}}})-[r:{rel_label}]->(b {{canonical_name: {self.cypher_val(tgt_name)}}})
            RETURN r LIMIT 1
            """
            try:
                existing_edge = self.age_client.execute_cypher(check_edge_q, columns=["r"], graph_name=self.graph_name)
            except Exception:
                existing_edge = []

            if existing_edge:
                edges_existing += 1
            else:
                doc_name = rel.source.document_name
                src_text = rel.source.source_text[:300]
                desc = rel.description or ""

                create_edge_q = f"""
                MATCH (a {{canonical_name: {self.cypher_val(src_name)}}}), (b {{canonical_name: {self.cypher_val(tgt_name)}}})
                CREATE (a)-[r:{rel_label} {{
                    document_id: {self.cypher_val(rel.source.document_id)},
                    document_name: {self.cypher_val(doc_name)},
                    page_number: {rel.source.page_number},
                    source_text: {self.cypher_val(src_text)},
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
                    logger.warning(f"Failed to create edge {src_name} -[{rel_label}]-> {tgt_name}: {e}")

        summary = {
            "graph_name": self.graph_name,
            "document_id": context.document_id,
            "nodes_created": nodes_created,
            "nodes_existing": nodes_existing,
            "edges_created": edges_created,
            "edges_existing": edges_existing,
            "total_entities_processed": len(context.entities),
            "total_relationships_processed": len(context.relationships)
        }
        logger.info(f"Graph ingestion completed for {context.document_name}: {summary}")
        return summary

    def get_all_entities(self, entity_type: Optional[str] = None, search: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """Query entities directly from Apache AGE."""
        if entity_type:
            label = self.sanitize_label(entity_type)
            cypher = f"MATCH (n:{label}) RETURN n LIMIT {limit}"
        else:
            cypher = f"MATCH (n) RETURN n LIMIT {limit}"

        results = self.age_client.execute_cypher(cypher, columns=["n"], graph_name=self.graph_name)
        nodes = []
        for r in results:
            n = r.get("n")
            if isinstance(n, dict):
                props = n.get("properties", {})
                props["id"] = n.get("id")
                props["label"] = n.get("label")
                if search:
                    name = props.get("name", "")
                    if search.lower() not in name.lower():
                        continue
                nodes.append(props)
        return nodes

    def get_all_relationships(self, rel_type: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """Query relationships directly from Apache AGE with source and target info."""
        if rel_type:
            rel_label = self.sanitize_label(rel_type).upper()
            cypher = f"MATCH (a)-[r:{rel_label}]->(b) RETURN a, r, b LIMIT {limit}"
        else:
            cypher = f"MATCH (a)-[r]->(b) RETURN a, r, b LIMIT {limit}"

        results = self.age_client.execute_cypher(cypher, columns=["a", "r", "b"], graph_name=self.graph_name)
        relationships = []
        for row in results:
            a = row.get("a", {})
            r = row.get("r", {})
            b = row.get("b", {})
            
            src_props = a.get("properties", {}) if isinstance(a, dict) else {}
            tgt_props = b.get("properties", {}) if isinstance(b, dict) else {}
            r_props = r.get("properties", {}) if isinstance(r, dict) else {}

            relationships.append({
                "id": r.get("id") if isinstance(r, dict) else None,
                "label": r.get("label") if isinstance(r, dict) else "RELATED_TO",
                "relationship_type": r.get("label") if isinstance(r, dict) else "RELATED_TO",
                "source_name": src_props.get("name") or src_props.get("canonical_name") or "Unnamed",
                "target_name": tgt_props.get("name") or tgt_props.get("canonical_name") or "Unnamed",
                "source_id": a.get("id") if isinstance(a, dict) else None,
                "target_id": b.get("id") if isinstance(b, dict) else None,
                "source": {
                    "id": a.get("id") if isinstance(a, dict) else None,
                    "name": src_props.get("name") or src_props.get("canonical_name"),
                    "type": src_props.get("entity_type") or a.get("label")
                },
                "target": {
                    "id": b.get("id") if isinstance(b, dict) else None,
                    "name": tgt_props.get("name") or tgt_props.get("canonical_name"),
                    "type": tgt_props.get("entity_type") or b.get("label")
                },
                "document_name": r_props.get("document_name", "N/A"),
                "page_number": r_props.get("page_number", 1),
                "source_text": r_props.get("source_text", ""),
                "properties": r_props
            })
        return relationships

    def get_document_subgraph(self, document_id: str) -> Dict[str, Any]:
        """
        Extract the complete subgraph for a specific document.
        Returns unique vertices and edges associated with the document.
        """
        nodes_dict = {}

        # 1. Fetch vertices for document
        node_q = f"MATCH (n {{document_id: {self.cypher_val(document_id)}}}) RETURN n"
        node_results = self.age_client.execute_cypher(node_q, columns=["n"], graph_name=self.graph_name)
        
        for row in node_results:
            n = row.get("n")
            if isinstance(n, dict):
                props = n.get("properties", {})
                nid = n.get("id")
                nodes_dict[nid] = {
                    "id": nid,
                    "label": n.get("label", "Concept"),
                    "name": props.get("name", "Unnamed"),
                    "canonical_name": props.get("canonical_name", props.get("name", "")),
                    "properties": props
                }

        # 2. Fetch edges for document
        edge_q = f"MATCH (a)-[r {{document_id: {self.cypher_val(document_id)}}}]->(b) RETURN a, r, b"
        edge_results = self.age_client.execute_cypher(edge_q, columns=["a", "r", "b"], graph_name=self.graph_name)
        
        edges = []
        for row in edge_results:
            a = row.get("a", {})
            r = row.get("r", {})
            b = row.get("b", {})
            
            # Ensure both endpoint nodes are in nodes_dict
            for node_obj in (a, b):
                if isinstance(node_obj, dict) and node_obj.get("id") not in nodes_dict:
                    props = node_obj.get("properties", {})
                    nid = node_obj.get("id")
                    nodes_dict[nid] = {
                        "id": nid,
                        "label": node_obj.get("label", "Concept"),
                        "name": props.get("name", "Unnamed"),
                        "canonical_name": props.get("canonical_name", props.get("name", "")),
                        "properties": props
                    }

            r_props = r.get("properties", {}) if isinstance(r, dict) else {}
            edges.append({
                "id": r.get("id") if isinstance(r, dict) else None,
                "label": r.get("label") if isinstance(r, dict) else "RELATED_TO",
                "source": a.get("id") if isinstance(a, dict) else None,
                "target": b.get("id") if isinstance(b, dict) else None,
                "properties": r_props
            })

        return {
            "document_id": document_id,
            "nodes": list(nodes_dict.values()),
            "edges": edges
        }

    def get_full_graph(self, limit: int = 300) -> Dict[str, Any]:
        """Fetch all vertices and edges for visual exploration."""
        cypher = f"MATCH (a)-[r]->(b) RETURN a, r, b LIMIT {limit}"
        rows = self.age_client.execute_cypher(cypher, columns=["a", "r", "b"], graph_name=self.graph_name)
        
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
                            "canonical_name": props.get("canonical_name", props.get("name", "")),
                            "properties": props
                        }

            if isinstance(r, dict):
                r_props = r.get("properties", {})
                edges.append({
                    "id": r.get("id"),
                    "label": r.get("label", "RELATED_TO"),
                    "source": a.get("id") if isinstance(a, dict) else None,
                    "target": b.get("id") if isinstance(b, dict) else None,
                    "properties": r_props
                })

        # If graph has isolated vertices not in edges
        if len(nodes_map) < limit:
            isolated_q = f"MATCH (n) RETURN n LIMIT {limit}"
            iso_rows = self.age_client.execute_cypher(isolated_q, columns=["n"], graph_name=self.graph_name)
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
                            "canonical_name": props.get("canonical_name", props.get("name", "")),
                            "properties": props
                        }

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges
        }

    def get_entity_provenance(self, entity_name: str) -> Dict[str, Any]:
        """Fetch full document provenance and connected relationships for an entity."""
        cypher = f"""
        MATCH (n {{canonical_name: {self.cypher_val(entity_name)}}})
        RETURN n
        LIMIT 1
        """
        results = self.age_client.execute_cypher(cypher, columns=["n"], graph_name=self.graph_name)
        if not results:
            return {"error": f"Entity '{entity_name}' not found in knowledge graph."}

        node_data = results[0]["n"]
        props = node_data.get("properties", {})

        # Fetch connected relationships
        rel_cypher = f"""
        MATCH (n {{canonical_name: {self.cypher_val(entity_name)}}})-[r]-(target)
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
                "relationship": r.get("label", "RELATED_TO"),
                "relationship_type": r.get("label", "RELATED_TO"),
                "connected_entity": tgt_props.get("name") or tgt_props.get("canonical_name"),
                "connected_type": tgt_props.get("entity_type") or tgt.get("label"),
                "document_name": r_props.get("document_name"),
                "page_number": r_props.get("page_number"),
                "source_text": r_props.get("source_text"),
                "provenance": {
                    "document_name": r_props.get("document_name"),
                    "page_number": r_props.get("page_number"),
                    "source_text": r_props.get("source_text")
                }
            })

        return {
            "entity_id": node_data.get("id"),
            "name": props.get("name"),
            "canonical_name": props.get("canonical_name"),
            "entity_type": props.get("entity_type") or node_data.get("label"),
            "document_id": props.get("document_id"),
            "document_name": props.get("document_name"),
            "page_number": props.get("page_number"),
            "source_text": props.get("source_text"),
            "description": props.get("description"),
            "aliases": props.get("aliases"),
            "entity": {
                "id": node_data.get("id"),
                "name": props.get("name"),
                "canonical_name": props.get("canonical_name"),
                "type": props.get("entity_type") or node_data.get("label"),
                "description": props.get("description"),
                "aliases": props.get("aliases")
            },
            "provenance": {
                "document_id": props.get("document_id"),
                "document_name": props.get("document_name"),
                "page_number": props.get("page_number"),
                "source_text": props.get("source_text"),
                "created_at": props.get("created_at")
            },
            "connections": connections
        }

    def get_graph_stats(self) -> Dict[str, Any]:
        """Return counts of total vertices, total edges, and entity types in Apache AGE."""
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
            logger.error(f"Error fetching graph stats: {e}")
            return {"graph_name": self.graph_name, "total_nodes": 0, "total_edges": 0, "entity_types": {}}
