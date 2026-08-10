import os
import logging
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class InstagramBrowser:
    def __init__(self):
        self.headless = os.environ.get("INSTAGRAM_HEADLESS", "true").lower() == "true"
        self.timeout_ms = int(os.environ.get("INSTAGRAM_TIMEOUT_SECONDS", "30")) * 1000
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    def start(self):
        logger.info(f"Starting browser (headless={self.headless})")
        self.playwright = sync_playwright().start()
        
        # We use Chromium for stability.
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        # Optional context configuration
        context_args = {
            "viewport": {'width': 1280, 'height': 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Load local auth if available
        import pathlib
        state_path = pathlib.Path(".local/instagram/storage_state.json")
        if state_path.exists():
            context_args["storage_state"] = str(state_path)
            
        self.context = self.browser.new_context(**context_args)
        self.context.set_default_timeout(self.timeout_ms)
        self.page = self.context.new_page()

    def stop(self):
        logger.info("Stopping browser")
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
