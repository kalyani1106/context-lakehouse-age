"""
Lakehouse & Apache AGE Duplicate/Legacy Document Cleanup Script
===============================================================
Audits all documents in the Lakehouse catalog, computes actual SHA-256 hashes,
selects one canonical document per unique file hash, re-aligns Apache AGE graph
provenance, and safely deletes redundant lakehouse tier artifacts.
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Set path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.lakehouse import LocalLakehouseStorageService
from storage.models import ProcessingStatus
from graph.age_client import AGEClient
from graph.graph_service import GraphService

def audit_and_cleanup(dry_run: bool = True):
    storage = LocalLakehouseStorageService()
    age_client = AGEClient()
    graph_service = GraphService(age_client=age_client)

    print("=" * 80)
    print("STEP 1: AUDIT LAKEHOUSE CATALOG & COMPUTE REAL SHA-256 HASHES")
    print("=" * 80)

    raw_dir = storage.raw_dir
    meta_dir = storage.metadata_dir

    all_docs = storage.list_documents()
    print(f"Total metadata records in catalog: {len(all_docs)}")

    doc_info_list = []
    for doc in all_docs:
        doc_id = doc.document_id
        raw_pdf_path = raw_dir / f"{doc_id}.pdf"
        
        real_sha256 = None
        file_size = 0
        if raw_pdf_path.exists():
            content = open(raw_pdf_path, "rb").read()
            real_sha256 = hashlib.sha256(content).hexdigest()
            file_size = len(content)
        
        doc_info_list.append({
            "doc_id": doc_id,
            "filename": doc.document_name,
            "stored_sha": getattr(doc, "sha256", None),
            "real_sha": real_sha256,
            "file_size": file_size,
            "status": doc.status,
            "entities": doc.total_entities,
            "rels": doc.total_relationships,
            "uploaded_at": doc.uploaded_at,
            "model_obj": doc
        })

    # Group by real SHA-256 hash
    grouped_by_hash = {}
    for d in doc_info_list:
        h = d["real_sha"] or "MISSING_RAW_FILE"
        grouped_by_hash.setdefault(h, []).append(d)

    print(f"\nDiscovered {len(grouped_by_hash)} unique document hashes across {len(doc_info_list)} records:")

    plan = []

    for h, group in grouped_by_hash.items():
        print(f"\nHash Group: {h[:16]}... ({len(group)} records)")
        # Prioritize high-precision newest record with valid SHA-256
        def rank_score(item):
            has_valid_sha = 2 if (item["stored_sha"] and item["stored_sha"] != "unknown_legacy" and len(item["stored_sha"]) == 64) else 0
            has_time = 1 if item["model_obj"].processing_time_sec is not None else 0
            # Newest uploaded_at
            upload_ts = item["uploaded_at"].timestamp() if hasattr(item["uploaded_at"], "timestamp") else 0
            return (has_valid_sha, has_time, upload_ts)

        sorted_group = sorted(group, key=rank_score, reverse=True)
        canonical = sorted_group[0]
        duplicates = sorted_group[1:]

        print(f"  --> KEEP CANONICAL: {canonical['doc_id']} ({canonical['filename']}) [Status: {canonical['status'].value}, Ents: {canonical['entities']}, Rels: {canonical['rels']}, Uploaded: {canonical['uploaded_at']}]")
        for dup in duplicates:
            print(f"  --> PRUNE DUPLICATE: {dup['doc_id']} ({dup['filename']}) [Status: {dup['status'].value}, Ents: {dup['entities']}, Rels: {dup['rels']}, Uploaded: {dup['uploaded_at']}]")

        plan.append({
            "sha256": h,
            "canonical": canonical,
            "duplicates": duplicates
        })

    if dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN COMPLETE. No changes made. Run with --execute to execute cleanup.")
        print("=" * 80)
        return plan

    print("\n" + "=" * 80)
    print("STEP 2: CLEANUP DUPLICATE LAKEHOUSE ARTIFACTS & GRAPH DATA")
    print("=" * 80)

    total_pruned_docs = 0

    for item in plan:
        canonical = item["canonical"]
        can_id = canonical["doc_id"]
        can_name = canonical["filename"]
        can_sha = item["sha256"]

        # Ensure canonical metadata has correct real SHA-256
        can_meta = storage.get_metadata(can_id)
        if can_meta:
            can_meta.sha256 = can_sha
            storage._save_metadata(can_meta)
            print(f"\n[Canonical Confirmed] {can_id} ({can_name}) with SHA-256 {can_sha[:16]}...")

        # Process each duplicate
        for dup in item["duplicates"]:
            dup_id = dup["doc_id"]
            print(f"  - Deleting duplicate Lakehouse artifacts for {dup_id} ({dup['filename']})...")
            storage.delete_document(dup_id)
            total_pruned_docs += 1

    # STEP 3: Clean and Re-synchronize Apache AGE Knowledge Graph for the 3 Canonical Documents
    print("\n" + "=" * 80)
    print("STEP 3: RE-SYNCHRONIZING APACHE AGE KNOWLEDGE GRAPH FOR CANONICAL DOCUMENTS")
    print("=" * 80)

    # Clean the graph and re-ingest clean canonical contexts
    from pipeline import PDFContextPipeline
    pipe = PDFContextPipeline()
    
    # Reset knowledge_graph
    conn = age_client.get_connection()
    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT drop_graph('{graph_service.graph_name}', true);")
            conn.commit()
            print(f"Reset knowledge graph '{graph_service.graph_name}'.")
        except Exception as e:
            conn.rollback()
            print(f"Drop graph note: {e}")
    conn.close()

    age_client.ensure_graph_exists(graph_service.graph_name)

    # Re-process each canonical document through pipeline
    for item in plan:
        can = item["canonical"]
        can_id = can["doc_id"]
        print(f"\nRe-processing canonical document {can_id} ({can['filename']})...")
        res = pipe.process_document(can_id, force_provider="heuristic", reprocess=True)
        print(f"  - Ingested {res['total_entities']} entities & {res['total_relationships']} relationships in {res['processing_time_sec']}s.")

    print("\n" + "=" * 80)
    print("STEP 3: POST-CLEANUP AUDIT VERIFICATION")
    print("=" * 80)

    remaining_docs = storage.list_documents()
    print(f"Remaining Canonical Documents in Catalog: {len(remaining_docs)}")
    for d in remaining_docs:
        print(f"  - [{d.document_id}] {d.document_name} | SHA-256: {d.sha256[:16]}... | Status: {d.status.value} | Pages: {d.total_pages} | Chunks: {d.total_chunks} | Ents: {d.total_entities} | Rels: {d.total_relationships} | Time: {d.processing_time_sec}s")

    stats = graph_service.get_graph_stats()
    print(f"\nApache AGE Graph Status:")
    print(f"  - Total Graph Vertices: {stats.get('total_nodes')}")
    print(f"  - Total Graph Edges: {stats.get('total_edges')}")
    print(f"\nCleanup finished successfully! Pruned {total_pruned_docs} duplicate records.")

if __name__ == "__main__":
    is_dry = "--execute" not in sys.argv
    audit_and_cleanup(dry_run=is_dry)
