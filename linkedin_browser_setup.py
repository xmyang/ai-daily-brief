#!/usr/bin/env python3
"""
LinkedIn Browser Setup — run this ONCE.
Opens a real Chrome browser, you log in manually,
then saves your session so auto-posting works every day.

Usage:
    python3 linkedin_browser_setup.py
"""

import os, sys, json

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright

DIR          = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(DIR, "linkedin_session.json")
CONFIG_FILE  = os.path.join(DIR, "brief_config.json")

def get_page_name():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        return cfg.get("linkedin", {}).get("page_slug", "")
    except:
        return ""

def run():
    print("\n🔐  LinkedIn Browser Setup")
    print("   A Chrome window will open.")
    print("   1. Log in to LinkedIn")
    print("   2. Navigate to your 'make ai practical' company page")
    print("   3. Come back here and press ENTER\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = context.new_page()

        page.goto("https://www.linkedin.com/login")
        print("   Browser opened. Log in and navigate to your page, then press ENTER here.")
        input("   Press ENTER when done > ")

        # Save session
        context.storage_state(path=SESSION_FILE)
        print(f"\n✅  Session saved to linkedin_session.json")
        print("   Auto-posting is now set up. Session stays valid for weeks.\n")

        browser.close()

if __name__ == "__main__":
    run()
