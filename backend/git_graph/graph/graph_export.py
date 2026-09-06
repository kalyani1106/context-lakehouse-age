"""
Knowledge Graph Export Service
==============================
Provides high-fidelity, one-click export of Apache AGE knowledge graphs
directly into standard formats:
- JSON (complete graph with nested provenance)
- CSV (relational vertices.csv and edges.csv)
- ZIP (complete archive with JSON, CSVs, and README metadata)
- GraphML (standard XML graph format for Gephi, Cytoscape, NetworkX)
"""

import io
import csv
import json
import logging
import zipfile
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from backend.config import settings
from backend.git_graph.config import git_settings
from backend.graph.age_client import AGEClient
from backend.git_graph.graph.git_graph_service import GitGraphService

logger = logging.getLogger("graph_export")

class GraphExportService:
    """
    Exports Apache AGE graph data for a repository into JSON, CSV, ZIP, or GraphML formats
    with complete line-level provenance and attribute preservation.
    """

    def __init__(self, age_client: Optional[AGEClient] = None, graph_name: Optional[str] = None):
        self.age_client = age_client or AGEClient()
        self.graph_name = graph_name or git_settings.GIT_AGE_GRAPH_NAME
        self.git_service = GitGraphService(self.age_client, self.graph_name)

    def _get_raw_graph_data(self, repo_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetch vertices and edges from Apache AGE with limit up to 50,000."""
        return self.git_service.get_repository_graph(repo_name=repo_name, limit=50000)

    def export_json(self, repo_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Export full graph as a structured JSON object with complete provenance.
        """
        raw = self._get_raw_graph_data(repo_name)
        nodes = raw.get("nodes", [])
        edges = raw.get("edges", [])

        # Build canonical_id map for edge resolution
        id_to_cid = {n["id"]: n.get("canonical_id", "") for n in nodes if "id" in n}

        formatted_vertices = []
        for n in nodes:
            props = n.get("properties", {})
            v_data = {
                "id": n.get("id"),
                "canonical_id": n.get("canonical_id") or props.get("canonical_id", ""),
                "label": n.get("label", "Concept"),
                "name": n.get("name", "Unnamed"),
                "entity_type": n.get("entity_type") or props.get("entity_type") or n.get("label", "Concept"),
                "repository_name": n.get("repository_name") or props.get("repository_name", repo_name or ""),
                "provenance": {
                    "file_path": n.get("file_path") or props.get("file_path", ""),
                    "start_line": n.get("start_line") or props.get("start_line", 1),
                    "end_line": n.get("end_line") or props.get("end_line", 1),
                    "commit_sha": props.get("commit_sha", ""),
                    "extraction_method": n.get("extraction_method") or props.get("extraction_method", "structural_ast"),
                    "source_snippet": n.get("source_snippet") or props.get("source_snippet", "")
                },
                "confidence": props.get("confidence", 1.0),
                "description": props.get("description", ""),
                "properties": props
            }
            formatted_vertices.append(v_data)

        formatted_edges = []
        for e in edges:
            props = e.get("properties", {})
            src_id = e.get("source")
            tgt_id = e.get("target")
            e_data = {
                "id": e.get("id"),
                "label": e.get("label", "RELATED_TO"),
                "relationship_type": e.get("relationship_type") or e.get("label", "RELATED_TO"),
                "source_id": src_id,
                "source_canonical_id": id_to_cid.get(src_id, ""),
                "target_id": tgt_id,
                "target_canonical_id": id_to_cid.get(tgt_id, ""),
                "repository_name": e.get("repository_name") or props.get("repository_name", repo_name or ""),
                "provenance": {
                    "file_path": e.get("file_path") or props.get("file_path", ""),
                    "start_line": e.get("start_line") or props.get("start_line", 1),
                    "end_line": e.get("end_line") or props.get("end_line", 1),
                    "commit_sha": props.get("commit_sha", ""),
                    "extraction_method": props.get("extraction_method", "structural_ast"),
                    "source_snippet": e.get("source_snippet") or props.get("source_snippet", "")
                },
                "weight": props.get("weight", 1.0),
                "description": props.get("description", ""),
                "properties": props
            }
            formatted_edges.append(e_data)

        return {
            "metadata": {
                "repository_name": repo_name or "all",
                "graph_name": self.graph_name,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_vertices": len(formatted_vertices),
                "total_edges": len(formatted_edges),
                "export_version": "1.0.0"
            },
            "vertices": formatted_vertices,
            "edges": formatted_edges
        }

    def export_csv_bundle(self, repo_name: Optional[str] = None) -> Tuple[str, str]:
        """
        Export graph as a pair of CSV strings (vertices_csv, edges_csv).
        """
        json_data = self.export_json(repo_name)
        vertices = json_data.get("vertices", [])
        edges = json_data.get("edges", [])

        # 1. Vertices CSV
        v_output = io.StringIO()
        v_writer = csv.writer(v_output, quoting=csv.QUOTE_MINIMAL)
        v_headers = [
            "id", "canonical_id", "label", "name", "entity_type",
            "file_path", "start_line", "end_line", "commit_sha",
            "extraction_method", "confidence", "description", "repository_name"
        ]
        v_writer.writerow(v_headers)

        for v in vertices:
            prov = v.get("provenance", {})
            v_writer.writerow([
                v.get("id"),
                v.get("canonical_id"),
                v.get("label"),
                v.get("name"),
                v.get("entity_type"),
                prov.get("file_path", ""),
                prov.get("start_line", 1),
                prov.get("end_line", 1),
                prov.get("commit_sha", ""),
                prov.get("extraction_method", ""),
                v.get("confidence", 1.0),
                v.get("description", ""),
                v.get("repository_name", "")
            ])

        # 2. Edges CSV
        e_output = io.StringIO()
        e_writer = csv.writer(e_output, quoting=csv.QUOTE_MINIMAL)
        e_headers = [
            "id", "source_id", "source_canonical_id", "target_id", "target_canonical_id",
            "label", "relationship_type", "file_path", "start_line", "end_line",
            "commit_sha", "extraction_method", "weight", "description", "repository_name"
        ]
        e_writer.writerow(e_headers)

        for e in edges:
            prov = e.get("provenance", {})
            e_writer.writerow([
                e.get("id"),
                e.get("source_id"),
                e.get("source_canonical_id"),
                e.get("target_id"),
                e.get("target_canonical_id"),
                e.get("label"),
                e.get("relationship_type"),
                prov.get("file_path", ""),
                prov.get("start_line", 1),
                prov.get("end_line", 1),
                prov.get("commit_sha", ""),
                prov.get("extraction_method", ""),
                e.get("weight", 1.0),
                e.get("description", ""),
                e.get("repository_name", "")
            ])

        return v_output.getvalue(), e_output.getvalue()

    def export_zip(self, repo_name: Optional[str] = None) -> bytes:
        """
        Package JSON, CSVs, and a README into an in-memory ZIP archive.
        """
        json_data = self.export_json(repo_name)
        v_csv, e_csv = self.export_csv_bundle(repo_name)

        meta = json_data.get("metadata", {})
        total_v = meta.get("total_vertices", 0)
        total_e = meta.get("total_edges", 0)
        export_time = meta.get("exported_at", datetime.now(timezone.utc).isoformat())
        repo_display = repo_name or "All Repositories"

        readme_content = f"""# Apache AGE Knowledge Graph Export
====================================
Repository: {repo_display}
Graph Name: {self.graph_name}
Exported At: {export_time}

## Dataset Contents
- `knowledge_graph.json`: Complete graph representation with nested line provenance.
- `vertices.csv`: Relational vertex entity table ({total_v} vertices).
- `edges.csv`: Relational edge relationship table ({total_e} edges).

## Provenance Standard
All vertices and edges include source file paths, start and end line ranges, commit SHAs,
and deterministic extraction methods to enable complete code navigation.
"""

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("knowledge_graph.json", json.dumps(json_data, indent=2))
            zf.writestr("vertices.csv", v_csv)
            zf.writestr("edges.csv", e_csv)
            zf.writestr("README.md", readme_content)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def export_graphml(self, repo_name: Optional[str] = None) -> str:
        """
        Export graph in standard XML GraphML format compatible with Gephi, Cytoscape, NetworkX, yEd.
        """
        json_data = self.export_json(repo_name)
        vertices = json_data.get("vertices", [])
        edges = json_data.get("edges", [])

        # Construct XML GraphML
        graphml = ET.Element("graphml", {
            "xmlns": "http://graphml.graphdrawing.org/xmlns",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
        })

        # Define Node Keys
        node_keys = [
            ("d_canonical_id", "node", "canonical_id", "string"),
            ("d_name", "node", "name", "string"),
            ("d_label", "node", "label", "string"),
            ("d_entity_type", "node", "entity_type", "string"),
            ("d_file_path", "node", "file_path", "string"),
            ("d_start_line", "node", "start_line", "int"),
            ("d_end_line", "node", "end_line", "int"),
            ("d_commit_sha", "node", "commit_sha", "string"),
            ("d_extraction_method", "node", "extraction_method", "string"),
            ("d_confidence", "node", "confidence", "double"),
            ("d_repo_name", "node", "repository_name", "string")
        ]
        for kid, kfor, kname, ktype in node_keys:
            ET.SubElement(graphml, "key", {
                "id": kid, "for": kfor, "attr.name": kname, "attr.type": ktype
            })

        # Define Edge Keys
        edge_keys = [
            ("e_label", "edge", "label", "string"),
            ("e_relationship_type", "edge", "relationship_type", "string"),
            ("e_file_path", "edge", "file_path", "string"),
            ("e_start_line", "edge", "start_line", "int"),
            ("e_end_line", "edge", "end_line", "int"),
            ("e_weight", "edge", "weight", "double"),
            ("e_repo_name", "edge", "repository_name", "string")
        ]
        for kid, kfor, kname, ktype in edge_keys:
            ET.SubElement(graphml, "key", {
                "id": kid, "for": kfor, "attr.name": kname, "attr.type": ktype
            })

        # Graph element
        graph = ET.SubElement(graphml, "graph", {
            "id": repo_name or "knowledge_graph",
            "edgedefault": "directed"
        })

        # Add Nodes
        for v in vertices:
            prov = v.get("provenance", {})
            node_elem = ET.SubElement(graph, "node", {"id": str(v.get("id"))})

            def add_data(key_id: str, val: Any):
                if val is not None:
                    d = ET.SubElement(node_elem, "data", {"key": key_id})
                    d.text = str(val)

            add_data("d_canonical_id", v.get("canonical_id"))
            add_data("d_name", v.get("name"))
            add_data("d_label", v.get("label"))
            add_data("d_entity_type", v.get("entity_type"))
            add_data("d_file_path", prov.get("file_path"))
            add_data("d_start_line", prov.get("start_line"))
            add_data("d_end_line", prov.get("end_line"))
            add_data("d_commit_sha", prov.get("commit_sha"))
            add_data("d_extraction_method", prov.get("extraction_method"))
            add_data("d_confidence", v.get("confidence"))
            add_data("d_repo_name", v.get("repository_name"))

        # Add Edges
        for e in edges:
            prov = e.get("provenance", {})
            edge_elem = ET.SubElement(graph, "edge", {
                "id": str(e.get("id")),
                "source": str(e.get("source_id")),
                "target": str(e.get("target_id"))
            })

            def add_edge_data(key_id: str, val: Any):
                if val is not None:
                    d = ET.SubElement(edge_elem, "data", {"key": key_id})
                    d.text = str(val)

            add_edge_data("e_label", e.get("label"))
            add_edge_data("e_relationship_type", e.get("relationship_type"))
            add_edge_data("e_file_path", prov.get("file_path"))
            add_edge_data("e_start_line", prov.get("start_line"))
            add_edge_data("e_end_line", prov.get("end_line"))
            add_edge_data("e_weight", e.get("weight"))
            add_edge_data("e_repo_name", e.get("repository_name"))

        # Render XML with encoding declaration
        xml_str = ET.tostring(graphml, encoding="utf-8", method="xml").decode("utf-8")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    def export_jpg(self, repo_name: Optional[str] = None) -> bytes:
        """
        Export graph visualization dynamically as a high-resolution JPEG image (.jpg)
        matching the dark UI theme and entity color mappings.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import networkx as nx
        from frontend.graph_visualizer import COLOR_MAP

        raw = self._get_raw_graph_data(repo_name)
        nodes = raw.get("nodes", [])
        edges = raw.get("edges", [])
        repo_display = repo_name or "Repository"

        fig, ax = plt.subplots(figsize=(20, 12), facecolor="#0F172A")
        ax.set_facecolor("#0F172A")

        if not nodes:
            ax.text(0.5, 0.5, f"No graph data available for {repo_display}", color="#94A3B8",
                    ha="center", va="center", fontsize=18)
            ax.axis("off")
            buf = io.BytesIO()
            plt.savefig(buf, format="jpeg", dpi=150, facecolor="#0F172A", bbox_inches="tight")
            plt.close(fig)
            return buf.getvalue()

        G = nx.DiGraph()
        node_colors = []
        node_labels = {}

        for n in nodes:
            nid = n["id"]
            props = n.get("properties") or {}
            name = n.get("name") or props.get("name") or n.get("label") or props.get("canonical_id") or str(nid)
            etype = n.get("entity_type") or props.get("entity_type") or n.get("label") or "Concept"
            color = COLOR_MAP.get(etype, "#3B82F6")

            disp_name = (name[:16] + "..") if len(name) > 18 else name
            G.add_node(nid, label=disp_name, full_name=name, entity_type=etype, color=color)
            node_colors.append(color)
            node_labels[nid] = disp_name

        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            if src in G and tgt in G:
                rel = e.get("relationship_type") or e.get("label") or "RELATED_TO"
                G.add_edge(src, tgt, label=rel)

        # Compute layout
        if len(G.nodes) > 1:
            try:
                pos = nx.spring_layout(G, k=0.5 / (len(G.nodes) ** 0.3), iterations=60, seed=42)
            except Exception:
                pos = nx.circular_layout(G)
        else:
            pos = {list(G.nodes)[0]: (0.5, 0.5)}

        # Draw Edges
        if G.edges:
            nx.draw_networkx_edges(
                G, pos, ax=ax,
                edge_color="#475569",
                alpha=0.6,
                arrows=True,
                arrowsize=14,
                arrowstyle="-|>",
                connectionstyle="arc3,rad=0.08",
                width=1.2
            )

        # Draw Nodes
        colors = [G.nodes[n]["color"] for n in G.nodes]
        nx.draw_networkx_nodes(
            G, pos, ax=ax,
            node_color=colors,
            node_size=850,
            edgecolors="#1E293B",
            linewidths=1.5,
            alpha=0.92
        )

        # Draw Labels with background box
        for n_id, (x, y) in pos.items():
            lbl = node_labels.get(n_id, "")
            ax.text(
                x, y, lbl,
                fontsize=8.5,
                fontweight="bold",
                color="#FFFFFF",
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#1E293B", edgecolor="none", alpha=0.75)
            )

        # Title & Metadata
        title_text = f"{repo_display} — Knowledge Graph"
        subtitle_text = f"Apache AGE Graph | {len(nodes)} Vertices | {len(edges)} Edges"
        ax.text(0.02, 0.97, title_text, transform=ax.transAxes, color="#38BDF8", fontsize=18, fontweight="bold", va="top")
        ax.text(0.02, 0.93, subtitle_text, transform=ax.transAxes, color="#94A3B8", fontsize=11, va="top")

        # Legend
        present_types = sorted(list(set(G.nodes[n]["entity_type"] for n in G.nodes)))
        legend_patches = [
            mpatches.Patch(color=COLOR_MAP.get(t, "#3B82F6"), label=t)
            for t in present_types if t in COLOR_MAP
        ]
        if legend_patches:
            legend = ax.legend(
                handles=legend_patches,
                loc="lower right",
                facecolor="#1E293B",
                edgecolor="#334155",
                fontsize=9,
                labelcolor="#F8FAFC",
                title="Entity Types",
                title_fontsize=10
            )
            legend.get_title().set_color("#38BDF8")

        ax.axis("off")
        buf = io.BytesIO()
        plt.savefig(buf, format="jpeg", dpi=150, facecolor="#0F172A", edgecolor="none", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()

