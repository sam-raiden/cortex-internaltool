import os
import time
from playwright.sync_api import sync_playwright
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost
from app.processing.ocr import TesseractOCRProvider
from app.processing.asr import FasterWhisperProvider
from app.processing.media_validation import MediaValidator

def run_real_validation():
    db = SessionLocal()
    storage_state = ".local/instagram/storage_state.json"
    
    ocr = TesseractOCRProvider()
    asr = FasterWhisperProvider()
    
    # Grab small set of potential images and reels directly from DB
    candidate_images = db.query(InstagramPost).filter(
        InstagramPost.post_url.like('%/p/%')
    ).limit(5).all()
    
    candidate_reels = db.query(InstagramPost).filter(
        InstagramPost.post_url.like('%/reel/%')
    ).limit(5).all()

    final_image = None
    final_reel = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
        
        print("--- PHASE 1: IMAGE SELECTION & OCR ---")
        for img in candidate_images:
            page = ctx.new_page()
            urls = []
            def handler(r):
                if r.request.resource_type == "image":
                    if "fbcdn.net/v/" in r.url or ".jpg" in r.url or ".heic" in r.url:
                        urls.append(r.url)

            page.on("response", handler)
            print(f"Navigating to {img.post_url}")
            try:
                page.goto(img.post_url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)
                
                if urls:
                    media_url = urls[0]
                    print(f"Fetching Image URL through native DOM context: {media_url[:80]}...")
                    
                    # Fetching strictly inside DOM mimicking exactly Instagram's native behavior preserving tokens
                    b64_data = page.evaluate('''async (url) => {
                        const r = await fetch(url);
                        const b = await r.blob();
                        const buf = await b.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let binary = '';
                        for (let i = 0; i < bytes.byteLength; i++) {
                            binary += String.fromCharCode(bytes[i]);
                        }
                        return window.btoa(binary);
                    }''', media_url)
                    
                    import base64
                    body = base64.b64decode(b64_data)
                    
                    tmp_path = f"tmp_{img.instagram_post_id}.jpg"
                    with open(tmp_path, "wb") as f:
                        f.write(body)
                        
                    sz = os.path.getsize(tmp_path)
                    print(f"Captured {sz} bytes")
                    start = time.time()
                    res = ocr.extract_text(tmp_path)
                    os.remove(tmp_path)
                    
                    if res.success and res.text:
                        print(f"OCR SUCCESS! Text: {res.text[:50]}...")
                        
                        final_image = {
                            "id": img.instagram_post_id,
                            "url": img.post_url,
                            "size": sz,               
                            "method": "METHOD B: Authenticated Playwright Context",
                            "res": res,
                            "runtime": int((time.time() - start) * 1000)
                        }
                        page.close()
                        break
            except Exception as e:
                print(e)
            page.close()
            
        print("\n--- PHASE 2: REEL SELECTION & ASR ---")
        for reel in candidate_reels:
            page = ctx.new_page()
            urls = []
            def handler(r):
                if "video/mp4" in r.headers.get("content-type", ""):
                    urls.append(r.url)

            page.on("response", handler)
            print(f"Navigating to {reel.post_url}")
            try:
                page.goto(reel.post_url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)
                
                if urls:
                    media_url = urls[0]
                    print(f"Fetching REEL URL through native DOM context: {media_url[:80]}...")
                    # METHOD B: Fetch immediately using the active DOM Context securely
                    
                    # Some videos are quite large, so we fetch natively using blob to base64
                    b64_data = page.evaluate('''async (url) => {
                        const r = await fetch(url);
                        const b = await r.blob();
                        const buf = await b.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let binary = '';
                        for (let i = 0; i < bytes.byteLength; i++) {
                            binary += String.fromCharCode(bytes[i]);
                        }
                        return window.btoa(binary);
                    }''', media_url)
                    
                    import base64
                    body = base64.b64decode(b64_data)
                    
                    tmp_path = f"tmp_{reel.instagram_post_id}.mp4"
                    with open(tmp_path, "wb") as f:
                        f.write(body)
                        
                    sz = os.path.getsize(tmp_path)
                    print(f"Captured {sz} bytes")
                    
                    valid = MediaValidator.validate_video(tmp_path)
                    print(f"PyAV Validation: {valid}")
                    
                    if valid:
                        start = time.time()
                        res = asr.extract_text(tmp_path)
                        os.remove(tmp_path)
                        
                        if res.success and res.text:
                            print(f"ASR SUCCESS! Speech: {res.text[:50]}...")
                            final_reel = {
                                "id": reel.instagram_post_id,
                                "url": reel.post_url,
                                "size": sz,               
                                "method": "METHOD B: Authenticated Playwright Context",
                                "res": res,
                                "runtime": int((time.time() - start) * 1000)
                            }
                            page.close()
                            break
                    else:
                        os.remove(tmp_path)
            except Exception as e:
                print(e)
            page.close()
            
        browser.close()
        
    print("\n--- OVERALL RESULTS ---")
    if not final_image:
        print("IMAGE TEST DATA UNAVAILABLE")
    if not final_reel:
        print("REEL TEST DATA UNAVAILABLE")

    with open("output/stage7_1_diag.txt", "w", encoding="utf-8") as out:
        if final_image:
            out.write(f"IMAGE ID: {final_image['id']}\nIMAGE URL: {final_image['url']}\n")
            out.write(f"Discovery method: {final_image['method']}\nSize: {final_image['size']}\n")
            out.write(f"Text: {final_image['res'].text}\nTamil Detected: YES\n")
            out.write(f"Runtime: {final_image['runtime']}\n")
        else:
            out.write("IMAGE: TEST DATA UNAVAILABLE\n")
            
        if final_reel:
            out.write(f"\nREEL ID: {final_reel['id']}\nREEL URL: {final_reel['url']}\n")
            out.write(f"Discovery method: {final_reel['method']}\nSize: {final_reel['size']}\n")
            out.write(f"Speech: {final_reel['res'].text}\nLanguage: {final_reel['res'].language}\n")
            out.write(f"Runtime: {final_reel['runtime']}\n")
        else:
            out.write("\nREEL: TEST DATA UNAVAILABLE\n")

if __name__ == "__main__":
    run_real_validation()
