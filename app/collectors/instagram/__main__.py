import json
import argparse
import sys
import os
import logging

from app.collectors.instagram.collector import InstagramCollector

logging.basicConfig(level=logging.INFO, format='[INSTAGRAM] %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Stage 3: Instagram Collector POC")
    parser.add_argument("--username", type=str, help="Run test on a single specific username")
    parser.add_argument("--limit", type=int, help="Limit to N pages from config")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to PostgreSQL")
    args = parser.parse_args()

    # Load configuration
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../config/pages.json"))
    with open(config_path, "r", encoding="utf-8") as f:
        pages_config = json.load(f)

    if args.username:
        pages_config = [
            {"username": args.username, "url": f"https://www.instagram.com/{args.username}/", "active": True}
        ]

    # Check for authentication state
    import pathlib
    state_path = pathlib.Path(".local/instagram/storage_state.json")
    auth_loaded = state_path.exists()
    
    collector = InstagramCollector(dry_run=args.dry_run)

    if args.limit == 1 or (args.username and args.limit is None):
        # Single-page test formatted output
        result = collector.run_batch(pages_config, limit=1)
        
        # Check if auth expired
        session_expired = False
        if auth_loaded and result.login_challenges > 0:
            session_expired = True

        print("\n========================================")
        print("AUTHENTICATED INSTAGRAM TEST")
        print("========================================")
        print(f"\nSession: {'LOADED' if auth_loaded else 'NOT LOADED'}")
        
        if session_expired:
            print("Account state:\nSESSION_EXPIRED\nPlease rerun python -m app.collectors.instagram.auth")
            print("========================================")
            return

        print(f"\nAccount state:\n{'AUTHENTICATED' if auth_loaded else 'UNAUTHENTICATED'}")
        
        target_page = pages_config[0].get('username') if not args.username else args.username
        print(f"\nTarget:\n@{target_page}")
        print(f"\nProfile:\n{'ACCESSIBLE' if result.pages_successful > 0 else 'INACCESSIBLE'}")
        
        print(f"\nPosts discovered:\n{result.posts_discovered}")
        
        if result.extracted_post_ids:
            print("")
            for i, pid in enumerate(result.extracted_post_ids, 1):
                print(f"{i}. post_id={pid}")
        
    else:
        # 5-page or 30-page test output
        result = collector.run_batch(pages_config, limit=args.limit)
        
        session_expired = auth_loaded and result.login_challenges > 0
        if session_expired:
            print("\nSESSION_EXPIRED - Please rerun manual authentication bootstrap\n")
            return
            
        print("\nCOLLECTION")
        print(f"Pages attempted     : {result.pages_attempted}")
        print(f"Pages accessible    : {result.pages_successful}")
        print(f"Pages failed        : {result.pages_failed}")
        print(f"Posts discovered    : {result.posts_discovered}")
        print(f"Posts with stable IDs: {result.posts_with_stable_ids}")
        
        print(f"\nLogin challenges    : {result.login_challenges}")
        print(f"Access-denied events: {result.access_denied_events}")
        print(f"Timeouts            : {result.timeouts}")
        print(f"Parser failures     : {result.parser_failures}")
        
        print(f"\nRuntime           : {result.duration_ms}ms")
        avg_time = result.duration_ms / max(1, result.pages_attempted)
        print(f"Average page time   : {avg_time:.0f}ms")
        
        if result.errors:
            print("\nFAILURES")
            for err in result.errors:
                print(f"- {err['page']}: {err['error']} ({err['msg']})")
                
    print("\n========================================")

if __name__ == "__main__":
    main()
