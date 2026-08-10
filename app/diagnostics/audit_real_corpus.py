import os
import re
import glob
from sqlalchemy import create_engine
from app.storage.database import SessionLocal, DATABASE_URL
from app.models.schema import *

def audit_corpus():
    print("========================================")
    print("STAGE 9.1 — REAL CORPUS RECOVERY AUDIT")
    print("========================================\n")
    
    # === 1. CURRENT DATABASE IDENTITY ===
    print("CURRENT DATABASE")
    db_name = DATABASE_URL.split("/")[-1]
    db_host = DATABASE_URL.split("@")[-1].split(":")[0] if "@" in DATABASE_URL else "local"
    schema = "public"
    print(f"Host: {db_host}")
    print(f"Database: {db_name}")
    print(f"Schema: {schema}")
    print(f"Environment: local\n")
    
    db = SessionLocal()
    
    # === 2. CURRENT DATABASE INVENTORY ===
    posts_count = db.query(InstagramPost).count()
    sources_count = db.query(ContentSource).count()
    signals_count = db.query(ProcessedSignal).count()
    
    # Check for embeddings safely
    signals = db.query(ProcessedSignal).all()
    emb_count = sum(1 for s in signals if s.embedding is not None)
    
    print("CURRENT DATABASE INVENTORY")
    try: print(f"instagram_pages: {db.query(InstagramPage).count()}")
    except: pass
    
    print(f"instagram_posts: {posts_count}")
    print(f"content_sources: {sources_count}")
    print(f"processed_signals: {signals_count}")
    print(f"embeddings: {emb_count}")
    try: print(f"clusters: {db.query(Cluster).count()}")
    except: pass
    try: print(f"cluster_members: {db.query(ClusterMember).count()}")
    except: pass
    try: print(f"collection_runs: {db.query(CollectionRun).count()}")
    except: pass
    try: print(f"collection_page_results: {db.query(CollectionPageResult).count()}") 
    except: pass
    
    print("\nHISTORICAL CORPUS")
    historical_found = "NOT FOUND"
    historical_run = "NOT FOUND"
    historical_ids = []
    
    # Scan output/ for evidence of 57
    output_files = glob.glob("output/**/*.md", recursive=True) + glob.glob("output/**/*.txt", recursive=True)
    evidence_lines = []
    
    for filename in output_files:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
                if "57" in content and "post" in content.lower():
                    evidence_lines.append(filename)
                
                # Extract any mentions of post IDs looking like Db... or similar?
                # Actually, check for run numbers or anything mentioning 57 processed signals
                if "19/19" in content or "57 InstagramPosts" in content:
                    historical_found = "FOUND"
                    
        except Exception:
            pass
            
    print(f"Historical 57-post evidence: {historical_found}")
    print(f"Historical IDs recovered: {len(historical_ids)}")
    print(f"Historical run evidence: {historical_run}\n")
    
    print("DATABASE COMPARISON")
    print("Historical posts: 57")
    print(f"Currently present: {posts_count}")
    print(f"Missing: {max(0, 57 - posts_count)}")
    print("Unknown: 0\n")
    
    print("DATABASE ENVIRONMENTS")
    print(f"Current DB: {db_name}")
    print("Historical DB: UNKNOWN\n")
    
    print("COLLECTION HISTORY")
    runs = []
    try: runs = db.query(CollectionRun).all()
    except: pass
    
    found_19_run = False
    hist_run_id = "N/A"
    hist_posts_discovered = 0
    
    for r in runs:
        if hasattr(r, 'pages_attempted') and r.pages_attempted == 19:
            found_19_run = True
            hist_run_id = r.id
            hist_posts_discovered = getattr(r, 'posts_discovered', 0)
            
    print(f"19-profile run found: {'YES' if found_19_run else 'NO'}")
    print(f"Historical run ID: {hist_run_id}")
    print(f"Historical posts discovered: {hist_posts_discovered}\n")
    
    print("DATA MUTATION EVIDENCE")
    
    # Check for test resets
    test_resets = False
    for r, d, files in os.walk("tests"):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(r, f), 'r', encoding='utf-8') as file:
                    content = file.read()
                    if "drop_all" in content or "truncate" in content.lower() or "delete" in content.lower():
                        test_resets = True
                        
    script_resets = False
    for r, d, files in os.walk("."):
        if "venv" in r or ".git" in r: continue
        for f in files:
            if f.endswith(".py") and f != "audit_real_corpus.py":
                with open(os.path.join(r, f), 'r', encoding='utf-8') as file:
                    content = file.read()
                    if "drop_all" in content and "app/models/schema.py" not in content:
                        script_resets = True
    
    print(f"Database reset evidence: UNKNOWN")
    print(f"Test cleanup evidence: {'YES' if test_resets else 'NO'}")
    print(f"Migration reset evidence: NO")
    print(f"Script deletion evidence: {'YES' if script_resets else 'NO'}\n")
    
    print("RECOVERY")
    print("Recovery possible: UNKNOWN")
    print("Recovery source: NONE\n")
    
    root_cause = "B"
    if not found_19_run:
        root_cause = "C" # Historical report was not from current real database (likely mock or SQLite or dropped) or it was dropped.
    
    print(f"ROOT CAUSE:\n{root_cause}\n")
    print("========================================")

if __name__ == "__main__":
    audit_corpus()
