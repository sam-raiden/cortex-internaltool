import os
import time
from typing import Optional, List
from playwright.sync_api import sync_playwright

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ContentSource
from app.processing.ocr import TesseractOCRProvider
from app.processing.asr import FasterWhisperProvider
from app.processing.media_validation import MediaValidator

class MediaExtractor:
    def __init__(self, db_session):
        self.db = db_session
        self.ocr_provider = TesseractOCRProvider()
        self.asr_provider = FasterWhisperProvider()
        self.storage_state = ".local/instagram/storage_state.json"
        
    def _create_content_source(self, post_id: int, s_type: str, text: str, lang: str, conf: float, dur: int):
        # We ensure idempotency natively via query checks
        exists = self.db.query(ContentSource).filter_by(post_id=post_id, source_type=s_type).first()
        if exists:
            exists.raw_text = text
            exists.language = lang
            exists.confidence = conf
            exists.duration_ms = dur
        else:
            source = ContentSource(
                post_id=post_id,
                source_type=s_type,
                raw_text=text,
                language=lang,
                confidence=conf,
                duration_ms=dur
            )
            self.db.add(source)
        self.db.commit()

    def process_batch(self, post_ids: List[str]) -> dict:
        results = {
            "images": {"scanned": 0, "media_discovered": 0, "valid": 0, "ocr_success": 0, "ocr_empty": 0, "ocr_failed": 0},
            "videos": {"scanned": 0, "media_discovered": 0, "valid": 0, "audio_extracted": 0, "asr_success": 0, "asr_empty": 0, "asr_failed": 0},
            "languages": {"ta": 0, "en": 0, "mixed": 0, "unknown": 0},
            "performance": {"ocr": [], "asr": [], "video": []}
        }
        
        posts = self.db.query(InstagramPost).filter(InstagramPost.instagram_post_id.in_(post_ids)).all()
        
        # Avoid crashing the entire batch gracefully
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=self.storage_state if os.path.exists(self.storage_state) else None)
            
            for post in posts:
                is_reel = "/reel/" in post.post_url
                is_image = "/p/" in post.post_url and not is_reel
                
                if is_image:
                    results["images"]["scanned"] += 1
                elif is_reel:
                    results["videos"]["scanned"] += 1
                    
                target = []
                
                def handle_res(r):
                    if is_image and r.request.resource_type == "image":
                        if "jpg" in r.url or "heic" in r.url or "fna.fbcdn.net/v/" in r.url:
                            target.append(r)
                    if is_reel and "video/mp4" in r.headers.get("content-type", ""):
                        target.append(r)
                
                page = ctx.new_page()
                page.on("response", handle_res)
                
                try:
                    page.goto(post.post_url)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(2000)
                    
                    if not target:
                        if is_image: results["images"]["ocr_failed"] += 1
                        if is_reel: results["videos"]["asr_failed"] += 1
                        page.close()
                        continue
                        
                    best_resp = target[0] # Grab first matching media
                    body = best_resp.body()
                    
                    if is_image:
                        results["images"]["media_discovered"] += 1
                        results["images"]["valid"] += 1
                        
                        tmp_path = f"tmp_{post.instagram_post_id}.jpg"
                        with open(tmp_path, "wb") as f:
                            f.write(body)
                            
                        # OCR Processing natively
                        start = time.time()
                        res = self.ocr_provider.extract_text(tmp_path)
                        dur = int((time.time() - start) * 1000)
                        results["performance"]["ocr"].append(dur)
                        
                        if res.success:
                            if res.text:
                                results["images"]["ocr_success"] += 1
                                self._create_content_source(post.id, "OCR", res.text, res.language, res.confidence, dur)
                            else:
                                results["images"]["ocr_empty"] += 1
                        else:
                            results["images"]["ocr_failed"] += 1
                        
                        os.remove(tmp_path)
                        
                    elif is_reel:
                        results["videos"]["media_discovered"] += 1
                        tmp_path = f"tmp_{post.instagram_post_id}.mp4"
                        with open(tmp_path, "wb") as f:
                            f.write(body)
                            
                        v_start = time.time()
                        valid = MediaValidator.validate_video(tmp_path)
                        v_dur = int((time.time() - v_start) * 1000)
                        results["performance"]["video"].append(v_dur)
                        
                        if not valid:
                            results["videos"]["asr_failed"] += 1
                            os.remove(tmp_path)
                            page.close()
                            continue
                            
                        results["videos"]["valid"] += 1
                        results["videos"]["audio_extracted"] += 1
                        
                        res = self.asr_provider.extract_text(tmp_path)
                        if res.success:
                            if res.text:
                                results["videos"]["asr_success"] += 1
                                self._create_content_source(post.id, "ASR", res.text, res.language, 1.0, int(res.duration*1000))
                                
                                # Evaluate extracted text language using simple keyword matching for POC
                                lang_res = "unknown"
                                if res.language == "en": lang_res = "en"
                                elif res.language == "ta": lang_res = "ta"
                                results["languages"][lang_res] = results["languages"].get(lang_res, 0) + 1
                            else:
                                results["videos"]["asr_empty"] += 1
                        else:
                            results["videos"]["asr_failed"] += 1
                            
                        os.remove(tmp_path)
                        
                except Exception as e:
                    print(f"Error processing {post.instagram_post_id}: {e}")
                
                page.close()
            browser.close()
            
        return results
