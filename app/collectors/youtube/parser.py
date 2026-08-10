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
        blocked/unavailable channel just fails that one collect() call.

        Deliberately does NOT substring-match raw page_text (page.content())
        against phrases like "video unavailable" or "recaptcha" -- verified
        live against a real, working channel page and both produced false
        positives: YouTube ships a full i18n string table on every page
        (e.g. `"DOWNLOAD_UNPLAYABLE":"Video unavailable offline"`) and a
        `RECAPTCHA_V3_SITEKEY` config value that's present defensively on
        every page, not just when a challenge is active. Only signals
        confirmed against real pages are checked here. A genuinely blocked
        channel that doesn't match any of these just yields 0 discovered
        Shorts and a plain SUCCESS -- honest and non-fabricated, if less
        specific than a dedicated error_type would be.
        """
        url = page.url
        title = (page.title() or "")

        if "consent.youtube.com" in url:
            return "consent_wall"
        # Confirmed live: a genuinely nonexistent channel returns a real
        # HTTP-level 404 response with this exact title, not YouTube's SPA
        # shell.
        if "404 Not Found" in title:
            return "channel_not_found"

        try:
            body_text = page.locator("body").inner_text().lower()
        except Exception:
            body_text = ""
        # Longer, specific phrase (Google's actual anti-bot interstitial
        # copy) rather than the two-word "unusual traffic"/"recaptcha",
        # which risk the same kind of boilerplate false positive seen above.
        if "our systems have detected unusual traffic" in body_text:
            return "captcha_challenge"

        return None
