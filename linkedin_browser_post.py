#!/usr/bin/env python3
"""
LinkedIn Browser Auto-Post
Posts the daily brief to the 'make ai practical' company page
using a saved browser session (no API key needed).

Called automatically by daily_brief.py.
"""

import os, sys, json, time
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DIR          = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(DIR, "linkedin_session.json")
CONFIG_FILE  = os.path.join(DIR, "brief_config.json")

# ── Format post text ──────────────────────────────────────────────────────────

def format_post(people_items: dict, topic_items: dict, pod_items: list) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    lines = []

    lines.append(f"🤖 AI Daily Brief — {today}")
    lines.append("")
    lines.append("What's happening in AI today — key stories you should know.")
    lines.append("")

    # Key Takeaways
    lines.append("📌 Key Takeaways")
    count = 0
    for name, items in people_items.items():
        if items and count < 5:
            title = items[0]["title"]
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"• {name}: {title}")
            count += 1
    lines.append("")

    # Topic Highlights
    TOPIC_LABELS = {
        "claude_agent":  "🤖 Claude / Agents",
        "vibe_coding":   "💻 Vibe Coding",
        "eng_pm":        "⚙️ Engineering & PM",
        "parenting_ai":  "👨‍👩‍👧 Parenting in AI Era",
        "future_work":   "🔮 Future of Work",
    }
    lines.append("🔥 Topic Highlights")
    for key, label in TOPIC_LABELS.items():
        items = topic_items.get(key, [])
        if items:
            title = items[0]["title"]
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"{label}: {title}")
    lines.append("")

    # Australia AI
    au_items = topic_items.get("australia_ai", [])
    if au_items:
        lines.append("🦘 AI in Australia")
        for it in au_items[:3]:
            title = it["title"]
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"• {title}")
        lines.append("")

    # Podcast
    if pod_items:
        title = pod_items[0]["title"]
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
        lines.append(f"🎙️ AI Daily Brief Podcast: {title}")
        lines.append("")

    lines.append("#AI #ArtificialIntelligence #AINews #MakeAIPractical #AIDaily #FutureOfWork #AIAustralia")

    post_text = "\n".join(lines)
    return post_text[:2950] + "..." if len(post_text) > 2950 else post_text


# ── Post via browser ──────────────────────────────────────────────────────────

def post_to_linkedin_browser(people_items: dict, topic_items: dict, pod_items: list) -> bool:
    if not os.path.exists(SESSION_FILE):
        print("  [LinkedIn] No browser session found — run linkedin_browser_setup.py first.")
        return False

    # Load page slug from config
    page_url = "https://www.linkedin.com/company/make-ai-practical/admin/page-posts/published/"
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        slug = cfg.get("linkedin", {}).get("page_slug", "make-ai-practical")
        page_url = f"https://www.linkedin.com/company/{slug}/admin/page-posts/published/"
    except:
        pass

    post_text = format_post(people_items, topic_items, pod_items)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # Navigate to LinkedIn feed (more reliable than admin page)
            print("  [LinkedIn] Loading LinkedIn…")
            page.goto("https://www.linkedin.com/feed/", timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)

            # Check we're logged in
            if "login" in page.url or "authwall" in page.url:
                print("  [LinkedIn] Session expired — re-run linkedin_browser_setup.py")
                browser.close()
                return False

            # Click "Start a post" on the feed
            print("  [LinkedIn] Looking for post button…")
            post_btn = None
            for selector in [
                "button:has-text('Start a post')",
                ".share-box-feed-entry__trigger",
                "[data-placeholder='Start a post']",
                "button.artdeco-button:has-text('Post')",
                "div.share-box-feed-entry__top-bar button",
            ]:
                try:
                    post_btn = page.wait_for_selector(selector, timeout=6000, state="visible")
                    if post_btn:
                        break
                except PWTimeout:
                    continue

            if not post_btn:
                print("  [LinkedIn] Could not find post button — saving screenshot for debug.")
                page.screenshot(path=os.path.join(DIR, "linkedin_debug.png"))
                browser.close()
                return False

            post_btn.click()
            time.sleep(2)

            # If "Post as" dropdown exists, switch to company page
            try:
                dropdown = page.wait_for_selector("button:has-text('Post as')", timeout=4000)
                if dropdown:
                    dropdown.click()
                    time.sleep(1)
                    page.click("text=make ai practical", timeout=5000)
                    time.sleep(1)
            except PWTimeout:
                pass  # No dropdown, posting as self

            # Type post content
            print("  [LinkedIn] Typing post…")
            editor = None
            for selector in [
                ".ql-editor[contenteditable='true']",
                "div.editor-content[contenteditable='true']",
                "[contenteditable='true']",
                "div[role='textbox']",
            ]:
                try:
                    editor = page.wait_for_selector(selector, timeout=6000, state="visible")
                    if editor:
                        break
                except PWTimeout:
                    continue

            if not editor:
                print("  [LinkedIn] Could not find text editor.")
                page.screenshot(path=os.path.join(DIR, "linkedin_debug.png"))
                browser.close()
                return False

            editor.click()
            editor.type(post_text, delay=15)
            time.sleep(2)

            # Click Post button
            print("  [LinkedIn] Publishing…")
            for selector in [
                "button.share-actions__primary-action",
                "button:has-text('Post')",
                "button[data-control-name='share.post']",
                ".share-actions button.artdeco-button--primary",
            ]:
                try:
                    btn = page.wait_for_selector(selector, timeout=5000, state="visible")
                    if btn:
                        btn.click()
                        time.sleep(4)
                        print("  ✅ LinkedIn posted to make ai practical page!")
                        browser.close()
                        return True
                except PWTimeout:
                    continue

            print("  [LinkedIn] Could not find Post button.")
            page.screenshot(path=os.path.join(DIR, "linkedin_debug.png"))
            browser.close()
            return False

        except Exception as e:
            print(f"  [LinkedIn] Browser error: {e}")
            try:
                page.screenshot(path=os.path.join(DIR, "linkedin_debug.png"))
                print(f"             Screenshot saved: {DIR}/linkedin_debug.png")
            except:
                pass
            browser.close()
            return False
