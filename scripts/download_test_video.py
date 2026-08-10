import os
import requests
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost

def download_reels():
    db = SessionLocal()
    cache_dir = ".local/media"
    os.makedirs(cache_dir, exist_ok=True)
    
    reels = db.query(InstagramPost).filter(
        InstagramPost.media_type == "REEL",
        InstagramPost.media_url != None
    ).limit(3).all()
    
    for r in reels:
        post_dir = os.path.join(cache_dir, r.instagram_post_id)
        os.makedirs(post_dir, exist_ok=True)
        file_path = os.path.join(post_dir, "media.mp4")
        
        print(f"Downloading {r.instagram_post_id} ...")
        try:
            resp = requests.get(r.media_url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Downloaded to {file_path}")
        except Exception as e:
            print(f"Failed to download {r.instagram_post_id}: {e}")

if __name__ == "__main__":
    download_reels()
