from unittest.mock import MagicMock

from app.models.schema import (
    Cluster, ClusterRun, ProcessedSignal, RawContent, Source, Trend,
    TrendRepresentative, TrendRun, TrendSemanticAnalysis,
)
from app.processing.llm_enrichment import (
    build_evidence, enrich_trend, evidence_hash,
)
from app.services.llm_client import LLMError

VALID_LLM_OUTPUT = {
    "normalized_topic": "Test Topic",
    "title": "Test Title",
    "english_title": "Test Title EN",
    "tamil_title": "Test Title TA",
    "category": "local_news",
    "hashtags": ["test", "topic"],
    "micro_insight": "A short insight.",
    "summary": "A one-paragraph summary.",
    "explanation": "Why this matters.",
    "confidence_reason": "Based on clear evidence.",
}


def _seed_trend(db_session, suffix: str, text: str = "Seed evidence text") -> Trend:
    source = Source(username=f"llm_seed_src_{suffix}", profile_url="http://seed", vertical="GENERAL")
    db_session.add(source)
    db_session.flush()

    post = RawContent(source_id=source.id, external_content_id=f"llm_seed_post_{suffix}", url="http://seed/post", platform="rss", vertical="GENERAL")
    db_session.add(post)
    db_session.flush()

    signal = ProcessedSignal(post_id=post.id, canonical_text=text, language="en", extracted_hashtags=["seed"], processing_status="DONE")
    db_session.add(signal)
    db_session.flush()

    cluster_run = ClusterRun(run_id=f"llm_seed_cr_{suffix}", algorithm="hdbscan")
    db_session.add(cluster_run)
    db_session.flush()

    cluster = Cluster(cluster_id=f"llm_seed_cluster_{suffix}", run_id=cluster_run.id, signal_count=1)
    db_session.add(cluster)
    db_session.flush()

    trend_run = TrendRun(run_id=f"llm_seed_run_{suffix}", cluster_run_id=cluster_run.id)
    db_session.add(trend_run)
    db_session.flush()

    trend = Trend(
        trend_run_id=trend_run.id, cluster_id=cluster.id, rank=1, label="Seed Label",
        trend_score=0.5, corpus_support=0.5, source_diversity=0.5,
        platform_diversity=1.0, cluster_size=1, embedding_cohesion=0.9,
    )
    db_session.add(trend)
    db_session.flush()

    db_session.add(TrendRepresentative(trend_id=trend.id, post_id=post.id, signal_id=signal.id, rank=1))
    db_session.commit()
    return trend


def _mock_client(return_value=None, side_effect=None):
    client = MagicMock()
    if side_effect:
        client.generate_json.side_effect = side_effect
    else:
        client.generate_json.return_value = return_value or dict(VALID_LLM_OUTPUT)
    return client


def test_build_evidence_assembles_representative_data(db_session):
    trend = _seed_trend(db_session, "evidence", text="A political rally draws large crowds")

    evidence = build_evidence(db_session, trend)

    assert evidence["representative_texts"] == ["A political rally draws large crowds"]
    assert "seed" in evidence["hashtags"]
    assert f"llm_seed_src_evidence" in evidence["accounts"]
    assert "rss" in evidence["platforms"]
    assert evidence["language_distribution"] == {"en": 1}
    assert evidence["deterministic_context"]["deterministic_label"] == "Seed Label"


def test_enrich_trend_cache_miss_calls_llm_and_persists_success(db_session):
    trend = _seed_trend(db_session, "miss")
    client = _mock_client()

    row = enrich_trend(db_session, trend, client=client)

    assert client.generate_json.call_count == 1
    assert row.status == "SUCCESS"
    assert row.title == "Test Title"
    assert row.category == "local_news"
    assert row.evidence_hash


def test_enrich_trend_cache_hit_does_not_call_llm_again(db_session):
    trend_a = _seed_trend(db_session, "cache_a", text="Identical evidence text for cache test")
    trend_b = _seed_trend(db_session, "cache_b", text="Identical evidence text for cache test")

    client_a = _mock_client()
    row_a = enrich_trend(db_session, trend_a, client=client_a)
    assert row_a.status == "SUCCESS"
    assert client_a.generate_json.call_count == 1

    client_b = _mock_client()
    row_b = enrich_trend(db_session, trend_b, client=client_b)

    assert client_b.generate_json.call_count == 0  # cache hit, LLM never called
    assert row_b.status == "SUCCESS"
    assert row_b.title == row_a.title
    assert row_b.evidence_hash == row_a.evidence_hash


def test_enrich_trend_different_evidence_does_not_hit_stale_cache(db_session):
    trend_a = _seed_trend(db_session, "diff_a", text="First distinct evidence text")
    trend_b = _seed_trend(db_session, "diff_b", text="Second, completely different evidence text")

    enrich_trend(db_session, trend_a, client=_mock_client())

    client_b = _mock_client()
    row_b = enrich_trend(db_session, trend_b, client=client_b)

    assert client_b.generate_json.call_count == 1  # not a cache hit
    assert row_b.status == "SUCCESS"


def test_enrich_trend_llm_failure_persists_failed_row_without_raising(db_session):
    trend = _seed_trend(db_session, "fail")
    client = _mock_client(side_effect=LLMError("model unreachable"))

    row = enrich_trend(db_session, trend, client=client)

    assert row.status == "FAILED"
    assert "model unreachable" in row.error_message
    # Trend row itself remains fully valid and untouched
    assert trend.label == "Seed Label"
    assert trend.trend_score == 0.5


def test_enrich_trend_invalid_llm_output_persists_failed_row(db_session):
    trend = _seed_trend(db_session, "invalid")
    bad_output = dict(VALID_LLM_OUTPUT)
    bad_output["category"] = "NOT_A_REAL_CATEGORY"
    client = _mock_client(return_value=bad_output)

    row = enrich_trend(db_session, trend, client=client)

    assert row.status == "FAILED"
    assert row.error_message is not None


def test_enrich_trend_no_representative_text_skips_llm_call(db_session):
    source = Source(username="llm_seed_src_empty", profile_url="http://seed", vertical="GENERAL")
    db_session.add(source)
    db_session.flush()
    post = RawContent(source_id=source.id, external_content_id="llm_seed_post_empty", url="http://seed/post", platform="rss", vertical="GENERAL")
    db_session.add(post)
    db_session.flush()
    cluster_run = ClusterRun(run_id="llm_seed_cr_empty", algorithm="hdbscan")
    db_session.add(cluster_run)
    db_session.flush()
    cluster = Cluster(cluster_id="llm_seed_cluster_empty", run_id=cluster_run.id, signal_count=0)
    db_session.add(cluster)
    db_session.flush()
    trend_run = TrendRun(run_id="llm_seed_run_empty", cluster_run_id=cluster_run.id)
    db_session.add(trend_run)
    db_session.flush()
    trend = Trend(trend_run_id=trend_run.id, cluster_id=cluster.id, rank=1, label="Empty", cluster_size=0)
    db_session.add(trend)
    db_session.commit()
    # No TrendRepresentative rows at all -> build_evidence returns empty texts

    client = _mock_client()
    row = enrich_trend(db_session, trend, client=client)

    assert client.generate_json.call_count == 0
    assert row.status == "FAILED"
    assert "no representative text" in row.error_message
