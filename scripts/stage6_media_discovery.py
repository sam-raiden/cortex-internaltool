import os
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost

def evaluate_media():
    db = SessionLocal()
    
    # Pick 3 images
    images = db.query(InstagramPost).filter(InstagramPost.post_url.like('%/p/%')).limit(3).all()
    # Pick 3 reels
    reels = db.query(InstagramPost).filter(InstagramPost.post_url.like('%/reel/%')).limit(3).all()
    
    storage = ".local/instagram/storage_state.json"
    os.makedirs("output/media_cache", exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage if os.path.exists(storage) else None)
        
        with open("output/stage6_media_diag.txt", "w", encoding="utf-8") as out:
            out.write(f"Total /p/ (Images): {len(images)}\n")
            out.write(f"Total /reel/ (Reels): {len(reels)}\n\n")
            
            def check_posts(post_group, label):
                for post in post_group:
                    out.write(f"POST ID: {post.instagram_post_id}\n")
                    out.write(f"URL: {post.post_url}\n")
                    out.write(f"TYPE: {label}\n")
                    
                    found_media = []
                    
                    # Intercept network requests natively capturing MP4
                    def handle_response(response):
                        url = response.url
                        ct = response.headers.get("content-type", "")
                        if "video/mp4" in ct or url.endswith(".mp4"):
                            found_media.append(url)
                    
                    page = ctx.new_page()
                    page.on("response", handle_response)
                    
                    try:
                        page.goto(post.post_url)
                        page.wait_for_load_state("networkidle")
                        
                        # Wait for hydration
                        page.wait_for_timeout(2000)
                        
                        # Inspect DOM natively for JPG
                        soup = BeautifulSoup(page.content(), 'html.parser')
                        if label == "IMAGE":
                            # Images on Instagram usually sit natively in specific meta or img tags
                            og_image = soup.find('meta', property='og:image')
                            if og_image and og_image.get('content'):
                                found_media.append(og_image.get('content'))
                                
                        if len(found_media) > 0:
                            out.write(f"MEDIA ACCESS: MEDIA_AVAILABLE\n")
                            out.write(f"MEDIA PATH: {found_media[0][:150]}...\n")
                            
                            # Cache Media (Mock download without huge bandwidth)
                            post.media_type = label
                            post.media_url = found_media[0]
                            db.commit()
                        else:
                            out.write(f"MEDIA ACCESS: MEDIA_NOT_ACCESSIBLE\n")
                            out.write(f"MEDIA PATH: None\n")
                            
                    except Exception as e:
                        out.write(f"MEDIA ACCESS: ERROR -> {str(e)}\n")
                    out.write("\n")
                    page.close()
                    
            out.write("--- IMAGES ---\n")
            check_posts(images, "IMAGE")
            out.write("--- REELS ---\n")
            check_posts(reels, "REEL")
            
        browser.close()
    db.close()

if __name__ == "__main__":
    evaluate_media()
