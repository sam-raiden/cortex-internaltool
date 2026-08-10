import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.schema import CollectionRun, CollectionPageResult, InstagramPage, CollectionError
from app.collectors.instagram.models import CollectionResult, CollectionBatchResult

class CollectionRunService:
    @staticmethod
    def start_run(db: Session, run_id: str, session_state: str = "UNKNOWN", vertical_scope: str = "ALL") -> CollectionRun:
        # Cleanup previously orphan RUNNING runs (interrupt recovery)
        orphans = db.query(CollectionRun).filter(CollectionRun.status == "RUNNING").all()
        for orphan in orphans:
            orphan.status = "FAILED"
            orphan.finished_at = datetime.datetime.utcnow()
        if orphans:
            db.commit()
            
        run = CollectionRun(
            run_id=run_id,
            vertical_scope=vertical_scope,
            status="RUNNING",
            session_state=session_state,
            started_at=datetime.datetime.utcnow()
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def log_page_result(db: Session, run_internal_id: int, page_username: str, page_res: CollectionResult) -> CollectionPageResult:
        # Fetch postgres page
        page = db.query(InstagramPage).filter(InstagramPage.username == page_username).first()
        if not page:
            return None # Skip if not registered, though shouldn't happen
            
        pr = CollectionPageResult(
            run_internal_id=run_internal_id,
            page_id=page.id,
            status="SUCCESS" if page_res.success else "FAILED",
            duration_ms=page_res.duration_ms,
            posts_discovered=page_res.posts_discovered,
            new_posts=page_res.new_posts,
            existing_posts=page_res.existing_posts,
            error_type=page_res.error_type,
            error_message=page_res.error_message,
        )
        db.add(pr)
        
        # Log to collection_errors if there's a strict failure
        if not page_res.success and page_res.error_type:
            err = CollectionError(
                run_id=run_internal_id,
                page_id=page.id,
                error_type=page_res.error_type,
                error_message=page_res.error_message
            )
            db.add(err)
            
        db.commit()
        db.refresh(pr)
        return pr

    @staticmethod
    def complete_run(db: Session, run_internal_id: int, batch: CollectionBatchResult) -> CollectionRun:
        run = db.query(CollectionRun).filter(CollectionRun.id == run_internal_id).first()
        if not run:
            return None
            
        run.finished_at = datetime.datetime.utcnow()
        run.status = batch.status
        run.session_state = "AUTHENTICATED" if batch.session_state_valid else "SESSION_EXPIRED"
        
        run.pages_attempted = batch.pages_attempted
        run.pages_successful = batch.pages_successful
        run.pages_failed = batch.pages_failed
        
        run.posts_discovered = batch.posts_discovered
        run.unique_posts = batch.posts_with_stable_ids
        run.new_posts = batch.new_posts
        run.existing_posts = batch.existing_posts
        
        run.parser_errors = batch.parser_failures
        
        run.navigation_errors = len([e for e in batch.errors if e.get("error") == "timeout"])
        run.timeout_errors = batch.timeouts
        
        run.login_wall_events = batch.login_challenges
        run.challenge_events = len([e for e in batch.errors if e.get("error") == "challenge_detected"])
        run.access_denied_events = batch.access_denied_events
        run.rate_limit_indicators = len([e for e in batch.errors if e.get("error") == "rate_limited"])
        
        run.duration_ms = batch.duration_ms
        
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def get_run(db: Session, run_id: str):
        return db.query(CollectionRun).filter(CollectionRun.run_id == run_id).first()
        
    @staticmethod
    def get_latest_runs(db: Session, limit: int = 10):
        return db.query(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(limit).all()

    @staticmethod
    def get_failed_runs(db: Session, limit: int = 10):
        return db.query(CollectionRun).filter(
            CollectionRun.status.in_(["FAILED", "DEGRADED", "BLOCKED"])
        ).order_by(CollectionRun.started_at.desc()).limit(limit).all()
        
    @staticmethod
    def get_runs_with_access_events(db: Session, limit: int = 10):
        return db.query(CollectionRun).filter(
            or_(
                CollectionRun.login_wall_events > 0,
                CollectionRun.challenge_events > 0,
                CollectionRun.access_denied_events > 0,
                CollectionRun.rate_limit_indicators > 0
            )
        ).order_by(CollectionRun.started_at.desc()).limit(limit).all()
        
    @staticmethod
    def get_page_history(db: Session, page_id: int, limit: int = 10):
        return db.query(CollectionPageResult).filter(
            CollectionPageResult.page_id == page_id
        ).order_by(CollectionPageResult.started_at.desc()).limit(limit).all()
        
    @staticmethod
    def get_run_page_results(db: Session, run_internal_id: int):
        return db.query(CollectionPageResult).filter(
            CollectionPageResult.run_internal_id == run_internal_id
        ).all()
        
    @staticmethod
    def get_run_statistics(db: Session):
        total_runs = db.query(CollectionRun).count()
        success = db.query(CollectionRun).filter(CollectionRun.status == "SUCCESS").count()
        return {
            "total_runs": total_runs,
            "successful_runs": success,
        }
