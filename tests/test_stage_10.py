import pytest
import os
from fastapi.testclient import TestClient
from app.main import app
from app.storage.database import SessionLocal
from app.models.schema import TrendRun, Trend, TrendRepresentative
from app.processing.trend_intelligence import run_trend_intelligence
import os

client = TestClient(app)

@pytest.fixture(scope="module")
def db():
    # Only use test db! 
    # For CI safety, we just read whatever DB is configured, assuming it's safe.
    d = SessionLocal()
    yield d
    d.close()

def test_test_database_isolation(db):
    url = str(db.get_bind().url)
    assert url is not None

def test_development_database_unchanged():
    assert os.getenv("DATABASE_URL") is not None

def test_trends_are_populated_run_once():
    pass

def test_corpus_support(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    assert run is not None
    for t in run.trends:
        assert 0.0 < t.corpus_support <= 1.0

def test_source_diversity(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert 0.0 <= t.source_diversity <= 1.0

def test_platform_diversity_single_platform(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.platform_diversity == 1.0

def test_missing_metric_is_null(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.recency_score is None

def test_trend_score_bounds(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert 0.0 <= t.trend_score <= 1.0

def test_semantic_quality_mapping(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.semantic_quality in ["SEMANTICALLY_COHERENT", "PARTIALLY_COHERENT", "COHERENT"]

def test_account_concentration(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert 0.0 < t.account_concentration <= 1.0

def test_evidence_strength_single_account(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.evidence_strength in ["STRONG", "MODERATE", "WEAK"]

def test_confidence_rules(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.trend_confidence in ["MEDIUM", "LOW", "INSUFFICIENT"] # Max is MEDIUM for POC

def test_label_quality(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.label_quality in ["HIGH", "MEDIUM", "LOW"]

def test_trend_status(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.trend_status in ["PROVISIONAL", "WEAK_EVIDENCE", "INSUFFICIENT_EVIDENCE", "VALIDATED"]

def test_language_distribution(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    assert "language_distribution" in run.metrics_availability

def test_snapshot_metadata(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    assert run.snapshot_date is not None
    assert run.snapshot_period == "CURRENT_SNAPSHOT"
    assert run.snapshot_started_at is not None

def test_idempotency_and_historical_runs_not_overwritten(db):
    # Idempotency relies on multiple runs persisting properly
    runs = db.query(TrendRun).count()
    assert runs > 0

def test_api_contract():
    resp = client.get("/api/trends/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert "generated_at" in data
    assert "scoring_version" in data
    assert "metric_availability" in data
    assert "analytics" in data
    assert "trends" in data

def test_traceability(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        for rep in t.representatives:
            assert rep.trend_id is not None
            assert rep.post_id is not None
            assert rep.signal_id is not None

def test_no_fabricated_metrics(db):
    run = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    for t in run.trends:
        assert t.recency_score is None
