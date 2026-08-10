import time
import logging
from datetime import datetime
from typing import List, Dict

from sqlalchemy.orm import Session
from app.collectors.instagram.browser import InstagramBrowser
from app.collectors.instagram.parser import InstagramParser
from app.collectors.instagram.models import CollectionResult, CollectionBatchResult
from app.storage.database import SessionLocal
from app.models.schema import InstagramPage, InstagramPost

logger = logging.getLogger(__name__)

class InstagramCollector:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        
    def run_batch(self, pages_config: List[Dict], limit: int = None, vertical_scope: str = "ALL") -> CollectionBatchResult:
        start_time = time.time()
        batch_result = CollectionBatchResult()
        
        active_pages = [p for p in pages_config if p.get("active")]
        
        if vertical_scope != "ALL":
            active_pages = [p for p in active_pages if p.get("vertical", "GENERAL").upper() == vertical_scope.upper()]
            
        if limit:
            active_pages = active_pages[:limit]
            
        with InstagramBrowser() as browser:
            for page_cfg in active_pages:
                batch_result.pages_attempted += 1
                try:
                    res = self._process_page(browser, page_cfg)
                    batch_result.results.append(res)
                    if res.success:
                        batch_result.pages_successful += 1
                    else:
                        batch_result.pages_failed += 1
                        batch_result.errors.append({"page": res.page_username, "error": res.error_type, "msg": res.error_message})
                        
                        if res.error_type in ["login_required", "login_wall_overlay"]:
                            batch_result.login_challenges += 1
                        elif res.error_type == "access_denied":
                            batch_result.access_denied_events += 1
                        elif res.error_type == "timeout":
                            batch_result.timeouts += 1
                        else:
                            batch_result.parser_failures += 1
                        
                        # CIRCUIT BREAKER LOGIC
                        critical_events = ["login_required", "login_wall_overlay", "access_denied", "rate_limited", "challenge_detected"]
                        if res.error_type in critical_events:
                            logger.error(f"CIRCUIT BREAKER TRIGGERED: {res.error_type}")
                            batch_result.status = "BLOCKED" if batch_result.pages_successful == 0 else "DEGRADED"
                            break

                    batch_result.posts_discovered += res.posts_discovered
                    batch_result.new_posts += res.new_posts
                    batch_result.existing_posts += res.existing_posts
                    batch_result.posts_with_stable_ids += len(res.extracted_post_ids)
                    batch_result.extracted_post_ids.extend(res.extracted_post_ids)
                except Exception as e:
                    logger.error(f"Unexpected error processing {page_cfg.get('username')}: {e}")
                    batch_result.pages_failed += 1
                    batch_result.parser_failures += 1
                    batch_result.errors.append({"page": page_cfg.get("username"), "error": "unexpected_error", "msg": str(e)})
                    
        batch_result.duration_ms = int((time.time() - start_time) * 1000)
        return batch_result

    def _process_page(self, browser: InstagramBrowser, page_cfg: dict) -> CollectionResult:
        username = page_cfg.get("username")
        url = page_cfg.get("url")
        start_time = time.time()
        result = CollectionResult(page_username=username, success=False)
        
        logger.info(f"Starting {username} at {url}")
        
        try:
            browser.page.goto(url)
            browser.page.wait_for_load_state("networkidle")
            
            challenge = InstagramParser.detect_challenge(browser.page)
            if challenge:
                logger.warning(f"Detection challenge {challenge} for {username}")
                result.error_type = challenge
                result.error_message = "Challenge block hit during initial load."
                return result

            # Wait for content to settle to get the most recent posts
            time.sleep(2)
            
            post_links = InstagramParser.get_latest_post_links(browser.page, limit=3)
            result.posts_discovered = len(post_links)
            logger.info(f"Found {result.posts_discovered} candidate posts for {username}")
            
            if result.posts_discovered == 0:
                logger.warning(f"0 posts discovered. URL: {browser.page.url}. Attempting to capture screenshot to output/debug_{username}.png")
                try:
                    browser.page.screenshot(path=f"output/debug_{username}.png")
                    with open(f"output/debug_{username}.html", "w", encoding="utf-8") as f:
                        f.write(browser.page.content())
                except Exception as e:
                    logger.error(f"Failed to screenshot/dump HTML: {e}")
            
            # Use database for deduplication and insertion
            db = SessionLocal() if not self.dry_run else None
            try:
                db_page = None
                if not self.dry_run:
                    db_page = db.query(InstagramPage).filter_by(username=username).first()
                    if not db_page:
                        # Should technically already be present if tracking is full, but we create mock here
                        db_page = InstagramPage(username=username, profile_url=url, active=True)
                        db.add(db_page)
                        db.commit()

                for link in post_links:
                    post_id = InstagramParser.extract_post_id_from_url(link)
                    if not post_id:
                        logger.warning(f"Failed to extract post ID from {link}")
                        continue
                    
                    result.extracted_post_ids.append(post_id)
                        
                    if not self.dry_run:
                        existing = db.query(InstagramPost).filter_by(instagram_post_id=post_id).first()
                        if existing:
                            logger.info(f"Existing post {post_id} skipped.")
                            result.existing_posts += 1
                            continue
                            
                    # Navigating to post to get raw metadata
                    browser.page.goto(link)
                    metadata = InstagramParser.extract_post_metadata(browser.page)
                    
                    if not self.dry_run:
                        logger.info(f"New post {post_id} found. Saving.")
                        new_post = InstagramPost(
                            page_id=db_page.id,
                            instagram_post_id=post_id,
                            post_url=link,
                            caption=metadata.get("caption"),
                            published_at=metadata.get("published_at"),
                        )
                        db.add(new_post)
                        db.commit()
                        result.new_posts += 1
                    else:
                        logger.info(f"[DRY-RUN] Would process new post {post_id}")
                        result.new_posts += 1
                
                result.success = True
                if not self.dry_run and result.success and db_page:
                    db_page.last_success_at = datetime.utcnow()
                    if result.new_posts > 0:
                        db_page.last_post_id = post_id
                    db.commit()

            finally:
                if db:
                    db.close()
                    
        except Exception as e:
            logger.exception(f"Exception while collecting from {username}")
            result.error_type = "collector_error"
            result.error_message = str(e)

        result.duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Completed {username} in {result.duration_ms}ms")
        return result
