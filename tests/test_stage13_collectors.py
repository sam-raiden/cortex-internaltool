import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.collectors.rss.collector import RSSCollector
from app.collectors.youtube.collector import YouTubeShortsCollector
from app.models.schema import Source
from app.services.scheduler import DAYPARTS, get_sources_due, set_schedule

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _mock_response(content_bytes: bytes, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content_bytes
    resp.raise_for_status = MagicMock()
    return resp


def _feed_xml(n: int = 3, prefix: str = None) -> bytes:
    """Builds a valid RSS feed with n items whose guids are unique per call
    (via a random prefix) -- RawContent.external_content_id is globally
    unique across all sources, and the shared db_session fixture only wipes
    tables at module teardown, so reusing static guids across test functions
    in this module would cause false dedup hits between unrelated tests."""
    prefix = prefix or uuid.uuid4().hex[:8]
    items = "\n".join(
        f"""<item>
              <title>Test Article {prefix}-{i}</title>
              <link>https://example.test/{prefix}/articles/{i}</link>
              <guid>https://example.test/{prefix}/articles/{i}</guid>
              <description>Summary of test article {prefix}-{i}.</description>
              <pubDate>Mon, 10 Aug 2026 0{i}:00:00 GMT</pubDate>
            </item>"""
        for i in range(n)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Tamil News Feed {prefix}</title>
    <link>https://example.test/{prefix}/</link>
    <description>Fixture feed for RSS collector tests</description>
    {items}
  </channel>
</rss>
""".encode("utf-8")


def _malformed_feed() -> bytes:
    return (FIXTURES / "malformed_feed.xml").read_bytes()


# ---------------------------------------------------------------------------
# RSS parsing / dedup
# ---------------------------------------------------------------------------

def test_rss_collect_creates_items_from_valid_feed(db_session):
    source = Source(username="rss_test_good", profile_url="https://example.test/feed.xml", vertical="GENERAL")
    source.platform = "rss"
    db_session.add(source)
    db_session.commit()

    with patch("app.collectors.rss.collector.requests.get", return_value=_mock_response(_feed_xml())):
        collector = RSSCollector(dry_run=False)
        result = collector.collect(source, context={"db": db_session})

    assert result.status == "SUCCESS"
    assert result.items_discovered == 3
    assert result.items_created == 3
    assert result.items_skipped == 0


def test_rss_collect_dedupes_on_second_call(db_session):
    source = Source(username="rss_test_dedup", profile_url="https://example.test/feed.xml", vertical="GENERAL")
    source.platform = "rss"
    db_session.add(source)
    db_session.commit()

    feed_bytes = _feed_xml(prefix="dedup_test")
    with patch("app.collectors.rss.collector.requests.get", return_value=_mock_response(feed_bytes)):
        collector = RSSCollector(dry_run=False)
        first = collector.collect(source, context={"db": db_session})
        second = collector.collect(source, context={"db": db_session})

    assert first.items_created == 3
    assert second.items_created == 0
    assert second.items_skipped == 3
    assert second.status == "SUCCESS"


def test_rss_collect_malformed_feed_fails_without_raising(db_session):
    source = Source(username="rss_test_bad", profile_url="https://example.test/broken.xml", vertical="GENERAL")
    source.platform = "rss"
    db_session.add(source)
    db_session.commit()

    with patch("app.collectors.rss.collector.requests.get", return_value=_mock_response(_malformed_feed())):
        collector = RSSCollector(dry_run=False)
        result = collector.collect(source, context={"db": db_session})

    assert result.status == "FAILED"
    assert result.error_type == "malformed_feed"


# ---------------------------------------------------------------------------
# Batch resilience: one bad feed must not stop others
# ---------------------------------------------------------------------------

def test_rss_run_batch_partial_status_when_one_feed_fails(db_session):
    good = Source(username="rss_batch_good", profile_url="https://example.test/good.xml", vertical="GENERAL")
    good.platform = "rss"
    bad = Source(username="rss_batch_bad", profile_url="https://example.test/bad.xml", vertical="GENERAL")
    bad.platform = "rss"
    db_session.add_all([good, bad])
    db_session.commit()

    responses = {
        good.url: _mock_response(_feed_xml(prefix="batch_good")),
        bad.url: _mock_response(_malformed_feed()),
    }

    def fake_get(url, timeout=None, headers=None):
        return responses[url]

    with patch("app.collectors.rss.collector.requests.get", side_effect=fake_get):
        collector = RSSCollector(dry_run=False)
        batch = collector.run_batch([good, bad], vertical_scope="ALL")

    assert batch.status == "PARTIAL"
    assert batch.pages_successful == 1
    assert batch.pages_failed == 1
    assert batch.items_created == 3  # the good feed's items were still created


# ---------------------------------------------------------------------------
# Dry-run mode: no DB writes
# ---------------------------------------------------------------------------

def test_rss_dry_run_makes_no_db_writes(db_session):
    source = Source(username="rss_dry_run", profile_url="https://example.test/feed.xml", vertical="GENERAL")
    source.platform = "rss"
    db_session.add(source)
    db_session.commit()

    with patch("app.collectors.rss.collector.requests.get", return_value=_mock_response(_feed_xml())):
        with patch.object(db_session, "add", wraps=db_session.add) as spy_add:
            collector = RSSCollector(dry_run=True)
            result = collector.collect(source, context={"db": db_session})
            spy_add.assert_not_called()

    assert result.items_discovered == 3
    assert result.items_created == 3  # parsing/counting still runs in dry-run, just no persistence


def test_youtube_dry_run_makes_no_db_writes(db_session):
    source = Source(username="yt_dry_run", profile_url="https://www.youtube.com/@handle/shorts", vertical="GENERAL")
    source.platform = "youtube"
    db_session.add(source)
    db_session.commit()

    mock_page = MagicMock()
    mock_page.url = "https://www.youtube.com/@handle/shorts"
    mock_page.content.return_value = "<html>no block markers here</html>"
    mock_page.locator.return_value.all.return_value = []  # no Shorts links found

    with patch.object(db_session, "add", wraps=db_session.add) as spy_add:
        collector = YouTubeShortsCollector(dry_run=True)
        result = collector.collect(source, context={"db": db_session, "page": mock_page})
        spy_add.assert_not_called()

    assert result.status == "SUCCESS"
    assert result.items_discovered == 0


# ---------------------------------------------------------------------------
# Cadence resolver
# ---------------------------------------------------------------------------

def test_get_sources_due_fail_open_when_no_schedule_set(db_session):
    s = Source(username="sched_no_config", profile_url="https://example.test/a", vertical="GENERAL")
    s.platform = "rss"
    db_session.add(s)
    db_session.commit()

    for daypart in DAYPARTS:
        due = get_sources_due(db_session, "rss", daypart)
        assert s.external_id in [d.external_id for d in due]


def test_get_sources_due_respects_daily_cadence(db_session):
    s = Source(username="sched_daily", profile_url="https://example.test/b", vertical="GENERAL")
    s.platform = "rss"
    db_session.add(s)
    db_session.commit()
    set_schedule(db_session, s.id, "daily", ["morning"])

    assert s.external_id in [d.external_id for d in get_sources_due(db_session, "rss", "morning")]
    assert s.external_id not in [d.external_id for d in get_sources_due(db_session, "rss", "evening")]
    assert s.external_id not in [d.external_id for d in get_sources_due(db_session, "rss", "afternoon")]


def test_get_sources_due_respects_twice_daily_cadence(db_session):
    s = Source(username="sched_twice", profile_url="https://example.test/c", vertical="GENERAL")
    s.platform = "rss"
    db_session.add(s)
    db_session.commit()
    set_schedule(db_session, s.id, "twice_daily", ["morning", "evening"])

    assert s.external_id in [d.external_id for d in get_sources_due(db_session, "rss", "morning")]
    assert s.external_id in [d.external_id for d in get_sources_due(db_session, "rss", "evening")]
    assert s.external_id not in [d.external_id for d in get_sources_due(db_session, "rss", "afternoon")]


def test_get_sources_due_excludes_disabled_sources(db_session):
    s = Source(username="sched_disabled", profile_url="https://example.test/d", vertical="GENERAL")
    s.platform = "rss"
    s.enabled = False
    db_session.add(s)
    db_session.commit()

    due = get_sources_due(db_session, "rss", "morning")
    assert s.external_id not in [d.external_id for d in due]


def test_set_schedule_rejects_mismatched_cadence_and_dayparts(db_session):
    s = Source(username="sched_invalid", profile_url="https://example.test/e", vertical="GENERAL")
    s.platform = "rss"
    db_session.add(s)
    db_session.commit()

    with pytest.raises(ValueError):
        set_schedule(db_session, s.id, "daily", ["morning", "evening"])  # daily requires exactly 1 daypart

    with pytest.raises(ValueError):
        set_schedule(db_session, s.id, "twice_daily", ["morning"])  # twice_daily requires exactly 2

    with pytest.raises(ValueError):
        set_schedule(db_session, s.id, "hourly", ["morning"])  # invalid cadence
