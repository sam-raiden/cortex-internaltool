import os
import argparse
import time
from playwright.sync_api import sync_playwright

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost
from app.collectors.instagram.parser import InstagramParser
from app.processing.caption_purifier import CaptionPurifier

def repair():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--post-id", type=str)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    
    if not args.all and not args.dry_run and not args.post_id:
        print("Defaulting to dry-run out of safety...")
        args.dry_run = True
        
    db = SessionLocal()
    query = db.query(InstagramPost)
    if args.post_id:
        query = query.filter(InstagramPost.instagram_post_id == args.post_id)
        
    if not args.all and not args.post_id:
        query = query.limit(args.limit)
        
    posts = query.all()
    if not posts:
        print("No posts found.")
        return
        
    purifier = CaptionPurifier()
        
    state_path = ".local/instagram/storage_state.json"
    if not os.path.exists(state_path):
        state_path = None
        
    print(f"Posts targeted: {len(posts)}")
    print(f"Executing with dry_run={args.dry_run}")
    
    stat_previously_populated = 0
    stat_recovered = 0
    stat_missing = 0
    stat_failures = 0
    
    source_stats = {"og:description": 0, "meta description": 0, "none": 0, "other": 0}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=state_path)
        page = ctx.new_page()
        
        for post in posts:
            if post.caption and str(post.caption).strip():
                print(f"[{post.instagram_post_id}] ALREADY_VALID")
                stat_previously_populated += 1
                continue
                
            try:
                page.goto(post.post_url)
                page.wait_for_load_state("networkidle")
                time.sleep(1) # Extra settling safely natively
                
                metadata = InstagramParser.extract_post_metadata(page)
                raw_caption = metadata.get("caption")
                source = metadata.get("metadata_source") or "none"
                
                if raw_caption:
                    cleaned_caption = purifier.purify(raw_caption)
                    if cleaned_caption and cleaned_caption.strip():
                        print(f"[{post.instagram_post_id}] UPDATED from {source}")
                        
                        source_stats[source] = source_stats.get(source, 0) + 1
                        stat_recovered += 1
                        
                        if not args.dry_run:
                            post.caption = cleaned_caption
                            db.commit()
                    else:
                        print(f"[{post.instagram_post_id}] NO_RELIABLE_DATA (purified was empty)")
                        source_stats["none"] += 1
                        stat_missing += 1
                else:
                    print(f"[{post.instagram_post_id}] NO_RELIABLE_DATA")
                    source_stats["none"] += 1
                    stat_missing += 1
                    
            except Exception as e:
                print(f"[{post.instagram_post_id}] SKIPPED/FAIL (Exception: {e})")
                stat_failures += 1
                
        browser.close()
    db.close()
    
    print("\n========================================")
    print("REPAIR VALIDATION RESULTS")
    print("========================================")
    print(f"Posts inspected: {len(posts)}")
    print(f"Previously populated captions: {stat_previously_populated}")
    print(f"New captions recovered: {stat_recovered}")
    print(f"Still missing: {stat_missing}")
    print(f"Extraction failures: {stat_failures}")
    
    print("\nSources:")
    for k, v in source_stats.items():
        if v > 0:
            print(f"{k}: {v}")
            
if __name__ == "__main__":
    repair()
