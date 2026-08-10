"""Stage 14 -- automated normalization: RawContent -> ContentSource(CAPTION).

Platform-neutral by construction: operates on RawContent.text regardless of
platform. A row with empty/None text is skipped (no fabricated source), which
is the honest behavior for e.g. a YouTube Short whose title failed to scrape.

Previously this logic only existed as a manual diagnostic script
(app/diagnostics/rebuild_caption_sources.py) that nobody called
automatically -- every collection run silently produced RawContent that
never became a ProcessedSignal unless someone remembered to run it by hand.
run_cycle.execute_cycle() for each platform now calls create_caption_sources()
automatically after collection completes.
"""
from sqlalchemy.orm import Session

from app.models.schema import ContentSource, RawContent


def create_caption_sources(db: Session, limit: int = None) -> dict:
    """Idempotently create-or-update a CAPTION ContentSource for every
    RawContent row with non-empty text. Safe to re-run at any time."""
    query = db.query(RawContent)
    if limit:
        query = query.limit(limit)
    posts = query.all()

    cap_before = db.query(ContentSource).filter(ContentSource.source_type == "CAPTION").count()

    new_sources = 0
    duplicates = 0
    skipped_empty = 0

    for post in posts:
        if not (post.text and post.text.strip()):
            skipped_empty += 1
            continue

        existing = db.query(ContentSource).filter_by(
            post_id=post.id,
            source_type="CAPTION"
        ).first()

        if existing:
            if existing.raw_text != post.text:
                existing.raw_text = post.text
                db.commit()
            duplicates += 1
        else:
            db.add(ContentSource(
                post_id=post.id,
                source_type="CAPTION",
                raw_text=post.text,
                language="unknown",
                confidence=1.0,
                duration_ms=0
            ))
            db.commit()
            new_sources += 1

    cap_after = db.query(ContentSource).filter(ContentSource.source_type == "CAPTION").count()

    return {
        "captions_before": cap_before,
        "captions_after": cap_after,
        "new_sources": new_sources,
        "duplicates": duplicates,
        "skipped_empty": skipped_empty,
    }
