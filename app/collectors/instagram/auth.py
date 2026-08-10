import os
import pathlib
from playwright.sync_api import sync_playwright

LOCAL_DIR = pathlib.Path(".local/instagram")
STORAGE_STATE_PATH = LOCAL_DIR / "storage_state.json"

def bootstrap_auth():
    """
    Launches a headful browser to allow manual authentication with Instagram.
    After the user confirms they're logged in, the storage state (cookies/localAuth) is saved locally.
    """
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    
    print("===================================================")
    print("INSTAGRAM AUTHENTICATION BOOTSTRAP")
    print("===================================================")
    print(f"Target save path: {STORAGE_STATE_PATH}")
    print("Launching Chromium in Headful mode...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("\nOpening Instagram...")
        page.goto("https://www.instagram.com/accounts/login/")
        
        print("\n*** ACTION REQUIRED ***")
        print("Please log into Instagram in the browser window.")
        print("DO NOT close the browser window!")
        input("\n---> PRESS ENTER HERE when you have completely logged in and are on the feed page... ")
        
        print("\nSaving session state...")
        context.storage_state(path=str(STORAGE_STATE_PATH))
        
        print(f"Session state successfully saved to {STORAGE_STATE_PATH}")
        print("You may now close the browser.")
        browser.close()

if __name__ == "__main__":
    bootstrap_auth()
