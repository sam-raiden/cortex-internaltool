import os
import json
import time
from app.collectors.instagram.browser import InstagramBrowser

def analyze_profile_state(page, start_url: str) -> str:
    # Get current URL and content
    final_url = page.url
    
    if "login" in final_url or "accounts/login" in page.content().lower():
        return "LOGIN_REQUIRED"
    
    if "challenge" in final_url:
        return "CHALLENGE"
        
    page_text = page.content().lower()
    if "restrict we restrict certain activity" in page_text:
        return "ACCESS_DENIED"
        
    if "sorry, this page isn't available" in page_text.replace("&#x27;", "'"):
        return "PAGE_NOT_AVAILABLE"
        
    # Technically if it navigated to a totally different path
    # But wait, Instagram adds trailing slash or parameters. Let's do a basic check.
    # Start URL: https://www.instagram.com/vikatan/
    # Final URL: https://www.instagram.com/vikatan/?hl=en
    if start_url.split("?")[0].rstrip("/") != final_url.split("?")[0].rstrip("/"):
        # Not a login redirect, but a page redirect
        return "REDIRECTED"
        
    # Look for specific profile elements indicating posts are visible
    # E.g., an article, or a grid of posts
    try:
        # A typical profile has an image, stats, and a grid. `article` usually groups the grid.
        # Or look for `_aabd _aa8k` classes or similar `a` links pointing to `/p/`.
        has_posts = page.locator("a[href*='/p/'], a[href*='/reel/']").count() > 0
        if has_posts:
            return "VALID_PROFILE"
        else:
            # private or empty profiles
            if "this account is private" in page_text:
                return "VALID_PROFILE_PRIVATE"
            return "UNKNOWN"  # Empty or unknown structure
    except Exception:
        return "UNKNOWN"

def run_diagnostics(limit: int = 3):
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../config/pages.json"))
    with open(config_path, "r", encoding="utf-8") as f:
        pages_config = json.load(f)
        
    test_pages = pages_config[:limit]
    
    print("=" * 40)
    print("INSTAGRAM URL VALIDATION")
    print("=" * 40)
    
    stats = {
        "Accounts tested": 0,
        "Valid profiles": 0,
        "Unavailable": 0,
        "Challenges": 0,
        "Redirects": 0
    }
    
    with InstagramBrowser() as browser:
        for index, p_data in enumerate(test_pages, 1):
            url = p_data["url"]
            display_name = p_data.get("display_name", p_data.get("username"))
            username = p_data["username"]
            
            print(f"\n{index}.")
            print(f"Display:\n{display_name}\n")
            print(f"Configured URL:\n{url}\n")
            
            try:
                browser.page.goto(url)
                browser.page.wait_for_load_state("networkidle")
                time.sleep(2)
                
                final_url = browser.page.url
                page_title = browser.page.title()
                state = analyze_profile_state(browser.page, url)
                
                print(f"Final URL:\n{final_url}\n")
                print(f"Page Title:\n{page_title}\n")
                print(f"State:\n{state}")
                
                if state.startswith("VALID_PROFILE"):
                    print("\nPROFILE PAGE VALID — READY FOR POST PARSER TEST")
                    stats["Valid profiles"] += 1
                elif state == "PAGE_NOT_AVAILABLE":
                    print("\nINVALID/UNAVAILABLE URL — USER VERIFICATION REQUIRED")
                    stats["Unavailable"] += 1
                elif state in ["CHALLENGE", "LOGIN_REQUIRED", "ACCESS_DENIED"]:
                    stats["Challenges"] += 1
                elif state == "REDIRECTED":
                    stats["Redirects"] += 1

                # Save screenshot
                browser.page.screenshot(path=f"output/diagnostic_{index}_{username}.png")
                
            except Exception as e:
                print(f"Error checking {url}: {e}")
            
            stats["Accounts tested"] += 1

    print("\n" + "=" * 40)
    print(f"Accounts tested: {stats['Accounts tested']}")
    print(f"Valid profiles: {stats['Valid profiles']}")
    print(f"Unavailable: {stats['Unavailable']}")
    print(f"Challenges: {stats['Challenges']}")
    print(f"Redirects: {stats['Redirects']}")
    print("=" * 40)

if __name__ == "__main__":
    run_diagnostics(limit=3)
