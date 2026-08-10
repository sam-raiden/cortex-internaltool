import re
import urllib.parse
from typing import List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


class YouTubeShortsParser:
    """Isolates DOM structure knowledge from the main collector."""

    @staticmethod
    def extract_video_id_from_url(url: str) -> Optional[str]:
        """https://www.youtube.com/shorts/AbC12dEfGhI -> AbC12dEfGhI"""
        match = re.search(r'/shorts/([A-Za-z0-9_-]{6,})', url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def get_latest_shorts_links(page: Page, limit: int = 10) -> List[str]:
        """Waits for the channel's Shorts grid to appear and extracts the
        newest Shorts links, deduped by video id, preserving order."""
        try:
            page.wait_for_selector("a[href*='/shorts/']", timeout=10000)
        except PlaywrightTimeoutError:
            # Empty channel, no Shorts tab content, or blocked -- caller decides via detect_block
            pass

        links = page.locator("a[href*='/shorts/']").all()
        video_urls = []
        for element in links:
            href = element.get_attribute("href")
            if href:
                full_url = urllib.parse.urljoin("https://www.youtube.com", href)
                video_urls.append(full_url)

        seen = set()
        unique_urls = []
        for u in video_urls:
            vid = YouTubeShortsParser.extract_video_id_from_url(u)
            if vid and vid not in seen:
                seen.add(vid)
                unique_urls.append(u)

        return unique_urls[:limit]

    @staticmethod
    def extract_shorts_metadata(page: Page) -> dict:
        """Best-effort metadata for a single Shorts page. View counts and
        relative-time strings ("3 days ago") are stored as raw text only --
        never parsed into a fabricated absolute timestamp or number, since a
        scraped relative string can't be converted to an exact value."""
        metadata = {
            "title": None,
            "thumbnail_url": None,
            "raw_relative_time": None,
            "raw_view_count_text": None,
        }

        try:
            og_title = page.locator("meta[property='og:title']")
            if og_title.count() > 0:
                metadata["title"] = og_title.first.get_attribute("content")
        except Exception:
            pass

        try:
            og_image = page.locator("meta[property='og:image']")
            if og_image.count() > 0:
                metadata["thumbnail_url"] = og_image.first.get_attribute("content")
        except Exception:
            pass

        try:
            time_text = page.locator("#info-strings, span.ytd-video-primary-info-renderer").first
            if time_text.count() > 0:
                metadata["raw_relative_time"] = time_text.inner_text()
        except Exception:
            pass

        try:
            view_text = page.locator("span.view-count, #info-text").first
            if view_text.count() > 0:
                metadata["raw_view_count_text"] = view_text.inner_text()
        except Exception:
            pass

        return metadata

    @staticmethod
    def detect_block(page: Page) -> Optional[str]:
        """Per-source classification only, not a circuit breaker -- YouTube
        has no login wall for public pages, so unlike Instagram there is
        nothing analogous to a batch-aborting critical-events list. A
        blocked/unavailable channel just fails that one collect() call."""
        url = page.url
        page_text = page.content().lower()

        if "consent.youtube.com" in url:
            return "consent_wall"
        if "this channel does not exist" in page_text or "channel not found" in page_text:
            return "channel_not_found"
        if "this video is unavailable" in page_text or "video unavailable" in page_text:
            return "video_unavailable"
        if "unusual traffic" in page_text or "recaptcha" in page_text:
            return "captcha_challenge"

        return None
