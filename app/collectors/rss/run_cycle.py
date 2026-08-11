import datetime
import json
import logging
import pathlib
import uuid
from typing import List, Optional

from sqlalchemy.exc import OperationalError, PendingRollbackError

from app.collectors.rss.collector import RSSCollector
from app.models.schema import Source
from app.processing.normalize_raw_content import create_caption_sources
from app.services.collection_run import CollectionRunService
from app.storage.database import SessionLocal

logger = logging.getLogger(__name__)


def execute_cycle(vertical_scope: str = "ALL", sources: Optional[List[Source]] = None, dry_run: bool = False):
    db = SessionLocal()
    try:
        if sources is None:
            sources = db.query(Source).filter(Source.platform == "rss", Source.enabled == True).all()

        run_id = f"run_{uuid.uuid4().hex[:8]}"
        start_time = datetime.datetime.utcnow()
        run_db = CollectionRunService.start_run(db, run_id, "N/A", vertical_scope)
        # Captured once as a plain int -- log_page_result() commits on every
        # call, which expires every ORM object on this session (default
        # expire_on_commit), so re-reading run_db.id on later loop
        # iterations can itself trigger a DB query. Confirmed live: a
        # transient connection drop turned that into an uncaught crash here,
        # discarding an already-successful collection run's bookkeeping.
        run_db_id = run_db.id

        collector = RSSCollector(dry_run=dry_run)
        batch = collector.run_batch(sources, vertical_scope=vertical_scope)
        batch.run_id = run_id
        finish_time = datetime.datetime.utcnow()

        for external_id, res in batch.metadata.get("results", []):
            try:
                CollectionRunService.log_page_result(db, run_db_id, external_id, res)
            except (OperationalError, PendingRollbackError):
                # Same hard-connection-abort recovery as the collectors
                # themselves (see app/collectors/rss/collector.py) -- close()
                # lets this session transparently get a fresh connection on
                # its next use, instead of leaving it in a state where every
                # remaining source's bookkeeping call also fails.
                logger.warning(f"Connection drop logging page result for {external_id}, recovering session")
                try:
                    db.close()
                except Exception:
                    pass
                db = SessionLocal()

        try:
            CollectionRunService.complete_run(db, run_db_id, batch)
        except (OperationalError, PendingRollbackError):
            logger.warning("Connection drop completing run, recovering session")
            db.close()
            db = SessionLocal()
        try:
            normalization_report = create_caption_sources(db)
        except (OperationalError, PendingRollbackError):
            # Same recovery as the collection/logging phases above -- a long
            # batch (real 80+ source runs observed taking several minutes)
            # gives a transient connection drop a real window to land here
            # too, and this step runs once at the very end, so losing it
            # would silently skip normalizing an otherwise fully-successful
            # collection run.
            logger.warning("Connection drop during normalization, recovering session and retrying once")
            db.close()
            db = SessionLocal()
            normalization_report = create_caption_sources(db)

        report_payload = {
            "run_id": run_id,
            "platform": "rss",
            "started_at": start_time.isoformat(),
            "finished_at": finish_time.isoformat(),
            "duration_ms": batch.duration_ms,
            "sources_attempted": batch.pages_attempted,
            "sources_successful": batch.pages_successful,
            "sources_failed": batch.pages_failed,
            "items_discovered": batch.items_discovered,
            "items_created": batch.items_created,
            "items_skipped": batch.items_skipped,
            "overall_status": batch.status,
            "errors": batch.errors,
            "normalization": normalization_report,
        }

        out_dir = pathlib.Path("output/repeatability/rss")
        out_dir.mkdir(parents=True, exist_ok=True)
        cycle_num = len(list(out_dir.glob("run_*.json"))) + 1
        with open(out_dir / f"run_{cycle_num:03d}.json", "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2)

        print("========================================")
        print(f"RSS COLLECTION — CYCLE {cycle_num}")
        print("========================================")
        print(f"Run ID: {run_id}")
        print(f"Sources attempted: {batch.pages_attempted}")
        print(f"Sources successful: {batch.pages_successful}")
        print(f"Sources failed: {batch.pages_failed}")
        print(f"Items created: {batch.items_created}")
        print(f"Overall status: {batch.status}")
        print("========================================")

        return batch
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    scope = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    execute_cycle(vertical_scope=scope)
