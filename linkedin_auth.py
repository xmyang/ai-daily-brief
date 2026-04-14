#!/usr/bin/env python3
"""
LinkedIn OAuth Setup — run this ONCE to get your access token.
Stores tokens to linkedin_tokens.json for use by daily_brief.py.

Usage:
    python3 linkedin_auth.py
"""

import os
import json
import urllib.parse
import http.server
import threading
import webbrowser
from datetime import datetime

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

CONFIG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief_config.json")
TOKENS_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_tokens.json")

REDIRECT_URI = "http://localhost:8765/callback"
AUTH_URL     = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL    = "https://www.linkedin.com/oauth/v2/accessToken"
# Scopes needed: post to company page + read org info
SCOPES       = "w_member_social w_organization_social r_organization_social"

# ── Load credentials from config ─────────────────────────────────────────────

def load_linkedin_config():
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    li = cfg.get("linkedin", {})
    if not li.get("client_id") or li.get("client_id") == "YOUR_CLIENT_ID":
        print("\n❌  LinkedIn credentials not set in brief_config.json")
        print("   See LINKEDIN_SETUP.md for instructions.\n")
        raise SystemExit(1)
    return li

# ── Local callback server ─────────────────────────────────────────────────────

auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        auth_code = params.get("code")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Done! You can close this tab and return to Terminal.</h2>")

    def log_message(self, *args):
        pass  # suppress access logs

# ── Main auth flow ────────────────────────────────────────────────────────────

def run():
    li = load_linkedin_config()

    # 1. Build auth URL
    params = {
        "response_type": "code",
        "client_id":     li["client_id"],
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
        "state":         "daily_brief",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    # 2. Start local server to capture callback
    server = http.server.HTTPServer(("localhost", 8765), CallbackHandler)
    t = threading.Thread(target=server.handle_request)
    t.daemon = True
    t.start()

    # 3. Open browser
    print("\n🔐  Opening LinkedIn in your browser…")
    print("   Log in and click Allow for your 'make ai practical' page.")
    print(f"\n   If browser doesn't open, paste this URL into Chrome:\n   {url}\n")
    webbrowser.open(url)
    t.join(timeout=300)  # 5 min timeout

    # 4. Fallback — if redirect failed, let user paste the URL manually
    if not auth_code:
        print("\n⚠️  Auto-capture failed (redirect issue).")
        print("   After approving on LinkedIn, your browser will show an error page.")
        print("   Copy the FULL URL from the browser address bar and paste it here:\n")
        manual_url = input("   Paste URL: ").strip()
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(manual_url).query))
        auth_code = params.get("code")

    if not auth_code:
        print("❌  Still no auth code. Check Client ID and redirect URL in LinkedIn app settings.")
        raise SystemExit(1)

    # 4. Exchange code for token
    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "code":          auth_code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     li["client_id"],
        "client_secret": li["client_secret"],
    })
    resp.raise_for_status()
    token_data = resp.json()

    # 5. Get the organisation ID for the page
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    org_resp = requests.get(
        "https://api.linkedin.com/v2/organizationalEntityAcls"
        "?q=roleAssignee&role=ADMINISTRATOR&projection=(elements*(organizationalTarget~(id,localizedName)))",
        headers=headers
    )
    pages = []
    if org_resp.ok:
        for el in org_resp.json().get("elements", []):
            target = el.get("organizationalTarget~", {})
            pages.append({"id": target.get("id"), "name": target.get("localizedName", "")})

    # Pick the right page
    org_id = None
    if len(pages) == 1:
        org_id = pages[0]["id"]
        print(f"✅  Found page: {pages[0]['name']} (id: {org_id})")
    elif len(pages) > 1:
        print("\nYou manage multiple LinkedIn pages:")
        for i, p in enumerate(pages):
            print(f"  {i+1}. {p['name']} (id: {p['id']})")
        choice = int(input("Enter number for 'make ai practical': ")) - 1
        org_id = pages[choice]["id"]
    else:
        org_id = li.get("org_id", "")
        print(f"⚠️   Could not auto-detect page. Using org_id from config: {org_id}")

    # 6. Save tokens
    tokens = {
        "access_token":  token_data["access_token"],
        "expires_in":    token_data.get("expires_in", 5183944),
        "org_id":        org_id,
        "saved_at":      datetime.now().isoformat(),
    }
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"\n✅  Tokens saved to linkedin_tokens.json")
    print("   You're all set — daily brief will now auto-post to LinkedIn.\n")

if __name__ == "__main__":
    run()
