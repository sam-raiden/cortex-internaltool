from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import datetime
import time

from app.models.schema import InstagramPost, ProcessedSignal
from app.processing.models import ContentSource, ProcessedSignalResult, ProcessedBatchResult
from app.processing.text_assembler import TextAssembler
from app.processing.normalizer import TextNormalizer
from app.processing.language_detector import LanguageDetector
from app.processing.hashtag_extractor import HashtagExtractor

class SignalProcessor:
    PROCESSOR_VERSION = "v1"
    
    @staticmethod
    def process_post(db: Session, post: InstagramPost) -> ProcessedSignalResult:
        start_ms = int(time.time() * 1000)
        
        # 1. Idempotency Check
        existing = db.query(ProcessedSignal).filter_by(
            post_id=post.id, 
            processor_version=SignalProcessor.PROCESSOR_VERSION
        ).first()
        
        if existing:
            return ProcessedSignalResult(
                post_id=post.instagram_post_id,
                success=True,
                error_type="skipped_duplicate"
            )
            
        try:
            # 2. Text Assembly
            sources = []
            if post.caption:
                sources.append(ContentSource(type_name="caption", text=post.caption))
            
            # Combine hashtags natively if stored structurally, or just pull from raw caption
            raw_text = TextAssembler.assemble(sources)
            
            # 3. Extraction/NLP layers
            tags = HashtagExtractor.extract_from_text(raw_text)
            
            # 4. Canonicalization
            canonical = TextNormalizer.normalize(raw_text)
            
            # 5. Language mapping
            lang = LanguageDetector.detect(canonical)
            
            # 6. Database creation
            signal = ProcessedSignal(
                post_id=post.id,
                raw_text=raw_text,
                canonical_text=canonical,
                language=lang,
                extracted_hashtags=tags,
                processing_status="COMPLETED",
                processor_version=SignalProcessor.PROCESSOR_VERSION,
                created_at=datetime.datetime.utcnow()
            )
            
            db.add(signal)
            db.commit()
            db.refresh(signal)
            
            duration = int(time.time() * 1000) - start_ms
            
            return ProcessedSignalResult(
                post_id=post.instagram_post_id,
                success=True,
                language=lang,
                raw_text_length=len(raw_text),
                canonical_text_length=len(canonical),
                hashtag_count=len(tags),
                processor_version=SignalProcessor.PROCESSOR_VERSION,
                duration_ms=duration
            )
            
        except Exception as e:
            db.rollback()
            return ProcessedSignalResult(
                post_id=post.instagram_post_id,
                success=False,
                error_type="processing_failure",
                error_message=str(e),
                processor_version=SignalProcessor.PROCESSOR_VERSION
            )

    @staticmethod
    def process_batch(db: Session, limit: int = 1000) -> ProcessedBatchResult:
        start_ms = int(time.time() * 1000)
        
        # Only fetch posts that do NOT have a v1 signal yet
        target_posts = db.query(InstagramPost).outerjoin(
            ProcessedSignal, 
            (ProcessedSignal.post_id == InstagramPost.id) & 
            (ProcessedSignal.processor_version == SignalProcessor.PROCESSOR_VERSION)
        ).filter(ProcessedSignal.id == None).limit(limit).all()
        
        batch = ProcessedBatchResult(posts_attempted=len(target_posts))
        
        for p in target_posts:
            res = SignalProcessor.process_post(db, p)
            if res.success:
                if res.error_type == "skipped_duplicate":
                    batch.posts_skipped += 1
                else:
                    batch.posts_processed += 1
                    lang_key = res.language if res.language in batch.languages_detected else "unknown"
                    batch.languages_detected[lang_key] += 1
            else:
                batch.posts_failed += 1
                
        batch.duration_ms = int(time.time() * 1000) - start_ms
        return batch
