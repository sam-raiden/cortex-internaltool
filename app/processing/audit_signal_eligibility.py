import argparse
from sqlalchemy import func
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource, ProcessedSignal

def audit():
    print("========================================")
    print("STAGE 9.1 — REAL CORPUS ELIGIBILITY AUDIT")
    print("========================================\n")
    
    db = SessionLocal()
    
    # === 1. INVENTORY ===
    posts = db.query(InstagramPost).all()
    signals = db.query(ProcessedSignal).all()
    sources = db.query(ContentSource).all()
    
    emb_count = sum(1 for s in signals if s.embedding is not None)
    
    print("POSTS")
    print(f"Instagram posts: {len(posts)}")
    print("\nCONTENT")
    
    cap_available = 0
    ocr_available = 0
    asr_available = 0
    
    for src in sources:
        if src.raw_text and len(src.raw_text.strip()) > 0:
            if src.source_type == 'CAPTION': cap_available += 1
            elif src.source_type == 'OCR': ocr_available += 1
            elif src.source_type == 'ASR': asr_available += 1
    
    print(f"Caption available: {cap_available}")
    print(f"OCR available: {ocr_available}")
    print(f"ASR available: {asr_available}")
    
    print("\nSIGNALS")
    non_empty_can = sum(1 for s in signals if s.canonical_text and len(s.canonical_text.strip()) > 0)
    insufficient_signals = sum(1 for s in signals if s.signal_quality == 'INSUFFICIENT')
    
    print(f"Processed signals: {len(signals)}")
    print(f"Non-empty canonical: {non_empty_can}")
    print(f"Insufficient: {insufficient_signals}")
    
    print("\nQUALITY")
    high = sum(1 for s in signals if s.signal_quality == 'HIGH')
    med = sum(1 for s in signals if s.signal_quality == 'MEDIUM')
    low = sum(1 for s in signals if s.signal_quality == 'LOW')
    
    print(f"HIGH: {high}")
    print(f"MEDIUM: {med}")
    print(f"LOW: {low}")
    print(f"INSUFFICIENT: {insufficient_signals}")
    
    print("\nEMBEDDING")
    eligible = sum(1 for s in signals if s.signal_quality != 'INSUFFICIENT' and s.canonical_text)
    print(f"Eligible: {eligible}")
    print(f"Ineligible: {len(signals) - eligible}")
    print(f"Already embedded: {emb_count}")
    
    print("\nFUNNEL")
    print(f"Posts: {len(posts)}")
    
    # Calculate funnel accurately mapping each post!
    posts_with_any_content = 0
    posts_with_canonical = 0
    posts_quality_passed = 0
    posts_embedded = 0
    
    reasons_count = {}
    
    for post in posts:
        post_sources = [s for s in sources if s.post_id == post.id]
        has_content = any(s.raw_text and len(s.raw_text.strip()) > 0 for s in post_sources)
        if has_content: posts_with_any_content += 1
        
        # Link ProcessedSignal via the post's source_ids vs sources
        post_signal = next((sig for sig in signals if sig.source_metadata and post_sources and str(post_sources[0].id) in str(sig.source_metadata.get('all_source_ids', []))), None)
        
        # In this POC, InstagramPost -> ProcessedSignal directly linked via collection? Wait. 
        # Actually ProcessedSignal doesn't have a post_id natively in the schema from stage 5!
        # It's mapped via CollectionRun, but wait, if it's 1-to-1, let's just use overall DB funnel counts!
        
        if post_signal is None:
            # Let's check by iterating signals which map to these sources!
            for sig in signals:
                if sig.source_metadata:
                    all_ids = sig.source_metadata.get('all_source_ids', [])
                    if any(src.id in all_ids for src in post_sources):
                        post_signal = sig
                        break
        
        if post_signal:
            if post_signal.canonical_text and len(post_signal.canonical_text.strip()) > 0:
                posts_with_canonical += 1
            
            if post_signal.signal_quality != 'INSUFFICIENT':
                posts_quality_passed += 1
                
            if post_signal.embedding:
                posts_embedded += 1
                
            # Classify reasons
            if post_signal.signal_quality == 'INSUFFICIENT':
                reason = "UNKNOWN"
                if not has_content:
                    reason = "EMPTY_CAPTION + NO_OCR + NO_ASR"
                elif not post_signal.canonical_text or len(post_signal.canonical_text.strip()) == 0:
                    reason = "CANONICALIZATION_FAILURE"
                else: # Has text but dropped due to length/content
                    # Emojis or hashtags?
                    text = post_signal.canonical_text.strip()
                    if text.startswith('#') and len(text.split()) == len([w for w in text.split() if w.startswith('#')]):
                        reason = "ONLY_HASHTAGS"
                    elif len(text) < 15:
                        reason = "TOO_SHORT"
                    else:
                        reason = "OTHER_METADATA_NOISE"
                
                reasons_count[reason] = reasons_count.get(reason, 0) + 1

    print(f"↓")
    print(f"Content: {posts_with_any_content}")
    print(f"↓")
    print(f"Canonical: {posts_with_canonical}")
    print(f"↓")
    print(f"Quality: {posts_quality_passed}")
    print(f"↓")
    print(f"Embedding eligible: {eligible}")
    
    print("\nTOP EXCLUSION REASONS")
    sorted_reasons = sorted(reasons_count.items(), key=lambda x: x[1], reverse=True)
    for i, (r, c) in enumerate(sorted_reasons, 1):
        print(f"{i}. {r}: {c}")
        
    print("\nROOT CAUSE:")
    if reasons_count.get("EMPTY_CAPTION + NO_OCR + NO_ASR", 0) > 30:
        print("A - EXPECTED DATA SPARSITY (Most Instagram Posts from this target legitimately have NO captions or text)")
    else:
        print("C - PROCESSING FAILURE (Content extracted but dropped)")
    
    print("========================================")

if __name__ == "__main__":
    audit()
