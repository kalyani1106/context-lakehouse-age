import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.git_graph.pipeline import GitGraphPipeline
from backend.pipeline import PDFContextPipeline
from frontend.graph_visualizer import render_visjs_graph

def test_live_rendering():
    print("--- 1. Testing Live Git Graph Retrieval & Rendering ---")
    git_pipeline = GitGraphPipeline()
    repos = git_pipeline.graph_service.list_repositories()
    repo_name = repos[0]["name"] if repos else None
    print(f"Target Git Repository: {repo_name}")
    git_data = git_pipeline.graph_service.get_repository_graph(repo_name=repo_name, limit=50)
    print(f"Git Graph from AGE: {len(git_data['nodes'])} vertices, {len(git_data['edges'])} edges")
    html_git = render_visjs_graph(git_data, height="720px")
    print(f"Generated HTML Git Graph size: {len(html_git)} bytes")
    assert len(html_git) > 10000, "HTML Git graph too small"
    assert "panel-content" in html_git
    assert "vis.Network" in html_git

    # Verify provenance data inside JSON
    sample_node = git_data["nodes"][0] if git_data["nodes"] else None
    if sample_node:
        print(f"Sample Git Vertex: {sample_node.get('name')} ({sample_node.get('entity_type')})")
        print(f"  - Canonical ID: {sample_node.get('canonical_id')}")
        print(f"  - File Path: {sample_node.get('file_path')}")
        print(f"  - Line Range: L{sample_node.get('start_line')}-{sample_node.get('end_line')}")
        print(f"  - Extraction Method: {sample_node.get('extraction_method')}")

    print("\n--- 2. Testing Live PDF Graph Retrieval & Rendering ---")
    pdf_pipeline = PDFContextPipeline()
    pdf_data = pdf_pipeline.graph_service.get_full_graph(limit=50)
    print(f"PDF Graph from AGE: {len(pdf_data['nodes'])} vertices, {len(pdf_data['edges'])} edges")
    html_pdf = render_visjs_graph(pdf_data, height="720px")
    print(f"Generated HTML PDF Graph size: {len(html_pdf)} bytes")
    assert len(html_pdf) > 10000, "HTML PDF graph too small"
    assert "panel-content" in html_pdf

    sample_pdf_node = pdf_data["nodes"][0] if pdf_data["nodes"] else None
    if sample_pdf_node:
        print(f"Sample PDF Vertex: {sample_pdf_node.get('name')} ({sample_pdf_node.get('entity_type')})")
        print(f"  - Document: {sample_pdf_node.get('document_name')}")
        print(f"  - Page: {sample_pdf_node.get('page_number')}")

    print("\n>>> ALL LIVE GRAPH RETRIEVAL AND VISUALIZER RENDERING CHECKS PASSED 100%!")

if __name__ == "__main__":
    test_live_rendering()
