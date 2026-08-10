import json
import pathlib
import datetime
from app.storage.database import SessionLocal
from app.models.schema import CollectionRun, CollectionPageResult, InstagramPage

def migrate():
    source_path = pathlib.Path("output/repeatability/run_001.json")
    if not source_path.exists():
        # Using sorted glob to pick the earliest run file
        existing_files = sorted(list(pathlib.Path("output/repeatability").glob("*.json")))
        if not existing_files:
            print("No run_001.json found.")
            return
        source_path = existing_files[0]

    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    run_id = data.get("run_id")
    
    db = SessionLocal()
    
    # Idempotency check 
    exists = db.query(CollectionRun).filter(CollectionRun.run_id == run_id).first()
    if exists:
        print(f"Run {run_id} already migrated.")
        db.close()
        return

    # Base dates
    start = datetime.datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.datetime.utcnow()
    finish = datetime.datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else datetime.datetime.utcnow()
    
    run = CollectionRun(
        run_id=run_id,
        status=data.get("overall_status", "SUCCESS"),
        session_state=data.get("session_state", "UNKNOWN"),
        started_at=start,
        finished_at=finish,
        
        pages_attempted=data.get("pages_attempted", 0),
        pages_successful=data.get("pages_accessible", 0),
        pages_failed=data.get("pages_failed", 0),
        
        posts_discovered=data.get("posts_discovered", 0),
        unique_posts=data.get("unique_posts", 0),
        new_posts=data.get("new_posts", 0),
        existing_posts=data.get("existing_posts", 0),
        
        parser_errors=data.get("parser_errors", 0),
        navigation_errors=data.get("navigation_errors", 0),
        timeout_errors=data.get("timeouts", 0),
        
        login_wall_events=data.get("login_wall_events", 0),
        challenge_events=data.get("challenge_events", 0),
        access_denied_events=data.get("access_denied_events", 0),
        rate_limit_indicators=data.get("rate_limit_indicators", 0),
        
        duration_ms=data.get("duration_ms", 0)
    )
    
    db.add(run)
    db.commit()
    db.refresh(run)

    for p in data.get("per_page_metrics", []):
        username = p.get("username")
        page = db.query(InstagramPage).filter(InstagramPage.username == username).first()
        if not page:
            continue
            
        pr = CollectionPageResult(
            run_internal_id=run.id,
            page_id=page.id,
            status=p.get("status", "FAILED"),
            duration_ms=p.get("duration_ms", 0),
            posts_discovered=p.get("posts_found", 0),
            new_posts=p.get("new_posts", 0),
            existing_posts=p.get("existing_posts", 0),
            error_type=p.get("error_type"),
            error_message=p.get("error_message")
        )
        db.add(pr)
        
    db.commit()
    print(f"Successfully migrated {run_id} into CollectionRun.")
    db.close()

if __name__ == "__main__":
    migrate()
