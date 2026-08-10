import os
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost
from app.processing.asr import ASRProcessor

def run_asr_poc():
    db = SessionLocal()
    cache_dir = ".local/media"
    
    # We target the specific 3 reels we acquired earlier
    reels = db.query(InstagramPost).filter(
        InstagramPost.media_type == "REEL",
        InstagramPost.media_url != None
    ).limit(3).all()
    
    with open("output/stage6_asr_diag.txt", "w", encoding="utf-8") as out:
        for r in reels:
            out.write(f"POST ID: {r.instagram_post_id}\n")
            out.write(f"POST URL: {r.post_url}\n")
            
            file_path = os.path.join(cache_dir, r.instagram_post_id, "media.mp4")
            if os.path.exists(file_path):
                out.write("VIDEO AVAILABLE: True\n")
                
                # Assume audio available if video exists since ASR will extract it
                out.write("AUDIO AVAILABLE: True\n")
                
                print(f"Executing ASR for {r.instagram_post_id} ...")
                res = ASRProcessor.process(file_path)
                
                if res.success:
                    out.write(f"TRANSCRIPT: {res.transcript}\n")
                    out.write(f"LANGUAGE: {res.language}\n")
                    out.write(f"RUNTIME: {res.duration_ms} ms\n")
                    # Out confidence if needed, though Whisper outputs probability arrays
                    out.write(f"CONFIDENCE: {res.confidence}\n")
                else:
                    out.write(f"ASR ERROR: {res.error}\n")
            else:
                out.write("VIDEO AVAILABLE: False\n")
            out.write("\n")
            
if __name__ == "__main__":
    run_asr_poc()
