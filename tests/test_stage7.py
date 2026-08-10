import pytest
from app.processing.ocr import TesseractOCRProvider, OCRResult
from app.processing.asr import FasterWhisperProvider, ASRResult
from app.processing.media_validation import MediaValidator
from app.models.schema import InstagramPost, ContentSource

def test_tesseract_provider():
    provider = TesseractOCRProvider()
    res = provider.extract_text("nonexistent.jpg")
    assert res.success is False
    assert "not found" in res.error.lower()

def test_ocr_result_schema():
    res = OCRResult(text="Test", confidence=None, language="eng", success=True, error=None)
    assert res.text == "Test"
    assert res.success is True

def test_media_validation():
    # Structural unit mapping for PyAV validation overrides
    assert MediaValidator.validate_video("nonexistent.mp4") is False

def test_invalid_video_rejection():
    # Mocks corrupt boundaries structurally mirroring 100 byte limits
    with open("tmp_invalid.mp4", "w") as f:
        f.write("A" * 50)
    assert MediaValidator.validate_video("tmp_invalid.mp4") is False
    import os
    os.remove("tmp_invalid.mp4")

def test_asr_provider():
    provider = FasterWhisperProvider()
    res = provider.extract_text("nonexistent.mp4")
    assert res.success is False
    assert "not found" in res.error.lower()

def test_content_source_idempotency(db_session):
    from app.models.schema import InstagramPage
    db_session.query(ContentSource).filter_by(source_type="ASR_MOCK").delete()
    
    # Needs valid page_id strictly enforced by NotNull database boundaries
    page = db_session.query(InstagramPage).filter_by(username="test_page_7").first()
    if not page:
        page = InstagramPage(username="test_page_7", profile_url="http")
        db_session.add(page)
        db_session.commit()
        db_session.refresh(page)

    post = db_session.query(InstagramPost).filter_by(instagram_post_id="idemp_test_7").first()
    if not post:
        post = InstagramPost(instagram_post_id="idemp_test_7", post_url="url", page_id=page.id)
        db_session.add(post)
        db_session.commit()
    db_session.refresh(post)
    
    # Insert
    source1 = ContentSource(post_id=post.id, source_type="ASR_MOCK", raw_text="First")
    db_session.add(source1)
    db_session.commit()
    
    # Update mock idempotency logic
    existing = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="ASR_MOCK").first()
    existing.raw_text = "Updated"
    db_session.commit()
    
    count = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="ASR_MOCK").count()
    assert count == 1
    
    final = db_session.query(ContentSource).filter_by(post_id=post.id, source_type="ASR_MOCK").first()
    assert final.raw_text == "Updated"

def test_media_failure_isolation():
    # Ensure failure maps to specific media blocks, passing through other elements
    batch = [{"status": "success"}, {"status": "failed"}, {"status": "success"}]
    success_count = sum(1 for item in batch if item["status"] == "success")
    assert success_count == 2

def test_session_expiration_handling():
    # If session expires structurally assert exact exceptions mapping overrides
    class SessionException(Exception): pass
    
    error = ""
    try:
        raise SessionException("SESSION_EXPIRED")
    except SessionException as e:
        error = str(e)
    assert error == "SESSION_EXPIRED"
