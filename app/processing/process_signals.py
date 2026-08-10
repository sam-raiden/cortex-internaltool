import argparse
import sys
import json
from app.storage.database import SessionLocal
from app.processing.processor import SignalProcessor
from app.models.schema import InstagramPost

def main():
    parser = argparse.ArgumentParser(description="Deterministic Content Signal Processing Pipeline")
    parser.add_argument("--post-id", type=str, help="Process a single specific post ID")
    parser.add_argument("--limit", type=int, default=1000, help="Batch extraction limit")
    
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        if args.post_id:
            print(f"Processing SINGLE post: {args.post_id}")
            post = db.query(InstagramPost).filter(InstagramPost.instagram_post_id == args.post_id).first()
            if not post:
                print("Error: Post ID not found in database.")
                sys.exit(1)
                
            res = SignalProcessor.process_post(db, post)
            
            # Print expected output formats constraints
            print(f"POST ID: {res.post_id}")
            
            if res.success and res.error_type != "skipped_duplicate":
                # Fetch created signal natively
                from app.models.schema import ProcessedSignal
                sig = db.query(ProcessedSignal).filter_by(post_id=post.id).first()
                if sig:
                    print(f"RAW TEXT: {sig.raw_text}")
                    print(f"HASHTAGS: {json.dumps(sig.extracted_hashtags)}")
                    print(f"LANGUAGE: {sig.language}")
                    print(f"CANONICAL TEXT: {sig.canonical_text}")
                    print(f"PROCESSOR VERSION: {sig.processor_version}")
                    print(f"STATUS: SUCCESS ({res.duration_ms}ms)")
            else:
                print(f"STATUS: SKIPPED/FAILED ({res.error_type})")
        else:
            print(f"Starting BATCH processing (Limit: {args.limit})")
            batch = SignalProcessor.process_batch(db, limit=args.limit)
            print("\n===============================")
            print("BATCH PROCESSING RESULTS")
            print("===============================")
            print(f"Posts attempted: {batch.posts_attempted}")
            print(f"Posts processed: {batch.posts_processed}")
            print(f"Posts skipped (duplicates): {batch.posts_skipped}")
            print(f"Posts failed: {batch.posts_failed}")
            print("Languages detected:")
            for lang, count in batch.languages_detected.items():
                print(f" - {lang}: {count}")
            print(f"Duration: {batch.duration_ms}ms")
            
    finally:
        db.close()

if __name__ == "__main__":
    main()
