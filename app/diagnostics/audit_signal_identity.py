from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.models.schema import ProcessedSignal, InstagramPost

def audit_identity():
    db: Session = SessionLocal()
    signals = db.query(ProcessedSignal).all()
    posts = db.query(InstagramPost).all()
    
    valid_ids = {p.id for p in posts}
    
    valid = 0
    null_id = 0
    orphans = 0
    post_signal_counts = {}
    
    for s in signals:
        if s.post_id is None:
            null_id += 1
        elif s.post_id not in valid_ids:
            orphans += 1
        else:
            valid += 1
            post_signal_counts[s.post_id] = post_signal_counts.get(s.post_id, 0) + 1
            
    duplicates = {k: v for k, v in post_signal_counts.items() if v > 1}
    
    print("========================================")
    print("SIGNAL IDENTITY AUDIT")
    print("========================================")
    print(f"Total ProcessedSignals: {len(signals)}")
    print(f"Signals with valid post_id: {valid}")
    print(f"Signals with NULL post_id: {null_id}")
    print(f"Orphan signals (invalid post_id): {orphans}")
    print(f"Posts with multiple signals: {len(duplicates)}")
    
    if duplicates:
        print("\nDUPLICATE SIGNALS:")
        for k, v in duplicates.items():
            print(f"- Post ID {k} maps to {v} signals")
            
    print("\nREASONS FOR DUPLICATE EXAMINED NATIVELY:")
    print("Zero duplicates expected if `SignalProcessor` successfully bypasses via idempotency. The system avoids duplicate inserts.")

    db.close()

if __name__ == "__main__":
    audit_identity()
