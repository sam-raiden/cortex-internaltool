import pytest
from collections import Counter
from fastapi.testclient import TestClient
from app.main import app
from app.processing.trend_intelligence import run_trend_intelligence, create_deterministic_label
from app.storage.database import SessionLocal
from app.models.schema import TrendRun, Trend

client = TestClient(app)

def test_deterministic_label():
    assert create_deterministic_label(["hi"], "Existing Hash") == "Existing Hash"
    assert create_deterministic_label([], "unknown tag") == "Unclassified Trend Cluster"
    
def test_no_fabricated_metrics_and_scoring_normalization():
    db = SessionLocal()
    tr = db.query(TrendRun).order_by(TrendRun.id.desc()).first()
    if not tr:
        pytest.skip("No TrendRun available for test database.")
        
    for trend in tr.trends:
        # Check recency is None (not fabricated)
        assert trend.recency_score is None
        # Check source diversity exists based on real accounts
        assert trend.source_diversity is not None
        # Support is < 1.0 since it's normalized against eligible
        assert 0.0 < trend.corpus_support <= 1.0
        
    db.close()

def test_idempotency_and_stability():
    run_trend_intelligence()
    db = SessionLocal()
    runs = db.query(TrendRun).order_by(TrendRun.id.desc()).limit(2).all()
    if len(runs) >= 2:
        run_a, run_b = runs[0], runs[1]
        assert run_a.trend_count == run_b.trend_count
        assert run_a.id != run_b.id
        
        trends_a = {t.label: t for t in run_a.trends}
        trends_b = {t.label: t for t in run_b.trends}
        
        for k, v in trends_a.items():
            assert k in trends_b
            assert abs(v.trend_score - trends_b[k].trend_score) < 0.001
            assert v.trend_strength == trends_b[k].trend_strength
            assert v.trend_confidence == trends_b[k].trend_confidence
            
    db.close()

def test_api_real_data_response():
    response = client.get("/api/trends/latest")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert "trends" in data
    
    if data["trends"]:
        t = data["trends"][0]
        assert "rank" in t
        assert "trend_id" in t
        assert "score" in t
        assert "recency_score" in t
        assert t["recency_score"] is None # Validating lack of fake telemetry
        assert len(t["representatives"]) > 0
