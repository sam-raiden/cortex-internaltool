import argparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import os

from app.storage.database import SessionLocal
from app.models.schema import InstagramPost, ProcessedSignal
from app.processing.hashtag_extractor import HashtagExtractor
from app.processing.caption_purifier import CaptionPurifier
from app.processing.processor import SignalProcessor
from app.processing.language_detector import LanguageDetector

def run_eval(post_ids):
    db = SessionLocal()
    posts = db.query(InstagramPost).filter(InstagramPost.instagram_post_id.in_(post_ids)).all()
    
    # Reset existing processed signals for these posts to test Stage 5 processing fresh
    p_ids = [p.id for p in posts]
    db.query(ProcessedSignal).filter(ProcessedSignal.post_id.in_(p_ids)).delete(synchronize_session=False)
    db.commit()
    
    storage_state = ".local/instagram/storage_state.json"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=storage_state if os.path.exists(storage_state) else None)
        page = ctx.new_page()
        
        with open("output/tests_output.txt", "w", encoding="utf-8") as out:
            for idx, post in enumerate(posts):
                out.write(f"========================================\n")
                out.write(f"TEST POST ROUND {idx+1}\n")
                out.write(f"POST ID: {post.instagram_post_id}\n")
                out.write(f"POST URL: {post.post_url}\n")
                
                page.goto(post.post_url)
                page.wait_for_load_state("domcontentloaded")
                
                soup = BeautifulSoup(page.content(), 'html.parser')
                
                raw_og = None
                og = soup.find('meta', property='og:description')
                if og and og.get('content'):
                    raw_og = og.get('content')
                else:
                    title = soup.find('title')
                    if title and title.string:
                        raw_og = title.string
                        
                out.write(f"OG DESCRIPTION: {raw_og}\n")
                
                caption = CaptionPurifier.purify(raw_og)
                out.write(f"PURIFIED CAPTION: {caption}\n")
                
                if caption:
                    post.caption = caption
                    db.commit()
                    
                # Now run Stage 5 on this post
                SignalProcessor.process_post(db, post)
                
                # Fetch the process mapping
                sig = db.query(ProcessedSignal).filter_by(post_id=post.id).first()
                if sig:
                    out.write(f"CANONICAL: {sig.canonical_text}\n")
                    out.write(f"LANGUAGE: {sig.language}\n")
                else:
                    out.write(f"CANONICAL: None\n")
                out.write("\n")
                
        browser.close()
    db.close()

if __name__ == "__main__":
    run_eval(['DbqIyoepZ_f', 'Dbc3-mJJoEe', 'DbYUYM2ifaA', 'Dbxmpd9Dwuu'])
