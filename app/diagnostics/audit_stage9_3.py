import os
import argparse
from sqlalchemy import create_engine, text
from app.storage.database import SessionLocal, DATABASE_URL

def audit():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=str, default="run_c0ddd34a")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    db = SessionLocal()
    conn = db.connection()
    
    print("========================================")
    print("STAGE 9.3.1 INTEGRITY AUDIT")
    print("========================================")
    
    # 1. DATABASE INVENTORY
    print("\n1. DATABASE INVENTORY")
    try: pages = conn.execute(text("SELECT count(*) FROM instagram_pages")).scalar()
    except: pages = 0
    posts = conn.execute(text("SELECT count(*) FROM instagram_posts")).scalar()
    sources = conn.execute(text("SELECT count(*) FROM content_sources")).scalar()
    signals = conn.execute(text("SELECT count(*) FROM processed_signals")).scalar()
    embeds = conn.execute(text("SELECT count(*) FROM processed_signals WHERE embedding IS NOT NULL")).scalar()
    try: runs = conn.execute(text("SELECT count(*) FROM collection_runs")).scalar()
    except: runs = 0
    try: res = conn.execute(text("SELECT count(*) FROM collection_page_results")).scalar()
    except: res = 0
    
    print(f"instagram_pages: {pages}")
    print(f"instagram_posts: {posts}")
    print(f"content_sources: {sources}")
    print(f"processed_signals: {signals}")
    print(f"embeddings: {embeds}")
    print(f"collection_runs: {runs}")
    print(f"collection_page_results: {res}")
    
    # 2. RUN VERIFICATION
    print(f"\n2. RUN VERIFICATION ({args.run_id})")
    run_record = None
    try:
        run_record = conn.execute(text(f"SELECT * FROM collection_runs WHERE run_id = '{args.run_id}'")).fetchone()
    except:
        pass
        
    if run_record:
        print("Exists in collection_runs: YES")
        print(f"run_id: {run_record.run_id}")
        print(f"status: {run_record.status}")
        print(f"pages_attempted: {run_record.pages_attempted}")
        print(f"pages_successful: {run_record.pages_successful}")
        print(f"posts_discovered: {run_record.posts_discovered}")
        print(f"new_posts: {run_record.new_posts}")
        print(f"existing_posts: {run_record.existing_posts}")
    else:
        print("Exists in collection_runs: NO")
        print("Data is stored via JSON files explicitly in output/repeatability/")
        
    # 3. VERIFY 59 POSTS
    print("\n3. POST VERIFICATION")
    post_rows = conn.execute(text("SELECT * FROM instagram_posts")).fetchall()
    print(f"Total: {len(post_rows)}")
    
    cap_not_null = 0
    cap_empty = 0
    cap_null = 0
    
    hash_not_null = 0
    media_url_not_null = 0
    thumb_url_not_null = 0
    
    for r in post_rows:
        c = r.caption
        if c is None:
            cap_null += 1
        else:
            cap_not_null += 1
            if str(c).strip() == "":
                cap_empty += 1
                
        if r.published_at is not None: hash_not_null += 1  # assuming this is just random field as hashtags are not in DB natively? Wait
        
    print(f"Caption available (IS NOT NULL): {cap_not_null}")
    print(f"Caption empty (whitespace): {cap_empty}")
    print(f"Caption NULL: {cap_null}")
    
    print("\nSAMPLE CAPTIONS (10)")
    for r in post_rows[:10]:
        c = str(r.caption).replace('\n', ' ')[:50]
        print(f"[{r.instagram_post_id}] {c}")
        
    # 5. CONTENTSOURCE VERIFICATION
    print("\n5. CONTENTSOURCE VERIFICATION")
    src_rows = conn.execute(text("SELECT source_type, count(*) FROM content_sources GROUP BY source_type")).fetchall()
    
    cap_s = sum(r[1] for r in src_rows if r[0] == "CAPTION")
    ocr_s = sum(r[1] for r in src_rows if r[0] == "OCR")
    asr_s = sum(r[1] for r in src_rows if r[0] == "ASR")
    print(f"CAPTION: {cap_s}")
    print(f"OCR: {ocr_s}")
    print(f"ASR: {asr_s}")
    print(f"Total: {sum(r[1] for r in src_rows)}")
    
    posts_with_src = conn.execute(text("SELECT count(DISTINCT post_id) FROM content_sources")).scalar()
    print(f"Distinct posts with ContentSource: {posts_with_src}")
    print(f"Posts with NO ContentSource: {posts - posts_with_src}")
    
    # 6. CAPTION -> CONTENTSOURCE TRACE
    print("\n6. TRACE CAPTION -> CONTENTSOURCE")
    for r in post_rows[:10]:
        has_src = conn.execute(text(f"SELECT COUNT(*) FROM content_sources WHERE post_id = {r.id}")).scalar()
        sig = conn.execute(text(f"SELECT * FROM processed_signals WHERE post_id = {r.id}")).fetchone()
        
        status = "MISSING" if r.caption is None else "DISCONNECTED" if has_src == 0 else "CONNECTED"
        if r.caption and not r.caption.strip(): status = "EMPTY"
        print(f"[{r.instagram_post_id}] {status}")
        
    # 7. PROCESSEDSIGNAL AUDIT
    print("\n7. PROCESSEDSIGNAL AUDIT")
    if signals > 0:
        sig_rows = conn.execute(text("SELECT * FROM processed_signals")).fetchall()
        empty_can = sum(1 for s in sig_rows if not s.canonical_text)
        non_empty_can = len(sig_rows) - empty_can
        print(f"Total: {len(sig_rows)}")
        print(f"empty canonical_text: {empty_can}")
        print(f"non-empty canonical_text: {non_empty_can}")
        
        print("\nQuality:")
        for q in ["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]:
            print(f"{q}: {sum(1 for s in sig_rows if s.signal_quality == q)}")
            
        print("\nLanguage:")
        for q in ["ta", "en", "mixed", "unknown"]:
            print(f"{q}: {sum(1 for s in sig_rows if s.language == q)}")
            
    # 13. OG METADATA
    print("\n13. INSTAGRAM OG METADATA CHECK")
    og_found = sum(1 for r in post_rows if r.caption and "likes" in r.caption.lower() and "comments" in r.caption.lower())
    print(f"Captions containing OG boilerplate: {og_found}")
    
    # OUTPUT FORMATTED DATA
    print("\n========================================")
    print(f"RAW POSTS: {posts}")
    print(f"CAPTIONS: {cap_not_null}")
    print(f"CONTENTSOURCES: {sources}")
    print(f"PROCESSED SIGNALS: {signals}")
    print(f"NON-EMPTY CANONICAL: {non_empty_can if signals > 0 else 0}")
    print(f"EMBEDDING ELIGIBLE: {embeds}")
    print(f"EMBEDDINGS: {embeds}")
    
    db.close()
    
if __name__ == "__main__":
    audit()
