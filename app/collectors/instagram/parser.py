import re
import urllib.parse
from typing import List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

class InstagramParser:
    """Isolates DOM structure knowledge from the main collector."""
    
    @staticmethod
    def extract_post_id_from_url(url: str) -> Optional[str]:
        """
        Extracts stable post ID from URL. 
        Example: https://www.instagram.com/p/ABC123/ -> ABC123
                 https://www.instagram.com/reel/ABC123/ -> ABC123
        """
        match = re.search(r'/(?:p|reel|tv)/([^/?#]+)', url)
        if match:
            return match.group(1)
        return None
        
    @staticmethod
    def get_latest_post_links(page: Page, limit: int = 3) -> List[str]:
        """
        Waits for the profile grid to appear and extracts the newest post links.
        We look for all anchor ('a') tags pointing to /p/ or /reel/.
        """
        try:
            # Wait for any post link to appear, up to the page timeout
            page.wait_for_selector("a[href*='/p/'], a[href*='/reel/']", timeout=10000)
        except PlaywrightTimeoutError:
            # If nothing loaded, it might be an empty profile or blocked Access
            pass
            
        links = page.locator("a[href*='/p/'], a[href*='/reel/']").all()
        post_urls = []
        for element in links:
            href = element.get_attribute("href")
            if href:
                # Resolve relative url if needed
                full_url = urllib.parse.urljoin("https://www.instagram.com", href)
                post_urls.append(full_url)
                
        # Return unique, maintaining insertion order
        seen = set()
        unique_urls = []
        for u in post_urls:
            id_val = InstagramParser.extract_post_id_from_url(u)
            if id_val and id_val not in seen:
                seen.add(id_val)
                unique_urls.append(u)
                
        return unique_urls[:limit]

    @staticmethod
    def extract_post_metadata(page: Page) -> dict:
        """
        Extracts metadata from a single post page natively pulling OG descriptors securely.
        """
        metadata = {
            "caption": None,
            "likes": None,
            "comments": None,
            "published_at": None,
            "metadata_source": None
        }
        
        # 1. Caption via OpenGraph Native Structure
        try:
            og_desc_loc = page.locator("meta[property='og:description']")
            if og_desc_loc.count() > 0:
                raw_og = og_desc_loc.first.get_attribute("content")
                if raw_og:
                    metadata["caption"] = raw_og
                    metadata["metadata_source"] = "og:description"
        except Exception:
            pass
            
        # 2. Fallbacks
        if not metadata["caption"]:
            try:
                meta_desc = page.locator("meta[name='description']")
                if meta_desc.count() > 0:
                    metadata["caption"] = meta_desc.first.get_attribute("content")
                    metadata["metadata_source"] = "meta description"
            except Exception:
                pass
                
        # 3. Published timestamp
        try:
            time_elem = page.locator("time")
            if time_elem.count() > 0:
                dt = time_elem.first.get_attribute("datetime")
                if dt:
                    metadata["published_at"] = dt
        except Exception:
            pass

        return metadata

    @staticmethod
    def detect_challenge(page: Page) -> Optional[str]:
        """
        Detects if a page hit a rate-limit, captcha, or login block.
        Returns the type of challenge if detected, or None.
        """
        url = page.url
        if "login" in url or 'accounts/login' in url:
            return "login_required"
        if "challenge" in url:
            return "challenge_detected"
            
        page_text = page.content().lower()
        if "try again later" in page_text:
            return "rate_limited"
        if "restrict we restrict certain activity" in page_text:
            return "access_denied"
        if "/accounts/login/" in page_text:
            return "login_wall_overlay"
            
        return None
