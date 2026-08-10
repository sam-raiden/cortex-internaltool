"""Stage 13 -- production YouTube Shorts collector.

Playwright-based, scraping public channel Shorts tabs -- no official API,
no authentication. Public pages need no login/session-state handling,
unlike Instagram, but that also means there is no login wall to detect: a
blocked or rate-limited channel just fails silently-ish (a changed page
layout, a consent wall, a CAPTCHA). This collector must degrade
gracefully per-source (and even per-video) -- one blocked or malformed
channel/video must never abort the whole batch.
"""
import datetime
import logging
import os
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectionBatchResult, CollectionResult
from app.collectors.youtube.browser import YouTubeBrowser
from app.collectors.youtube.parser import YouTubeShortsParser
from app.models.schema import RawContent, Source
from app.storage.database import SessionLocal

logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = float(os.environ.get("YOUTUBE_REQUEST_DELAY_SECONDS", "2"))


class YouTubeShortsCollector(BaseCollector):
    def __init__(self, dry_run: bool = False):
        super().__init__(dry_run=dry_run)

    def collect(self, source: Source, context: Optional[Dict] = None) -> CollectionResult:
        context = context or {}
        db: Optional[Session] = context.get("db")
        page = context.get("page")
        started = time.time()
        result = CollectionResult(source_id=getattr(source, "id", None), platform="youtube")

        if page is None:
            result.status, result.error_type, result.error_message = "FAILED", "collector_error", "no browser page in context"
            return self._finish(result, started)

        try:
            page.goto(source.url)
            page.wait_for_load_state("networkidle")

            block = YouTubeShortsParser.detect_block(page)
            if block:
                result.status, result.error_type = "FAILED", block
                result.error_message = f"Blocked/unavailable channel page detected: {block}"
                return self._finish(result, started)

            links = YouTubeShortsParser.get_latest_shorts_links(page, limit=10)
            result.items_discovered = len(links)

            own_db = False
            if db is None and not self.dry_run:
                db = SessionLocal()
                own_db = True
            try:
                latest_id = None
                for link in links:
                    video_id = YouTubeShortsParser.extract_video_id_from_url(link)
                    if not video_id:
                        result.items_failed += 1
                        continue

                    if not self.dry_run:
                        existing = db.query(RawContent).filter_by(external_content_id=video_id).first()
                        if existing:
                            result.items_skipped += 1
                            continue

                    try:
                        page.goto(link)
                        page.wait_for_load_state("networkidle")
                        metadata = YouTubeShortsParser.extract_shorts_metadata(page)
                    except Exception as e:
                        logger.warning(f"Failed to load/extract Shorts video {video_id}: {e}")
                        result.items_failed += 1
                        continue

                    if not self.dry_run:
                        db.add(RawContent(
                            source_id=source.id,
                            external_content_id=video_id,
                            platform="youtube",
                            vertical=source.vertical,
                            content_type="SHORT",
                            title=metadata.get("title"),
                            url=link,
                            thumbnail_url=metadata.get("thumbnail_url"),
                            media_type="video",
                            raw_payload=metadata,
                        ))
                        db.commit()
                    result.items_created += 1
                    latest_id = video_id

                result.status = "SUCCESS"
                if not self.dry_run:
                    source.last_collected_at = datetime.datetime.utcnow()
                    if latest_id:
                        source.last_success_at = datetime.datetime.utcnow()
                        source.last_post_id = latest_id
                    db.commit()
            finally:
                if own_db:
                    db.close()

        except Exception as e:
            logger.exception(f"Unexpected YouTube collection error for {source.external_id}")
            result.status, result.error_type, result.error_message = "FAILED", "collector_error", str(e)

        return self._finish(result, started)

    @staticmethod
    def _finish(result: CollectionResult, started: float) -> CollectionResult:
        result.finished_at = datetime.datetime.utcnow()
        result.duration_ms = int((time.time() - started) * 1000)
        return result

    def run_batch(self, sources_config: List[Source], limit: int = None, vertical_scope: str = "ALL") -> CollectionBatchResult:
        """NOTE: despite base.py's `List[Dict]` type hint, this accepts a list of
        Source ORM rows. Opens one YouTubeBrowser + one SessionLocal for the
        whole batch (matches Instagram's one-resource-per-batch pattern).
        Per-source CollectionResults land in batch.metadata["results"] as
        (external_id, CollectionResult) tuples for run_cycle.py to log.
        """
        start = time.time()
        batch = CollectionBatchResult(platform="youtube", vertical_scope=vertical_scope)
        batch.metadata["results"] = []

        active = list(sources_config)
        if vertical_scope != "ALL":
            active = [s for s in active if (s.vertical or "GENERAL").upper() == vertical_scope.upper()]
        if limit:
            active = active[:limit]

        db = SessionLocal() if not self.dry_run else None
        try:
            with YouTubeBrowser() as browser:
                for i, source in enumerate(active):
                    batch.pages_attempted += 1
                    try:
                        res = self.collect(source, context={"db": db, "page": browser.page})
                    except Exception as e:
                        logger.error(f"Unexpected error collecting YouTube source {source.external_id}: {e}")
                        res = CollectionResult(platform="youtube", status="FAILED", error_type="unexpected_error", error_message=str(e))

                    batch.metadata["results"].append((source.external_id, res))

                    if res.status == "SUCCESS":
                        batch.pages_successful += 1
                    else:
                        batch.pages_failed += 1
                        batch.errors.append({"source": source.external_id, "error_type": res.error_type, "message": res.error_message})

                    batch.items_discovered += res.items_discovered
                    batch.items_created += res.items_created
                    batch.items_skipped += res.items_skipped
                    batch.items_failed += res.items_failed

                    if i < len(active) - 1 and REQUEST_DELAY_SECONDS > 0:
                        time.sleep(REQUEST_DELAY_SECONDS)
        finally:
            if db:
                db.close()

        if batch.pages_attempted == 0:
            batch.status = "FAILED"
        elif batch.pages_failed == 0:
            batch.status = "SUCCESS"
        elif batch.pages_successful > 0:
            batch.status = "PARTIAL"
        else:
            batch.status = "FAILED"

        batch.duration_ms = int((time.time() - start) * 1000)
        batch.finished_at = datetime.datetime.utcnow()
        return batch
