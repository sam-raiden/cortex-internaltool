from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.storage.database import get_db
from app.services.collection_run import CollectionRunService
from app.models.schema import CollectionRun, CollectionPageResult

router = APIRouter(prefix="/api/collection-runs", tags=["observability"])

def serialize_run(run: CollectionRun):
    return {
        "run_id": run.run_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        
        "pages": {
            "attempted": run.pages_attempted,
            "successful": run.pages_successful,
            "failed": run.pages_failed
        },
        "posts": {
            "discovered": run.posts_discovered,
            "unique": run.unique_posts,
            "new": run.new_posts,
            "existing": run.existing_posts
        },
        "errors": {
            "parser": run.parser_errors,
            "navigation": run.navigation_errors,
            "timeouts": run.timeout_errors
        },
        "access_events": {
            "login_wall": run.login_wall_events,
            "challenge": run.challenge_events,
            "access_denied": run.access_denied_events,
            "rate_limit": run.rate_limit_indicators
        }
    }

@router.get("")
def list_runs(limit: int = 10, db: Session = Depends(get_db)):
    runs = CollectionRunService.get_latest_runs(db, limit)
    return [serialize_run(r) for r in runs]

@router.get("/statistics")
def run_statistics(db: Session = Depends(get_db)):
    return CollectionRunService.get_run_statistics(db)

@router.get("/access-events")
def access_events(limit: int = 10, db: Session = Depends(get_db)):
    runs = CollectionRunService.get_runs_with_access_events(db, limit)
    return [serialize_run(r) for r in runs]

@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = CollectionRunService.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return serialize_run(run)

@router.get("/{run_id}/pages")
def get_run_pages(run_id: str, db: Session = Depends(get_db)):
    run = CollectionRunService.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    pages = CollectionRunService.get_run_page_results(db, run.id)
    return [
        {
            "page_id": p.source_id,
            "status": p.status,
            "duration_ms": p.duration_ms,
            "posts_discovered": p.posts_discovered,
            "new_posts": p.new_posts,
            "existing_posts": p.existing_posts,
            "error_type": p.error_type
        } for p in pages
    ]

@router.get("/{run_id}/errors")
def get_run_errors(run_id: str, db: Session = Depends(get_db)):
    run = CollectionRunService.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    pages = CollectionRunService.get_run_page_results(db, run.id)
    errors = [p for p in pages if p.error_type is not None]
    
    return [
        {
             "page_id": e.source_id,
             "error_type": e.error_type,
             "error_message": e.error_message
        } for e in errors
    ]
