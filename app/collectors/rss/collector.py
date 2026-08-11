"""Stage 13 -- production RSS/Atom collector.

Fetches a source's feed URL, parses it with feedparser, dedupes entries
against RawContent.external_content_id, and inserts new entries. One
broken feed (network failure, malformed XML, timeout) must never abort a
batch of other feeds -- each source's failure is isolated and reported
per-source.
"""
import datetime
import logging
import time
from typing import Dict, List, Optional

import feedparser
import requests
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectionBatchResult, CollectionResult
from app.models.schema import RawContent, Source
from app.storage.database import SessionLocal

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
# A self-identifying bot UA gets 403'd by at least one real source (News18
# Tamil) even though its RSS feed is public and meant to be polled --
# confirmed live. A standard browser UA (matching what the Playwright
# collectors already send) gets through.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class RSSCollector(BaseCollector):
    def __init__(self, dry_run: bool = False):
        super().__init__(dry_run=dry_run)

    def collect(self, source: Source, context: Optional[Dict] = None) -> CollectionResult:
        context = context or {}
        db: Optional[Session] = context.get("db")
        started = time.time()
        result = CollectionResult(source_id=getattr(source, "id", None), platform="rss")

        try:
            resp = requests.get(source.url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            result.status, result.error_type = "FAILED", "network_timeout"
            result.error_message = f"timeout fetching {source.url}"
            return self._finish(result, started)
        except requests.exceptions.RequestException as e:
            result.status, result.error_type, result.error_message = "FAILED", "network_error", str(e)
            return self._finish(result, started)

        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            result.status, result.error_type = "FAILED", "malformed_feed"
            result.error_message = str(feed.get("bozo_exception", "unparseable feed"))
            return self._finish(result, started)

        result.items_discovered = len(feed.entries)
        if not feed.entries:
            result.status = "SUCCESS"
            result.metadata["empty_feed"] = True
            return self._finish(result, started)

        own_db = False
        if db is None and not self.dry_run:
            db = SessionLocal()
            own_db = True
        try:
            latest_id = None
            for entry in feed.entries:
                ext_id = entry.get("id") or entry.get("guid") or entry.get("link")
                if not ext_id:
                    result.items_failed += 1
                    continue

                if not self.dry_run:
                    existing = db.query(RawContent).filter_by(external_content_id=ext_id).first()
                    if existing:
                        result.items_skipped += 1
                        continue

                published_at = None
                if entry.get("published_parsed"):
                    published_at = datetime.datetime(*entry.published_parsed[:6])

                if not self.dry_run:
                    db.add(RawContent(
                        source_id=source.id,
                        external_content_id=ext_id,
                        platform="rss",
                        vertical=source.vertical,
                        content_type="ARTICLE",
                        title=entry.get("title"),
                        text=entry.get("summary") or entry.get("description"),
                        url=entry.get("link"),
                        published_at=published_at,
                        raw_payload={
                            "title": entry.get("title"),
                            "link": entry.get("link"),
                            "summary": entry.get("summary"),
                            "published": entry.get("published"),
                        },
                    ))
                    db.commit()
                result.items_created += 1
                latest_id = ext_id

            result.status = "SUCCESS"
            if not self.dry_run:
                source.last_collected_at = datetime.datetime.utcnow()
                if latest_id:
                    source.last_success_at = datetime.datetime.utcnow()
                    source.last_post_id = latest_id
                db.commit()
        except Exception as e:
            logger.exception(f"Unexpected RSS collection error for {source.external_id}")
            result.status, result.error_type, result.error_message = "FAILED", "collector_error", str(e)
            # A failed insert/commit leaves a shared, batch-level session in a
            # PendingRollbackError state -- without rolling back here, every
            # subsequent source in the same run_batch() would also fail,
            # cascading one bad record into the whole batch. Roll back only
            # (never close) when this collect() call didn't own the session.
            if not own_db and db is not None:
                db.rollback()
        finally:
            if own_db:
                db.close()

        return self._finish(result, started)

    @staticmethod
    def _finish(result: CollectionResult, started: float) -> CollectionResult:
        result.finished_at = datetime.datetime.utcnow()
        result.duration_ms = int((time.time() - started) * 1000)
        return result

    def run_batch(self, sources_config: List[Source], limit: int = None, vertical_scope: str = "ALL") -> CollectionBatchResult:
        """NOTE: despite base.py's `List[Dict]` type hint, this accepts a list of
        Source ORM rows (matches collect(), which reads source.external_id /
        source.id / source.url / source.vertical directly).

        Per-source CollectionResults are accumulated into
        batch.metadata["results"] as (external_id, CollectionResult) tuples so
        callers (run_cycle.py) can still log a per-source result without a
        dedicated results list on the generic CollectionBatchResult model.
        """
        start = time.time()
        batch = CollectionBatchResult(platform="rss", vertical_scope=vertical_scope)
        batch.metadata["results"] = []

        active = list(sources_config)
        if vertical_scope != "ALL":
            active = [s for s in active if (s.vertical or "GENERAL").upper() == vertical_scope.upper()]
        if limit:
            active = active[:limit]

        db = SessionLocal() if not self.dry_run else None
        try:
            for source in active:
                batch.pages_attempted += 1
                try:
                    res = self.collect(source, context={"db": db})
                except Exception as e:
                    logger.error(f"Unexpected error collecting RSS source {source.external_id}: {e}")
                    res = CollectionResult(platform="rss", status="FAILED", error_type="unexpected_error", error_message=str(e))

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
