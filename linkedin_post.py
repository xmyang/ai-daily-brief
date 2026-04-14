#!/usr/bin/env python3
"""
LinkedIn post formatter and publisher.
Called automatically by daily_brief.py after the email is sent.
"""

import os
import json
from datetime import datetime

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_tokens.json")

# ── Format brief data as LinkedIn post ───────────────────────────────────────

def format_post(people_items: dict, topic_items: dict, pod_items: list) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    lines = []

    lines.append(f"🤖 AI Daily Brief — {today}")
    lines.append("")
    lines.append("What's happening in AI today — key stories you should know.")
    lines.append("")

    # ── Key Takeaways (top story per person, max 5) ──
    lines.append("📌 Key Takeaways")
    count = 0
    for name, items in people_items.items():
        if items and count < 5:
            title = items[0]["title"]
            # Trim Google News source suffix if present (e.g. "... - Reuters")
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"• {name}: {title}")
            count += 1
    lines.append("")

    # ── Topic Highlights ──
    TOPIC_LABELS = {
        "claude_agent":  "🤖 Claude / Agents",
        "vibe_coding":   "💻 Vibe Coding",
        "eng_pm":        "⚙️ Engineering & PM",
        "parenting_ai":  "👨‍👩‍👧 Parenting in AI Era",
        "future_work":   "🔮 Future of Work",
        "australia_ai":  "🦘 AI in Australia",
    }

    lines.append("🔥 Topic Highlights")
    for key, label in TOPIC_LABELS.items():
        if key == "australia_ai":
            continue  # Australia gets its own section
        items = topic_items.get(key, [])
        if items:
            title = items[0]["title"]
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"{label}: {title}")
    lines.append("")

    # ── Australia AI ──
    au_items = topic_items.get("australia_ai", [])
    if au_items:
        lines.append("🦘 AI in Australia")
        for it in au_items[:3]:
            title = it["title"]
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            lines.append(f"• {title}")
        lines.append("")

    # ── Podcast ──
    if pod_items:
        ep = pod_items[0]
        title = ep["title"]
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
        lines.append(f"🎙️ AI Daily Brief Podcast: {title}")
        lines.append("")

    # ── Hashtags ──
    lines.append("#AI #ArtificialIntelligence #AINews #MakeAIPractical #AIDaily #FutureOfWork #AIAustralia")

    post_text = "\n".join(lines)

    # LinkedIn max 3000 chars — trim if needed
    if len(post_text) > 2950:
        post_text = post_text[:2947] + "..."

    return post_text


# ── Post to LinkedIn company page ────────────────────────────────────────────

def post_to_linkedin(people_items: dict, topic_items: dict, pod_items: list) -> bool:
    if not os.path.exists(TOKENS_FILE):
        print("  [LinkedIn] No tokens found — run linkedin_auth.py first. Skipping.")
        return False

    with open(TOKENS_FILE) as f:
        tokens = json.load(f)

    access_token = tokens.get("access_token")
    org_id       = tokens.get("org_id")

    if not access_token or not org_id:
        print("  [LinkedIn] Incomplete tokens — re-run linkedin_auth.py. Skipping.")
        return False

    post_text = format_post(people_items, topic_items, pod_items)
    author    = f"urn:li:organization:{org_id}"

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    resp = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers=headers,
        json=payload,
    )

    if resp.status_code in (200, 201):
        post_id = resp.headers.get("x-restli-id", "unknown")
        print(f"  ✅ LinkedIn posted! Post ID: {post_id}")
        return True
    else:
        print(f"  [LinkedIn] Post failed: {resp.status_code} — {resp.text[:200]}")
        return False
