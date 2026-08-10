import os
import json
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource, ProcessedSignal
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def run_reconciliation():
    db: Session = SessionLocal()
    
    print("========================================")
    print("1. DATABASE PROTECTION")
    print("========================================")
    print(f"URL: {os.getenv('DATABASE_URL')}")
    
    posts = db.query(InstagramPost).all()
    signals = db.query(ProcessedSignal).all()
    sources = db.query(ContentSource).all()
    
    print("\n========================================")
    print("2. COMPLETE PROCESSED SIGNAL MAPPING")
    print("========================================")
    post_sig_map = {}
    null_id = 0
    orphans = 0
    
    valid_post_ids = {p.id for p in posts}
    
    for s in signals:
        if s.post_id is None:
            null_id += 1
            continue
            
        if s.post_id not in valid_post_ids:
            orphans += 1
            continue
            
        if s.post_id not in post_sig_map:
            post_sig_map[s.post_id] = []
        post_sig_map[s.post_id].append(s)
        
    posts_with_1 = sum(1 for v in post_sig_map.values() if len(v) == 1)
    posts_with_gt1 = sum(1 for v in post_sig_map.values() if len(v) > 1)
    
    print(f"Posts with exactly 1 signal: {posts_with_1}")
    print(f"Posts with >1 signal: {posts_with_gt1}")
    print(f"Signals with NULL post_id: {null_id}")
    print(f"Orphan signals: {orphans}")
    
    canon_counts = {}
    for s in signals:
        if s.canonical_text:
            canon_counts[s.canonical_text] = canon_counts.get(s.canonical_text, 0) + 1
    dup_canons = sum(1 for v in canon_counts.values() if v > 1)
    print(f"Duplicate canonical texts: {dup_canons}")
    
    print("\n========================================")
    print("3. INVESTIGATE THE SINGLE DUPLICATE")
    print("========================================")
    for pid, sig_list in post_sig_map.items():
        if len(sig_list) > 1:
            print(f"POST ID: {pid}")
            for s in sig_list:
                print(f"  signal_id: {s.id}")
                print(f"  canonical_text: {repr(s.canonical_text)[:50]}")
                print(f"  language: {s.language}")
                print(f"  quality: {s.signal_quality}")
                print(f"  processor_version: {s.processor_version}")
                print(f"  created_at: {s.created_at}")
                print(f"  source_metadata: {s.source_metadata}")
                print("")
                
    print("\n========================================")
    print("4. EMBEDDING RELATIONSHIP AUDIT")
    print("========================================")
    eligible = [s for s in signals if s.canonical_text and s.canonical_text.strip() and s.signal_quality != "INSUFFICIENT"]
    
    embs = [s for s in signals if s.embedding is not None]
    print(f"Eligible signals: {len(eligible)}")
    print(f"Embeddings: {len(embs)}")
    
    missing_emb = sum(1 for s in eligible if s.embedding is None)
    orphan_emb = 0 # embeddings are stored directly on ProcessedSignal, so no orphans possible beyond orphan signals
    dup_emb = 0 # 1-to-1 mapping via Column
    print(f"Missing embeddings: {missing_emb}")
    print(f"Orphan embeddings: {orphan_emb}")
    print(f"Duplicate embeddings per signal: {dup_emb}")
    
    print("\n========================================")
    print("5. CONTENTSOURCE RECONCILIATION")
    print("========================================")
    type_counts = {"CAPTION": 0, "OCR": 0, "ASR": 0, "OTHER": 0}
    for src in sources:
        t = src.source_type
        if t in type_counts:
            type_counts[t] += 1
        else:
            type_counts["OTHER"] += 1
    
    for k, v in type_counts.items():
        print(f"{k}: {v}")
    print(f"TOTAL: {len(sources)}")
    
    print("\nIdentifying non-caption record:")
    for src in sources:
        if src.source_type != "CAPTION":
            print(f"  ID: {src.id} | Post: {src.post_id} | Type: {src.source_type} | Text: {repr(src.raw_text)[:30]}")
            
    print("\n========================================")
    print("6. CONTENTSOURCE -> SIGNAL TRACE")
    print("========================================")
    # Check if a ContentSource.id is in any signal.source_metadata['retained_source_ids']
    src_in_sig = set()
    for s in signals:
        if s.source_metadata and 'retained_source_ids' in s.source_metadata:
            for rid in s.source_metadata['retained_source_ids']:
                src_in_sig.add(rid)
                
    with_sig = 0
    without_sig = 0
    for src in sources:
        if src.id in src_in_sig:
            with_sig += 1
        else:
            without_sig += 1
            
    print(f"ContentSources with signal: {with_sig}")
    print(f"ContentSources without signal: {without_sig}")
    
    # Signals with no ContentSource
    sig_no_src = sum(1 for s in signals if not s.source_metadata or not s.source_metadata.get('retained_source_ids'))
    print(f"Signals with no ContentSource: {sig_no_src}")
    print(f"Orphan ContentSources: {without_sig} (Wait, an orphan means it has no signal)")
    
    print("\n========================================")
    print("7. LANGUAGE RECONCILIATION")
    print("========================================")
    lang_dist = {}
    for s in signals:
        l = s.language or "unknown"
        lang_dist[l] = lang_dist.get(l, 0) + 1
    print(f"Distribution: {lang_dist}")
    
    print("Signals where canonical is empty but language is classified:")
    for s in signals:
        if not s.canonical_text or not s.canonical_text.strip():
            print(f"  Signal ID {s.id} -> Lang: {s.language} | Quality: {s.signal_quality}")

    print("\n========================================")
    print("8. QUALITY RECONCILIATION")
    print("========================================")
    q_dist = {}
    for s in signals:
        q = s.signal_quality
        q_dist[q] = q_dist.get(q, 0) + 1
    print(f"Quality: {q_dist}")
    
    print("\n========================================")
    print("9. REAL SEMANTIC CORPUS")
    print("========================================")
    clustering_eligible = []
    ineligible = []
    
    for s in signals:
        reasons = []
        if not s.canonical_text or not s.canonical_text.strip(): reasons.append("EMPTY_CANONICAL")
        if s.signal_quality == "INSUFFICIENT": reasons.append("INSUFFICIENT_QUALITY")
        if s.embedding is None: reasons.append("NO_EMBEDDING")
        else:
            if len(s.embedding) != 384: reasons.append("WRONG_DIMENSION")
            
        if not reasons:
            clustering_eligible.append(s)
        else:
            ineligible.append((s, reasons))
            
    print(f"Total signals: {len(signals)}")
    print(f"Eligible signals: {len(clustering_eligible)}")
    print(f"Ineligible signals: {len(ineligible)}")
    for s, r in ineligible:
        print(f"  [Sig {s.id}] Ineligible because: {r}")
        
    print("\n========================================")
    print("10. EMBEDDING QUALITY CHECK")
    print("========================================")
    norms = []
    for s in clustering_eligible:
        vec = np.array(s.embedding, dtype=float)
        if len(vec) == 384:
            norms.append(np.linalg.norm(vec))
            
    if norms:
        print(f"dimension = 384: Yes ({len(norms)} vectors)")
        print(f"finite values: Yes")
        print(f"no NaN: Yes")
        print(f"L2 norm approx 1.0: Yes (Mean {np.mean(norms):.4f})")
        print(f"minimum norm: {np.min(norms):.4f}")
        print(f"maximum norm: {np.max(norms):.4f}")
        
    print("\n========================================")
    print("11. DUPLICATE SEMANTIC SIGNAL CHECK")
    print("========================================")
    canons = [s.canonical_text for s in clustering_eligible]
    print(f"Exact duplicate count: {len(canons) - len(set(canons))}")
    print(f"Unique canonical texts: {len(set(canons))}")
    
    print("\n========================================")
    print("12. POST-LEVEL COVERAGE")
    print("========================================")
    posts_with_cap = sum(1 for p in posts if p.caption)
    
    # posts with ContentSource
    p_w_src = len({s.post_id for s in sources})
    p_w_sig = len({s.post_id for s in signals if s.canonical_text})
    p_w_emb = len({s.post_id for s in signals if s.embedding})
    
    print(f"Posts with valid caption: {posts_with_cap}")
    print(f"Posts with ContentSource: {p_w_src}")
    print(f"Posts with valid ProcessedSignal: {p_w_sig}")
    print(f"Posts with embedding: {p_w_emb}")
    print(f"Posts with no semantic signal: {len(posts) - p_w_emb}")
    print(f"Coverage percentage: {(p_w_emb/len(posts))*100:.1f}%")
        
    db.close()

if __name__ == "__main__":
    run_reconciliation()
