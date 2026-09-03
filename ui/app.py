"""
Streamlit UI: PDF → Context Lakehouse → Apache AGE Knowledge Graph
==================================================================
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json

from config import settings
from pipeline import PDFContextPipeline
from storage.models import ProcessingStatus
from ui.graph_visualizer import render_visjs_graph

st.set_page_config(
    page_title="PDF → Context Lakehouse → Apache AGE",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize pipeline
@st.cache_resource
def get_pipeline():
    return PDFContextPipeline()

pipeline = get_pipeline()

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
    .engine-badge-llm {
        background: #059669;
        color: #FFFFFF;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 12px;
    }
    .engine-badge-heuristic {
        background: #475569;
        color: #F8FAFC;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://raw.githubusercontent.com/apache/age/master/img/age-logo.png", width=160)
    st.markdown("### ⚙️ System Status")
    
    try:
        health = pipeline.graph_service.age_client.test_connection()
        st.success(f"🟢 **PostgreSQL + AGE Connected**\n\nHost: `{health['host']}:{health['port']}`\n\nGraph: `{health['current_graph']}`")
    except Exception as e:
        st.error(f"🔴 **AGE Connection Error**: {e}")

    st.markdown("---")
    st.markdown("### 🤖 Extraction Engine")
    
    has_openai = bool(settings.OPENAI_API_KEY)
    has_gemini = bool(settings.GEMINI_API_KEY)
    
    st.caption(f"🔑 OpenAI Key: {'Configured' if has_openai else 'Not Set'}")
    st.caption(f"🔑 Gemini Key: {'Configured' if has_gemini else 'Not Set'}")

    provider_choice = st.selectbox(
        "Extraction Mode",
        options=["auto", "heuristic", "openai", "gemini"],
        format_func=lambda x: {
            "auto": f"Auto ({'LLM' if has_openai else 'Heuristic NLP (Offline)'})",
            "heuristic": "Deterministic Heuristic NLP (Offline)",
            "openai": "OpenAI GPT-4o-mini",
            "gemini": "Google Gemini"
        }[x],
        index=0
    )

    st.markdown("---")
    st.markdown("### 📚 Lakehouse Architecture")
    st.markdown("""
    - **Raw Tier**: PDF binaries (SHA-256 deduplicated)
    - **Metadata Tier**: Document catalog
    - **Pages Tier**: Page text Parquet/JSON
    - **Chunks Tier**: Passage spans
    - **Context Tier**: Structured Entities/Relations
    - **Graph Tier**: Apache AGE Knowledge Graph
    """)

# Header
st.markdown('<div class="main-header">PDF → Context Lakehouse → Apache AGE Knowledge Graph</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated ingestion from unstructured PDFs into structured Lakehouse context and Apache AGE property graphs with full provenance.</div>', unsafe_allow_html=True)

# Top Metrics Row
stats = pipeline.graph_service.get_graph_stats()
docs = pipeline.storage.list_documents()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{len(docs)}</div><div class="stat-label">Lakehouse Documents</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{stats.get("total_nodes", 0)}</div><div class="stat-label">AGE Graph Vertices</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="stat-card"><div class="stat-number">{stats.get("total_edges", 0)}</div><div class="stat-label">AGE Graph Edges</div></div>', unsafe_allow_html=True)
with col4:
    completed_docs = sum(1 for d in docs if d.status == ProcessingStatus.COMPLETED)
    st.markdown(f'<div class="stat-card"><div class="stat-number">{completed_docs}</div><div class="stat-label">Synced to Graph</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📄 1. Lakehouse Document Ingestion",
    "🧠 2. Structured Context & Provenance",
    "🕸️ 3. Apache AGE Graph Visualizer",
    "⚡ 4. Cypher Query Console"
])

# ----------------- TAB 1: Lakehouse Ingestion -----------------
with tab1:
    st.subheader("Upload PDF Document to Lakehouse")
    
    uploaded_file = st.file_uploader("Select a research paper or document PDF", type=["pdf"])
    if uploaded_file is not None:
        if st.button("📤 Upload & Ingest into Lakehouse", type="primary"):
            file_bytes = uploaded_file.read()
            with st.spinner("Calculating SHA-256 and checking Lakehouse catalog..."):
                meta = pipeline.upload_pdf(filename=uploaded_file.name, file_bytes=file_bytes)
                
                # Check if this was a duplicate
                all_matching = [d for d in pipeline.storage.list_documents() if getattr(d, 'sha256', None) == meta.sha256]
                if len(all_matching) > 0 and all_matching[0].document_id == meta.document_id and meta.status == ProcessingStatus.COMPLETED:
                    st.info(f"ℹ️ **Duplicate PDF detected!** This exact PDF already exists in Lakehouse as `{meta.document_id}` (`{meta.document_name}`). Re-using existing record.")
                else:
                    st.success(f"✅ Document registered in Lakehouse with ID: `{meta.document_id}` (SHA-256: `{meta.sha256[:16]}...`)")
                st.rerun()

    st.markdown("---")
    st.subheader("Lakehouse Document Catalog")

    if not docs:
        st.info("No documents uploaded yet. Upload a PDF above or run a test from the repository.")
    else:
        doc_table = []
        for d in docs:
            doc_table.append({
                "Document ID": d.document_id,
                "Filename": d.document_name,
                "Size (KB)": round(d.file_size_bytes / 1024, 1),
                "SHA-256": getattr(d, 'sha256', 'legacy')[:12] + "...",
                "Pages": d.total_pages if d.total_pages is not None else "-",
                "Chunks": d.total_chunks if d.total_chunks is not None else "-",
                "Entities": d.total_entities if d.total_entities is not None else "-",
                "Relations": d.total_relationships if d.total_relationships is not None else "-",
                "Time (s)": f"{d.processing_time_sec}s" if d.processing_time_sec is not None else "-",
                "Engine": d.extraction_method.value if d.extraction_method else "-",
                "Status": d.status.value,
                "Uploaded At": d.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        st.dataframe(pd.DataFrame(doc_table), use_container_width=True)

        st.markdown("### Process Document Through Pipeline")
        doc_options = {f"{d.document_name} ({d.document_id}) [{d.status.value}]": d.document_id for d in docs}
        selected_label = st.selectbox("Select document to process:", options=list(doc_options.keys()))
        selected_doc_id = doc_options[selected_label]
        
        col_btn, col_chk = st.columns([1, 2])
        with col_chk:
            force_reprocess = st.checkbox("Force Reprocess (re-extract and update graph even if already COMPLETED)", value=False)

        with col_btn:
            if st.button("🚀 Run Pipeline", type="primary"):
                progress_bar = st.progress(0, text="Starting pipeline execution...")
                
                try:
                    progress_bar.progress(20, text="1/5 Extracting page-level text...")
                    result = pipeline.process_document(
                        selected_doc_id,
                        force_provider=provider_choice,
                        reprocess=force_reprocess
                    )
                    
                    if result.get("already_processed"):
                        progress_bar.progress(100, text="Already processed!")
                        st.info(f"⚡ Document **{result['document_name']}** was already completed. Loaded existing Lakehouse context ({result['total_entities']} entities, {result['total_relationships']} relationships) without duplicating graph vertices.")
                    else:
                        progress_bar.progress(50, text="2/5 Chunking passages with provenance...")
                        progress_bar.progress(70, text="3/5 Extracting entities and relationships...")
                        progress_bar.progress(90, text="4/5 Ingesting vertices and edges into Apache AGE...")
                        progress_bar.progress(100, text="5/5 Pipeline completed successfully!")
                        
                        st.success(f"✅ Pipeline complete for **{result['document_name']}** in **{result['processing_time_sec']}s**! Extracted **{result['total_entities']}** entities, **{result['total_relationships']}** relations.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Pipeline error: {str(e)}")

# ----------------- TAB 2: Structured Context Explorer -----------------
with tab2:
    st.subheader("Structured Context & Provenance Inspector")
    if not docs:
        st.info("No documents in Lakehouse.")
    else:
        doc_dict = {f"{d.document_name} ({d.document_id})": d.document_id for d in docs}
        active_doc_label = st.selectbox("Select document:", options=list(doc_dict.keys()), key="context_doc_sel")
        active_doc_id = doc_dict[active_doc_label]
        
        meta = pipeline.storage.get_metadata(active_doc_id)
        context_data = pipeline.storage.get_context(active_doc_id)
        pages_data = pipeline.storage.get_extracted_pages(active_doc_id)
        chunks_data = pipeline.storage.get_chunks(active_doc_id)

        if not context_data:
            st.warning(f"No structured context generated yet for this document. Please process it in Tab 1.")
        else:
            sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5 = st.tabs([
                "📋 Quality & Summary",
                "🏷️ Extracted Entities",
                "🔗 Extracted Relationships",
                "📦 Passage Chunks",
                "🔍 Raw Context JSON"
            ])

            with sub_tab1:
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                engine_str = context_data.get('extraction_method', 'HEURISTIC_NLP')
                col_m1.metric("Extraction Engine", engine_str)
                col_m2.metric("Processing Time", f"{meta.processing_time_sec}s" if meta and meta.processing_time_sec else "-")
                col_m3.metric("Entities", len(context_data.get("entities", [])))
                col_m4.metric("Relationships", len(context_data.get("relationships", [])))

                st.markdown(f"**Document Summary:**")
                st.info(context_data.get("summary", "No summary available."))

                st.markdown(f"**Document Hash (SHA-256):** `{getattr(meta, 'sha256', 'N/A')}`")

            with sub_tab2:
                entities = context_data.get("entities", [])
                st.markdown(f"**{len(entities)} Canonical Entities Extracted**")
                
                ent_rows = []
                for e in entities:
                    src = e.get("source", {})
                    ent_rows.append({
                        "Canonical Name": e.get("canonical_name"),
                        "Entity Type": e.get("type"),
                        "Confidence": e.get("confidence", 1.0),
                        "Aliases": ", ".join(e.get("aliases", [])),
                        "Source Page": f"Page {src.get('page_number', 'N/A')}",
                        "Source Snippet": src.get("source_text", "")[:100] + "..."
                    })
                st.dataframe(pd.DataFrame(ent_rows), use_container_width=True)

            with sub_tab3:
                relationships = context_data.get("relationships", [])
                st.markdown(f"**{len(relationships)} Directed Relationships Extracted**")
                
                rel_rows = []
                for r in relationships:
                    src = r.get("source", {})
                    rel_rows.append({
                        "Source Entity": r.get("source_entity"),
                        "Relationship Type": f"-[:{r.get('relationship_type')}]->",
                        "Target Entity": r.get("target_entity"),
                        "Source Page": f"Page {src.get('page_number', 'N/A')}",
                        "Evidence Snippet": src.get("source_text", "")
                    })
                st.dataframe(pd.DataFrame(rel_rows), use_container_width=True)

            with sub_tab4:
                if chunks_data:
                    st.markdown(f"**{len(chunks_data)} Passage Chunks in Lakehouse Chunks Tier**")
                    for c in chunks_data[:10]:
                        with st.expander(f"Chunk `{c['chunk_id']}` (Page {c['page_number']} | {c['word_count']} words)"):
                            st.write(c["text"])

            with sub_tab5:
                st.json(context_data)

# ----------------- TAB 3: Graph Visualizer -----------------
with tab3:
    st.subheader("Apache AGE Knowledge Graph Visualizer")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        view_mode = st.radio("Graph Scope", options=["Selected Document Subgraph", "Full Cross-Document Knowledge Graph"], horizontal=True)
    with col_b:
        test_simple = st.checkbox("🧪 Test Simple Render (Node A ➔ Node B)", value=False, help="Render a minimal test graph to verify frontend canvas rendering")

    if test_simple:
        graph_data = {
            "nodes": [
                {"id": 1, "name": "Node A (Test Source)", "canonical_name": "Node A", "entity_type": "Technology", "document_name": "Test", "page_number": 1, "source_text": "Test sample node A."},
                {"id": 2, "name": "Node B (Test Target)", "canonical_name": "Node B", "entity_type": "Concept", "document_name": "Test", "page_number": 1, "source_text": "Test sample node B."}
            ],
            "edges": [
                {"id": "e_test", "source": 1, "target": 2, "label": "TEST_LINK", "document_name": "Test", "page_number": 1, "source_text": "Test link from A to B."}
            ]
        }
        st.info("🧪 **Running simple fallback test graph (Node A ➔ Node B).** Uncheck above to return to real Apache AGE graph.")
    elif view_mode == "Selected Document Subgraph" and docs:
        sub_doc_options = {f"{d.document_name} ({d.document_id})": d.document_id for d in docs if d.status == ProcessingStatus.COMPLETED}
        if sub_doc_options:
            selected_sub_label = st.selectbox("Select document subgraph:", options=list(sub_doc_options.keys()))
            graph_data = pipeline.graph_service.get_document_subgraph(sub_doc_options[selected_sub_label])
        else:
            st.info("No completed documents yet.")
            graph_data = {"nodes": [], "edges": []}
    else:
        graph_data = pipeline.graph_service.get_full_graph(limit=300)

    nodes_count = len(graph_data.get("nodes", []))
    edges_count = len(graph_data.get("edges", []))
    st.markdown(f"**Rendering {nodes_count} Nodes and {edges_count} Edges directly from Apache AGE**")

    with st.expander("🔍 Graph Diagnostic Data (Nodes & Edges Inspector)", expanded=False):
        st.write(f"**Graph Data Received:** Nodes: `{nodes_count}`, Edges: `{edges_count}`")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**First Node Sample:**")
            if graph_data.get("nodes"):
                st.json(graph_data["nodes"][0])
            else:
                st.write("No nodes in graph data.")
        with col_d2:
            st.markdown("**First Edge Sample:**")
            if graph_data.get("edges"):
                st.json(graph_data["edges"][0])
            else:
                st.write("No edges in graph data.")
    
    # Render Vis.js HTML graph component
    html_graph = render_visjs_graph(graph_data, height="700px")
    components.html(html_graph, height=700, scrolling=False)

# ----------------- TAB 4: Cypher Query Console -----------------
with tab4:
    st.subheader("⚡ Apache AGE Cypher Query Console")
    st.markdown("Execute openCypher queries directly against the PostgreSQL Apache AGE graph database.")

    sample_queries = {
        "1. List all entities (limit 25)": "MATCH (n) RETURN n LIMIT 25",
        "2. List all relationships (limit 25)": "MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 25",
        "3. Find all Technology entities": "MATCH (n:Technology) RETURN n LIMIT 25",
        "4. Find entities connected to 'Apache AGE'": "MATCH (a {canonical_name: 'Apache AGE'})-[r]-(b) RETURN a, r, b",
        "5. Find EXTENDS relationships": "MATCH (a)-[r:EXTENDS]->(b) RETURN a, r, b",
        "6. Find USES relationships": "MATCH (a)-[r:USES]->(b) RETURN a, r, b"
    }

    selected_sample = st.selectbox("Load sample Cypher query:", options=list(sample_queries.keys()))
    cypher_input = st.text_area("Cypher Query", value=sample_queries[selected_sample], height=120)

    if st.button("▶️ Execute Cypher Query", type="primary"):
        with st.spinner("Executing query on Apache AGE..."):
            try:
                if "RETURN a, r, b" in cypher_input:
                    cols = ["a", "r", "b"]
                elif "RETURN n" in cypher_input:
                    cols = ["n"]
                else:
                    cols = ["result"]

                results = pipeline.graph_service.age_client.execute_cypher(
                    cypher_query=cypher_input,
                    columns=cols,
                    graph_name=pipeline.graph_service.graph_name
                )
                
                st.success(f"Query returned **{len(results)}** rows from Apache AGE.")
                
                if results:
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    
                    with st.expander("Raw agtype JSON Results"):
                        st.json(results)
                else:
                    st.info("Query returned 0 matching rows.")

            except Exception as e:
                st.error(f"Cypher Error: {str(e)}")
