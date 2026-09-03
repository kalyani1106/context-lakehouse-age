"""
Interactive Knowledge Graph HTML/JS Visualizer
==============================================
Generates high-performance Vis.js graph components for Streamlit,
with color-coded entity nodes, relationship edges, and provenance click handlers.
Includes embedded library support, robust CSS dimensions, auto-fit, and diagnostics.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List

COLOR_MAP = {
    "Technology": "#2563EB",  # Blue
    "Concept": "#059669",     # Emerald Green
    "Organization": "#D97706", # Amber
    "Person": "#DB2777",      # Pink
    "Framework": "#7C3AED",   # Purple
    "Layer": "#4F46E5",       # Indigo
    "Dataset": "#0891B2",     # Cyan
    "ResearchPaper": "#475569",# Slate
    "Algorithm": "#DC2626",   # Red
    "Project": "#EA580C"      # Orange
}

# Try to load local vis-network.min.js if present for air-gapped / offline support
LOCAL_VIS_JS_PATH = Path(__file__).parent / "static" / "vis-network.min.js"
LOCAL_VIS_JS_CONTENT = None
if LOCAL_VIS_JS_PATH.exists():
    try:
        LOCAL_VIS_JS_CONTENT = LOCAL_VIS_JS_PATH.read_text(encoding="utf-8")
    except Exception:
        LOCAL_VIS_JS_CONTENT = None

def render_visjs_graph(graph_data: Dict[str, Any], height: str = "650px", debug: bool = False) -> str:
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
        
        name = n.get("canonical_name") or n.get("name") or props.get("canonical_name") or props.get("name") or str(nid)
        etype = n.get("entity_type") or n.get("label") or props.get("entity_type") or "Concept"
        color = COLOR_MAP.get(etype, "#3B82F6")
        
        doc_name = n.get("document_name") or props.get("document_name") or "N/A"
        page_num = n.get("page_number") or props.get("page_number") or 1
        src_text = n.get("source_text") or props.get("source_text") or ""
        desc = n.get("description") or props.get("description") or ""
        aliases = n.get("aliases") or props.get("aliases") or ""
        if isinstance(aliases, list):
            aliases = ", ".join(aliases)

        tooltip = f"<b>{name}</b><br>Type: {etype}<br>Doc: {doc_name} (p.{page_num})"

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
                "type": etype,
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
        
        doc_name = e.get("document_name") or props.get("document_name") or "N/A"
        page_num = e.get("page_number") or props.get("page_number") or 1
        src_text = e.get("source_text") or props.get("source_text") or ""

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
                    "document_name": doc_name,
                    "page_number": page_num,
                    "source_text": src_text
                }
            })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    # Determine JS library tag: Use embedded inline JS if available, else use CDN with fallback
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
                background-color: #0F172A;
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
                background: #0F172A radial-gradient(#1E293B 1px, transparent 1px);
                background-size: 20px 20px;
                position: relative;
            }}
            #provenance-panel {{
                width: 340px;
                height: 100%;
                background: #1E293B;
                border-left: 1px solid #334155;
                padding: 16px;
                overflow-y: auto;
                font-size: 13px;
                flex-shrink: 0;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                background: #3B82F6;
                color: #FFFFFF;
                margin-bottom: 8px;
            }}
            .panel-title {{
                font-size: 16px;
                font-weight: 700;
                margin: 0 0 8px 0;
                color: #38BDF8;
                word-break: break-word;
            }}
            .field-label {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #94A3B8;
                margin-top: 12px;
                margin-bottom: 2px;
                font-weight: 600;
            }}
            .field-value {{
                color: #E2E8F0;
                line-height: 1.4;
                word-break: break-word;
            }}
            .quote-box {{
                background: #0F172A;
                border-left: 3px solid #38BDF8;
                padding: 8px 10px;
                border-radius: 4px;
                margin-top: 4px;
                font-style: italic;
                color: #CBD5E1;
                line-height: 1.4;
                max-height: 160px;
                overflow-y: auto;
            }}
            .legend {{
                position: absolute;
                bottom: 12px;
                left: 12px;
                background: rgba(30, 41, 59, 0.92);
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                font-size: 11px;
                pointer-events: none;
                z-index: 10;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 6px;
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
                    <h4 style="margin-top:0; color:#38BDF8;">Traceability Inspector</h4>
                    <p style="color:#94A3B8; line-height:1.5;">Click any entity node or relationship edge in the graph to view its exact document provenance, page number, and original text snippet.</p>
                    <hr style="border:0; border-top:1px solid #334155; margin:16px 0;">
                    <div style="font-size:12px; color:#64748B;">
                        <div><b>Total Vertices:</b> {len(vis_nodes)}</div>
                        <div><b>Total Edges:</b> {len(vis_edges)}</div>
                    </div>
                </div>
            </div>
            <div class="legend">
                <div class="legend-item"><div class="legend-dot" style="background:#2563EB;"></div>Technology</div>
                <div class="legend-item"><div class="legend-dot" style="background:#059669;"></div>Concept</div>
                <div class="legend-item"><div class="legend-dot" style="background:#D97706;"></div>Organization</div>
                <div class="legend-item"><div class="legend-dot" style="background:#DB2777;"></div>Person</div>
                <div class="legend-item"><div class="legend-dot" style="background:#EA580C;"></div>Project</div>
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
                        
                        panel.innerHTML = `
                            <span class="badge" style="background:${{node.color.background}};">${{p.type || 'Entity'}}</span>
                            <div class="panel-title">${{p.name || node.label}}</div>
                            
                            ${{p.description ? `<div class="field-label">Description</div><div class="field-value">${{p.description}}</div>` : ''}}
                            ${{p.aliases ? `<div class="field-label">Aliases</div><div class="field-value">${{p.aliases}}</div>` : ''}}
                            
                            <div class="field-label">Source Document</div>
                            <div class="field-value">📄 <b>${{p.document_name || 'N/A'}}</b></div>
                            
                            <div class="field-label">Page Provenance</div>
                            <div class="field-value">📍 Page <b>${{p.page_number || 'N/A'}}</b></div>
                            
                            <div class="field-label">Source Text Evidence</div>
                            <div class="quote-box">"${{p.source_text || 'No snippet available'}}..."</div>
                        `;
                    }} else if (params.edges.length > 0) {{
                        const edgeId = params.edges[0];
                        const edge = edges.get(edgeId);
                        const p = edge.provenance || {{}};
                        const fromNode = nodes.get(edge.from);
                        const toNode = nodes.get(edge.to);

                        panel.innerHTML = `
                            <span class="badge" style="background:#4F46E5;">Relationship</span>
                            <div class="panel-title">${{fromNode ? fromNode.label : ''}} ➔ ${{toNode ? toNode.label : ''}}</div>
                            <div class="field-label">Relationship Type</div>
                            <div class="field-value"><b>-[:${{p.relationship_type || edge.label}}]-></b></div>
                            
                            <div class="field-label">Source Document</div>
                            <div class="field-value">📄 <b>${{p.document_name || 'N/A'}}</b></div>
                            
                            <div class="field-label">Page Provenance</div>
                            <div class="field-value">📍 Page <b>${{p.page_number || 'N/A'}}</b></div>
                            
                            <div class="field-label">Source Text Evidence</div>
                            <div class="quote-box">"${{p.source_text || 'No snippet available'}}..."</div>
                        `;
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
