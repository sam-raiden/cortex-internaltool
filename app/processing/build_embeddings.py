import os
import sys
import time
import argparse
from typing import List
from collections import Counter

from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource, ProcessedSignal
from app.processing.signal_composer import SignalTextComposer
from app.processing.embeddings import EmbeddingProvider

def main():
    parser = argparse.ArgumentParser(description="Build Semantic Signals and Embeddings for POC limits")
    parser.add_argument("--limit", type=int, default=0, help="Max records to evaluate/process, 0 = no limit (process everything eligible)")
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    
    print("========================================")
    print("STAGE 8 — SEMANTIC SIGNALS")
    print("========================================")
    
    t0 = time.time()
    
    # 1. Initialize components
    composer = SignalTextComposer()
    
    t_m1 = time.time()
    provider = EmbeddingProvider()
    model_load_ms = int((time.time() - t_m1) * 1000)
    
    # 2. Fetch targets
    # Find active posts. We use InstagramPost as the core root to gather all sources
    # (a legacy alias for RawContent -- this covers every platform, not just Instagram).
    # Newest-first so a real --limit (if ever passed) prioritizes fresh content over
    # whatever happened to be inserted first.
    query = db.query(InstagramPost).order_by(InstagramPost.id.desc())
    if args.limit > 0:
        query = query.limit(args.limit)
    posts = query.all()
    
    evaluated = 0
    eligible = 0
    insufficient = 0
    created_embeddings = 0
    skipped_duplicates = 0
    failures = 0
    
    source_composition = Counter()
    lang_dist = Counter()
    quality_dist = Counter()
    
    sum_sig_time = 0
    
    for post in posts:
        evaluated += 1
        sources = db.query(ContentSource).filter(ContentSource.post_id == post.id).all()
        
        t_s1 = time.time()
        
        # Build canonical
        signal = composer.compose(post_id=post.id, sources=sources)
        quality_dist[signal.signal_quality] += 1
        
        # Track components
        if signal.signal_quality == "INSUFFICIENT":
            insufficient += 1
            continue
            
        eligible += 1
        
        lang_dist[signal.language or "unknown"] += 1
        
        # Track sources exactly via source IDs natively
        retained = signal.source_metadata.get("retained_source_ids", [])
        types_retained = [s.source_type for s in sources if s.id in retained]
        types_retained.sort() # ASR, CAPTION, OCR
        
        key = " + ".join(types_retained) if types_retained else "None"
        source_composition[key] += 1
        
        # Idempotency 
        existing = db.query(ProcessedSignal).filter(ProcessedSignal.post_id == post.id).first()
        
        if existing and existing.processor_version == signal.processor_version and existing.embedding is not None:
            # Already embedded
            skipped_duplicates += 1
            sum_sig_time += int((time.time() - t_s1) * 1000)
            continue
            
        # Create Embedding
        try:
            vec = provider.embed(signal.canonical_text)
            
            # Persist back
            if existing:
                existing.canonical_text = signal.canonical_text
                existing.language = signal.language
                existing.signal_quality = signal.signal_quality
                existing.source_metadata = signal.source_metadata
                existing.embedding = vec
                existing.processor_version = signal.processor_version
                existing.embedding_metadata = {
                    "model_name": provider.model_name,
                    "dimension": provider.dimension,
                    "normalized": provider.normalized,
                    "version": "v1"
                }
            else:
                signal.embedding = vec
                signal.embedding_metadata = {
                    "model_name": provider.model_name,
                    "dimension": provider.dimension,
                    "normalized": provider.normalized,
                    "version": "v1"
                }
                db.add(signal)
            db.commit()
            created_embeddings += 1
            
        except Exception as e:
            db.rollback()
            failures += 1
            print(f"Error embedding post {post.id}: {e}")
            
        sum_sig_time += int((time.time() - t_s1) * 1000)
        
    db.close()
    
    total_ms = int((time.time() - t0) * 1000)
    avg_ms = sum_sig_time // evaluated if evaluated > 0 else 0
    
    print(f"\nSignals evaluated: {evaluated}")
    print(f"Eligible signals: {eligible}")
    print(f"Insufficient signals: {insufficient}\n")
    
    print("Source composition:")
    for k, v in source_composition.items():
        print(f"{k}: {v}")
        
    print("\nLanguages:")
    for lang in ['ta', 'en', 'mixed', 'unknown']:
        print(f"{lang.capitalize()}: {lang_dist[lang]}")
        
    print("\nQUALITY:")
    print(f"High: {quality_dist['HIGH']}")
    print(f"Medium: {quality_dist['MEDIUM']}")
    print(f"Low: {quality_dist['LOW']}")
    print(f"Insufficient: {quality_dist['INSUFFICIENT']}\n")
    
    print("EMBEDDINGS:")
    print(f"Model: {provider.model_name}")
    print(f"Dimension: {provider.dimension}")
    print(f"Created: {created_embeddings}")
    print(f"Skipped duplicates: {skipped_duplicates}")
    print(f"Failures: {failures}\n")
    
    print("PERFORMANCE:")
    print(f"Model load: {model_load_ms} ms")
    print(f"Average signal: {avg_ms} ms")
    print(f"Total: {total_ms} ms")
    
    print("========================================")

if __name__ == "__main__":
    main()
