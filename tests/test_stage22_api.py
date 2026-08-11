import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.schema import (
    Cluster, ClusterMember, ClusterRun, ProcessedSignal, RawContent, Source,
    Trend, TrendRepresentative, TrendRun,
)

client = TestClient(app)


def _seed_trend(db_session, suffix, platform="instagram", vertical="GENERAL",
                 text=None, trend_run=None, label=None, trend_score=0.5,
                 published_at=None, likes=None, comments=None):
    source = Source(username=f"seed_src_{suffix}", profile_url=f"http://seed/{suffix}", vertical=vertical)
    source.platform = platform
    db_session.add(source)
    db_session.flush()

    post = RawContent(
        source_id=source.id, external_content_id=f"seed_post_{suffix}",
        url=f"http://seed/{suffix}/post", platform=platform, vertical=vertical,
        title=f"Title {suffix}", published_at=published_at, likes=likes, comments=comments,
    )
    db_session.add(post)
    db_session.flush()

    signal = ProcessedSignal(
        post_id=post.id, canonical_text=text or f"Seed evidence text {suffix}",
        language="en", extracted_hashtags=["seed", suffix], processing_status="DONE",
    )
    db_session.add(signal)
    db_session.flush()

    cluster_run = ClusterRun(run_id=f"seed_cr_{suffix}", algorithm="hdbscan")
    db_session.add(cluster_run)
    db_session.flush()

    cluster = Cluster(cluster_id=f"seed_cluster_{suffix}", run_id=cluster_run.id, signal_count=1)
    db_session.add(cluster)
    db_session.flush()

    db_session.add(ClusterMember(cluster_id=cluster.id, signal_id=signal.id, membership_probability=1.0, is_representative=True))
    db_session.flush()

    if trend_run is None:
        trend_run = TrendRun(
            run_id=f"seed_run_{suffix}", cluster_run_id=cluster_run.id, corpus_size=1,
            snapshot_period="evening", snapshot_started_at=datetime.datetime.utcnow(),
        )
        db_session.add(trend_run)
        db_session.flush()

    trend = Trend(
        trend_run_id=trend_run.id, cluster_id=cluster.id, rank=1, label=label or f"Label {suffix}",
        trend_score=trend_score, corpus_support=0.5, source_diversity=1.0,
        platform_diversity=1.0, cluster_size=1, embedding_cohesion=0.9,
        evidence_strength="MODERATE",
    )
    db_session.add(trend)
    db_session.flush()

    db_session.add(TrendRepresentative(trend_id=trend.id, post_id=post.id, signal_id=signal.id, rank=1))
    db_session.commit()
    return trend, trend_run


# ---------------------------------------------------------------------------
# Must run FIRST in this module (before any other test seeds a ClusterRun --
# db_session only wipes tables at module teardown, not between tests, and
# run_trend_intelligence() looks at the most recent ClusterRun regardless of
# which test created it).
# ---------------------------------------------------------------------------

def test_snapshot_refresh_without_cluster_run_returns_error(db_session):
    # Refresh is now async (job_queue) -- the POST itself just enqueues and
    # always returns 202; the "no cluster run" error now surfaces as a
    # FAILED job, not a synchronous error response. TestClient runs
    # BackgroundTasks to completion before .post() returns, so the job is
    # already resolved by the time we poll it.
    resp = client.post("/api/v1/snapshot/refresh", json={})
    assert resp.status_code == 202
    job_id = resp.json()["data"]["jobId"]

    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    job = job_resp.json()["data"]
    assert job["status"] == "FAILED"
    assert "No cluster run available" in job["errorMessage"]


def test_snapshot_no_data_returns_error_envelope(db_session):
    resp = client.get("/api/v1/snapshot")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NO_SNAPSHOT"


# ---------------------------------------------------------------------------
# Response envelope / shape (seeds data -- must run after the two tests above)
# ---------------------------------------------------------------------------

def test_snapshot_endpoint_shape_and_envelope(db_session):
    _seed_trend(db_session, "shape")

    resp = client.get("/api/v1/snapshot")
    assert resp.status_code == 200
    body = resp.json()

    assert body["success"] is True
    assert "meta" in body and "timestamp" in body["meta"] and "version" in body["meta"]
    data = body["data"]
    for key in (
        "id", "date", "dayOfWeek", "daypart", "daypartLabel", "lastUpdated",
        "postsAnalyzed", "trendSignals", "sourcesCount", "topTrends",
        "platformPulse", "platformLeadership", "fastestRising",
        "instagramContent", "emergingTrends",
    ):
        assert key in data, f"missing key: {key}"


# ---------------------------------------------------------------------------
# Medical intelligence: includes MEDICAL, excludes GENERAL
# ---------------------------------------------------------------------------

def test_medical_intelligence_includes_medical_excludes_general(db_session):
    med_trend, trend_run = _seed_trend(db_session, "med", vertical="MEDICAL", label="Medical Topic")
    _seed_trend(db_session, "gen", vertical="GENERAL", label="General Topic", trend_run=trend_run)

    resp = client.get("/api/v1/medical-intelligence")
    assert resp.status_code == 200
    data = resp.json()["data"]

    ids = [t["id"] for t in data["rankedMedicalTrends"]]
    assert f"tr-{med_trend.id}" in ids
    assert len(data["rankedMedicalTrends"]) == 1
    assert data["topMedicalTrend"]["id"] == f"tr-{med_trend.id}"


def test_medical_intelligence_404_when_no_medical_trends(db_session):
    _seed_trend(db_session, "onlygeneral", vertical="GENERAL")

    resp = client.get("/api/v1/medical-intelligence")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NO_MEDICAL_TRENDS"


# ---------------------------------------------------------------------------
# Platform pulse
# ---------------------------------------------------------------------------

def test_platform_pulse_reflects_seeded_platforms(db_session):
    trend_a, trend_run = _seed_trend(db_session, "pulse_ig", platform="instagram")
    _seed_trend(db_session, "pulse_rss", platform="rss", trend_run=trend_run)

    resp = client.get("/api/v1/platform-pulse")
    assert resp.status_code == 200
    platforms = {p["platform"]: p for p in resp.json()["data"]}

    assert "instagram" in platforms
    assert "rss" in platforms
    assert platforms["instagram"]["totalActiveSignals"] >= 1
    assert platforms["rss"]["totalActiveSignals"] >= 1


# ---------------------------------------------------------------------------
# Instagram content: engagement honestly null, not fabricated
# ---------------------------------------------------------------------------

def test_instagram_content_engagement_is_null_when_not_scraped(db_session):
    _seed_trend(db_session, "ig_content", platform="instagram", likes=None, comments=None)

    resp = client.get("/api/v1/instagram-content")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    assert items[0]["engagement"] is None
    assert items[0]["avatar"] == ""  # required string field, honest empty not fabricated


# ---------------------------------------------------------------------------
# Trends: category filter, sort, get-by-id
# ---------------------------------------------------------------------------

def test_trends_list_and_get_by_id(db_session):
    trend, trend_run = _seed_trend(db_session, "byid", label="Findable Trend")

    resp = client.get("/api/v1/trends")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] >= 1
    assert any(t["id"] == f"tr-{trend.id}" for t in body["trends"])

    resp2 = client.get(f"/api/v1/trends/tr-{trend.id}")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["title"] == "Findable Trend"


def test_get_trend_by_id_not_found(db_session):
    resp = client.get("/api/v1/trends/tr-999999")
    assert resp.status_code == 404
    assert resp.json()["success"] is False


def test_get_trend_by_id_invalid_format(db_session):
    resp = client.get("/api/v1/trends/not-an-id")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Emerging trends: no prior run -> all current trends surface with honest +0%
# ---------------------------------------------------------------------------

def test_emerging_trends_with_no_prior_run_shows_zero_momentum(db_session):
    _seed_trend(db_session, "emerging_first", label="First Ever Trend")

    resp = client.get("/api/v1/emerging-trends")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert data[0]["momentumSpike"] == "+0%"


# ---------------------------------------------------------------------------
# Snapshot refresh
# ---------------------------------------------------------------------------

def test_snapshot_refresh_creates_new_trend_run(db_session):
    cluster_run = ClusterRun(run_id="refresh_cr", algorithm="hdbscan")
    db_session.add(cluster_run)
    db_session.flush()

    source = Source(username="refresh_src", profile_url="http://seed/refresh", vertical="GENERAL")
    source.platform = "rss"
    db_session.add(source)
    db_session.flush()
    post = RawContent(source_id=source.id, external_content_id="refresh_post", url="http://seed/refresh/post", platform="rss", vertical="GENERAL")
    db_session.add(post)
    db_session.flush()
    signal = ProcessedSignal(post_id=post.id, canonical_text="Refresh evidence", language="en", signal_quality="HIGH", embedding=[0.1] * 384)
    db_session.add(signal)
    db_session.flush()

    cluster = Cluster(cluster_id="refresh_cluster", run_id=cluster_run.id, signal_count=1, coherence_score=0.9)
    db_session.add(cluster)
    db_session.flush()
    db_session.add(ClusterMember(cluster_id=cluster.id, signal_id=signal.id, membership_probability=1.0, is_representative=True))
    db_session.commit()

    before_count = db_session.query(TrendRun).count()

    # Async now -- POST just enqueues (202 + jobId), the real work runs in a
    # BackgroundTask. TestClient runs it to completion before .post()
    # returns, so polling the job immediately after already sees the
    # resolved SUCCESS state.
    resp = client.post("/api/v1/snapshot/refresh", json={})
    assert resp.status_code == 202
    job_id = resp.json()["data"]["jobId"]

    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    job = job_resp.json()["data"]
    assert job["status"] == "SUCCESS"
    result = job["result"]
    assert "snapshot" in result and "refreshedAt" in result and "signalsIngested" in result

    # The background task committed via its own DB session (job_queue.run_job
    # opens SessionLocal() directly, not db_session) -- db_session.query()
    # here issues a fresh SELECT against the same real test database, which
    # sees the other session's already-committed row under Postgres's
    # default READ COMMITTED isolation.
    after_count = db_session.query(TrendRun).count()
    assert after_count == before_count + 1


