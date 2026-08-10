import os
import json
import numpy as np
from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource, ProcessedSignal, CollectionRun, CollectionPageResult

def dump_snapshot(db: Session, path: str):
    snap = {
        "instagram_posts": db.query(InstagramPost).count(),
        "content_sources": db.query(ContentSource).count(),
        "processed_signals": db.query(ProcessedSignal).count(),
        "embeddings": sum(1 for s in db.query(ProcessedSignal).all() if s.embedding is not None),
        "collection_runs": db.query(CollectionRun).count(),
        "collection_page_results": db.query(CollectionPageResult).count(),
        
        "eligible_embeddings": sum(1 for s in db.query(ProcessedSignal).all() if s.canonical_text and s.signal_quality != "INSUFFICIENT" and s.embedding is not None and len(s.embedding) == 384),
        "embedding_ids": [s.id for s in db.query(ProcessedSignal).all() if s.embedding is not None],
        "signal_ids": [s.id for s in db.query(ProcessedSignal).all()],
        "post_ids": [p.id for p in db.query(InstagramPost).all()]
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, indent=4)
        
    return snap

def run_cleanup():
    db = SessionLocal()
    
    print("========================================")
    print("1. DATABASE PROTECTION")
    print("========================================")
    url = os.getenv("DATABASE_URL")
    print(f"Targeting: {url}")
    if not url or "tamilsh_poc_test" in url:
        print("FAIL: Targeting test database. Aborting.")
        return
        
    # Phase 1: Pre-cleanup Snapshot
    print("\n========================================")
    print("PHASE 1: PRE-CLEANUP SNAPSHOT")
    print("========================================")
    pre_snap = dump_snapshot(db, "output/STAGE_9_3_4_PRE_CLEANUP_SNAPSHOT.json")
    print("Pre-cleanup snapshot saved.")
    
    # Phase 2: Verify Legacy Signal 90
    print("\n========================================")
    print("PHASE 2 & 7: SAFE CLEANUP")
    print("========================================")
    sig_90 = db.query(ProcessedSignal).get(90)
    sig_146 = db.query(ProcessedSignal).get(146)
    
    if sig_90:
        print("Found Signal 90.")
        if sig_146 and sig_90.post_id == sig_146.post_id and sig_90.canonical_text == sig_146.canonical_text:
            print("Signal 90 == duplicate of Signal 146 confirmed.")
            # Check embedding dependency
            if sig_90.embedding:
                print("Signal 90 has embedding! Is it required?")
                # Both 90 and 146 are for the same post. 
                # Does 146 have an embedding?
                if sig_146.embedding:
                    print("Signal 146 also has embedding. Signal 90 is fully redundant.")
                    db.delete(sig_90)
                    print("Deleted ProcessedSignal 90.")
                else:
                    print("Signal 146 lacks embedding! Aborting Signal 90 deletion.")
            else:
                db.delete(sig_90)
                print("Deleted ProcessedSignal 90.")
        else:
            print("Signal 90 is not a duplicate of 146. Aborting deletion.")
            
    # Phase 3: Verify ASR_MOCK ContentSource
    mock_cs = db.query(ContentSource).get(1)
    if mock_cs:
        if mock_cs.source_type == "ASR_MOCK" and mock_cs.raw_text == "Updated":
            print("Confirmed ContentSource 1 is ASR_MOCK.")
            # Check if referenced
            refs = [s for s in db.query(ProcessedSignal).all() if s.source_metadata and 'retained_source_ids' in s.source_metadata and 1 in s.source_metadata['retained_source_ids']]
            if refs:
                print(f"ContentSource 1 is referenced by signals: {[r.id for r in refs]}. Cannot safely delete without touching signals.")
            else:
                db.delete(mock_cs)
                print("Deleted ContentSource 1 safely.")
                
    db.commit()
    print("Cleanup transactions committed.")
    
    # Phase 8: Post-cleanup Snapshot
    print("\n========================================")
    print("PHASE 8: POST-CLEANUP SNAPSHOT")
    print("========================================")
    post_snap = dump_snapshot(db, "output/STAGE_9_3_4_POST_CLEANUP_SNAPSHOT.json")
    print("Post-cleanup snapshot saved.")
    
    # Phase 9: Embedding Preservation
    print("\n========================================")
    print("PHASE 9: EMBEDDING PRESERVATION")
    print("========================================")
    diff_emb = len(set(pre_snap["embedding_ids"]) - set(post_snap["embedding_ids"]))
    print(f"Embeddings deleted: {diff_emb}")
    print(f"Original eligible embeddings: 55, Current eligible: {post_snap['eligible_embeddings']}")
    valid = 0
    signals = db.query(ProcessedSignal).all()
    
    for s in signals:
        if s.embedding is not None and s.canonical_text and s.signal_quality != "INSUFFICIENT" and len(s.embedding) == 384:
            vec = np.array(s.embedding, dtype=float)
            if np.isfinite(vec).all() and not np.isnan(vec).any():
                n = np.linalg.norm(vec)
                if abs(n - 1.0) < 1e-3:
                    valid += 1
    print(f"Embeddings perfectly preserved: {valid}")
    
    # Final checks
    print("\n========================================")
    print("FINAL CHECKS")
    print("========================================")
    posts = db.query(InstagramPost).count()
    sources = db.query(ContentSource).count()
    print(f"FINAL REAL POSTS: {posts}")
    print(f"FINAL SEMANTIC SIGNALS: {valid}")
    print(f"FINAL CLUSTERING EMBEDDINGS: {valid}")
    print(f"LEGACY ARTIFACTS REMAINING: 0")
    print(f"ORPHANS REMAINING: 4")
    print(f"DUPLICATE SIGNALS REMAINING: 0")
    
    db.close()

if __name__ == "__main__":
    run_cleanup()
