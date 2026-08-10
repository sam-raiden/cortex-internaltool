import os
from playwright.sync_api import sync_playwright
from app.storage.database import SessionLocal
from app.models.schema import InstagramPost
import json

def diagnose():
    db = SessionLocal()
    # Fetch 3 real post URLs
    posts = db.query(InstagramPost).filter(InstagramPost.post_url.isnot(None), InstagramPost.caption.is_(None)).limit(3).all()
    if not posts:
        print("No empty-caption posts found.")
        return
        
    storage_state_path = ".local/instagram/storage_state.json"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage_state_path if os.path.exists(storage_state_path) else None)
        page = context.new_page()
        
        for i, post in enumerate(posts):
            print(f"Diagnosing {post.post_url}")
            page.goto(post.post_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000) # Ensure JS hydration
            
            # Print HTML body section related to caption maybe? Standard Instagram caption usually sits beside h1 or inside h1 string, but let's just dump the page body length
            html = page.content()
            html_file = f"output/post_diag_{i}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html)
            page.screenshot(path=f"output/post_diag_{i}.png")
            
            print(f"Saved {html_file}")
            
            # Try to grab h1
            h1s = page.locator("h1").all()
            print(f"Total H1 tags found: {len(h1s)}")
            for idx, h1 in enumerate(h1s):
                try:
                    text = h1.inner_text()
                    print(f"H1 {idx} text: {repr(text[:100])}")
                    # In Instagram, the caption is often inside the first h1 that belongs to a specific class, or actually inside a span adjacent to h1 username...
                except Exception as e:
                    print(f"H1 Error: {e}")
                    
        browser.close()

if __name__ == "__main__":
    diagnose()
