import os
import json
import uuid
import hashlib
from collections import Counter
from datetime import datetime
import numpy as np
import hdbscan
from sqlalchemy.orm import Session
from sqlalchemy import func
from sklearn.metrics import silhouette_score, davies_bouldin_score

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource, ProcessedSignal
from app.models.schema import ClusterRun, Cluster, ClusterMember

def generate_title(texts):
    import re
    # Simple deterministic logic
    words = []
    hashtags = []
    for text in texts:
        t = text.lower()
        parts = t.split()
        for p in parts:
            if p.startswith('#'): hashtags.append(p)
            else:
                tp = re.sub(r'[^\w\s]', '', p)
                if len(tp) > 3: words.append(tp)
    
    c_hash = Counter(hashtags).most_common(2)
    c_word = Counter(words).most_common(3)
    
    title_parts = []
    for w, count in c_hash: title_parts.append(w)
    for w, count in c_word: title_parts.append(w)
    
    if not title_parts:
        if texts:
            r = re.sub(r'[^\w\s]', '', texts[0])
            title_parts.append(r[:25].strip())
        else:
            title_parts.append("Unknown")
            
    return " / ".join(title_parts).title()

def run_clustering():
    db = SessionLocal()
    
    url = os.getenv("DATABASE_URL")
    if not url or "tamilsh_poc_test" in url:
        print("FAIL: test DB detected.")
        return
        
    print("PHASE 2 - READ-ONLY CORPUS AUDIT")
    signals = db.query(ProcessedSignal).all()
    eligible = []
    
    for s in signals:
        if s.canonical_text and s.signal_quality != "INSUFFICIENT" and s.embedding is not None and len(s.embedding) == 384:
            vec = np.array(s.embedding, dtype=float)
            if np.isfinite(vec).all() and not np.isnan(vec).any():
                eligible.append((s, vec))
                
    print(f"Total ProcessedSignals: {len(signals)}")
    print(f"Eligible signals: {len(eligible)}")
    
    if not eligible:
        print("No eligible embeddings. Aborting.")
        return
        
    X = np.array([v for s, v in eligible])
    signal_objects = [{"id": s.id, "post_id": s.post_id, "canonical_text": s.canonical_text, "language": s.language} for s, v in eligible]
    
    print("\nPHASE 3 - DISTANCE MODEL")
    print("Algorithm: HDBSCAN, metric=euclidean (safe due to L2 norm=1.0).")
    
    print("\nPHASE 4 - PARAMETER SWEEP")
    sweep_results = []
    sizes = [2, 3, 4, 5]
    samples = [1, 2, 3]
    
    for mcs in sizes:
        for ms in samples:
            clusterer = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=ms, metric='euclidean', gen_min_span_tree=True)
            labels = clusterer.fit_predict(X)
            
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            n_noise = list(labels).count(-1)
            
            if n_clusters > 0:
                cluster_sizes = [list(labels).count(i) for i in range(n_clusters)]
                min_s = min(cluster_sizes)
                max_s = max(cluster_sizes)
                avg_s = sum(cluster_sizes)/len(cluster_sizes)
            else:
                min_s, max_s, avg_s = 0, 0, 0
                
            sil = -1
            db_score = -1
            if n_clusters > 1 and n_noise < len(labels) - 2:
                # Valid for silhouette
                mask = labels != -1
                if len(set(labels[mask])) > 1:
                    sil = silhouette_score(X[mask], labels[mask], metric='euclidean')
                    db_score = davies_bouldin_score(X[mask], labels[mask])
                    
            res = {
                "mcs": mcs,
                "ms": ms,
                "n_clusters": n_clusters,
                "n_noise": n_noise,
                "noise_pct": (n_noise / len(labels)) * 100,
                "min_s": min_s,
                "max_s": max_s,
                "avg_s": avg_s,
                "sil": sil,
                "db": db_score
            }
            sweep_results.append(res)
            print(f"mcs={mcs}, ms={ms}: clusters={n_clusters}, noise={n_noise} ({res['noise_pct']:.1f}%), sil={sil:.3f}")
            
    # Select best config deterministically
    valid_configs = [r for r in sweep_results if r['n_clusters'] > 1 and r['sil'] > 0]
    if valid_configs:
        best = max(valid_configs, key=lambda x: x['sil'])
    else:
        # fallback to minimal sizing purely analytical
        valid_configs = [r for r in sweep_results if r['n_clusters'] > 0]
        if valid_configs:
            best = min(valid_configs, key=lambda x: x['noise_pct'])
        else:
            best = sweep_results[0]
            
    print(f"\nPhase 6/7/8/12 - Selected Config: mcs={best['mcs']}, ms={best['ms']}")
    
    # Run final model twice for Stability/Idempotency
    def run_hdbscan():
        c = hdbscan.HDBSCAN(min_cluster_size=best['mcs'], min_samples=best['ms'], metric='euclidean', gen_min_span_tree=True)
        l = c.fit_predict(X)
        probs = c.probabilities_
        return l, probs
        
    labels_a, probs_a = run_hdbscan()
    labels_b, probs_b = run_hdbscan()
    
    diff = sum(1 for i in range(len(labels_a)) if labels_a[i] != labels_b[i])
    print(f"Stability Diff count: {diff}")
    
    labels = labels_a
    probs = probs_a
    
    report_clusters = []
    
    run_id = str(uuid.uuid4())
    run_obj = ClusterRun(
        run_id=run_id,
        run_name=f"sweep_run_{int(datetime.utcnow().timestamp())}",
        algorithm="HDBSCAN",
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dimension=384,
        metric="euclidean",
        hdbscan_version="unknown",
        min_cluster_size=best['mcs'],
        min_samples=best['ms'],
        corpus_size=len(labels),
        cluster_count=best['n_clusters'],
        noise_count=best['n_noise'],
        configuration_hash=hashlib.md5(f"{best['mcs']}-{best['ms']}".encode()).hexdigest()
    )
    # Remove db.flush()
    # db.add(run_obj) happens but no flush
    
    final_output = {
        "run_id": run_id,
        "configuration": best,
        "clusters": [],
        "noise": [],
        "language_distribution": {"clusters": {}, "noise": {}}
    }
    
    noise_idx = []
    cluster_idx = {}
    for i, p in enumerate(labels):
        if p == -1: noise_idx.append(i)
        else:
            if p not in cluster_idx: cluster_idx[p] = []
            cluster_idx[p].append(i)
            
    noise_langs = {}
    for i in noise_idx:
        sig = signal_objects[i]
        final_output["noise"].append({
            "signal_id": sig["id"],
            "post_id": sig["post_id"],
            "distance_to_nearest": "NO_CLOSE_CLUSTER"
        })
        lang = sig["language"] or "unknown"
        noise_langs[lang] = noise_langs.get(lang, 0) + 1
    final_output["language_distribution"]["noise"] = noise_langs
        
    for cid, idxs in cluster_idx.items():
        sub_X = X[idxs]
        reps = []
        for i in range(len(sub_X)):
            dists = [np.linalg.norm(sub_X[i] - sub_X[j]) for j in range(len(sub_X))]
            reps.append(np.mean(dists))
        medoid_local = np.argmin(reps)
        medoid_global = idxs[medoid_local]
        
        texts = [signal_objects[i]["canonical_text"] for i in idxs]
        title = generate_title(texts)
        
        langs = {"ta":0, "en":0, "mixed":0, "unknown":0}
        for i in idxs:
            l = signal_objects[i]["language"] or "unknown"
            if l in langs: langs[l] += 1
            else: langs[l] = 1
            
        c_obj = Cluster(
            cluster_id=f"{run_id}-{cid}",
            run=run_obj,
            cluster_label=title,
            status="DETERMINISTIC",
            representative_signal_id=signal_objects[medoid_global]["id"],
            signal_count=len(idxs),
            coherence_score=float(np.mean(probs[idxs]))
        )
        db.add(c_obj)
        
        members_out = []
        for local_idx, global_idx in enumerate(idxs):
            m = ClusterMember(
                cluster=c_obj,
                signal_id=signal_objects[global_idx]["id"],
                similarity_score=float(1.0 - (reps[local_idx]/2.0)), # approx
                membership_probability=float(probs[global_idx]),
                is_representative=(global_idx == medoid_global)
            )
            db.add(m)
            members_out.append({
                "signal_id": signal_objects[global_idx]["id"],
                "post_id": signal_objects[global_idx]["post_id"],
                "text": signal_objects[global_idx]["canonical_text"]
            })
            
        final_output["clusters"].append({
            "cluster_label": title,
            "size": len(idxs),
            "coherence": float(np.mean(probs[idxs])),
            "representative_text": signal_objects[medoid_global]["canonical_text"],
            "languages": langs,
            "members": members_out
        })
        
    db.commit()
    db.close()
    
    with open("output/stage_9_4_clusters.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)
        
    print(f"\nFinal persistence complete to ClusterRun: {run_id}.")
    print("\nREPORT DETAILS:")
    for c in final_output["clusters"]:
        print("-" * 50)
        print(f"CLUSTER: {c['cluster_label']}")
        print(f"Size: {c['size']} | Coherence: {c['coherence']:.3f} | Langs: {c['languages']}")
        print(f"Rep: {c['representative_text'][:100]}")
        print("\nMembers:")
        for m in c['members'][:5]:
            print(f"- [Post {m['post_id']}] {m['text'][:50]}")
            
if __name__ == "__main__":
    run_clustering()
