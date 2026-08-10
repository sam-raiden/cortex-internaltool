import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.schema import CollectionRun, CollectionPageResult, Source, CollectionError
from app.collectors.base import CollectionResult, CollectionBatchResult

# error_type values that map to a dedicated CollectionRun counter. Anything not in this
# set (from any platform) is counted as a generic parser_errors event.
_LOGIN_WALL_TYPES = ("login_required", "login_wall_overlay")
_CHALLENGE_TYPES = ("challenge_detected",)
_ACCESS_DENIED_TYPES = ("access_denied",)
_RATE_LIMIT_TYPES = ("rate_limited",)
_TIMEOUT_TYPES = ("timeout",)
_CLASSIFIED_TYPES = _LOGIN_WALL_TYPES + _CHALLENGE_TYPES + _ACCESS_DENIED_TYPES + _RATE_LIMIT_TYPES + _TIMEOUT_TYPES


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
    def log_page_result(db: Session, run_internal_id: int, source_external_id: str, result: CollectionResult) -> CollectionPageResult:
        source = db.query(Source).filter(Source.external_id == source_external_id).first()
        if not source:
            return None  # Skip if not registered, though shouldn't happen

        pr = CollectionPageResult(
            run_internal_id=run_internal_id,
            source_id=source.id,
            status=result.status,
            duration_ms=result.duration_ms,
            posts_discovered=result.items_discovered,
            new_posts=result.items_created,
            existing_posts=result.items_skipped,
            error_type=result.error_type,
            error_message=result.error_message,
        )
        db.add(pr)

        if result.status != "SUCCESS" and result.error_type:
            err = CollectionError(
                run_id=run_internal_id,
                source_id=source.id,
                error_type=result.error_type,
                error_message=result.error_message
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

        run.posts_discovered = batch.items_discovered
        run.unique_posts = batch.items_discovered
        run.new_posts = batch.items_created
        run.existing_posts = batch.items_skipped

        run.login_wall_events = len([e for e in batch.errors if e.get("error_type") in _LOGIN_WALL_TYPES])
        run.challenge_events = len([e for e in batch.errors if e.get("error_type") in _CHALLENGE_TYPES])
        run.access_denied_events = len([e for e in batch.errors if e.get("error_type") in _ACCESS_DENIED_TYPES])
        run.rate_limit_indicators = len([e for e in batch.errors if e.get("error_type") in _RATE_LIMIT_TYPES])
        run.navigation_errors = run.timeout_errors = len([e for e in batch.errors if e.get("error_type") in _TIMEOUT_TYPES])
        run.parser_errors = len([e for e in batch.errors if e.get("error_type") not in _CLASSIFIED_TYPES])

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
            CollectionPageResult.source_id == page_id
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
