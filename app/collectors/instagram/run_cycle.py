import logging
import os
import json
import uuid
import datetime
from typing import List, Optional
from sqlalchemy.exc import OperationalError, PendingRollbackError
from app.collectors.instagram.collector import InstagramCollector
from app.collectors.base import CollectionResult as GenericResult, CollectionBatchResult as GenericBatchResult
from app.storage.database import SessionLocal
from app.processing.normalize_raw_content import create_caption_sources
from app.services.collection_run import CollectionRunService
from app.collectors.instagram.models import CollectionBatchResult
from app.models.schema import Source
import pathlib

logger = logging.getLogger(__name__)


def _adapt_result(r) -> GenericResult:
    return GenericResult(
        platform="instagram",
        status="SUCCESS" if r.success else "FAILED",
        items_discovered=r.posts_discovered,
        items_created=r.new_posts,
        items_skipped=r.existing_posts,
        duration_ms=r.duration_ms,
        error_type=r.error_type,
        error_message=r.error_message,
    )


def _adapt_batch(b) -> GenericBatchResult:
    errors = [{"source": e.get("page"), "error_type": e.get("error"), "message": e.get("msg")} for e in b.errors]
    return GenericBatchResult(
        run_id=b.run_id, platform="instagram", status=b.status,
        pages_attempted=b.pages_attempted, pages_successful=b.pages_successful, pages_failed=b.pages_failed,
        items_discovered=b.posts_discovered, items_created=b.new_posts, items_skipped=b.existing_posts,
        duration_ms=b.duration_ms, errors=errors, session_state_valid=b.session_state_valid,
    )


def execute_cycle(vertical_scope: str = "ALL", sources: Optional[List[Source]] = None, dry_run: bool = False):
    if sources is not None:
        pages_config = [
            {"username": s.external_id, "url": s.url, "active": True, "vertical": s.vertical}
            for s in sources
        ]
    else:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../config/pages.json"))
        with open(config_path, "r", encoding="utf-8") as f:
            pages_config = json.load(f)

    # 1. Session health check
    state_path = pathlib.Path(".local/instagram/storage_state.json")
    auth_loaded = state_path.exists()

    # 2. Assign unique ID and timestamps
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_time = datetime.datetime.utcnow()

    db = SessionLocal()
    session_state = "AUTHENTICATED" if auth_loaded else "SESSION_EXPIRED"
    run_db = CollectionRunService.start_run(db, run_id, session_state, vertical_scope)
    # See app/collectors/rss/run_cycle.py's identical fix/comment --
    # captured once as a plain int since log_page_result()'s commits expire
    # run_db on this session, and a later re-read of run_db.id can itself
    # trigger a DB query that fails on a dropped connection.
    run_db_id = run_db.id

    if not auth_loaded:
        print("SESSION_EXPIRED")
        CollectionRunService.complete_run(db, run_db_id, _adapt_batch(CollectionBatchResult(status="FAILED")))
        db.close()
        return

    # 3. Collection
    collector = InstagramCollector(dry_run=dry_run)
    batch_result: CollectionBatchResult = collector.run_batch(pages_config, limit=len(pages_config) or 19, vertical_scope=vertical_scope)
    batch_result.run_id = run_id

    finish_time = datetime.datetime.utcnow()

    # If the circuit breaker stopped it and pages_successful=0, mark FAILED if not BLOCKED
    if batch_result.status == "SUCCESS":
        if batch_result.pages_failed > 0:
            batch_result.status = "PARTIAL"
        if batch_result.pages_attempted == 0:
            batch_result.status = "FAILED"

    # Persist page-results into observability layer
    for r in batch_result.results:
        try:
            CollectionRunService.log_page_result(db, run_db_id, r.page_username, _adapt_result(r))
        except (OperationalError, PendingRollbackError):
            # See app/collectors/rss/run_cycle.py's identical fix -- close()
            # lets this session transparently get a fresh connection on its
            # next use instead of leaving every remaining page's bookkeeping
            # call failing on a dropped transaction.
            logger.warning(f"Connection drop logging page result for {r.page_username}, recovering session")
            try:
                db.close()
            except Exception:
                pass
            db = SessionLocal()

    try:
        CollectionRunService.complete_run(db, run_db_id, _adapt_batch(batch_result))
    except (OperationalError, PendingRollbackError):
        logger.warning("Connection drop completing run, recovering session")
        db.close()
        db = SessionLocal()
    try:
        create_caption_sources(db)
    except (OperationalError, PendingRollbackError):
        # See app/collectors/rss/run_cycle.py's identical fix.
        logger.warning("Connection drop during normalization, recovering session and retrying once")
        db.close()
        db = SessionLocal()
        create_caption_sources(db)
    db.close()
            
    # Serialize results API payload
    profiles_with_3 = sum(1 for r in batch_result.results if r.posts_discovered >= 3)
    profiles_with_1_2 = sum(1 for r in batch_result.results if 1 <= r.posts_discovered < 3)
    profiles_with_0 = sum(1 for r in batch_result.results if r.posts_discovered == 0)

    report_payload = {
        "run_id": run_id,
        "started_at": start_time.isoformat(),
        "finished_at": finish_time.isoformat(),
        "duration_ms": batch_result.duration_ms,
        "session_state": "AUTHENTICATED" if auth_loaded else "SESSION_EXPIRED",
        "pages_attempted": batch_result.pages_attempted,
        "pages_accessible": batch_result.pages_successful,
        "pages_failed": batch_result.pages_failed,
        "posts_discovered": batch_result.posts_discovered,
        "unique_posts": batch_result.posts_with_stable_ids,
        "new_posts": batch_result.new_posts,
        "existing_posts": batch_result.existing_posts,
        "parser_errors": batch_result.parser_failures,
        "navigation_errors": len([e for e in batch_result.errors if e.get("error") == "timeout"]),
        "timeouts": batch_result.timeouts,
        "login_wall_events": batch_result.login_challenges,
        "challenge_events": len([e for e in batch_result.errors if e.get("error") == "challenge_detected"]),
        "access_denied_events": batch_result.access_denied_events,
        "rate_limit_indicators": len([e for e in batch_result.errors if e.get("error") == "rate_limited"]),
        "overall_status": batch_result.status,
        "per_page_metrics": [
            {
                "run_id": run_id,
                "username": r.page_username,
                "url": f"https://www.instagram.com/{r.page_username}/",
                "duration_ms": r.duration_ms,
                "status": "SUCCESS" if r.success else "FAILED",
                "posts_found": r.posts_discovered,
                "new_posts": r.new_posts,
                "existing_posts": r.existing_posts,
                "error_type": r.error_type,
                "error_message": r.error_message
            } for r in batch_result.results
        ]
    }

    # Persist
    out_dir = pathlib.Path("output/repeatability")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # List existing files to auto-increment
    existing_files = list(out_dir.glob("run_*.json"))
    cycle_num = len(existing_files) + 1
    file_name = f"run_{cycle_num:03d}.json"
    
    out_path = out_dir / file_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    # Output Cycle format
    print("========================================")
    print(f"INSTAGRAM REPEATABILITY — CYCLE {cycle_num}")
    print("========================================")
    print(f"Run ID:\n{run_id}\n")
    print(f"Started:\n{start_time.isoformat()}\n")
    print(f"Finished:\n{finish_time.isoformat()}\n")
    print(f"Duration:\n{batch_result.duration_ms}ms\n")
    
    print("SESSION\n")
    print(f"Authenticated:\n{'YES' if auth_loaded else 'NO'}\n")
    
    print("COLLECTION\n")
    print(f"Profiles attempted:\n{batch_result.pages_attempted}\n")
    print(f"Profiles accessible:\n{batch_result.pages_successful}\n")
    print(f"Profiles failed:\n{batch_result.pages_failed}\n")
    print(f"Profiles with 3 posts:\n{profiles_with_3}\n")
    print(f"Profiles with 1–2 posts:\n{profiles_with_1_2}\n")
    print(f"Profiles with 0 posts:\n{profiles_with_0}\n")
    print(f"Posts discovered:\n{batch_result.posts_discovered}\n")
    print(f"Unique posts:\n{batch_result.posts_with_stable_ids}\n")
    print(f"New posts:\n{batch_result.new_posts}\n")
    print(f"Existing posts:\n{batch_result.existing_posts}\n")
    
    print("ERRORS\n")
    print(f"Parser errors:\n{batch_result.parser_failures}\n")
    print(f"Navigation errors:\n{report_payload['navigation_errors']}\n")
    print(f"Timeouts:\n{batch_result.timeouts}\n")
    
    print("ACCESS EVENTS\n")
    print(f"Login wall:\n{batch_result.login_challenges}\n")
    print(f"Challenges:\n{report_payload['challenge_events']}\n")
    print(f"Access denied:\n{batch_result.access_denied_events}\n")
    print(f"Rate-limit indicators:\n{report_payload['rate_limit_indicators']}\n")
    
    print(f"Overall status:\n{batch_result.status}\n")
    print("========================================")

if __name__ == "__main__":
    import sys
    scope = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    execute_cycle(vertical_scope=scope)
