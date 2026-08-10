import pytest
from app.processing.normalizer import TextNormalizer
from app.processing.language_detector import LanguageDetector
from app.processing.hashtag_extractor import HashtagExtractor
from app.processing.text_assembler import TextAssembler
from app.processing.models import ContentSource
from app.processing.processor import SignalProcessor
from app.models.schema import InstagramPost, ProcessedSignal, InstagramPage
from app.storage.database import SessionLocal, Base, engine
import uuid

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_language_detection():
    # 1. Tamil
    assert LanguageDetector.detect("தமிழ்நாட்டில் இன்று என்ன நடக்கிறது?") == "ta"
    # 2. English
    assert LanguageDetector.detect("New movie announcement today") == "en"
    # 3. Mixed
    assert LanguageDetector.detect("இன்னைக்கு new movie announcement 🔥") == "mixed"
    # 4. Tanglish (unknown fallback safely)
    assert LanguageDetector.detect("innaiku semma update bro 🔥") == "unknown"

def test_text_normalization():
    # Whitespaces / Newlines / Unicorns
    assert TextNormalizer.normalize("Hello   \n\n  World") == "Hello World"
    # Emojis stay natively
    assert TextNormalizer.normalize("semma mass da 🔥🔥🔥") == "semma mass da 🔥🔥🔥"
    # URL stripping natively
    assert TextNormalizer.normalize("New video 🔥 https://example.com/test @creator") == "New video 🔥 @creator"
    # Empty
    assert TextNormalizer.normalize("") == ""

def test_hashtag_extraction():
    assert HashtagExtractor.extract_from_text("#TamilCinema #Leo #விஜய்") == ["TamilCinema", "Leo", "விஜய்"]
    assert HashtagExtractor.extract_from_text("No tags here") == []

def test_text_assembler():
    c1 = ContentSource(type_name="caption", text="Caption block")
    c2 = ContentSource(type_name="ocr", text="OCR block")
    assm = TextAssembler.assemble([c1, c2])
    assert assm == "Caption block\n\nOCR block"

def test_signal_processor_idempotency(db_session):
    # Construct a native dummy post safely
    test_id = uuid.uuid4().hex[:8]
    page = InstagramPage(username=f"test_signal_page_{test_id}", profile_url="x")
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)
    
    post = InstagramPost(instagram_post_id=f"signal_post_{test_id}", post_url="url", page_id=page.id, caption="Test post 1 🙏 #Test")
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    
    # Process run 1
    res1 = SignalProcessor.process_post(db_session, post)
    assert res1.success is True
    assert res1.hashtag_count == 1
    
    # Process run 2
    res2 = SignalProcessor.process_post(db_session, post)
    assert res2.success is True
    assert res2.error_type == "skipped_duplicate"
    
    sig = db_session.query(ProcessedSignal).filter_by(post_id=post.id).all()
    assert len(sig) == 1
    assert sig[0].raw_text == "Test post 1 🙏 #Test"

def test_caption_purifier():
    from app.processing.caption_purifier import CaptionPurifier
    # 1. Standard OG wrapper
    assert CaptionPurifier.purify('100 likes, 10 comments - uname on May 5, 2026: "Standard text"') == "Standard text"
    # 2. Empty caption
    assert CaptionPurifier.purify('100 likes, 10 comments - uname on May 5, 2026: ""') == ""
    # 3. Emoji caption
    assert CaptionPurifier.purify('uname on Instagram: "🔥😎"') == "🔥😎"
    # 4. @mention caption
    assert CaptionPurifier.purify('uname on Instagram: "@user hello"') == "@user hello"
    # 5. Hashtag caption
    assert CaptionPurifier.purify('10 likes - uname on June 1, 2026: "#test #trend"') == "#test #trend"
    # 6. Quotation marks inside caption
    assert CaptionPurifier.purify('10 likes - uname on June 1, 2026: "He said "hello""') == 'He said "hello"'
    # 7. Multiline caption
    assert CaptionPurifier.purify('uname on Instagram: "Line 1\nLine 2"') == "Line 1\nLine 2"
    # 8. Colon inside caption
    assert CaptionPurifier.purify('10 likes - uname on June 1, 2026: "Time is: 10:00"') == "Time is: 10:00"
    # 9. Malformed OG description
    assert CaptionPurifier.purify('Some random metadata string without prefix') is None
    # 10. Truncated/uncertain OG description
    assert CaptionPurifier.purify('100 likes, 10 comments - uname on May 5, 2026: "Truncated te') == "Truncated te"

def test_language_detection_advanced():
    assert LanguageDetector.detect("no thoughts just spidey") == "en"
    assert LanguageDetector.detect("i severely overestimate my athletic abilities") == "en"
    assert LanguageDetector.detect("new movie announcement") == "en"
    assert LanguageDetector.detect("thank you for inviting me") == "en"
    
    # Tamil
    assert LanguageDetector.detect("இன்று என்ன நடக்கிறது?") == "ta"
    assert LanguageDetector.detect("தமிழ்நாட்டில் புதிய அறிவிப்பு") == "ta"
    
    # Mixed
    assert LanguageDetector.detect("இன்று new movie announcement 🔥") == "mixed"
    assert LanguageDetector.detect("தமிழ்நாட்டில் today ஒரு முக்கிய update") == "mixed"
    
    # Tanglish (must be unknown to prevent false en hits logically if uncertain)
    assert LanguageDetector.detect("innaiku semma update") == "unknown"
    assert LanguageDetector.detect("enna da ithu") == "unknown"
    assert LanguageDetector.detect("semma mass bro") == "unknown"
    
    # Short Ambiguous text
    assert LanguageDetector.detect("Mass 🔥") == "unknown"
    assert LanguageDetector.detect("Semma") == "unknown"
    assert LanguageDetector.detect("Super da") == "unknown"
    assert LanguageDetector.detect("LOL") == "unknown"
    assert LanguageDetector.detect("🔥🔥🔥") == "unknown"
