import os
import re
from collections import defaultdict
from playwright.sync_api import sync_playwright

def inspect_network():
    storage_state = ".local/instagram/storage_state.json"
    target_url = "https://www.instagram.com/sivaangi.krish/reel/DbvPY3nhoAn/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
        
        page = ctx.new_page()
        
        video_responses = []
        ranges_seen = defaultdict(list)
        overlaps = defaultdict(int)
        
        def handle_response(response):
            nonlocal overlaps
            req = response.request
            
            # Inspecting metadata tracking DASH / Octet Streams
            ct = response.headers.get("content-type", "").lower()
            url = response.url.lower()
            if "video" in ct or ".mp4" in url or ("fbcdn.net/v/" in url and ("mp4" in url or "octet-stream" in ct or "application" in ct)):
                c_range = response.headers.get("content-range", "")
                c_len = response.headers.get("content-length", "")
                acc_range = response.headers.get("accept-ranges", "")
                r_range = req.headers.get("range", "")
                
                meta = {
                    "req_url": req.url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type", ""),
                    "content_length": c_len,
                    "content_range": c_range,
                    "accept_ranges": acc_range,
                    "request_range": r_range,
                    "resp_url": response.url
                }
                video_responses.append(meta)
                
                
                # Check for FB CDN specific range requests embedded tightly into the query offsets mapping 200 OK payloads cleanly
                start, end, t_sz = None, None, None
                if response.status == 206 and c_range:
                    match = re.search(r"bytes (\d+)-(\d+)/(\d+)", c_range)
                    if match:
                        start, end, t_sz = int(match.group(1)), int(match.group(2)), int(match.group(3))
                elif response.status == 200 and "bytestart=" in response.url:
                    match_s = re.search(r"bytestart=(\d+)", response.url)
                    match_e = re.search(r"byteend=(\d+)", response.url)
                    if match_s and match_e:
                        start = int(match_s.group(1))
                        end = int(match_e.group(1))
                        
                if start is not None and end is not None:
                    rng = (start, end)
                    base = response.url.split("?")[0]
                    
                    # Check overlaps
                    for existing in ranges_seen[base]:
                        if max(rng[0], existing[0]) <= min(rng[1], existing[1]):
                            overlaps[base] += 1
                            break
                            
                    ranges_seen[base].append(rng)
        
        page.on("response", handle_response)
        
        print(f"Navigating to {target_url}...")
        try:
            page.goto(target_url)
            page.wait_for_load_state("networkidle")
            # Click play to trigger natural streaming
            page.click("video")
            page.wait_for_timeout(7000)
        except Exception as e:
            print(f"Error: {e}")
            
        browser.close()
        
    print("========================================")
    print("========================================")
    print("========================================")
    print("STAGE 7.2 — REEL MEDIA DIAGNOSTIC (PRE-COMPUTE)")
    print("========================================")
    
    num_206 = sum(1 for v in video_responses if (v["status"] == 206 or "bytestart=" in v["resp_url"]))
    
    with open("output/stage7_2_range_dump.txt", "w", encoding="utf-8") as f:
        f.write("RAW METADATA PEEK:\n")
        f.write(f"VIDEO RESPONSES: {len(video_responses)}\n")
        f.write(f"206 RESPONSES: {num_206}\n\n")
        
        f.write(f"DELIVERY MODEL: SEGMENTED_MEDIA (via URL bytestart query params)\n\n")
        
        for base, ranges in ranges_seen.items():
            f.write(f"STREAM: {base.split('/')[-1][:30]}...\n")
            obs_bytes = sum(r[1] - r[0] + 1 for r in ranges)
            f.write(f"  TOTAL OBSERVED BYTES: {obs_bytes}\n")
            
            ranges_sorted = sorted(ranges)
            gaps = 0
            current_end = -1
            for s, e in ranges_sorted:
                if s > current_end + 1 and current_end != -1:
                    gaps += 1
                current_end = max(current_end, e)
                
            f.write(f"  GAPS: {gaps}\n")
            f.write(f"  OVERLAPS: {overlaps[base]}\n\n")
            
        for i, v in enumerate(video_responses[:30]):
            f.write(f"[{i}] Status: {v['status']} | Length: {v['content_length']} | Type: {v['content_type']}\n")
            f.write(f"    URL: {v['resp_url']}\n")
            
        print("Logged metadata to output/stage7_2_range_dump.txt successfully!")

if __name__ == "__main__":
    inspect_network()
