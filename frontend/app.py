"""
Streamlit UI: Multi-Modal Knowledge Graph Explorer
==================================================
Supports both:
1. Git Repository → Apache AGE Knowledge Graph ("Graphify")
2. PDF → Context Lakehouse → Apache AGE Pipeline
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json

from backend.config import settings
from backend.pipeline import PDFContextPipeline
from backend.storage.models import ProcessingStatus
from frontend.graph_visualizer import render_visjs_graph
from backend.git_graph.pipeline import GitGraphPipeline
from backend.git_graph.graph.git_graph_service import GitGraphService
from backend.git_graph.graph.graph_insights import GraphInsightsService
from backend.git_graph.graph.graph_export import GraphExportService
from backend.git_graph.graph.cypher_queries import SAMPLE_CYPHER_QUERIES
from backend.context_engine import (
    ContextEngine,
    ContextQueryRequest,
    RetrievalMode,
    QueryIntent,
)

st.set_page_config(
    page_title="Graphify & Context Lakehouse — Apache AGE",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize pipelines and services
@st.cache_resource
def get_pdf_pipeline():
    return PDFContextPipeline()

@st.cache_resource
def get_git_pipeline():
    return GitGraphPipeline()

@st.cache_resource
def get_insights_service():
    return GraphInsightsService()

@st.cache_resource
def get_export_service():
    return GraphExportService()

@st.cache_resource
def get_context_engine():
    return ContextEngine()

pdf_pipeline = get_pdf_pipeline()
git_pipeline = get_git_pipeline()
insights_service = get_insights_service()
export_service = get_export_service()
context_engine = get_context_engine()

# Custom CSS for modern styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #3B82F6 0%, #8B5CF6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .stat-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .stat-number {
        font-size: 1.8rem;
        font-weight: 700;
        color: #38BDF8;
    }
    .stat-label {
        font-size: 0.85rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .insight-card {
        background: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .badge-git {
        background: #4F46E5;
        color: #FFFFFF;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 12px;
    }
    .badge-http-get { background: #0284C7; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-http-post { background: #059669; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-http-delete { background: #DC2626; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
    .badge-http-put { background: #D97706; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://raw.githubusercontent.com/apache/age/master/img/age-logo.png", width=160)
    st.markdown("### ⚙️ System Status")
    
    try:
        health = pdf_pipeline.graph_service.age_client.test_connection()
        st.success(f"🟢 **PostgreSQL + AGE Connected**\n\nHost: `{health['host']}:{health['port']}`\n\nDatabase: `{health.get('current_graph', 'postgres')}`")
    except Exception as e:
        st.error(f"🔴 **AGE Connection Error**: {e}")

    st.markdown("---")
    st.markdown("### 🕸️ Graph Graphs")
    st.caption(f"📁 PDF Graph: `{pdf_pipeline.graph_service.graph_name}`")
    st.caption(f"🐙 Git Graph: `{git_pipeline.graph_service.graph_name}`")

    st.markdown("---")
    st.markdown("### 📚 Architecture")
    st.markdown("""
    - **Git Graphify**: AST code analysis, imports, configs & docs → Apache AGE
    - **Insights Engine**: Deterministic topology, tech stack & call graph summaries
    - **Export Engine**: JSON, CSV, ZIP, GraphML formats
    - **PDF Lakehouse**: Raw Tier, Chunks, Extraction → Apache AGE
    - **Provenance Engine**: Exact line numbers & snippets
    - **Query Layer**: openCypher via Apache AGE
    """)

# Header
st.markdown('<div class="main-header">Git Graphify & Context Lakehouse ➔ Apache AGE</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated knowledge graph generation from Git source repositories and PDF documents with deterministic AST parsing and complete provenance.</div>', unsafe_allow_html=True)

# Top Metrics Row
git_stats = git_pipeline.graph_service.get_graph_stats()
pdf_stats = pdf_pipeline.graph_service.get_graph_stats()
git_repos = git_pipeline.graph_service.list_repositories()
pdf_docs = pdf_pipeline.storage.list_documents()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{len(git_repos)}</div><div class="stat-label">Analyzed Git Repos</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{git_stats.get("total_nodes", 0)}</div><div class="stat-label">Git Graph Vertices</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{git_stats.get("total_edges", 0)}</div><div class="stat-label">Git Graph Edges</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{len(pdf_docs)}</div><div class="stat-label">Lakehouse Documents</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Navigation Tabs
tab_git, tab_pdf_ingest, tab_pdf_context, tab_context_engine, tab_graph, tab_cypher = st.tabs([
    "🐙 1. Git Graphify",
    "📄 2. Lakehouse Ingestion",
    "📊 3. Structured Context Explorer",
    "🧠 4. Context Engine",
    "🕸️ 5. Apache AGE Graph Visualizer",
    "⚡ 6. openCypher Query Console"
])

# ----------------- TAB 1: Git Graphify -----------------
with tab_git:
    st.markdown("## 🐙 Git Graphify")
    st.markdown("Transform any GitHub repository into an interactive Apache AGE knowledge graph with deterministic AST parsing and complete provenance.")

    col_url, col_branch = st.columns([3, 1])
    with col_url:
        repo_url_input = st.text_input(
            "GitHub Repository URL:",
            value=st.session_state.get("repo_url_input", "https://github.com/kalyani1106/context-lakehouse-age"),
            placeholder="https://github.com/owner/repository",
            help="Accepts https://github.com/owner/repo or a local directory path"
        )
    with col_branch:
        branch_input = st.text_input(
            "Branch:",
            value=st.session_state.get("branch_input", "main"),
            placeholder="main",
            help="Target git branch (e.g. main, master)"
        )

    with st.expander("⚙️ Advanced Options (Subdirectory, Specific Commit)", expanded=False):
        col_sub, col_com = st.columns(2)
        with col_sub:
            subdir_input = st.text_input("Subdirectory (Optional):", value="", placeholder="e.g. src/ or api/")
        with col_com:
            commit_input = st.text_input("Commit SHA / Tag (Optional):", value="", placeholder="e.g. HEAD or specific SHA")

    if st.button("🚀 Create Knowledge Graph", type="primary", use_container_width=True):
        progress_container = st.container()
        step_placeholders = {}
        
        steps = [
            "1. Cloning repository",
            "2. Scanning files",
            "3. Parsing source code",
            "4. Extracting entities and relationships",
            "5. Normalizing entities",
            "6. Ingesting into Apache AGE",
            "7. Loading graph"
        ]

        with progress_container:
            st.markdown("### 🔄 Analyzing Repository...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            step_cols = st.columns(len(steps))
            for idx, s in enumerate(steps):
                with step_cols[idx]:
                    step_placeholders[idx + 1] = st.empty()
                    step_placeholders[idx + 1].markdown(
                        f"<div style='text-align:center; color:#94A3B8; font-size:11px; padding:6px; background:#1E293B; border:1px solid #334155; border-radius:6px; min-height:54px;'><b>Step {idx+1}</b><br>{s.split('. ')[1]}</div>",
                        unsafe_allow_html=True
                    )

        def update_progress(step_num: int, message: str):
            pct = int((step_num / 7) * 100)
            progress_bar.progress(pct)
            status_text.markdown(f"**Current Stage:** `{message}`")
            for i in range(1, step_num):
                step_placeholders[i].markdown(
                    f"<div style='text-align:center; color:#34D399; font-size:11px; padding:6px; background:#064E3B; border:1px solid #10B981; border-radius:6px; min-height:54px;'><b>Step {i} ✅</b><br>{steps[i-1].split('. ')[1]}</div>",
                    unsafe_allow_html=True
                )
            step_placeholders[step_num].markdown(
                f"<div style='text-align:center; color:#38BDF8; font-size:11px; padding:6px; background:#0C4A6E; border:1px solid #38BDF8; border-radius:6px; min-height:54px;'><b>Step {step_num} ⏳</b><br>{steps[step_num-1].split('. ')[1]}</div>",
                unsafe_allow_html=True
            )
            time.sleep(0.12)

        try:
            result = git_pipeline.analyze(
                repository_url=repo_url_input.strip(),
                branch=branch_input.strip() or "main",
                commit=commit_input.strip() or None,
                subdirectory=subdir_input.strip() or None,
                cleanup=True,
                progress_callback=update_progress
            )

            # Update final step visual
            update_progress(7, "7. Loading graph")
            step_placeholders[7].markdown(
                f"<div style='text-align:center; color:#34D399; font-size:11px; padding:6px; background:#064E3B; border:1px solid #10B981; border-radius:6px; min-height:54px;'><b>Step 7 ✅</b><br>Loading graph</div>",
                unsafe_allow_html=True
            )
            progress_bar.progress(100)
            status_text.empty()

            st.session_state["last_git_result"] = result.to_dict()
            st.session_state["active_git_repo"] = result.repository_name
            st.session_state["repo_url_input"] = repo_url_input.strip()
            st.session_state["branch_input"] = branch_input.strip()

        except Exception as e:
            st.error(f"❌ Analysis failed: {str(e)}")

    # Show Completion Card & Statistics if a repository has been analyzed
    if "last_git_result" in st.session_state:
        res = st.session_state["last_git_result"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.success("### 🎉 Knowledge Graph Created Successfully")
        
        st.markdown("<div style='display:inline-block; background:#059669; color:#FFFFFF; font-weight:700; padding:6px 14px; border-radius:8px; font-size:14px; margin-bottom:12px;'>Status: COMPLETED</div>", unsafe_allow_html=True)
        
        st.markdown("#### 📊 Extraction Statistics")
        stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
        with stat_c1:
            st.markdown(f'<div class="stat-card"><div class="stat-number" style="font-size:1.2rem; word-break:break-all;">{res.get("repository_name")}</div><div class="stat-label">Repository</div></div>', unsafe_allow_html=True)
        with stat_c2:
            sha_val = str(res.get("commit_sha", ""))
            sha_disp = sha_val[:10] + "..." if len(sha_val) > 10 else (sha_val or "HEAD")
            st.markdown(f'<div class="stat-card"><div class="stat-number" style="font-size:1.2rem; font-family:monospace;" title="{sha_val}">{sha_disp}</div><div class="stat-label">Commit SHA</div></div>', unsafe_allow_html=True)
        with stat_c3:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{res.get("files_scanned", 0)}</div><div class="stat-label">Files Scanned</div></div>', unsafe_allow_html=True)
        with stat_c4:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{res.get("duration_seconds", 0)}s</div><div class="stat-label">Execution Duration</div></div>', unsafe_allow_html=True)

        stat_c5, stat_c6, stat_c7, stat_c8 = st.columns(4)
        with stat_c5:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{res.get("entities_extracted", 0)}</div><div class="stat-label">Entities Extracted</div></div>', unsafe_allow_html=True)
        with stat_c6:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{res.get("relationships_extracted", 0)}</div><div class="stat-label">Relationships Extracted</div></div>', unsafe_allow_html=True)
        with stat_c7:
            total_v = res.get("nodes_created", 0) + res.get("nodes_existing", 0)
            st.markdown(f'<div class="stat-card"><div class="stat-number">{total_v}</div><div class="stat-label">AGE Vertices (+{res.get("nodes_created",0)} new)</div></div>', unsafe_allow_html=True)
        with stat_c8:
            total_e = res.get("edges_created", 0) + res.get("edges_existing", 0)
            st.markdown(f'<div class="stat-card"><div class="stat-number">{total_e}</div><div class="stat-label">AGE Edges (+{res.get("edges_created",0)} new)</div></div>', unsafe_allow_html=True)

    # ----------------- Render Apache AGE Graph for Git Repository -----------------
    st.markdown("---")
    st.markdown("### 🕸️ Apache AGE Knowledge Graph")
    
    # Reload repository list
    active_repos = git_pipeline.graph_service.list_repositories()
    if active_repos:
        canonical_repos = [r for r in active_repos if not r.get("is_legacy_temp")]
        display_repos = canonical_repos if canonical_repos else active_repos
        repo_names = [r.get("name") for r in display_repos if r.get("name")]
        
        all_repo_names = [r.get("name") for r in active_repos if r.get("name")]
        if "active_git_repo" in st.session_state and st.session_state["active_git_repo"] not in repo_names and st.session_state["active_git_repo"] in all_repo_names:
            repo_names.insert(0, st.session_state["active_git_repo"])

        default_ix = 0
        if "active_git_repo" in st.session_state and st.session_state["active_git_repo"] in repo_names:
            default_ix = repo_names.index(st.session_state["active_git_repo"])
        
        g_col1, g_col2 = st.columns([3, 1])
        with g_col1:
            selected_git_repo = st.selectbox("Select Repository to Explore & Download:", options=repo_names, index=default_ix, key="git_tab_repo_sel")
        with g_col2:
            git_node_limit = st.slider("Max Node Limit", min_value=50, max_value=500, value=250, step=50, key="git_tab_node_lim")

        repo_graph_data = git_pipeline.graph_service.get_repository_graph(repo_name=selected_git_repo, limit=git_node_limit)
        
        v_count = len(repo_graph_data.get("nodes", []))
        e_count = len(repo_graph_data.get("edges", []))
        st.markdown(f"**Rendering {v_count} Vertices and {e_count} Edges directly from Apache AGE `{git_pipeline.graph_service.graph_name}`**")
        st.caption("💡 Click any node or relationship to inspect its exact source code provenance (Entity Type, Name, Canonical ID, Commit SHA, File Path, Lines, Extraction Method, Source Snippet).")

        html_git_graph = render_visjs_graph(repo_graph_data, height="720px")
        components.html(html_git_graph, height=720, scrolling=False)

        # ---------------------------------------------------------------------
        # FEATURE 1: 🧠 Understand Knowledge Graph (Human-Readable Insights)
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.markdown(f"### 🧠 Understand `{selected_git_repo}` Knowledge Graph")
        st.caption("Deterministic, graph-grounded architectural summary, technology stack, project tree, file rankings, class/method breakdowns, APIs, and execution flows.")

        try:
            repo_insights = insights_service.get_repository_insights(repo_name=selected_git_repo)
            
            ins_tab_overview, ins_tab_tech, ins_tab_tree, ins_tab_files, ins_tab_classes, ins_tab_apis, ins_tab_flows, ins_tab_ask = st.tabs([
                "📋 Overview & Architecture",
                "🛠️ Tech Stack & Dependencies",
                "📁 Project Tree",
                "⭐ Important Files",
                "🧩 Classes & Functions",
                "🌐 APIs & Endpoints",
                "⚡ Call & Code Flows",
                "💬 Ask the Graph"
            ])

            # 1. Overview & Architecture
            with ins_tab_overview:
                st.markdown("#### 📖 Project Overview")
                st.markdown(repo_insights.overview)

                st.markdown("---")
                st.markdown("#### 🏛️ Architecture Breakdown")
                st.markdown(repo_insights.architecture_summary)

                st.markdown("---")
                st.markdown("#### 📦 Dependency & Integration Summary")
                st.markdown(repo_insights.dependency_summary)

                st.markdown("---")
                st.markdown("#### 📊 Graph Topology Statistics")
                st_c1, st_c2 = st.columns(2)
                with st_c1:
                    st.markdown("**Vertices by Label:**")
                    if repo_insights.statistics.vertices_by_label:
                        v_df = pd.DataFrame([
                            {"Entity Label": k, "Count": v}
                            for k, v in sorted(repo_insights.statistics.vertices_by_label.items(), key=lambda x: x[1], reverse=True)
                        ])
                        st.dataframe(v_df, use_container_width=True)
                with st_c2:
                    st.markdown("**Edges by Relationship Type:**")
                    if repo_insights.statistics.edges_by_type:
                        e_df = pd.DataFrame([
                            {"Relationship Type": k, "Count": v}
                            for k, v in sorted(repo_insights.statistics.edges_by_type.items(), key=lambda x: x[1], reverse=True)
                        ])
                        st.dataframe(e_df, use_container_width=True)

            # 2. Tech Stack & Dependencies
            with ins_tab_tech:
                st.markdown("#### 🛠️ Discovered Technologies")
                if repo_insights.technologies:
                    tech_rows = []
                    for t in repo_insights.technologies:
                        prov_loc = f"{t.provenance.file_path}:L{t.provenance.start_line}" if t.provenance and t.provenance.file_path else "-"
                        tech_rows.append({
                            "Technology": t.name,
                            "Category": t.category,
                            "Usage Count": t.used_in_files_count,
                            "Provenance File": prov_loc
                        })
                    st.dataframe(pd.DataFrame(tech_rows), use_container_width=True)
                else:
                    st.info("No specific technology entities identified.")

                st.markdown("#### 📚 Libraries & Frameworks")
                if repo_insights.libraries:
                    lib_rows = []
                    for l in repo_insights.libraries:
                        prov_loc = f"{l.provenance.file_path}:L{l.provenance.start_line}" if l.provenance and l.provenance.file_path else "-"
                        lib_rows.append({
                            "Library Name": l.name,
                            "Category": l.category,
                            "Version": l.version or "Any",
                            "Imported In Files": l.used_in_files_count,
                            "Provenance Location": prov_loc
                        })
                    st.dataframe(pd.DataFrame(lib_rows), use_container_width=True)
                else:
                    st.info("No external libraries identified.")

                st.markdown("#### 🔗 Detailed Dependency Linkages")
                if repo_insights.dependencies:
                    dep_rows = []
                    for d in repo_insights.dependencies[:50]:
                        dep_rows.append({
                            "Source File": d.source_file,
                            "Relationship": d.relationship_type,
                            "Target Entity": d.target_entity,
                            "Target Type": d.target_type,
                            "Line": d.line_number or 1
                        })
                    st.dataframe(pd.DataFrame(dep_rows), use_container_width=True)

            # 3. Project Tree
            with ins_tab_tree:
                st.markdown("#### 📁 Repository Directory Hierarchy")
                st.caption("Reconstructed deterministically from `Directory` and `File` vertices in Apache AGE:")
                st.code(repo_insights.project_structure_text, language="text")

            # 4. Important Files
            with ins_tab_files:
                st.markdown("#### ⭐ Ranked Important Files")
                st.caption("Ranked by graph degree centrality, definitions count, and dependency weight:")
                if repo_insights.important_files:
                    file_rows = []
                    for f in repo_insights.important_files:
                        file_rows.append({
                            "File Path": f.file_path,
                            "Importance Score": f.importance_score,
                            "Definitions": f.definitions_count,
                            "Imports": f.imports_count,
                            "Incoming Edges": f.in_degree,
                            "Outgoing Edges": f.out_degree,
                            "Lines": f.line_count,
                            "Defined Classes": ", ".join(f.defined_classes) if f.defined_classes else "-",
                            "Defined Functions": ", ".join(f.defined_functions[:4]) if f.defined_functions else "-"
                        })
                    st.dataframe(pd.DataFrame(file_rows), use_container_width=True)
                else:
                    st.info("No file entities found.")

            # 5. Classes & Functions
            with ins_tab_classes:
                st.markdown(f"#### 🏛️ Classes Defined ({len(repo_insights.classes)})")
                if repo_insights.classes:
                    for c in repo_insights.classes:
                        with st.expander(f"📦 Class `{c.name}` ({c.file_path}:{c.line_range})", expanded=False):
                            st.markdown(f"- **Canonical ID:** `{c.canonical_id}`")
                            st.markdown(f"- **File:** `{c.file_path}` ({c.line_range})")
                            st.markdown(f"- **Methods ({len(c.methods)}):** {', '.join([f'`{m}()`' for m in c.methods]) if c.methods else 'None'}")
                            if c.source_snippet:
                                st.markdown("**Source Snippet:**")
                                st.code(c.source_snippet, language="python")
                else:
                    st.info("No class declarations found.")

                st.markdown("---")
                st.markdown(f"#### ⚡ Functions & Methods ({len(repo_insights.functions)})")
                if repo_insights.functions:
                    func_rows = []
                    for fn in repo_insights.functions[:100]:
                        func_rows.append({
                            "Function Name": fn.name,
                            "Class": fn.parent_class or "(Standalone)",
                            "File Path": fn.file_path,
                            "Line Range": fn.line_range,
                            "Async": "⚡ Yes" if fn.is_async else "No",
                            "Extraction": fn.extraction_method or "AST"
                        })
                    st.dataframe(pd.DataFrame(func_rows), use_container_width=True)

            # 6. APIs & Endpoints
            with ins_tab_apis:
                st.markdown(f"#### 🌐 Registered API Endpoints ({len(repo_insights.apis)})")
                if repo_insights.apis:
                    api_rows = []
                    for a in repo_insights.apis:
                        prov_str = f"{a.file_path}:L{a.line_number}" if a.file_path else "-"
                        api_rows.append({
                            "Method": a.http_method,
                            "Endpoint Route": a.endpoint,
                            "Handler Function": a.handler_name or "-",
                            "Source File & Line": prov_str
                        })
                    st.dataframe(pd.DataFrame(api_rows), use_container_width=True)
                else:
                    st.info("No API routes discovered in this repository.")

            # 7. Code Flows
            with ins_tab_flows:
                st.markdown(f"#### ⚡ Deterministic Execution & Usage Flows ({len(repo_insights.code_flows)})")
                if repo_insights.code_flows:
                    flow_rows = []
                    for fl in repo_insights.code_flows[:60]:
                        flow_rows.append({
                            "Step": fl.step_number,
                            "From Entity": f"{fl.from_name if hasattr(fl, 'from_name') else fl.from_entity} ({fl.from_type})",
                            "Relationship": fl.relationship_type,
                            "To Entity": f"{fl.to_name if hasattr(fl, 'to_name') else fl.to_entity} ({fl.to_type})",
                            "File": fl.file_path or "-"
                        })
                    st.dataframe(pd.DataFrame(flow_rows), use_container_width=True)
                else:
                    st.info("No call/use flows recorded.")

            # 8. Ask the Graph
            with ins_tab_ask:
                st.markdown("#### 💬 Ask the Knowledge Graph")
                st.caption("Ask architectural or dependency questions answered directly from Apache AGE graph connections:")

                question_options = {
                    "What technologies and libraries does this repository use?": "tech_stack",
                    "What are the most important files and entrypoints?": "important_files",
                    "What classes exist and what methods do they have?": "classes_methods",
                    "What APIs or endpoints are exposed?": "apis",
                    "Where is an Entity / Class / Function defined and used?": "entity_search",
                    "What does a specific file import and define?": "file_details",
                    "What are the primary code call and usage flows?": "code_flows"
                }

                sel_q_label = st.selectbox("Select Question:", options=list(question_options.keys()), key="ask_q_sel")
                sel_q_id = question_options[sel_q_label]

                param_val = ""
                if sel_q_id == "entity_search":
                    param_val = st.text_input("Enter Entity, Class, or Function Name:", placeholder="e.g. GitGraphPipeline, UserService, or AGEClient")
                elif sel_q_id == "file_details":
                    param_val = st.text_input("Enter File Name or Substring:", placeholder="e.g. app.py or routes.py")

                if st.button("🧠 Ask Graph", type="primary", key="ask_graph_btn"):
                    with st.spinner("Querying Apache AGE knowledge graph..."):
                        answer_data = insights_service.ask_question(
                            repo_name=selected_git_repo,
                            question_id=sel_q_id,
                            param=param_val
                        )
                        st.markdown(f"**Question:** {answer_data.get('question', sel_q_label)}")
                        if "answer" in answer_data:
                            st.success(answer_data["answer"])
                        if "source" in answer_data:
                            st.caption(f"🔍 Grounded Source: `{answer_data['source']}`")
                        
                        st.json(answer_data)

        except Exception as e:
            st.error(f"Error loading repository insights: {e}")

        # ---------------------------------------------------------------------
        # FEATURE 2: ⬇️ Download Knowledge Graph
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.markdown(f"### ⬇️ Download Knowledge Graph for `{selected_git_repo}`")
        st.caption("Download the complete Apache AGE knowledge graph with full line-level source code provenance in your preferred format:")

        d_col1, d_col2, d_col3, d_col4, d_col5 = st.columns(5)
        
        # Prepare exports safely in memory
        try:
            json_export_data = export_service.export_json(selected_git_repo)
            json_str = json.dumps(json_export_data, indent=2)
            zip_bytes = export_service.export_zip(selected_git_repo)
            graphml_str = export_service.export_graphml(selected_git_repo)
            jpg_bytes = export_service.export_jpg(selected_git_repo)
            clean_repo_name = selected_git_repo.replace(" ", "_").replace("/", "_")

            with d_col1:
                st.download_button(
                    label="📥 Download JSON",
                    data=json_str,
                    file_name=f"{clean_repo_name}_knowledge_graph.json",
                    mime="application/json",
                    use_container_width=True,
                    help="Complete graph JSON with metadata, vertices, edges, and line-level provenance."
                )
                st.caption(f"📄 Full JSON ({json_export_data['metadata']['total_vertices']} nodes, {json_export_data['metadata']['total_edges']} edges)")

            with d_col2:
                st.download_button(
                    label="📊 Download CSVs (ZIP)",
                    data=zip_bytes,
                    file_name=f"{clean_repo_name}_csv_bundle.zip",
                    mime="application/zip",
                    use_container_width=True,
                    help="ZIP archive containing vertices.csv and edges.csv with line-level provenance."
                )
                st.caption("📑 `vertices.csv` & `edges.csv`")

            with d_col3:
                st.download_button(
                    label="📦 Download ZIP Archive",
                    data=zip_bytes,
                    file_name=f"{clean_repo_name}_knowledge_graph.zip",
                    mime="application/zip",
                    use_container_width=True,
                    help="Complete bundle: knowledge_graph.json + vertices.csv + edges.csv + README.md"
                )
                st.caption("📦 Complete dataset archive")

            with d_col4:
                st.download_button(
                    label="🌐 Download GraphML (XML)",
                    data=graphml_str,
                    file_name=f"{clean_repo_name}_knowledge_graph.graphml",
                    mime="application/xml",
                    use_container_width=True,
                    help="Standard XML GraphML format compatible with Gephi, Cytoscape, NetworkX, yEd."
                )
                st.caption("🌐 Compatible with Gephi & Cytoscape")

            with d_col5:
                st.download_button(
                    label="🖼️ Download Knowledge Graph (JPG)",
                    data=jpg_bytes,
                    file_name=f"{clean_repo_name}_knowledge_graph.jpg",
                    mime="image/jpeg",
                    use_container_width=True,
                    help="Download the Knowledge Graph visualization as a high-resolution JPG image."
                )
                st.caption("🖼️ High-resolution JPEG image")

        except Exception as e:
            st.error(f"Error preparing graph download: {e}")

    else:
        st.info("No repositories analyzed yet. Enter a GitHub repository URL above and click '🚀 Create Knowledge Graph'.")

    # Repository Catalog Table
    st.markdown("---")
    st.markdown("### 📚 All Analyzed Repositories in Apache AGE")
    if active_repos:
        canonical_repos = [r for r in active_repos if not r.get("is_legacy_temp")]
        legacy_repos = [r for r in active_repos if r.get("is_legacy_temp")]

        if canonical_repos:
            repo_table = []
            for r in canonical_repos:
                repo_table.append({
                    "Repository Name": r.get("name") or r.get("repository_name"),
                    "Branch": r.get("branch", "main"),
                    "Commit SHA": str(r.get("commit_sha", ""))[:12] + "..." if r.get("commit_sha") else "-",
                    "Total Files": r.get("total_files", "-"),
                    "Total Lines": r.get("total_lines", "-"),
                    "URL": r.get("url") or r.get("repository_url") or "-"
                })
            st.dataframe(pd.DataFrame(repo_table), use_container_width=True)
        else:
            st.info("No canonical Git repositories analyzed yet. Enter a GitHub URL above to analyze.")

        if legacy_repos:
            with st.expander(f"🕒 Legacy / Test Repository Records ({len(legacy_repos)})", expanded=False):
                st.caption("These records represent previous local test runs or development sessions preserved non-destructively in Apache AGE:")
                legacy_table = []
                for r in legacy_repos:
                    legacy_table.append({
                        "Repository Name": r.get("name"),
                        "Branch": r.get("branch", "main"),
                        "Commit SHA": str(r.get("commit_sha", ""))[:12] + "..." if r.get("commit_sha") else "-",
                        "Path / URL": r.get("url") or r.get("repository_url") or "-",
                        "Status": "Legacy Test Record"
                    })
                st.dataframe(pd.DataFrame(legacy_table), use_container_width=True)
    else:
        st.caption("No analyzed repositories in Apache AGE catalog yet.")

# ----------------- TAB 2: Multi-Format Lakehouse Ingestion -----------------
with tab_pdf_ingest:
    st.markdown("### 📂 Upload Document / Data File to Lakehouse")
    st.caption("Select a file format, upload your document or dataset, and ingest into structured Lakehouse tiers with automatic Apache AGE property graph generation.")

    # Format definitions and metadata
    FORMAT_CONFIG = {
        "All Supported Formats": {
            "extensions": ["pdf", "docx", "txt", "md", "markdown", "csv", "tsv", "xlsx", "xls", "json", "jsonl", "ndjson", "xml", "html", "htm", "parquet", "feather", "arrow", "yaml", "yml", "sql", "rtf"],
            "description": "Universal ingestion • Ingest documents, tabular data, spreadsheets, and analytics datasets",
            "badge": "All Formats"
        },
        "PDF (.pdf)": {
            "extensions": ["pdf"],
            "description": "Document format • Page-level text, headers, and semantic entity extraction",
            "badge": "PDF"
        },
        "DOCX (.docx)": {
            "extensions": ["docx"],
            "description": "Word document • Paragraphs, headings, and structured table extraction",
            "badge": "DOCX"
        },
        "TXT (.txt)": {
            "extensions": ["txt", "text"],
            "description": "Plain text • Unstructured text and document passage extraction",
            "badge": "TXT"
        },
        "Markdown (.md)": {
            "extensions": ["md", "markdown"],
            "description": "Markdown document • Section headers, lists, and formatted text",
            "badge": "Markdown"
        },
        "CSV (.csv)": {
            "extensions": ["csv"],
            "description": "Structured tabular data • Columns, inferred data types, and record samples",
            "badge": "CSV"
        },
        "TSV (.tsv)": {
            "extensions": ["tsv"],
            "description": "Tab-separated values • Delimited columns, schema types, and records",
            "badge": "TSV"
        },
        "Excel (.xlsx, .xls)": {
            "extensions": ["xlsx", "xls"],
            "description": "Spreadsheet workbook • Multi-sheet extraction, column schemas, and rows",
            "badge": "Excel"
        },
        "JSON (.json)": {
            "extensions": ["json"],
            "description": "Structured hierarchical data • Key-value trees, nested schemas, and fields",
            "badge": "JSON"
        },
        "JSONL / NDJSON (.jsonl, .ndjson)": {
            "extensions": ["jsonl", "ndjson"],
            "description": "Newline-delimited JSON • Line-by-line record parsing and schema extraction",
            "badge": "JSONL"
        },
        "XML (.xml)": {
            "extensions": ["xml"],
            "description": "Hierarchical markup • Element tag hierarchy, attributes, and text nodes",
            "badge": "XML"
        },
        "HTML (.html, .htm)": {
            "extensions": ["html", "htm"],
            "description": "Web document • Clean DOM text, headings, and structured tables",
            "badge": "HTML"
        },
        "Parquet (.parquet)": {
            "extensions": ["parquet", "pq"],
            "description": "Columnar analytics dataset • PyArrow schema, data types, and records",
            "badge": "Parquet"
        },
        "Feather (.feather)": {
            "extensions": ["feather", "arrow"],
            "description": "Arrow IPC binary table • Column definitions and record batches",
            "badge": "Feather"
        },
        "YAML (.yaml, .yml)": {
            "extensions": ["yaml", "yml"],
            "description": "Configuration markup • Mappings, keys, and structured hierarchy",
            "badge": "YAML"
        },
        "SQL (.sql)": {
            "extensions": ["sql"],
            "description": "SQL queries and DDL • Table definitions, statements, and schemas",
            "badge": "SQL"
        },
        "RTF (.rtf)": {
            "extensions": ["rtf"],
            "description": "Rich text format • Formatted text extraction and document passages",
            "badge": "RTF"
        }
    }

    col_fmt, col_desc = st.columns([1, 2])
    with col_fmt:
        selected_fmt = st.selectbox(
            "Select File Type:",
            options=list(FORMAT_CONFIG.keys()),
            index=0,
            key="lakehouse_format_selector",
            help="Filter upload validation to specific format or select 'All Supported Formats' for universal ingestion."
        )
    with col_desc:
        current_cfg = FORMAT_CONFIG[selected_fmt]
        st.markdown(f"""
        <div class="insight-card" style="margin-top: 24px; padding: 10px 16px;">
            <span style="color: #38BDF8; font-weight: 600;">{current_cfg['badge']}</span> • <span style="color: #94A3B8; font-size: 13px;">{current_cfg['description']}</span>
        </div>
        """, unsafe_allow_html=True)

    allowed_types = current_cfg["extensions"]
    uploaded_file = st.file_uploader(
        f"Select or drag & drop a {selected_fmt} file (Max: 200 MB)",
        type=allowed_types,
        key="lakehouse_file_uploader",
        help=f"Accepts: {', '.join(['.' + ext for ext in allowed_types])}"
    )

    st.caption("Supported formats: **PDF • DOCX • TXT • MD • CSV • TSV • XLSX • XLS • JSON • JSONL • XML • HTML • Parquet • Feather • YAML • SQL • RTF** • Maximum file size: **200 MB**")

    if uploaded_file is not None:
        file_ext = Path(uploaded_file.name).suffix.lower().lstrip(".")
        if allowed_types and file_ext not in allowed_types:
            st.warning(f"⚠️ **File type mismatch**: You selected **{selected_fmt}** but uploaded a `.{file_ext}` file. Please select the matching format in the dropdown or upload a valid file.")
        else:
            file_bytes = uploaded_file.getvalue()
            file_size_kb = round(len(file_bytes) / 1024, 1)
            file_size_mb = round(file_size_kb / 1024, 2)
            size_display = f"{file_size_mb} MB ({file_size_kb:,} KB)" if file_size_mb >= 1.0 else f"{file_size_kb:,} KB"

            st.markdown("---")
            st.markdown("#### 📄 File Ready for Ingestion")
            c_info1, c_info2, c_info3 = st.columns(3)
            with c_info1:
                st.markdown(f"**Filename:** `{uploaded_file.name}`")
            with c_info2:
                st.markdown(f"**Type:** `{current_cfg['badge']}` (`.{file_ext}`)")
            with c_info3:
                st.markdown(f"**Size:** `{size_display}`")

            if st.button("🚀 Upload & Ingest into Lakehouse", type="primary", use_container_width=True):
                with st.spinner("Calculating SHA-256 and registering in Lakehouse tiers..."):
                    try:
                        meta = pdf_pipeline.upload_document(filename=uploaded_file.name, file_bytes=file_bytes)
                        st.success(f"✅ Document registered in Lakehouse with ID: `{meta.document_id}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Upload failed: {e}")

    st.markdown("---")
    st.subheader("Lakehouse Document Catalog")

    if not pdf_docs:
        st.info("No documents uploaded yet.")
    else:
        doc_table = []
        for d in pdf_docs:
            fname = d.document_name.lower()
            custom = d.custom_metadata or {}
            
            if "sheet_count" in custom:
                metric_str = f"{custom['sheet_count']} sheets"
            elif "record_count" in custom:
                metric_str = f"{custom['record_count']} records"
            elif "element_count" in custom:
                metric_str = f"{custom['element_count']} elements"
            elif fname.endswith(('.xlsx', '.xls')):
                metric_str = f"{d.total_pages} sheets" if d.total_pages is not None else "-"
            elif fname.endswith(('.csv', '.tsv', '.parquet', '.feather', '.jsonl', '.ndjson')):
                metric_str = f"{d.total_pages} records" if d.total_pages is not None else "-"
            elif fname.endswith(('.json',)):
                metric_str = f"{d.total_pages} items" if d.total_pages is not None else "-"
            elif fname.endswith(('.xml',)):
                metric_str = f"{d.total_pages} elements" if d.total_pages is not None else "-"
            else:
                metric_str = f"{d.total_pages} pages" if d.total_pages is not None else "-"

            doc_table.append({
                "Document ID": d.document_id,
                "Filename": d.document_name,
                "File Type": d.file_type or "application/octet-stream",
                "Size (KB)": round(d.file_size_bytes / 1024, 1),
                "Pages / Sheets / Records": metric_str,
                "Entities": d.total_entities if d.total_entities is not None else "-",
                "Relations": d.total_relationships if d.total_relationships is not None else "-",
                "Status": d.status.value
            })
        st.dataframe(pd.DataFrame(doc_table), use_container_width=True)

        st.markdown("### Process Document Through Pipeline")
        doc_options = {f"{d.document_name} ({d.document_id}) [{d.status.value}]": d.document_id for d in pdf_docs}
        selected_label = st.selectbox("Select document to process:", options=list(doc_options.keys()))
        selected_doc_id = doc_options[selected_label]
        
        if st.button("🚀 Run Lakehouse Ingestion Pipeline", type="primary"):
            with st.spinner("Processing document through multi-format pipeline..."):
                try:
                    res = pdf_pipeline.process_document(selected_doc_id)
                    st.success(f"✅ Ingestion Complete! Extracted {res['total_entities']} entities & {res['total_relationships']} relations into Apache AGE.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Processing failed: {e}")

# ----------------- TAB 3: Structured Context Explorer -----------------
with tab_pdf_context:
    st.subheader("Structured Context & Provenance")
    if not pdf_docs:
        st.info("No documents in Lakehouse.")
    else:
        pdf_dict = {f"{d.document_name} ({d.document_id})": d.document_id for d in pdf_docs}
        active_doc_label = st.selectbox("Select document:", options=list(pdf_dict.keys()), key="pdf_context_doc_sel")
        active_doc_id = pdf_dict[active_doc_label]
        
        context_data = pdf_pipeline.storage.get_context(active_doc_id)
        if not context_data:
            st.warning("No structured context generated yet for this document. Process it in Tab 2.")
        else:
            st.json(context_data)

# ----------------- TAB 4: Context Engine -----------------
with tab_context_engine:
    st.markdown("## 🧠 Intelligent Context Engine")
    st.markdown("Query the hybrid intelligence layer bridging **Apache AGE Knowledge Graphs** and **Context Lakehouse Storage**. Deterministically analyzes queries, traverses graph topology, scores passages with BM25, ranks with multi-factor weighting, and generates token-budgeted context with line-level provenance.")

    # Target Scope Selection
    scope_col1, scope_col2 = st.columns([1, 2])
    with scope_col1:
        target_scope_type = st.selectbox(
            "Target Scope:",
            options=["Global (All Repositories & Documents)", "Specific Git Repository", "Specific Lakehouse Document"],
            key="ce_scope_type"
        )
    
    scoped_repo_name = None
    scoped_doc_name = None
    scoped_doc_id = None

    with scope_col2:
        if target_scope_type == "Specific Git Repository":
            repo_names = [r.get("name") for r in git_repos if r.get("name")]
            if repo_names:
                scoped_repo_name = st.selectbox("Select Target Repository:", options=repo_names, key="ce_repo_sel")
            else:
                st.info("No Git repositories analyzed yet. (Analyze in Tab 1)")
        elif target_scope_type == "Specific Lakehouse Document":
            if pdf_docs:
                doc_map = {f"{d.document_name} ({d.document_id})": d for d in pdf_docs}
                sel_doc_label = st.selectbox("Select Target Document:", options=list(doc_map.keys()), key="ce_doc_sel")
                sel_doc_obj = doc_map[sel_doc_label]
                scoped_doc_name = sel_doc_obj.document_name
                scoped_doc_id = sel_doc_obj.document_id
            else:
                st.info("No documents in Lakehouse yet. (Upload in Tab 2)")

    # Quick Example Prompts
    st.markdown("**💡 Quick Query Templates:**")
    q_col1, q_col2, q_col3, q_col4, q_col5 = st.columns(5)
    
    default_prompt = "How does authentication and token verification work in this codebase?"
    if "ce_query_input" not in st.session_state:
        st.session_state["ce_query_input"] = default_prompt

    if q_col1.button("🏗️ Architecture", use_container_width=True):
        st.session_state["ce_query_input"] = "What is the high-level architecture, main components, and layer design?"
        st.rerun()
    if q_col2.button("🔐 Authentication", use_container_width=True):
        st.session_state["ce_query_input"] = "How does authentication, login, JWT tokens, and user verification work?"
        st.rerun()
    if q_col3.button("🌐 API Endpoints", use_container_width=True):
        st.session_state["ce_query_input"] = "What are the REST API endpoints, FastAPI routes, and request handlers?"
        st.rerun()
    if q_col4.button("📦 Dependencies", use_container_width=True):
        st.session_state["ce_query_input"] = "What classes inherit from BaseStorage and what modules import AgeClient?"
        st.rerun()
    if q_col5.button("📊 Schemas & Flow", use_container_width=True):
        st.session_state["ce_query_input"] = "Describe the data flow from ingestion to chunking and Apache AGE graph storage."
        st.rerun()

    # Query Input
    query_text = st.text_area(
        "Natural Language Query / Prompt for Context Engine:",
        value=st.session_state.get("ce_query_input", default_prompt),
        height=90,
        key="ce_active_query_text"
    )

    # Retrieval & Ranking Parameters Expander
    with st.expander("⚙️ Advanced Retrieval & Ranking Parameters", expanded=False):
        c_mode, c_topk, c_tokens, c_depth = st.columns(4)
        with c_mode:
            mode_choice = st.selectbox(
                "Retrieval Mode:",
                options=["hybrid", "graph", "semantic"],
                index=0,
                help="Hybrid combines graph topology + lexical search. Graph uses only Apache AGE. Semantic uses only Lakehouse chunks."
            )
        with c_topk:
            top_k_val = st.slider("Top K Results:", min_value=3, max_value=30, value=10, step=1)
        with c_tokens:
            max_tokens_val = st.slider("Max Context Tokens:", min_value=500, max_value=12000, value=4000, step=500)
        with c_depth:
            depth_val = st.slider("Graph Traversal Depth:", min_value=1, max_value=3, value=2, step=1)

        st.markdown("**Scoring Weights:**")
        w_col1, w_col2, w_col3 = st.columns(3)
        with w_col1:
            g_weight = st.slider("Graph Connectivity Weight:", 0.0, 1.0, 0.5, 0.05)
        with w_col2:
            s_weight = st.slider("Semantic / BM25 Weight:", 0.0, 1.0, 0.3, 0.05)
        with w_col3:
            p_weight = st.slider("Provenance Completeness Weight:", 0.0, 1.0, 0.2, 0.05)

    # Execution Button
    if st.button("🚀 Retrieve & Assemble Context", type="primary", use_container_width=True):
        if not query_text.strip():
            st.warning("Please enter a query.")
        else:
            with st.spinner("Analyzing query, traversing Apache AGE graphs & scoring Lakehouse passages..."):
                try:
                    req = ContextQueryRequest(
                        query=query_text.strip(),
                        repo_name=scoped_repo_name,
                        doc_name=scoped_doc_name,
                        document_id=scoped_doc_id,
                        mode=RetrievalMode(mode_choice),
                        top_k=top_k_val,
                        max_context_tokens=max_tokens_val,
                        graph_weight=g_weight,
                        semantic_weight=s_weight,
                        provenance_weight=p_weight,
                        traversal_depth=depth_val,
                    )
                    resp = context_engine.query_context(req)
                    st.session_state["ce_last_response"] = resp
                except Exception as e:
                    st.error(f"Context retrieval error: {e}")

    # Display results if available
    if "ce_last_response" in st.session_state:
        resp = st.session_state["ce_last_response"]
        st.markdown("---")
        
        # 1. Query Analysis Banner
        qa = resp.query_analysis
        st.markdown("### 🎯 Query Understanding & Intent")
        qa_col1, qa_col2, qa_col3 = st.columns([1, 2, 2])
        with qa_col1:
            st.markdown(f"**Intent**: `{qa.intent.value}`")
        with qa_col2:
            entities_str = ", ".join([f"`{e}`" for e in qa.extracted_entities]) if qa.extracted_entities else "*None detected*"
            st.markdown(f"**Entities**: {entities_str}")
        with qa_col3:
            targets_str = ", ".join([f"`{t}`" for t in qa.detected_targets]) if qa.detected_targets else "*None detected*"
            st.markdown(f"**Target Symbols/Files**: {targets_str}")

        # 2. Retrieval Metrics KPI
        st.markdown("<br>", unsafe_allow_html=True)
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        with m_col1:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{resp.stats.retrieval_time_ms:.1f} ms</div><div class="stat-label">Retrieval Latency</div></div>', unsafe_allow_html=True)
        with m_col2:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{resp.stats.nodes_retrieved + resp.stats.edges_retrieved}</div><div class="stat-label">Graph Items (Nodes+Edges)</div></div>', unsafe_allow_html=True)
        with m_col3:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{resp.stats.chunks_retrieved}</div><div class="stat-label">Lakehouse Chunks</div></div>', unsafe_allow_html=True)
        with m_col4:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{resp.stats.total_tokens_estimated}</div><div class="stat-label">Assembled Tokens</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. Assembled Context Markdown Block
        st.markdown("### 📋 Assembled Context Payload (LLM Ready)")
        st.caption(f"Token budget: {resp.stats.total_tokens_estimated} / {resp.query_analysis.filters.get('max_tokens', 4000)} estimated tokens.")
        st.code(resp.assembled_context, language="markdown")

        # 4. Interactive Knowledge Subgraph Visualization
        from backend.context_engine.models import ContextType
        graph_nodes = [item for item in resp.items if item.type == ContextType.ENTITY]
        graph_edges = [item for item in resp.items if item.type == ContextType.RELATIONSHIP]

        if graph_nodes or graph_edges:
            with st.expander(f"🕸️ Retrieved Knowledge Subgraph ({len(graph_nodes)} Entities, {len(graph_edges)} Relations)", expanded=True):
                sub_vis_nodes = []
                sub_vis_edges = []
                node_id_map = {}
                
                for idx, gn in enumerate(graph_nodes):
                    nid = gn.metadata.get("node_id") or f"sub_node_{idx}"
                    label = gn.metadata.get("label", "Concept")
                    name = gn.title.split(": ")[-1].split(" [")[0]
                    node_id_map[gn.id] = nid
                    node_id_map[name] = nid
                    sub_vis_nodes.append({
                        "id": nid,
                        "label": label,
                        "name": name,
                        "canonical_id": gn.id,
                        "entity_type": label,
                        "file_path": gn.provenance.file_path if gn.provenance else "",
                        "start_line": gn.provenance.start_line if gn.provenance else 1,
                        "source_snippet": gn.provenance.snippet if gn.provenance else "",
                        "properties": gn.metadata.get("properties", {})
                    })

                for idx, ge in enumerate(graph_edges):
                    src_name = ge.metadata.get("source", "")
                    tgt_name = ge.metadata.get("target", "")
                    rel_type = ge.metadata.get("relationship_type", "RELATED_TO")
                    
                    src_id = node_id_map.get(src_name) or f"src_{idx}"
                    tgt_id = node_id_map.get(tgt_name) or f"tgt_{idx}"
                    
                    if src_id == f"src_{idx}":
                        sub_vis_nodes.append({"id": src_id, "label": "Concept", "name": src_name, "entity_type": "Concept"})
                        node_id_map[src_name] = src_id
                    if tgt_id == f"tgt_{idx}":
                        sub_vis_nodes.append({"id": tgt_id, "label": "Concept", "name": tgt_name, "entity_type": "Concept"})
                        node_id_map[tgt_name] = tgt_id

                    sub_vis_edges.append({
                        "id": f"sub_edge_{idx}",
                        "label": rel_type,
                        "relationship_type": rel_type,
                        "source": src_id,
                        "target": tgt_id,
                        "file_path": ge.provenance.file_path if ge.provenance else "",
                        "start_line": ge.provenance.start_line if ge.provenance else 1,
                        "source_snippet": ge.provenance.snippet if ge.provenance else "",
                    })

                if sub_vis_nodes:
                    sub_graph_data = {"nodes": sub_vis_nodes, "edges": sub_vis_edges}
                    sub_html = render_visjs_graph(sub_graph_data, height="450px")
                    components.html(sub_html, height=450, scrolling=False)

        # 5. Ranked Context Items Inspector
        with st.expander(f"📑 Ranked Context Items Breakdown ({len(resp.items)} items)", expanded=False):
            for idx, item in enumerate(resp.items, 1):
                st.markdown(f"**{idx}. [{item.type.value}] {item.title}** — *Composite Score: `{item.score:.3f}` (Graph: `{item.graph_score:.2f}`, Semantic: `{item.semantic_score:.2f}`, Provenance: `{item.provenance_score:.2f}`)*")
                st.markdown(item.content)
                if item.provenance:
                    prov = item.provenance
                    if prov.source_type == "git":
                        loc_str = f"`{prov.file_path}:L{prov.start_line}-L{prov.end_line}`" if prov.start_line else f"`{prov.file_path}`"
                        st.caption(f"📍 Provenance: Repository `{prov.repo_name}` | File {loc_str} | Commit `[{prov.commit_hash[:7] if prov.commit_hash else 'HEAD'}]`")
                    else:
                        st.caption(f"📍 Provenance: Document `{prov.document_name or prov.document_id}` | Page {prov.page_number} | Chunk `{prov.chunk_id}`")
                st.markdown("---")

        # 6. Citations & Provenance Ledger
        with st.expander(f"🏷️ Citation & Provenance Ledger ({len(resp.citations)} Sources)", expanded=False):
            if resp.citations:
                cit_data = []
                for c in resp.citations:
                    cit_data.append({
                        "Type": c.source_type.upper(),
                        "Target / File / Document": c.file_path or c.document_name or c.document_id or "-",
                        "Line / Page": f"L{c.start_line}-L{c.end_line}" if c.start_line else (f"Page {c.page_number}" if c.page_number else "-"),
                        "Repository / Doc ID": c.repo_name or c.document_id or "-",
                        "Commit / Chunk": c.commit_hash[:7] if c.commit_hash else (c.chunk_id or "-"),
                    })
                st.dataframe(pd.DataFrame(cit_data), use_container_width=True)
            else:
                st.info("No explicit citations found.")

        # 7. Raw JSON Response Expander
        with st.expander("🔍 Raw JSON Response (API Format)", expanded=False):
            st.json(resp.model_dump())

# ----------------- TAB 5: Apache AGE Graph Visualizer -----------------
with tab_graph:
    st.subheader("🕸️ Apache AGE Knowledge Graph Visualizer")
    
    col_scope, col_limit = st.columns([3, 1])
    with col_scope:
        graph_target = st.radio(
            "Select Graph Source:",
            options=["Git Repository Knowledge Graph", "Document / Dataset Subgraph", "Full Lakehouse Knowledge Graph"],
            horizontal=True
        )
    with col_limit:
        node_limit = st.slider("Max Node Limit", min_value=50, max_value=500, value=250, step=50)

    if graph_target == "Git Repository Knowledge Graph":
        if git_repos:
            repo_names = [r.get("name") for r in git_repos if r.get("name")]
            default_ix = 0
            if "active_git_repo" in st.session_state and st.session_state["active_git_repo"] in repo_names:
                default_ix = repo_names.index(st.session_state["active_git_repo"])
            
            selected_repo = st.selectbox("Select Repository:", options=repo_names, index=default_ix)
            graph_data = git_pipeline.graph_service.get_repository_graph(repo_name=selected_repo, limit=node_limit)
        else:
            st.info("No Git repositories analyzed yet. Analyze a repository in Tab 1.")
            graph_data = {"nodes": [], "edges": []}
    elif graph_target == "Document / Dataset Subgraph" and pdf_docs:
        sub_doc_options = {f"{d.document_name} ({d.document_id})": d.document_id for d in pdf_docs if d.status == ProcessingStatus.COMPLETED}
        if sub_doc_options:
            selected_sub_label = st.selectbox("Select Document / Dataset Subgraph:", options=list(sub_doc_options.keys()))
            graph_data = pdf_pipeline.graph_service.get_document_subgraph(sub_doc_options[selected_sub_label])
        else:
            st.info("No completed documents in Lakehouse yet.")
            graph_data = {"nodes": [], "edges": []}
    else:
        graph_data = pdf_pipeline.graph_service.get_full_graph(limit=node_limit)

    nodes_count = len(graph_data.get("nodes", []))
    edges_count = len(graph_data.get("edges", []))
    st.markdown(f"**Rendering {nodes_count} Vertices and {edges_count} Edges directly from Apache AGE**")

    # Render Vis.js HTML graph component with Code & Provenance Inspector
    html_graph = render_visjs_graph(graph_data, height="720px")
    components.html(html_graph, height=720, scrolling=False)

# ----------------- TAB 5: openCypher Query Console -----------------
with tab_cypher:
    st.subheader("⚡ openCypher Query Console")
    st.markdown("Execute openCypher graph queries directly against PostgreSQL with the Apache AGE extension.")

    col_target_g, col_sample = st.columns([1, 2])
    with col_target_g:
        target_graph_choice = st.selectbox(
            "Target AGE Graph:",
            options=[git_pipeline.graph_service.graph_name, pdf_pipeline.graph_service.graph_name]
        )
    with col_sample:
        selected_sample_key = st.selectbox("Load Sample Cypher Query:", options=list(SAMPLE_CYPHER_QUERIES.keys()))

    query_template = SAMPLE_CYPHER_QUERIES[selected_sample_key]
    cypher_input = st.text_area("Cypher Query", value=query_template, height=130)

    if st.button("▶️ Execute Cypher Query", type="primary"):
        with st.spinner("Executing query in Apache AGE..."):
            try:
                # Infer return columns
                if "RETURN a, r, b" in cypher_input or "RETURN p, r, c" in cypher_input or "RETURN f, r, c" in cypher_input or "RETURN f, r, l" in cypher_input or "RETURN api, r, fn" in cypher_input or "RETURN repo, r, tech" in cypher_input:
                    cols = ["a", "r", "b"]
                elif "RETURN f, c" in cypher_input:
                    cols = ["f", "c"]
                elif "RETURN f, l" in cypher_input:
                    cols = ["f", "l"]
                elif "RETURN n" in cypher_input or "RETURN f" in cypher_input:
                    cols = ["result"]
                else:
                    cols = ["result"]

                results = git_pipeline.graph_service.age_client.execute_cypher(
                    cypher_query=cypher_input,
                    columns=cols,
                    graph_name=target_graph_choice
                )
                
                st.success(f"Query returned **{len(results)}** rows from Apache AGE `{target_graph_choice}`.")
                
                if results:
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    with st.expander("Raw agtype JSON Results"):
                        st.json(results)
                else:
                    st.info("Query returned 0 matching rows.")

            except Exception as e:
                st.error(f"Cypher Error: {str(e)}")
