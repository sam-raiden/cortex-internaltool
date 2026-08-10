"""Stage 12 — production source governance.

Validates and seeds Source rows from platform config files. Seeding is
idempotent (safe to re-run) and never fabricates data: every record must
come from the caller (a config file or explicit input), and vertical
classification is never guessed — MEDICAL must be stated explicitly by
the caller, otherwise a source defaults to GENERAL.
"""
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from app.models.schema import Source

ALLOWED_PLATFORMS = {"instagram", "youtube", "news"}
ALLOWED_VERTICALS = {"GENERAL", "MEDICAL"}
PLATFORM_SOURCE_TYPES = {
    "instagram": "INSTAGRAM_ACCOUNT",
    "youtube": "YOUTUBE_CHANNEL",
    "news": "RSS_FEED",
}
HEALTH_STATES = {"UNKNOWN", "HEALTHY", "DEGRADED", "FAILING", "INVALID"}


def validate_record(record: dict, platform: str, seen_external_ids: set) -> list:
    """Return a list of validation error strings; empty list means valid."""
    errors = []

    if platform not in ALLOWED_PLATFORMS:
        errors.append(f"invalid platform: {platform!r}")

    external_id = (record.get("external_id") or record.get("username") or "").strip()
    url = (record.get("url") or record.get("profile_url") or "").strip()
    if not external_id and not url:
        errors.append("missing identity: both external_id and url are empty")

    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"invalid url: {url!r}")

    vertical = record.get("vertical")
    if vertical is not None and vertical not in ALLOWED_VERTICALS:
        errors.append(f"invalid vertical: {vertical!r}")

    source_type = record.get("source_type")
    expected_type = PLATFORM_SOURCE_TYPES.get(platform)
    if source_type is not None and expected_type is not None and source_type != expected_type:
        errors.append(f"unsupported source_type {source_type!r} for platform {platform!r} (expected {expected_type!r})")

    dedup_key = (platform, external_id.lower())
    if external_id and dedup_key in seen_external_ids:
        errors.append(f"duplicate source in batch: {external_id!r} on platform {platform!r}")

    return errors


@dataclass
class SeedReport:
    platform: str
    added: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    rejected: list = field(default_factory=list)  # list of (record, errors)
    unchanged: list = field(default_factory=list)

    @property
    def total_valid(self):
        return len(self.added) + len(self.updated) + len(self.unchanged)


def seed_platform(db, platform: str, records: list) -> SeedReport:
    """Idempotently upsert `records` into the sources table for `platform`.

    Invalid records are rejected (not inserted) and returned with their
    validation errors. Existing sources are matched on (platform, external_id)
    and updated in place; health/timestamps are preserved on update.
    """
    report = SeedReport(platform=platform)
    seen_external_ids = set()

    for record in records:
        errors = validate_record(record, platform, seen_external_ids)
        external_id = (record.get("external_id") or record.get("username") or "").strip()
        if errors:
            report.rejected.append({"record": record, "errors": errors})
            continue

        seen_external_ids.add((platform, external_id.lower()))

        vertical = record.get("vertical") or "GENERAL"
        url = (record.get("url") or record.get("profile_url") or "").strip()
        name = record.get("name") or record.get("display_name")
        priority = record.get("priority", record.get("tier", 1))
        source_type = record.get("source_type") or PLATFORM_SOURCE_TYPES.get(platform)
        enabled = record.get("enabled", record.get("active", True))

        existing = (
            db.query(Source)
            .filter(Source.platform == platform, Source.external_id == external_id)
            .first()
        )

        if existing is None:
            new_source = Source(
                external_id=external_id,
                url=url,
                platform=platform,
                source_type=source_type,
                vertical=vertical,
                name=name,
                priority=priority,
                enabled=enabled,
                status="ACTIVE",
                health="UNKNOWN",
            )
            db.add(new_source)
            report.added.append(external_id)
        else:
            changed = False
            for field_name, value in (
                ("url", url),
                ("vertical", vertical),
                ("name", name),
                ("priority", priority),
                ("source_type", source_type),
                ("enabled", enabled),
            ):
                if getattr(existing, field_name) != value and value not in (None, ""):
                    setattr(existing, field_name, value)
                    changed = True
            if changed:
                existing.updated_at = datetime.utcnow()
                report.updated.append(external_id)
            else:
                report.unchanged.append(external_id)

    db.commit()
    return report


def quarantine_invalid_sources(db) -> list:
    """Sweep existing sources for validation failures and quarantine them.

    Quarantine = enabled=False, health='INVALID', reason recorded in
    `configuration`. Rows are never deleted -- this is reversible.
    """
    quarantined = []
    all_sources = db.query(Source).all()
    for source in all_sources:
        record = {
            "external_id": source.external_id,
            "url": source.url,
            "vertical": source.vertical,
            "source_type": source.source_type,
        }
        errors = validate_record(record, source.platform, seen_external_ids=set())
        if errors and source.health != "INVALID":
            source.enabled = False
            source.health = "INVALID"
            source.status = "QUARANTINED"
            config = dict(source.configuration or {})
            config["quarantine_reason"] = errors
            config["quarantined_at"] = datetime.utcnow().isoformat()
            source.configuration = config
            quarantined.append({"id": source.id, "external_id": source.external_id, "errors": errors})

    if quarantined:
        db.commit()
    return quarantined


def governance_snapshot(db) -> dict:
    """Return counts by platform/vertical/status/health for reporting."""
    sources = db.query(Source).all()

    def count_by(key_fn):
        counts = {}
        for s in sources:
            key = key_fn(s)
            counts[key] = counts.get(key, 0) + 1
        return counts

    return {
        "total": len(sources),
        "by_platform": count_by(lambda s: s.platform),
        "by_vertical": count_by(lambda s: s.vertical),
        "by_status": count_by(lambda s: s.status),
        "by_health": count_by(lambda s: s.health),
        "enabled_count": sum(1 for s in sources if s.enabled),
        "disabled_count": sum(1 for s in sources if not s.enabled),
        "platform_vertical_breakdown": count_by(lambda s: f"{s.platform}:{s.vertical}"),
    }


def activate_source(db, source_id: int) -> Source:
    source = db.query(Source).get(source_id)
    if source is None:
        raise ValueError(f"source {source_id} not found")
    source.enabled = True
    if source.status == "QUARANTINED":
        source.status = "ACTIVE"
    db.commit()
    return source


def deactivate_source(db, source_id: int) -> Source:
    source = db.query(Source).get(source_id)
    if source is None:
        raise ValueError(f"source {source_id} not found")
    source.enabled = False
    db.commit()
    return source
