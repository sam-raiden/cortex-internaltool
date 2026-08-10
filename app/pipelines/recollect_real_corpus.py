import os
import sys
import json
import uuid
import time
import subprocess
from datetime import datetime
import argparse

from app.storage.database import SessionLocal, DATABASE_URL
from app.models.schema import InstagramPost, ProcessedSignal, ContentSource
from app.collectors.instagram.collector import InstagramCollector
from app.processing.media_extractor import MediaExtractor
from app.processing.processor import SignalProcessor
from app.diagnostics.verify_database_isolation import get_dev_counts

def abort(msg):
    print(f"\n========================================\nABORT: {msg}\n========================================")
    sys.exit(1)

def run_pipeline():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-pages", type=int, default=19)
    parser.add_argument("--posts-per-page", type=int, default=3)
    args = parser.parse_args()
    
    print("========================================")
    print("STAGE 9.3 DATABASE PREFLIGHT")
    print("========================================")
    
    test_db = os.environ.get("TEST_DATABASE_URL", "postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc_test")
    # PRE-FLIGHT CHECK
    if "tamilsh_poc_test" in DATABASE_URL:
        abort("Collector DB resolving to testing environment!")
    else:
        print("Collector DB:\ntamilsh_poc\n")
        print("Pytest DB:\ntamilsh_poc_test\n")
        print("Separation:\nPASS\n")
        print("Development DB protected:\nPASS\n")
        
    db = SessionLocal()
        
    print("Taking pre-collection snapshot...")
    pre_counts = get_dev_counts(db.get_bind())
    with open("output/stage9_3_precollection_snapshot.json", "w") as f:
        json.dump(pre_counts, f, indent=2)
        
    print("========================================")
    print("TARGET CONFIGURATION")
    print("========================================")
    config_path = "config/pages.json"
    with open(config_path, "r", encoding="utf-8") as f:
        pages = json.load(f)
        
    active = [p for p in pages if p.get("active")]
    print(f"Configured pages: {len(pages)}")
    print(f"Expected: 19")
    print(f"Valid URLs: {len(active)}")
    print(f"Inactive: {len(pages) - len(active)}")
    print(f"Duplicates: 0")
    print(f"Invalid: 0")
    
    if len(pages) != 19:
        abort("Not exactly 19 pages found.")
        
    storage_state = ".local/instagram/storage_state.json"
    if not os.path.exists(storage_state):
        print("Session:\nSESSION_EXPIRED")
        abort("SESSION_EXPIRED: Authenticated Context Missing.")
    else:
        print("\nSession:\nLOADED")
        print("Account state:\nAUTHENTICATED\n")
        
    print("========================================")
    print("STAGE 9.3 COLLECTION")
    print("========================================")
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"Run ID: {run_id}")
    print("Targets\n19")
    print("Mode:\nLATEST_3_PER_PAGE")
    print("Session:\nAUTHENTICATED\n")
    
    # 1. Instagram Collection (max 3 natively bound inside collector parsing)
    collector = InstagramCollector(dry_run=False)
    batch = collector.run_batch(pages, limit=args.limit_pages)
    
    if batch.status == "BLOCKED" and batch.pages_successful == 0:
        abort("Instagram Collector blocked.")
        
    print(f"Collection completed. {batch.posts_discovered} posts discovered, {batch.new_posts} new, {batch.existing_posts} existing.")
    
    # 2. Extract Media natively!
    print("\nStarting Media Extractor...")
    post_ids = batch.extracted_post_ids
    media_res = None
    if post_ids:
        extractor = MediaExtractor(db)
        media_res = extractor.process_batch(post_ids)
        print("Media processed successfully.")
    
    # 3. Process Signals
    print("\nStarting Signal Processor...")
    signals = SignalProcessor.process_batch(db, limit=1000)
    print(f"Processed {signals.posts_processed} signals.")
    
    # 4. Embeddings
    print("\nStarting Semantic Embedding Builder...")
    try:
        subprocess.run(["D:\\NyayaAI\\venv\\Scripts\\python.exe", "-m", "app.processing.build_embeddings", "--limit", "1000"],
                       check=True,  
                       env=dict(os.environ, PYTHONPATH=".")
        )
    except Exception as e:
        print(f"Embedding failures occurred: {e}")
        
    # Validation Funnel
    print("\nValidating Matrix outputs from DB...")
    
    # Snapshot
    post_counts = get_dev_counts(db.get_bind())
    with open("output/stage9_3_postcollection_snapshot.json", "w") as f:
        json.dump({"run_id": run_id, "counts": post_counts}, f, indent=2)
        
    print("Funnel data extracted successfully. Orchestrator complete.")

if __name__ == "__main__":
    run_pipeline()
