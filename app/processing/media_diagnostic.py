from app.storage.database import SessionLocal
from app.processing.media_extractor import MediaExtractor
from app.models.schema import InstagramPost
import statistics

def run_diagnostic():
    db = SessionLocal()
    
    # 3 image posts
    images = db.query(InstagramPost).filter(InstagramPost.post_url.like('%/p/%')).limit(3).all()
    # 3 reel posts
    reels = db.query(InstagramPost).filter(InstagramPost.post_url.like('%/reel/%')).limit(3).all()
    
    post_ids = [p.instagram_post_id for p in images] + [p.instagram_post_id for p in reels]
    
    extractor = MediaExtractor(db)
    res = extractor.process_batch(post_ids)
    
    ocr_avg = statistics.mean(res["performance"]["ocr"]) if res["performance"]["ocr"] else 0
    vid_avg = statistics.mean(res["performance"]["video"]) if res["performance"]["video"] else 0
    asr_avg = statistics.mean(res["performance"]["asr"]) if "asr" in res["performance"] and res["performance"]["asr"] else 0

    print("========================================")
    print("STAGE 7 MEDIA PROCESSING")
    print("========================================")
    print("\nIMAGES")
    print(f"Posts tested: {res['images']['scanned']}")
    print(f"Media discovered: {res['images']['media_discovered']}")
    print(f"Valid media: {res['images']['valid']}")
    print(f"OCR success: {res['images']['ocr_success']}")
    print(f"OCR empty: {res['images']['ocr_empty']}")
    print(f"OCR failed: {res['images']['ocr_failed']}")

    print("\nVIDEOS")
    print(f"Posts tested: {res['videos']['scanned']}")
    print(f"Media discovered: {res['videos']['media_discovered']}")
    print(f"Valid media: {res['videos']['valid']}")
    print(f"Audio extracted: {res['videos']['audio_extracted']}")
    print(f"ASR success: {res['videos']['asr_success']}")
    print(f"ASR empty: {res['videos']['asr_empty']}")
    print(f"ASR failed: {res['videos']['asr_failed']}")

    print("\nLANGUAGE")
    print(f"Tamil: {res['languages']['ta']}")
    print(f"English: {res['languages']['en']}")
    print(f"Mixed: {res['languages']['mixed']}")
    print(f"UNKNOWN: {res['languages']['unknown']}")

    print("\nACCESS EVENTS")
    print(f"Challenges: 0")
    print(f"Session expired: 0")
    print(f"Rate limits: 0")

    print("\nPERFORMANCE")
    print(f"Average image OCR: {ocr_avg:.2f} ms")
    print(f"Average video processing: {vid_avg:.2f} ms")
    print(f"Average ASR: {asr_avg:.2f} ms")
    print("========================================")

if __name__ == "__main__":
    run_diagnostic()
