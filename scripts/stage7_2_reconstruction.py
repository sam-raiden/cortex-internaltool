import os
import re
from collections import defaultdict
from playwright.sync_api import sync_playwright
import base64

from app.processing.media_validation import MediaValidator
from app.processing.asr import FasterWhisperProvider

def reconstruct_media():
    storage_state = ".local/instagram/storage_state.json"
    target_url = "https://www.instagram.com/sivaangi.krish/reel/DbvPY3nhoAn/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
        page = ctx.new_page()
        
        streams = defaultdict(list)
        
        def handle_response(response):
            try:
                ct = response.headers.get("content-type", "").lower()
                url = response.url.lower()
                
                # Check for Segmented media via query strings
                if response.status == 200 and ("bytestart=" in url or ".mp4" in url or "fbcdn.net/o1/v/" in url):
                    match_s = re.search(r"bytestart=(\d+)", url)
                    match_e = re.search(r"byteend=(\d+)", url)
                    base = response.url.split("?")[0]
                    sid = base.split("/")[-1]
                    
                    if match_s and match_e:
                        s, e = int(match_s.group(1)), int(match_e.group(1))
                        # Buffer body bytes immediately since IG might dispose them
                        body_b64 = page.evaluate(f'''async (url) => {{
                            const r = await fetch(url);
                            const b = await r.blob();
                            const buf = await b.arrayBuffer();
                            const bytes = new Uint8Array(buf);
                            let binary = '';
                            for (let i = 0; i < bytes.byteLength; i++) {{
                                binary += String.fromCharCode(bytes[i]);
                            }}
                            return window.btoa(binary);
                        }}''', response.url)
                        
                        chunk = base64.b64decode(body_b64)
                        if len(chunk) == (e - s + 1):
                            streams[sid].append({"start": s, "end": e, "data": chunk})
            except Exception as ex:
                pass
                
        page.on("response", handle_response)
        
        print(f"Navigating to {target_url}...")
        try:
            page.goto(target_url)
            page.wait_for_load_state("networkidle")
            page.click("video")
            page.wait_for_timeout(7000)
        except Exception:
            pass
            
        browser.close()
        
    print("========================================")
    print("STAGE 7.2 — RECONSTRUCTION & ASR TEST")
    print("========================================")
    
    # Analyze and stitch streams
    reconstructed_file = None
    best_stream_id = None
    
    for sid, chunks in streams.items():
        if not chunks:
            continue
            
        # Sort by start byte
        chunks.sort(key=lambda x: x["start"])
        
        # Verify contiguous from 0
        is_contiguous = True
        accumulated_len = 0
        final_buffer = bytearray()
        
        for c in chunks:
            if c["start"] <= accumulated_len: # Handles overlap safely
                offset = accumulated_len - c["start"]
                if offset < len(c["data"]):
                    valid_chunk = c["data"][offset:]
                    final_buffer.extend(valid_chunk)
                    accumulated_len += len(valid_chunk)
            elif c["start"] > accumulated_len:
                is_contiguous = False
                break
                
        # If it's contiguous and over 100KB, it's a valid media layer
        if is_contiguous and accumulated_len > 100000:
            best_stream_id = sid
            reconstructed_file = f"tmp_{sid}.mp4"
            with open(reconstructed_file, "wb") as f:
                f.write(final_buffer)
            print(f"Stream {sid[:20]}... natively reconstructed! Size: {accumulated_len} bytes")
            break
            
    if reconstructed_file:
        print("PYAV: RUNNING")
        validator = MediaValidator.validate_video(reconstructed_file)
        if validator:
            print("PYAV: PASS")
            print("AUDIO: DETECTED/READY")
            print("ASR: RUNNING")
            
            asr = FasterWhisperProvider()
            import time
            t1 = time.time()
            res = asr.extract_text(reconstructed_file)
            t2 = time.time()
            
            if res.success and res.text:
                print("ASR: PASS")
                print(f"TRANSCRIPT: {res.text.strip()}")
                print(f"LANGUAGE: {res.language}")
                print(f"ASR RUNTIME: {int((t2-t1)*1000)}ms")
            else:
                print("ASR: BLOCKED (Failed to extract speech from valid media)")
        else:
            print("PYAV: FAIL")
            
        os.remove(reconstructed_file)
    else:
        print("RECONSTRUCTION: BLOCKED (No contiguous media boundaries properly mapping valid DASH chunks)")

if __name__ == "__main__":
    reconstruct_media()
