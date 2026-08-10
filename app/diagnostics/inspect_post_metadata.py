import os
import argparse
import json
from playwright.sync_api import sync_playwright

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost

def inspect():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--post-id", type=str)
    args = parser.parse_args()
    
    db = SessionLocal()
    query = db.query(InstagramPost)
    if args.post_id:
        query = query.filter(InstagramPost.instagram_post_id == args.post_id)
        
    posts = query.limit(args.limit).all()
    if not posts:
        print("No posts found.")
        return
        
    state_path = ".local/instagram/storage_state.json"
    if not os.path.exists(state_path):
        state_path = None
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=state_path)
        page = ctx.new_page()
        
        for post in posts:
            print("========================================")
            print(f"POST ID: {post.instagram_post_id}")
            print(f"URL: {post.post_url}")
            print(f"Db Caption: {post.caption}")
            
            try:
                page.goto(post.post_url)
                page.wait_for_load_state("networkidle")
                
                # 1. og:description
                og_desc = page.locator("meta[property='og:description']").get_attribute("content")
                print(f"\nog:description: {og_desc}")
                
                # 2. meta description
                meta_desc = page.locator("meta[name='description']").get_attribute("content")
                print(f"meta description: {meta_desc}")
                
                # 3. JSON-LD
                json_ld_raw = None
                try:
                    locator = page.locator("script[type='application/ld+json']")
                    if locator.count() > 0:
                        json_ld_raw = locator.first.inner_text()
                        data = json.loads(json_ld_raw)
                        caption_ld = data.get("articleBody") or data.get("headline")
                        print(f"JSON-LD Caption: {caption_ld}")
                    else:
                        print("JSON-LD: Not Found")
                except:
                    print("JSON-LD: Error parsing")
                    
                # 5. Fallback DOM approaches
                try:
                    # Generic text within main role or article tag
                    # Instagram often wraps captions in <h1> inside a <div> or generic <span>s
                    h1 = page.locator("h1").first.inner_text() if page.locator("h1").count() > 0 else None
                    print(f"H1 tag text: {h1}")
                    
                    # Inspect span inside the specific caption block (often the first span inside a div next to the username)
                    # We can grab all 'span' tags mapping exactly. Just checking basic visibility.
                except:
                    pass
                    
            except Exception as e:
                print(f"Error inspecting {post.instagram_post_id}: {e}")
                
        browser.close()
    db.close()
    
if __name__ == "__main__":
    inspect()
