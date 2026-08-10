import argparse
from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource

def rebuild():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    posts = db.query(InstagramPost).all()
    
    cap_before = db.query(ContentSource).filter(ContentSource.source_type == "CAPTION").count()
    
    new_sources = 0
    duplicates = 0
    
    for post in posts:
        if post.caption and post.caption.strip():
            # Check idempotency
            existing = db.query(ContentSource).filter_by(
                post_id=post.id, 
                source_type="CAPTION"
            ).first()
            
            if existing:
                if existing.raw_text != post.caption:
                    existing.raw_text = post.caption
                    db.commit()
                duplicates += 1
            else:
                db.add(ContentSource(
                    post_id=post.id,
                    source_type="CAPTION",
                    raw_text=post.caption,
                    language="unknown",
                    confidence=1.0,
                    duration_ms=0
                ))
                db.commit()
                new_sources += 1
                
    cap_after = db.query(ContentSource).filter(ContentSource.source_type == "CAPTION").count()
    db.close()
    
    print("========================================")
    print("CONTENTSOURCE REBUILD RESULTS")
    print("========================================")
    print(f"Caption ContentSources before: {cap_before}")
    print(f"Caption ContentSources after: {cap_after}")
    print(f"New Caption ContentSources: {new_sources}")
    print(f"Duplicates prevented: {duplicates}")

if __name__ == "__main__":
    rebuild()
