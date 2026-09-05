"""
Live Verification & Demonstration Script for Git Graphify Pipeline
==================================================================
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from backend.git_graph.pipeline import GitGraphPipeline
from backend.git_graph.graph.git_graph_service import GitGraphService

def run_demonstration():
    pipeline = GitGraphPipeline()
    print("==================================================================")
    print("STEP 1: ANALYZING LOCAL / CURRENT REPOSITORY")
    print("==================================================================")
    result = pipeline.analyze(
        repository_url=".",
        branch="main"
    )
    print(f"Status: {result.status}")
    print(f"Repository: {result.repository_name}")
    print(f"Commit SHA: {result.commit_sha}")
    print(f"Files Scanned: {result.files_scanned}")
    print(f"Lines Scanned: {result.lines_scanned}")
    print(f"Entities Extracted: {result.entities_extracted}")
    print(f"Relationships Extracted: {result.relationships_extracted}")
    print(f"Nodes Created: {result.nodes_created} (Existing: {result.nodes_existing})")
    print(f"Edges Created: {result.edges_created} (Existing: {result.edges_existing})")
    print(f"Execution Duration: {result.duration_seconds}s")
    print(f"Languages: {result.languages}")

    print("\n==================================================================")
    print("STEP 2: QUERYING LIVE APACHE AGE GRAPH STATISTICS")
    print("==================================================================")
    stats = pipeline.graph_service.get_graph_stats()
    print(f"Graph Name: {stats['graph_name']}")
    print(f"Total Vertices in AGE: {stats['total_nodes']}")
    print(f"Total Edges in AGE: {stats['total_edges']}")
    print("Entity Breakdown:")
    for k, v in stats['entity_types'].items():
        print(f"  - {k}: {v}")

    print("\n==================================================================")
    print("STEP 3: SAMPLE OPENCYPHER QUERIES ON APACHE AGE")
    print("==================================================================")
    print("[Cypher] Classes defined in repository:")
    classes = pipeline.graph_service.age_client.execute_cypher(
        "MATCH (f:File)-[r:DEFINES]->(c:Class) RETURN f.name AS file, c.name AS class_name LIMIT 6",
        columns=["file", "class_name"],
        graph_name=pipeline.graph_service.graph_name
    )
    for c in classes:
        print(f"  - File '{c.get('file')}' -[:DEFINES]-> Class '{c.get('class_name')}'")

    print("\n[Cypher] External Libraries imported by repository:")
    libs = pipeline.graph_service.age_client.execute_cypher(
        "MATCH (f:File)-[r:IMPORTS]->(l:Library) RETURN f.name AS file, l.name AS lib LIMIT 6",
        columns=["file", "lib"],
        graph_name=pipeline.graph_service.graph_name
    )
    for l in libs:
        print(f"  - File '{l.get('file')}' -[:IMPORTS]-> Library '{l.get('lib')}'")

    print("\n[Cypher] API Endpoints:")
    apis = pipeline.graph_service.age_client.execute_cypher(
        "MATCH (api:API)-[r:IMPLEMENTED_BY]->(fn) RETURN api.name AS api_endpoint, fn.name AS handler LIMIT 5",
        columns=["api_endpoint", "handler"],
        graph_name=pipeline.graph_service.graph_name
    )
    for a in apis:
        print(f"  - Endpoint '{a.get('api_endpoint')}' -[:IMPLEMENTED_BY]-> Function '{a.get('handler')}'")

    print("\n==================================================================")
    print("STEP 4: EXACT LINE-LEVEL SOURCE CODE PROVENANCE TRACEBACK")
    print("==================================================================")
    for target_symbol in ["GitGraphPipeline", "AGEClient", "analyze_repository"]:
        prov = pipeline.graph_service.get_entity_provenance(target_symbol)
        if "error" not in prov:
            print(f"\n--- Entity: {prov['name']} ({prov['entity_type']}) ---")
            print(f"Canonical ID: {prov['canonical_id']}")
            print(f"Repository:   {prov['repository_name']}")
            print(f"File Path:    {prov['file_path']}")
            print(f"Line Range:   L{prov['start_line']}-{prov['end_line']}")
            print(f"Method:       {prov['extraction_method']}")
            snippet_preview = prov['source_snippet'].replace('\n', ' ')[:140]
            print(f"Code Snippet: \"{snippet_preview}...\"")
            print(f"Connections:  {len(prov.get('connections', []))} connected relationships")

    print("\n==================================================================")
    print("STEP 5: IDEMPOTENCY VERIFICATION (REPEATED INGESTION RUN)")
    print("==================================================================")
    res_repeat = pipeline.analyze(
        repository_url=".",
        branch="main"
    )
    print(f"Nodes Created on 2nd Run: {res_repeat.nodes_created} (Existing: {res_repeat.nodes_existing})")
    print(f"Edges Created on 2nd Run: {res_repeat.edges_created} (Existing: {res_repeat.edges_existing})")
    assert res_repeat.nodes_created == 0, "Duplicate nodes were created!"
    assert res_repeat.edges_created == 0, "Duplicate edges were created!"
    print(">>> SUCCESS: 0 duplicate nodes/edges created. Idempotency verified 100%.")
    print("==================================================================")

if __name__ == "__main__":
    run_demonstration()
