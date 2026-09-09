"""
Interactive Knowledge Graph HTML/JS Visualizer
==============================================
Generates high-performance Vis.js graph components for Streamlit,
with color-coded entity nodes, relationship edges, and code/document provenance click handlers.
Includes embedded library support, robust CSS dimensions, auto-fit, and diagnostics.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List

COLOR_MAP = {
    # Git Repository Entities
    "Repository": "#4F46E5",   # Indigo
    "Directory": "#64748B",    # Slate
    "File": "#0284C7",         # Sky Blue
    "Module": "#06B6D4",       # Cyan
    "Class": "#8B5CF6",        # Purple
    "Function": "#3B82F6",     # Blue
    "Method": "#2563EB",       # Royal Blue
    "Library": "#EC4899",      # Pink
    "Technology": "#10B981",   # Emerald Green
    "API": "#F59E0B",          # Amber
    "Service": "#EA580C",      # Orange
    "Table": "#6366F1",        # Indigo
    "Concept": "#14B8A6",      # Teal
    # Document Entities
    "Organization": "#D97706", # Amber
    "Person": "#DB2777",      # Pink
    "Framework": "#7C3AED",   # Purple
    "Layer": "#4F46E5",       # Indigo
    "Dataset": "#0891B2",     # Cyan
    "ResearchPaper": "#475569",# Slate
    "Algorithm": "#DC2626",   # Red
    "Project": "#EA580C",     # Orange
    # Structured & Multi-Format Entities
    "Workbook": "#8B5CF6",    # Purple
    "Sheet": "#3B82F6",       # Blue
    "Column": "#06B6D4",      # Cyan
    "DataType": "#64748B",    # Slate
    "Field": "#0284C7",       # Sky Blue
    "XmlElement": "#F59E0B",  # Amber
    "Configuration": "#10B981", # Emerald
    "ConfigKey": "#14B8A6",   # Teal
    "JsonDataset": "#0891B2"  # Dark Cyan
}

# Try to load local vis-network.min.js if present for air-gapped / offline support
LOCAL_VIS_JS_PATH = Path(__file__).parent / "static" / "vis-network.min.js"
LOCAL_VIS_JS_CONTENT = None
if LOCAL_VIS_JS_PATH.exists():
    try:
        LOCAL_VIS_JS_CONTENT = LOCAL_VIS_JS_PATH.read_text(encoding="utf-8")
    except Exception:
        LOCAL_VIS_JS_CONTENT = None

def render_visjs_graph(graph_data: Dict[str, Any], height: str = "680px", debug: bool = False) -> str:
    """
    Generate an interactive Vis.js HTML document rendering nodes and edges directly from Apache AGE.
    Clicking a node or edge displays a detailed provenance traceback card.
    """
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    vis_nodes = []
    node_id_map = {}

    for n in nodes:
        nid = n.get("id")
        props = n.get("properties") or {}
        
        name = n.get("name") or n.get("canonical_name") or props.get("name") or props.get("canonical_name") or str(nid)
        cid = n.get("canonical_id") or props.get("canonical_id") or ""
        etype = n.get("entity_type") or n.get("label") or props.get("entity_type") or "Concept"
        color = COLOR_MAP.get(etype, "#3B82F6")
        
        repo_name = n.get("repository_name") or props.get("repository_name") or ""
        commit_sha = props.get("commit_sha") or n.get("commit_sha") or ""
        file_path = n.get("file_path") or props.get("file_path") or ""
        start_line = n.get("start_line") or props.get("start_line")
        end_line = n.get("end_line") or props.get("end_line")
        source_snippet = n.get("source_snippet") or props.get("source_snippet") or ""
        extraction_method = n.get("extraction_method") or props.get("extraction_method") or "STRUCTURAL_AST"

        doc_name = n.get("document_name") or props.get("document_name") or repo_name or "N/A"
        page_num = n.get("page_number") or props.get("page_number")
        src_text = n.get("source_text") or props.get("source_text") or source_snippet
        desc = n.get("description") or props.get("description") or ""
        aliases = n.get("aliases") or props.get("aliases") or ""
        if isinstance(aliases, list):
            aliases = ", ".join(aliases)

        tooltip = f"<b>{name}</b><br>Type: {etype}"
        if file_path:
            tooltip += f"<br>File: {file_path}"
            if start_line:
                tooltip += f" (L{start_line}-{end_line or start_line})"
        elif doc_name != "N/A":
            tooltip += f"<br>Doc: {doc_name}"
            if page_num:
                tooltip += f" (p.{page_num})"

        node_obj = {
            "id": nid,
            "label": name,
            "title": tooltip,
            "color": {
                "background": color,
                "border": "#1E293B",
                "highlight": {"background": "#F59E0B", "border": "#B45309"}
            },
            "font": {"color": "#FFFFFF", "size": 13, "face": "Inter, sans-serif"},
            "shape": "box",
            "margin": 9,
            "provenance": {
                "name": name,
                "canonical_id": cid,
                "type": etype,
                "repository_name": repo_name,
                "commit_sha": commit_sha,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "source_snippet": source_snippet,
                "extraction_method": extraction_method,
                "document_name": doc_name,
                "page_number": page_num,
                "source_text": src_text,
                "description": desc,
                "aliases": aliases
            }
        }
        vis_nodes.append(node_obj)
        node_id_map[nid] = node_obj

    vis_edges = []
    for idx, e in enumerate(edges):
        props = e.get("properties") or {}
        src = e.get("source") or e.get("source_id") or e.get("start_id")
        tgt = e.get("target") or e.get("target_id") or e.get("end_id")
        label = e.get("label") or e.get("relationship_type") or props.get("relationship_type") or "RELATED_TO"
        
        repo_name = e.get("repository_name") or props.get("repository_name") or ""
        commit_sha = props.get("commit_sha") or e.get("commit_sha") or ""
        file_path = e.get("file_path") or props.get("file_path") or ""
        start_line = e.get("start_line") or props.get("start_line")
        end_line = e.get("end_line") or props.get("end_line")
        source_snippet = e.get("source_snippet") or props.get("source_snippet") or ""
        extraction_method = e.get("extraction_method") or props.get("extraction_method") or ""

        doc_name = e.get("document_name") or props.get("document_name") or repo_name or "N/A"
        page_num = e.get("page_number") or props.get("page_number")
        src_text = e.get("source_text") or props.get("source_text") or source_snippet

        if src and tgt:
            vis_edges.append({
                "id": f"edge_{idx}",
                "from": src,
                "to": tgt,
                "label": label,
                "arrows": "to",
                "font": {"size": 11, "align": "middle", "color": "#94A3B8"},
                "color": {"color": "#64748B", "highlight": "#F59E0B"},
                "provenance": {
                    "relationship_type": label,
                    "repository_name": repo_name,
                    "commit_sha": commit_sha,
                    "file_path": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "source_snippet": source_snippet,
                    "extraction_method": extraction_method,
                    "document_name": doc_name,
                    "page_number": page_num,
                    "source_text": src_text
                }
            })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    if LOCAL_VIS_JS_CONTENT:
        script_tags = f"<script type=\"text/javascript\">{LOCAL_VIS_JS_CONTENT}</script>"
    else:
        script_tags = """
        <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"></script>
        <script>
            if (typeof vis === 'undefined') {
                document.write('<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"><\\/script>');
            }
        </script>
        """

    html_code = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {script_tags}
        <style>
            * {{
                box-sizing: border-box;
            }}
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                min-height: {height};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: #0B0F19;
                color: #F8FAFC;
                overflow: hidden;
            }}
            #container {{
                display: flex;
                width: 100vw;
                height: 100vh;
                min-height: {height};
                position: relative;
            }}
            #network {{
                flex: 1;
                width: 100%;
                height: 100%;
                min-height: {height};
                background: #0B0F19 radial-gradient(#1E293B 1px, transparent 1px);
                background-size: 24px 24px;
                position: relative;
            }}
            #provenance-panel {{
                width: 390px;
                height: 100%;
                background: #0F172A;
                border-left: 1px solid #1E293B;
                padding: 18px 20px;
                overflow-y: auto;
                font-size: 13px;
                flex-shrink: 0;
                box-shadow: -4px 0 16px rgba(0, 0, 0, 0.3);
            }}
            #provenance-panel::-webkit-scrollbar {{
                width: 6px;
            }}
            #provenance-panel::-webkit-scrollbar-thumb {{
                background: #334155;
                border-radius: 3px;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                background: #3B82F6;
                color: #FFFFFF;
                letter-spacing: 0.03em;
            }}
            .method-badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                background: #065F46;
                border: 1px solid #10B981;
                color: #34D399;
                margin-left: 6px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }}
            .panel-title {{
                font-size: 16px;
                font-weight: 700;
                margin: 6px 0 10px 0;
                color: #38BDF8;
                word-break: break-word;
                line-height: 1.3;
            }}
            .field-label {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: #94A3B8;
                margin-top: 12px;
                margin-bottom: 3px;
                font-weight: 600;
            }}
            .field-value {{
                color: #E2E8F0;
                line-height: 1.45;
                word-break: break-word;
            }}
            .code-box {{
                background: #050811;
                border: 1px solid #1E293B;
                border-left: 3px solid #8B5CF6;
                padding: 10px 12px;
                border-radius: 6px;
                margin-top: 6px;
                font-family: "Fira Code", "SFMono-Regular", Consolas, monospace;
                font-size: 12px;
                color: #E2E8F0;
                line-height: 1.45;
                max-height: 220px;
                overflow-y: auto;
                white-space: pre-wrap;
            }}
            .quote-box {{
                background: #050811;
                border: 1px solid #1E293B;
                border-left: 3px solid #38BDF8;
                padding: 10px 12px;
                border-radius: 6px;
                margin-top: 6px;
                font-style: italic;
                color: #CBD5E1;
                line-height: 1.45;
                max-height: 180px;
                overflow-y: auto;
            }}
            .legend {{
                position: absolute;
                bottom: 14px;
                left: 14px;
                background: rgba(15, 23, 42, 0.94);
                backdrop-filter: blur(8px);
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 14px;
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                font-size: 11px;
                pointer-events: none;
                z-index: 10;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 6px;
                color: #CBD5E1;
                font-weight: 500;
            }}
            .legend-dot {{
                width: 10px;
                height: 10px;
                border-radius: 3px;
            }}
            #debug-error {{
                display: none;
                position: absolute;
                top: 12px;
                left: 12px;
                background: #7F1D1D;
                border: 1px solid #DC2626;
                color: #FECACA;
                padding: 10px 14px;
                border-radius: 6px;
                font-size: 12px;
                z-index: 99;
                max-width: 500px;
            }}
        </style>
    </head>
    <body>
        <div id="container">
            <div id="debug-error"></div>
            <div id="network"></div>
            <div id="provenance-panel">
                <div id="panel-content">
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                        <span style="font-size:16px;">🔍</span>
                        <h4 style="margin:0; color:#38BDF8; font-size:15px; font-weight:700;">Node Provenance Inspector</h4>
                    </div>
                    <p style="color:#94A3B8; line-height:1.5; font-size:12px; margin-bottom:14px;">Click any entity node or relationship edge in the graph to inspect its exact repository source, file path, line numbers, and source code snippet.</p>
                    <hr style="border:0; border-top:1px solid #1E293B; margin:14px 0;">
                    <div style="font-size:12px; color:#64748B; background:#0B0F19; border:1px solid #1E293B; border-radius:6px; padding:10px 12px; display:flex; justify-content:space-around;">
                        <div><b>Vertices:</b> <span style="color:#38BDF8;">{len(vis_nodes)}</span></div>
                        <div style="border-left:1px solid #334155;"></div>
                        <div><b>Edges:</b> <span style="color:#38BDF8;">{len(vis_edges)}</span></div>
                    </div>
                </div>
            </div>
            <div class="legend">
                <div class="legend-item"><div class="legend-dot" style="background:#4F46E5;"></div>Repository</div>
                <div class="legend-item"><div class="legend-dot" style="background:#0284C7;"></div>File</div>
                <div class="legend-item"><div class="legend-dot" style="background:#8B5CF6;"></div>Class</div>
                <div class="legend-item"><div class="legend-dot" style="background:#3B82F6;"></div>Function</div>
                <div class="legend-item"><div class="legend-dot" style="background:#2563EB;"></div>Method</div>
                <div class="legend-item"><div class="legend-dot" style="background:#EC4899;"></div>Library</div>
                <div class="legend-item"><div class="legend-dot" style="background:#10B981;"></div>Technology</div>
                <div class="legend-item"><div class="legend-dot" style="background:#F59E0B;"></div>API</div>
                <div class="legend-item"><div class="legend-dot" style="background:#14B8A6;"></div>Concept</div>
            </div>
        </div>

        <script type="text/javascript">
            window.addEventListener('error', function(e) {{
                const errBox = document.getElementById("debug-error");
                if (errBox) {{
                    errBox.style.display = "block";
                    errBox.innerHTML = "<b>Visualizer Error:</b> " + e.message;
                }}
            }});

            try {{
                const nodesData = {nodes_json};
                const edgesData = {edges_json};

                if (typeof vis === 'undefined') {{
                    throw new Error("Vis.js network library failed to load. Please check network connection or static files.");
                }}

                const nodes = new vis.DataSet(nodesData);
                const edges = new vis.DataSet(edgesData);

                const container = document.getElementById('network');
                const data = {{ nodes: nodes, edges: edges }};
                
                const options = {{
                    nodes: {{
                        borderWidth: 2,
                        shadow: true
                    }},
                    edges: {{
                        width: 2,
                        smooth: {{ type: 'continuous' }},
                        shadow: true
                    }},
                    physics: {{
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: {{
                            gravitationalConstant: -40,
                            centralGravity: 0.01,
                            springLength: 100,
                            springConstant: 0.08
                        }},
                        maxVelocity: 50,
                        minVelocity: 0.1,
                        stabilization: {{ iterations: 120 }}
                    }},
                    interaction: {{
                        hover: true,
                        tooltipDelay: 150,
                        navigationButtons: true,
                        keyboard: true
                    }}
                }};

                const network = new vis.Network(container, data, options);

                network.once("stabilizationIterationsDone", function () {{
                    network.fit({{
                        animation: {{
                            duration: 500,
                            easingFunction: 'easeInOutQuad'
                        }}
                    }});
                }});

                setTimeout(function() {{
                    network.fit();
                }}, 300);

                network.on("click", function (params) {{
                    const panel = document.getElementById("panel-content");
                    if (params.nodes.length > 0) {{
                        const nodeId = params.nodes[0];
                        const node = nodes.get(nodeId);
                        const p = node.provenance || {{}};
                        
                        let html = '';
                        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
                        html += '  <span class="badge" style="background:' + (node.color.background || '#3B82F6') + ';">' + (p.type || node.label || 'Entity') + '</span>';
                        if (p.extraction_method) {{
                            html += '  <span class="method-badge">' + p.extraction_method + '</span>';
                        }}
                        html += '</div>';

                        html += '<div class="panel-title">' + (p.name || node.label || 'Unnamed') + '</div>';
                        
                        html += '<div class="field-label">Entity Type</div>';
                        html += '<div class="field-value"><b>' + (p.type || node.label || 'Entity') + '</b></div>';

                        html += '<div class="field-label">Entity Name</div>';
                        html += '<div class="field-value"><b>' + (p.name || node.label || 'Unnamed') + '</b></div>';

                        if (p.canonical_id) {{
                            html += '<div class="field-label">Canonical ID</div>';
                            html += '<div class="field-value" style="font-family:monospace; font-size:11px; color:#A78BFA; word-break:break-all;">' + p.canonical_id + '</div>';
                        }}

                        if (p.repository_name) {{
                            let shaStr = p.commit_sha ? ' <span style="font-family:monospace; color:#94A3B8; font-size:11px;">(' + p.commit_sha.substring(0, 8) + ')</span>' : '';
                            html += '<div class="field-label">Repository</div>';
                            html += '<div class="field-value">🐙 <b>' + p.repository_name + '</b>' + shaStr + '</div>';
                        }}

                        if (p.commit_sha && !p.repository_name) {{
                            html += '<div class="field-label">Commit SHA</div>';
                            html += '<div class="field-value" style="font-family:monospace; font-size:11px; color:#94A3B8;">' + p.commit_sha + '</div>';
                        }}

                        if (p.file_path) {{
                            html += '<div class="field-label">File Path</div>';
                            html += '<div class="field-value">📁 <b>' + p.file_path + '</b></div>';
                        }}

                        if (p.document_name && p.document_name !== 'N/A' && !p.file_path) {{
                            let pgStr = p.page_number ? ' (p. ' + p.page_number + ')' : '';
                            html += '<div class="field-label">Document</div>';
                            html += '<div class="field-value">📄 <b>' + p.document_name + '</b>' + pgStr + '</div>';
                        }}

                        if (p.start_line !== undefined && p.start_line !== null) {{
                            html += '<div class="field-label">Start Line</div>';
                            html += '<div class="field-value">' + p.start_line + '</div>';
                        }}

                        if (p.end_line !== undefined && p.end_line !== null) {{
                            html += '<div class="field-label">End Line</div>';
                            html += '<div class="field-value">' + p.end_line + '</div>';
                        }}

                        if (p.extraction_method) {{
                            html += '<div class="field-label">Extraction Method</div>';
                            html += '<div class="field-value"><span class="method-badge" style="margin-left:0;">' + p.extraction_method + '</span></div>';
                        }}

                        if (p.description) {{
                            html += '<div class="field-label">Description / Docstring</div>';
                            html += '<div class="field-value">' + p.description + '</div>';
                        }}

                        if (p.aliases) {{
                            html += '<div class="field-label">Aliases</div>';
                            html += '<div class="field-value">' + p.aliases + '</div>';
                        }}

                        if (p.source_snippet) {{
                            html += '<div class="field-label">Source Snippet</div>';
                            html += '<pre class="code-box"><code>' + p.source_snippet + '</code></pre>';
                        }} else if (p.source_text) {{
                            html += '<div class="field-label">Source Quote</div>';
                            html += '<div class="quote-box">"' + p.source_text + '"</div>';
                        }}

                        panel.innerHTML = html;

                    }} else if (params.edges.length > 0) {{
                        const edgeId = params.edges[0];
                        const edge = edges.get(edgeId);
                        const p = edge.provenance || {{}};
                        const fromNode = nodes.get(edge.from);
                        const toNode = nodes.get(edge.to);

                        let html = '';
                        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
                        html += '  <span class="badge" style="background:#4F46E5;">Relationship</span>';
                        if (p.extraction_method) {{
                            html += '  <span class="method-badge">' + p.extraction_method + '</span>';
                        }}
                        html += '</div>';

                        html += '<div class="panel-title">' + (fromNode ? fromNode.label : '') + ' ➔ ' + (toNode ? toNode.label : '') + '</div>';
                        html += '<div class="field-label">Relationship Type</div>';
                        html += '<div class="field-value"><b>-[:' + (p.relationship_type || edge.label || 'RELATED_TO') + ']-></b></div>';

                        if (p.repository_name) {{
                            html += '<div class="field-label">Repository</div>';
                            html += '<div class="field-value">🐙 <b>' + p.repository_name + '</b></div>';
                        }}

                        if (p.file_path) {{
                            let lineStr = p.start_line ? ' (Line ' + p.start_line + ')' : '';
                            html += '<div class="field-label">Source File</div>';
                            html += '<div class="field-value">📁 <b>' + p.file_path + '</b>' + lineStr + '</div>';
                        }}

                        if (p.document_name && p.document_name !== 'N/A' && !p.file_path) {{
                            let pgStr = p.page_number ? ' (Page ' + p.page_number + ')' : '';
                            html += '<div class="field-label">Document</div>';
                            html += '<div class="field-value">📄 <b>' + p.document_name + '</b>' + pgStr + '</div>';
                        }}

                        if (p.start_line !== undefined && p.start_line !== null) {{
                            html += '<div class="field-label">Start Line</div>';
                            html += '<div class="field-value">' + p.start_line + '</div>';
                        }}

                        if (p.end_line !== undefined && p.end_line !== null) {{
                            html += '<div class="field-label">End Line</div>';
                            html += '<div class="field-value">' + p.end_line + '</div>';
                        }}

                        if (p.source_snippet) {{
                            html += '<div class="field-label">Relationship Evidence Snippet</div>';
                            html += '<pre class="code-box"><code>' + p.source_snippet + '</code></pre>';
                        }} else if (p.source_text) {{
                            html += '<div class="field-label">Relationship Evidence Quote</div>';
                            html += '<div class="quote-box">"' + p.source_text + '"</div>';
                        }}

                        panel.innerHTML = html;
                    }}
                }});

            }} catch (err) {{
                console.error("Vis.js initialization error:", err);
                const errBox = document.getElementById("debug-error");
                if (errBox) {{
                    errBox.style.display = "block";
                    errBox.innerHTML = "<b>Graph Rendering Error:</b> " + err.message;
                }}
            }}
        </script>
    </body>
    </html>
    """
    return html_code
