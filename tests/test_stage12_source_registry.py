import os
import pytest
from app.models.schema import Source
from app.services.source_registry import (
    validate_record,
    seed_platform,
    quarantine_invalid_sources,
    governance_snapshot,
    activate_source,
    deactivate_source,
)

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://tamilsh:pocpassword@localhost:5433/tamilsh_poc_test")


def test_database_protection(db_session):
    """Ensure these tests never run against the protected development db."""
    assert "tamilsh_poc_test" in TEST_DB_URL


# --- validation ---

def test_validate_missing_identity():
    errors = validate_record({}, "instagram", set())
    assert any("missing identity" in e for e in errors)


def test_validate_invalid_platform():
    errors = validate_record({"external_id": "x", "url": "https://x.com"}, "tiktok", set())
    assert any("invalid platform" in e for e in errors)


def test_validate_invalid_vertical():
    errors = validate_record(
        {"external_id": "x", "url": "https://x.com", "vertical": "SPORTS"}, "instagram", set()
    )
    assert any("invalid vertical" in e for e in errors)


def test_validate_invalid_url():
    errors = validate_record({"external_id": "x", "url": "not-a-url"}, "instagram", set())
    assert any("invalid url" in e for e in errors)


def test_validate_unsupported_source_type():
    errors = validate_record(
        {"external_id": "x", "url": "https://x.com", "source_type": "RSS_FEED"}, "instagram", set()
    )
    assert any("unsupported source_type" in e for e in errors)


def test_validate_duplicate_in_batch():
    seen = {("instagram", "dupe")}
    errors = validate_record({"external_id": "dupe", "url": "https://x.com"}, "instagram", seen)
    assert any("duplicate source in batch" in e for e in errors)


def test_validate_accepts_valid_record():
    errors = validate_record(
        {"external_id": "goodpage", "url": "https://instagram.com/goodpage", "vertical": "GENERAL"},
        "instagram",
        set(),
    )
    assert errors == []


# --- seeding ---

def test_seed_platform_inserts_valid_and_rejects_invalid(db_session):
    records = [
        {"external_id": "valid_one", "url": "https://instagram.com/valid_one", "vertical": "GENERAL"},
        {"external_id": "", "url": "not-a-url"},  # invalid: missing identity + bad url
    ]
    report = seed_platform(db_session, "instagram", records)

    assert "valid_one" in report.added
    assert len(report.rejected) == 1

    stored = db_session.query(Source).filter_by(platform="instagram", external_id="valid_one").first()
    assert stored is not None
    assert stored.vertical == "GENERAL"
    assert stored.health == "UNKNOWN"
    assert stored.status == "ACTIVE"


def test_seed_platform_is_idempotent(db_session):
    record = [{"external_id": "idem_page", "url": "https://instagram.com/idem_page", "vertical": "GENERAL"}]

    first = seed_platform(db_session, "instagram", record)
    assert "idem_page" in first.added

    second = seed_platform(db_session, "instagram", record)
    assert "idem_page" in second.unchanged
    assert "idem_page" not in second.added

    count = db_session.query(Source).filter_by(platform="instagram", external_id="idem_page").count()
    assert count == 1


def test_seed_platform_updates_changed_fields(db_session):
    record = [{"external_id": "update_page", "url": "https://instagram.com/update_page", "vertical": "GENERAL", "priority": 1}]
    seed_platform(db_session, "instagram", record)

    updated_record = [{"external_id": "update_page", "url": "https://instagram.com/update_page", "vertical": "GENERAL", "priority": 5}]
    report = seed_platform(db_session, "instagram", updated_record)

    assert "update_page" in report.updated
    stored = db_session.query(Source).filter_by(platform="instagram", external_id="update_page").first()
    assert stored.priority == 5


def test_vertical_defaults_general_never_guesses_medical(db_session):
    """A record with no explicit vertical must default to GENERAL, even if the
    external_id/url looks health-related. MEDICAL must only ever come from an
    explicit vertical field in the input record."""
    record = [{"external_id": "doctorvibes_health", "url": "https://instagram.com/doctorvibes_health"}]
    report = seed_platform(db_session, "instagram", record)
    assert "doctorvibes_health" in report.added

    stored = db_session.query(Source).filter_by(platform="instagram", external_id="doctorvibes_health").first()
    assert stored.vertical == "GENERAL"


def test_vertical_explicit_medical_is_honored(db_session):
    record = [{"external_id": "explicit_med", "url": "https://instagram.com/explicit_med", "vertical": "MEDICAL"}]
    seed_platform(db_session, "instagram", record)
    stored = db_session.query(Source).filter_by(platform="instagram", external_id="explicit_med").first()
    assert stored.vertical == "MEDICAL"


def test_seed_platform_rejects_wrong_platform_source_type(db_session):
    record = [{"external_id": "wrong_type", "url": "https://youtube.com/wrong_type", "source_type": "RSS_FEED"}]
    report = seed_platform(db_session, "youtube", record)
    assert report.added == []
    assert len(report.rejected) == 1


# --- quarantine ---

def test_quarantine_flags_invalid_existing_sources_without_deleting(db_session):
    bad = Source(external_id="bad_url_source", url="x", platform="instagram", vertical="GENERAL")
    db_session.add(bad)
    db_session.commit()

    quarantined = quarantine_invalid_sources(db_session)
    ids = [q["id"] for q in quarantined]
    assert bad.id in ids

    db_session.refresh(bad)
    assert bad.enabled is False
    assert bad.health == "INVALID"
    assert bad.status == "QUARANTINED"
    assert "quarantine_reason" in (bad.configuration or {})

    # never deleted
    still_there = db_session.query(Source).filter_by(id=bad.id).first()
    assert still_there is not None


def test_quarantine_does_not_touch_valid_sources(db_session):
    good = Source(external_id="good_source_quarantine", url="https://instagram.com/good_source_quarantine", platform="instagram", vertical="GENERAL")
    db_session.add(good)
    db_session.commit()

    quarantine_invalid_sources(db_session)
    db_session.refresh(good)
    assert good.enabled is True
    assert good.health != "INVALID"


# --- activation / governance ---

def test_activate_and_deactivate_source(db_session):
    src = Source(external_id="toggle_source", url="https://instagram.com/toggle_source", platform="instagram", vertical="GENERAL")
    db_session.add(src)
    db_session.commit()

    deactivate_source(db_session, src.id)
    db_session.refresh(src)
    assert src.enabled is False

    activate_source(db_session, src.id)
    db_session.refresh(src)
    assert src.enabled is True


def test_governance_snapshot_counts(db_session):
    db_session.add_all([
        Source(external_id="snap_gen", url="https://instagram.com/snap_gen", platform="instagram", vertical="GENERAL"),
        Source(external_id="snap_med", url="https://instagram.com/snap_med", platform="instagram", vertical="MEDICAL"),
    ])
    db_session.commit()

    snapshot = governance_snapshot(db_session)
    assert snapshot["total"] >= 2
    assert snapshot["by_platform"].get("instagram", 0) >= 2
    assert "GENERAL" in snapshot["by_vertical"]
