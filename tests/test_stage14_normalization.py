from app.models.schema import ContentSource, RawContent, Source
from app.processing.normalize_raw_content import create_caption_sources


def _make_source(db_session, username: str, platform: str) -> Source:
    s = Source(username=username, profile_url=f"https://example.test/{username}", vertical="GENERAL")
    s.platform = platform
    db_session.add(s)
    db_session.commit()
    return s


def test_create_caption_sources_works_for_rss_and_youtube_platforms(db_session):
    rss_source = _make_source(db_session, "norm_rss_src", "rss")
    yt_source = _make_source(db_session, "norm_yt_src", "youtube")

    rss_post = RawContent(source_id=rss_source.id, external_content_id="norm_rss_post", url="https://example.test/rss/1", text="An RSS article body.", platform="rss", vertical="GENERAL")
    yt_post = RawContent(source_id=yt_source.id, external_content_id="norm_yt_post", url="https://example.test/yt/1", text="A Shorts video title", platform="youtube", vertical="GENERAL")
    db_session.add_all([rss_post, yt_post])
    db_session.commit()

    report = create_caption_sources(db_session)

    assert report["new_sources"] >= 2
    rss_caption = db_session.query(ContentSource).filter_by(post_id=rss_post.id, source_type="CAPTION").first()
    yt_caption = db_session.query(ContentSource).filter_by(post_id=yt_post.id, source_type="CAPTION").first()
    assert rss_caption is not None and rss_caption.raw_text == "An RSS article body."
    assert yt_caption is not None and yt_caption.raw_text == "A Shorts video title"


def test_create_caption_sources_is_idempotent(db_session):
    source = _make_source(db_session, "norm_idem_src", "rss")
    post = RawContent(source_id=source.id, external_content_id="norm_idem_post", url="https://example.test/idem", text="Original text", platform="rss", vertical="GENERAL")
    db_session.add(post)
    db_session.commit()

    first = create_caption_sources(db_session)
    assert first["new_sources"] >= 1

    second = create_caption_sources(db_session)
    assert second["new_sources"] == 0
    assert second["duplicates"] >= 1

    count = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="CAPTION").count()
    assert count == 1


def test_create_caption_sources_updates_changed_text(db_session):
    source = _make_source(db_session, "norm_update_src", "rss")
    post = RawContent(source_id=source.id, external_content_id="norm_update_post", url="https://example.test/update", text="Version one", platform="rss", vertical="GENERAL")
    db_session.add(post)
    db_session.commit()

    create_caption_sources(db_session)

    post.text = "Version two"
    db_session.commit()

    create_caption_sources(db_session)

    caption = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="CAPTION").first()
    assert caption.raw_text == "Version two"
    count = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="CAPTION").count()
    assert count == 1


def test_create_caption_sources_skips_empty_text(db_session):
    source = _make_source(db_session, "norm_empty_src", "youtube")
    post = RawContent(source_id=source.id, external_content_id="norm_empty_post", url="https://example.test/empty", text=None, platform="youtube", vertical="GENERAL")
    db_session.add(post)
    db_session.commit()

    report = create_caption_sources(db_session)

    assert report["skipped_empty"] >= 1
    caption = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="CAPTION").first()
    assert caption is None
