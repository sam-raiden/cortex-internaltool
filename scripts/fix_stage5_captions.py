import argparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import os
import json

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost
from app.processing.hashtag_extractor import HashtagExtractor

def fix_captions(limit: int = 3):
    db = SessionLocal()
    posts = db.query(InstagramPost).filter(InstagramPost.caption == None).limit(limit).all()
    if not posts:
        print("No null-caption posts found.")
        return
        
    storage_state = ".local/instagram/storage_state.json"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
        page = ctx.new_page()
        
        for post in posts:
            print(f"Processing fixing extraction for {post.instagram_post_id} -> {post.post_url}")
            page.goto(post.post_url)
            page.wait_for_load_state("domcontentloaded")
            
            # The most un-obfuscated baseline text sits natively anchored inside OpenGraph params
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            caption = None
            
            # Technique 1: <meta property="og:description">
            og = soup.find('meta', property='og:description')
            if og and og.get('content'):
                # Format: "X likes, Y comments - uname on Date: "caption here""
                raw = og.get('content')
                match = re.search(r':\s"(.*)"$', raw)
                if match:
                    caption = match.group(1)
                else:
                    caption = raw
                    
            # Technique 2: <title>
            if not caption:
                title = soup.find('title')
                if title and title.string:
                    # Format: "uname on Instagram: "caption here""
                    match = re.search(r':\s"(.*)"$', title.string)
                    if match:
                        caption = match.group(1)
            
            if caption:
                print(f"Extraction Success: {repr(caption[:100])}...")
                post.caption = caption
                # We can natively execute parser tagging limits on caption hooks
                tags = HashtagExtractor.extract_from_text(caption)
                post.hashtags = tags
                
                db.commit()
                print("Database Post Updated.")
            else:
                print("CAPTION_NOT_ACCESSIBLE")
                
        browser.close()
    db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    fix_captions(args.limit)
