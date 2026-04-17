#!/usr/bin/env python3
"""
AI Daily Brief
Fetches news from configured sources and sends a formatted HTML email.
Run daily at 7:00 AM Melbourne time.
"""

import os
import json
import smtplib
import urllib.parse
import html as html_lib
import tempfile
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    import feedparser
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "-q"])
    import feedparser

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief_config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}\nPlease fill in brief_config.json first.")
    with open(CONFIG_FILE) as f:
        return json.load(f)

# ─── Sources ──────────────────────────────────────────────────────────────────

PEOPLE = {
    # ── Anthropic ──
    "Dario Amodei": {
        "icon": "🧠",
        "role": "Anthropic CEO & Co-founder",
        "queries": ["Dario Amodei jobs society interview", "Dario Amodei future work humanity"],
        "rss": ["https://www.anthropic.com/rss.xml"]
    },
    "Daniela Amodei": {
        "icon": "💡",
        "role": "Anthropic President & Co-founder",
        "queries": ["Daniela Amodei interview society workers", "Daniela Amodei AI impact people"],
        "rss": ["https://www.anthropic.com/rss.xml"]
    },
    "Boris Cherny": {
        "icon": "⌨️",
        "role": "Claude Code Author · Anthropic",
        "queries": ["Boris Cherny AI productivity workers", "Claude Code non-technical users productivity"],
        "rss": ["https://www.anthropic.com/rss.xml"]
    },
    # ── OpenAI ──
    "Sam Altman": {
        "icon": "🚀",
        "role": "OpenAI CEO",
        "queries": ["Sam Altman jobs workers future society", "Sam Altman AI daily life impact"],
        "rss": ["https://openai.com/blog/rss.xml"]
    },
    # ── Investor / Thinker ──
    "Naval Ravikant": {
        "icon": "⚓",
        "role": "Investor & Philosopher",
        "queries": ["Naval Ravikant work life meaning AI", "Naval Ravikant interview 2025"],
        "rss": ["https://nav.al/feed"]
    },
    # ── Top 5 Active AI Builders ──
    "Andrej Karpathy": {
        "icon": "🔬",
        "role": "AI Researcher & Educator (ex-OpenAI, ex-Tesla)",
        "queries": ["Andrej Karpathy education learning AI", "Andrej Karpathy future skills workers"],
        "rss": ["https://karpathy.github.io/feed.xml"]
    },
    "Demis Hassabis": {
        "icon": "🏆",
        "role": "Google DeepMind CEO",
        "queries": ["Demis Hassabis AI society healthcare humanity", "Demis Hassabis interview future"],
        "rss": ["https://deepmind.google/blog/rss.xml"]
    },
    "Yann LeCun": {
        "icon": "🎓",
        "role": "Meta Chief AI Scientist",
        "queries": ["Yann LeCun AI society jobs future interview", "Yann LeCun human intelligence work"],
        "rss": []
    },
    "Ilya Sutskever": {
        "icon": "🛡️",
        "role": "Safe Superintelligence (SSI) Co-founder",
        "queries": ["Ilya Sutskever AI safety society future", "Ilya Sutskever interview humanity"],
        "rss": []
    },
    "Fei-Fei Li": {
        "icon": "🌏",
        "role": "World Labs CEO & Stanford AI Professor",
        "queries": ["Fei-Fei Li AI women education society", "Fei-Fei Li human-centered AI interview"],
        "rss": ["https://worldlabs.ai/blog/rss.xml"]
    },
}

# Groups used for email sections and cards
GROUP_BUILDERS  = "builders"
GROUP_WORK      = "work"
GROUP_LIFE      = "life"

GROUP_META = {
    GROUP_BUILDERS: {"label": "🌟 What the World's Top AI Builders Are Saying",  "short": "Top Builders"},
    GROUP_WORK:     {"label": "💼 What's Happening to Knowledge Workers",         "short": "Work & Agents"},
    GROUP_LIFE:     {"label": "🏡 What's Changing in Daily Life",                 "short": "Daily Life"},
}

TOPICS = [
    # ── Group: Knowledge Workers ──
    {
        "key": "claude_agent",
        "label": "Claude / Agents / Cowork",
        "icon": "🤖",
        "group": GROUP_WORK,
        "queries": ["AI assistant productivity knowledge workers daily", "Claude AI helping professionals work smarter"]
    },
    {
        "key": "vibe_coding",
        "label": "Vibe Coding",
        "icon": "💻",
        "group": GROUP_WORK,
        "queries": ["AI tools non-technical professionals no-code productivity", "AI automate everyday tasks without coding"]
    },
    {
        "key": "eng_pm",
        "label": "Engineering & Product Management",
        "icon": "⚙️",
        "group": GROUP_WORK,
        "queries": ["AI knowledge workers managers professionals impact", "AI changing office work white collar jobs"]
    },
    {
        "key": "future_work",
        "label": "Future of Work",
        "icon": "🔮",
        "group": GROUP_WORK,
        "queries": ["AI future work jobs replaced augmented 2025", "AI workforce skills career adapt"]
    },
    # ── Group: Daily Life ──
    {
        "key": "parenting_ai",
        "label": "Parenting in the AI Era",
        "icon": "👨‍👩‍👧",
        "group": GROUP_LIFE,
        "queries": ["parenting children AI screen time education family", "kids growing up AI generation school"]
    },
    {
        "key": "australia_ai",
        "label": "AI in Australia",
        "icon": "🦘",
        "group": GROUP_LIFE,
        "queries": ["artificial intelligence Australia society business impact", "AI Australia workers jobs education policy"]
    },
]

# ─── Fetchers ─────────────────────────────────────────────────────────────────

def _parse_date(date_str: str):
    """Parse RSS date string, return datetime or None."""
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        try:
            from datetime import timezone
            import re
            # fallback: strip timezone and parse common formats
            clean = re.sub(r'\s+[A-Z]{2,4}$', '', date_str).strip()
            for fmt in ("%a, %d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(clean, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
    return None


def fetch_google_news(query: str, max_items: int = 4, days: int = 3, seen_urls: set = None) -> list[dict]:
    """Pull items from Google News RSS. Filters to last `days` days.
    Falls back to most recent articles if nothing found within the window."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    cutoff = datetime.utcnow() - timedelta(days=days)
    seen_urls = seen_urls or set()
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            return []

        fresh, fallback = [], []
        for entry in feed.entries:
            if len(fresh) >= max_items:
                break
            link = entry.get("link", "#")
            item = {
                "title":     entry.get("title", "Untitled"),
                "link":      link,
                "source":    entry.get("source", {}).get("title", "Google News"),
                "published": entry.get("published", ""),
            }
            if link in seen_urls:
                continue
            pub = _parse_date(entry.get("published", ""))
            if pub and pub < cutoff:
                if len(fallback) < max_items:
                    fallback.append(item)
                continue
            fresh.append(item)

        # Return fresh items; if none, fall back to most recent regardless of age
        return fresh if fresh else fallback[:max_items]
    except Exception as e:
        print(f"  [WARN] Google News fetch failed for '{query}': {e}")
        return []


def fetch_rss(rss_url: str, max_items: int = 3) -> list[dict]:
    """Pull latest items from any RSS feed."""
    try:
        feed = feedparser.parse(rss_url)
        items = []
        for entry in feed.entries[:max_items]:
            summary = entry.get("summary", "")
            # Strip HTML tags from summary
            import re
            summary = re.sub(r"<[^>]+>", "", summary)[:400]
            items.append({
                "title":   entry.get("title", "Untitled"),
                "link":    entry.get("link", "#"),
                "summary": summary,
                "published": entry.get("published", ""),
            })
        return items
    except Exception as e:
        print(f"  [WARN] RSS fetch failed for '{rss_url}': {e}")
        return []


# ─── Email builder ────────────────────────────────────────────────────────────

STYLE = """
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
.wrapper { max-width: 680px; margin: 24px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%); padding: 28px 32px; }
.header h1 { color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; }
.header .date { color: #a0c4ff; font-size: 13px; margin-top: 4px; }
.section { padding: 0 32px; }
.section-title { font-size: 17px; font-weight: 700; color: #1a1a2e; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e8eaf6; }
.person-block { margin-bottom: 20px; }
.person-label { font-size: 13px; font-weight: 700; color: #0f3460; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.news-item { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.news-item:last-child { border-bottom: none; }
.news-item a { color: #1a1a2e; font-size: 14px; text-decoration: none; font-weight: 500; line-height: 1.5; }
.news-item a:hover { color: #0f3460; text-decoration: underline; }
.news-source { font-size: 11px; color: #888; margin-top: 2px; }
.podcast-item { background: #f8f9ff; border-left: 3px solid #4361ee; padding: 12px 14px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }
.podcast-item a { color: #1a1a2e; font-weight: 600; font-size: 14px; text-decoration: none; }
.podcast-summary { font-size: 13px; color: #555; margin-top: 5px; line-height: 1.5; }
.no-items { font-size: 13px; color: #aaa; font-style: italic; }
.news-summary { font-size: 12px; color: #4361ee; margin-top: 3px; font-style: italic; line-height: 1.4; }
.footer { background: #f8f9ff; padding: 16px 32px; text-align: center; border-top: 1px solid #e8eaf6; }
.footer p { font-size: 11px; color: #aaa; margin: 0; }
.takeaway-box { background: #f0f4ff; border-radius: 8px; padding: 18px 20px; margin: 20px 0 8px; }
.takeaway-box h2 { font-size: 15px; font-weight: 700; color: #1a1a2e; margin: 0 0 12px; }
.takeaway-row { display: flex; align-items: flex-start; gap: 8px; padding: 7px 0; border-bottom: 1px solid #dde3f5; }
.takeaway-row:last-child { border-bottom: none; }
.takeaway-tag { font-size: 11px; font-weight: 700; color: #4361ee; white-space: nowrap; min-width: 110px; padding-top: 1px; }
.takeaway-text { font-size: 13px; color: #222; line-height: 1.5; }
.takeaway-text a { color: #0f3460; text-decoration: none; font-weight: 500; }
.takeaway-src { font-size: 11px; color: #888; margin-left: 6px; }
"""

def build_news_rows(items: list[dict]) -> str:
    if not items:
        return '<p class="no-items">No recent news found.</p>'
    rows = ""
    for it in items:
        title   = html_lib.escape(it["title"])
        link    = html_lib.escape(it["link"])
        src     = html_lib.escape(it.get("source", ""))
        pub     = it.get("published", "")[:16]
        summary = html_lib.escape(it.get("summary", ""))
        rows += f"""
        <div class="news-item">
          <a href="{link}" target="_blank">{title}</a>
          {f'<div class="news-summary">💡 {summary}</div>' if summary else ""}
          <div class="news-source">{src} {f"· {pub}" if pub else ""}</div>
        </div>"""
    return rows


def build_podcast_rows(items: list[dict]) -> str:
    if not items:
        return '<p class="no-items">No recent episodes found.</p>'
    rows = ""
    for it in items:
        title   = html_lib.escape(it["title"])
        link    = html_lib.escape(it["link"])
        summary = html_lib.escape(it.get("summary", ""))
        rows += f"""
        <div class="podcast-item">
          <a href="{link}" target="_blank">🎧 {title}</a>
          {f'<div class="podcast-summary">{summary}…</div>' if summary else ""}
        </div>"""
    return rows


def build_takeaway_row(icon: str, label: str, item: dict) -> str:
    if not item:
        return ""
    title  = html_lib.escape(item["title"])
    link   = html_lib.escape(item["link"])
    src    = html_lib.escape(item.get("source", ""))
    return f"""
    <div class="takeaway-row">
      <div class="takeaway-tag">{icon} {label}</div>
      <div class="takeaway-text">
        <a href="{link}" target="_blank">{title}</a>
        {f'<span class="takeaway-src">— {src}</span>' if src else ""}
      </div>
    </div>"""


def summarise_item(item: dict, context: str, api_key: str) -> str:
    """Call Claude API to generate a one-line 'why it matters' summary."""
    if not api_key:
        return ""
    try:
        import urllib.request
        prompt = (
            f"Headline: {item['title']}\n"
            f"Context: {context}\n\n"
            "In ONE sentence (max 20 words), explain why this matters to a knowledge worker or parent. "
            "Be specific and practical. No fluff. Do not start with 'This'."
        )
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 80,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except Exception:
        return ""


def fetch_all(config: dict) -> tuple:
    """Fetch all news data. Returns (people_items, pod_items, topic_items)."""
    max_items = config.get("max_items_per_section", 4)
    seen      = load_seen_urls()
    api_key   = config.get("claude_api_key", "")
    if seen:
        print(f"  Skipping {len(seen)} URLs already shown in last brief.")

    people_items = {}
    for name, meta in PEOPLE.items():
        print(f"  Fetching news for {name}…")
        items = []
        # Try Google News first
        for q in meta["queries"][:1]:
            items = fetch_google_news(q, max_items, seen_urls=seen)
            if items:
                break
        # Fallback: direct RSS feeds
        if not items:
            for rss_url in meta.get("rss", []):
                rss_items = fetch_rss(rss_url, max_items=max_items)
                if rss_items:
                    items = rss_items
                    break
        # Add summaries
        if api_key and items:
            for it in items[:2]:
                it["summary"] = summarise_item(it, f"{name}, {meta['role']}", api_key)
        people_items[name] = items

    print("  Fetching AI Daily Brief…")
    pod_items = fetch_rss(config.get("podcast_rss", "https://aidailybrief.beehiiv.com/feed"), max_items=3)

    topic_items = {}
    for topic in TOPICS:
        print(f"  Fetching topic: {topic['label']}…")
        items = []
        for q in topic["queries"][:1]:
            items = fetch_google_news(q, max_items, seen_urls=seen)
            if items:
                break
        # Add summaries
        if api_key and items:
            for it in items[:2]:
                it["summary"] = summarise_item(it, topic["label"], api_key)
        topic_items[topic["key"]] = items

    return people_items, pod_items, topic_items


def build_email(config: dict, people_items: dict = None, pod_items: list = None, topic_items: dict = None) -> str:
    today_str = datetime.now().strftime("%A, %B %d %Y")

    # Allow pre-fetched data to be passed in (avoids double fetching)
    if people_items is None or pod_items is None or topic_items is None:
        people_items, pod_items, topic_items = fetch_all(config)

    # ── Key Takeaways block ──
    takeaway_rows = ""
    # Top story per leader
    for name, meta in PEOPLE.items():
        items = people_items.get(name, [])
        if items:
            takeaway_rows += build_takeaway_row(meta["icon"], name.split()[0], items[0])
    # Top podcast item
    if pod_items:
        takeaway_rows += build_takeaway_row("🎙️", "AI Podcast", pod_items[0])
    # Top story per topic
    for topic in TOPICS:
        items = topic_items.get(topic["key"], [])
        if items:
            takeaway_rows += build_takeaway_row(topic["icon"], topic["label"].split("/")[0].strip(), items[0])

    takeaways_html = f"""
    <div class="section">
      <div class="takeaway-box">
        <h2>📌 Today's Key Takeaways</h2>
        {takeaway_rows if takeaway_rows else '<p class="no-items">No stories found today.</p>'}
      </div>
    </div>"""

    # ── Group 1: Builders (people) ──
    people_html = ""
    for name, meta in PEOPLE.items():
        people_html += f"""
        <div class="person-block">
          <div class="person-label">{meta["icon"]} {name} · {meta["role"]}</div>
          {build_news_rows(people_items.get(name, []))}
        </div>"""

    # ── Podcast ──
    podcast_html = build_podcast_rows(pod_items)

    # ── Group 2: Knowledge Workers ──
    work_html = ""
    for topic in TOPICS:
        if topic["group"] != GROUP_WORK:
            continue
        work_html += f"""
        <div class="person-block">
          <div class="person-label">{topic["icon"]} {topic["label"]}</div>
          {build_news_rows(topic_items.get(topic["key"], []))}
        </div>"""

    # ── Group 3: Daily Life ──
    life_html = ""
    for topic in TOPICS:
        if topic["group"] != GROUP_LIFE:
            continue
        life_html += f"""
        <div class="person-block">
          <div class="person-label">{topic["icon"]} {topic["label"]}</div>
          {build_news_rows(topic_items.get(topic["key"], []))}
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>{STYLE}</style>
</head>
<body>
  <div class="wrapper">

    <div class="header">
      <h1>🤖 AI Daily Brief</h1>
      <div class="date">{today_str} · Good morning!</div>
    </div>

    {takeaways_html}

    <div class="section">
      <div class="section-title">🌟 What the World's Top AI Builders Are Saying</div>
      {people_html}

      <div class="section-title">🎙️ AI Daily Brief Podcast</div>
      {podcast_html}

      <div class="section-title">💼 What's Happening to Knowledge Workers</div>
      {work_html}

      <div class="section-title">🏡 What's Changing in Daily Life</div>
      {life_html}
    </div>

    <div class="footer">
      <p>AI Daily Brief · Generated automatically · Sources: Google News, Podcast RSS</p>
    </div>
  </div>
</body>
</html>"""


# ─── Card generators ──────────────────────────────────────────────────────────

def _build_card_html(people_items, topic_items, pod_items, clickable=False):
    """Build the card HTML. clickable=True adds links; False = static for PNG screenshot."""
    today = datetime.now().strftime("%B %d, %Y")

    def clean(title):
        return title.rsplit(" - ", 1)[0] if " - " in title else title

    def make_row(label, it, clickable):
        title = html_lib.escape(clean(it["title"]))
        src   = html_lib.escape(it.get("source", ""))
        link  = it.get("link", "#")
        if clickable:
            return f"""
            <div class="row">
              <div class="tag">{label}</div>
              <div class="story-wrap">
                <a class="story-link" href="{link}" target="_blank">{title}</a>
                {f'<span class="src">— {src}</span>' if src else ''}
              </div>
            </div>"""
        else:
            short = html_lib.escape(clean(it["title"])[:72] + ("…" if len(clean(it["title"])) > 72 else ""))
            return f"""
            <div class="row">
              <span class="tag">{label}</span>
              <span class="story">{short}</span>
            </div>"""

    def make_section_rows(group_key):
        rows = ""
        if group_key == GROUP_BUILDERS:
            for name, meta in PEOPLE.items():
                items = people_items.get(name, [])
                if not items:
                    continue
                rows += make_row(f"{meta['icon']} {name}", items[0], clickable)
                if clickable and len(items) > 1:
                    rows += make_row(f"{meta['icon']} {name}", items[1], clickable)
        else:
            count = 3 if clickable else 1
            for topic in TOPICS:
                if topic["group"] != group_key:
                    continue
                items = topic_items.get(topic["key"], [])
                label = f"{topic['icon']} {topic['label'].split('/')[0].strip()}"
                for it in items[:count]:
                    rows += make_row(label, it, clickable)
        return rows

    # Podcast rows
    pod_rows = ""
    if pod_items:
        for it in pod_items[:2]:
            title   = html_lib.escape(it["title"])
            link    = it.get("link", "#")
            summary = html_lib.escape(it.get("summary", "")[:120])
            if clickable:
                pod_rows += f"""
                <div class="row">
                  <div class="tag">🎙️ Podcast</div>
                  <div class="story-wrap">
                    <a class="story-link" href="{link}" target="_blank">{title}</a>
                    {f'<div class="summary">{summary}…</div>' if summary else ''}
                  </div>
                </div>"""
            else:
                short = html_lib.escape(title[:72] + ("…" if len(title) > 72 else ""))
                pod_rows += f"""
                <div class="row">
                  <span class="tag">🎙️ Podcast</span>
                  <span class="story">{short}</span>
                </div>"""

    if clickable:
        # Rich scrollable HTML for email attachment — 3 grouped sections
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Daily Brief — {today}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  background: #0d1b2a;
  font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
  min-height: 100vh; padding: 0 0 48px;
}}
.header {{
  background: linear-gradient(135deg, #0d1b2a 0%, #1b2a4a 55%, #0f3460 100%);
  padding: 32px 48px 24px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  position: sticky; top: 0; z-index: 10;
}}
.logo {{ display: flex; align-items: center; gap: 14px; }}
.logo-badge {{
  background: linear-gradient(135deg, #e63946, #c1121f);
  color: white; font-weight: 900; font-size: 20px;
  padding: 7px 14px; border-radius: 8px; letter-spacing: 1px;
}}
.logo-text {{ color: white; font-size: 18px; font-weight: 700; line-height: 1.2; }}
.logo-sub {{ color: #a0c4ff; font-size: 12px; font-weight: 400; }}
.date-badge {{
  background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
  color: #a0c4ff; font-size: 13px; padding: 6px 16px; border-radius: 20px;
}}
.content {{ max-width: 860px; margin: 0 auto; padding: 32px 24px 0; }}
.section-title {{
  color: #e63946; font-size: 11px; font-weight: 800;
  letter-spacing: 2px; text-transform: uppercase;
  margin: 32px 0 12px; padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}}
.row {{
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 10px; padding: 12px 16px;
  display: flex; gap: 16px; margin-bottom: 8px;
  transition: background 0.15s;
}}
.row:hover {{ background: rgba(255,255,255,0.08); }}
.tag {{
  color: #a0c4ff; font-size: 12px; font-weight: 700;
  white-space: nowrap; min-width: 140px; padding-top: 2px;
}}
.story-wrap {{ flex: 1; }}
.story-link {{
  color: #ffffff; font-size: 14px; font-weight: 500;
  text-decoration: none; line-height: 1.5; display: block;
}}
.story-link:hover {{ color: #a0c4ff; text-decoration: underline; }}
.src {{ color: #6b8cba; font-size: 11px; margin-top: 3px; display: block; }}
.summary {{ color: #8fa8c8; font-size: 12px; margin-top: 4px; line-height: 1.5; }}
.footer {{
  text-align: center; padding: 40px 24px 0;
  color: rgba(160,196,255,0.4); font-size: 12px;
}}
</style>
</head>
<body>
  <div class="header">
    <div class="logo">
      <div class="logo-badge">MAP</div>
      <div class="logo-text">AI Daily Brief<div class="logo-sub">Make AI Practical</div></div>
    </div>
    <div class="date-badge">📅 {today}</div>
  </div>
  <div class="content">
    <div class="section-title">🌟 What the World's Top AI Builders Are Saying</div>
    {make_section_rows(GROUP_BUILDERS)}
    <div class="section-title">💼 What's Happening to Knowledge Workers</div>
    {make_section_rows(GROUP_WORK)}
    <div class="section-title">🏡 What's Changing in Daily Life</div>
    {make_section_rows(GROUP_LIFE)}
    {f'<div class="section-title">🎙️ Podcast</div>{pod_rows}' if pod_rows else ''}
  </div>
  <div class="footer">
    #AI #FutureOfWork #MakeAIPractical #AINews #AIAustralia · makeaipractical.com
  </div>
</body>
</html>"""

    else:
        # ── Pick top 1 story per person/topic for the card ──
        def top_story(items):
            return clean(items[0]["title"]) if items else None

        builder_bullets = []
        for name, meta in PEOPLE.items():
            items = people_items.get(name, [])
            s = top_story(items)
            if s and len(builder_bullets) < 4:
                builder_bullets.append((meta["icon"], name.split()[0], s))

        work_bullets = []
        for topic in TOPICS:
            if topic["group"] != GROUP_WORK:
                continue
            items = topic_items.get(topic["key"], [])
            s = top_story(items)
            if s and len(work_bullets) < 3:
                work_bullets.append((topic["icon"], topic["label"].split("/")[0].strip(), s))

        life_bullets = []
        for topic in TOPICS:
            if topic["group"] != GROUP_LIFE:
                continue
            items = topic_items.get(topic["key"], [])
            s = top_story(items)
            if s and len(life_bullets) < 3:
                life_bullets.append((topic["icon"], topic["label"].split("/")[0].strip(), s))

        def render_bullets(bullets):
            rows = ""
            for icon, label, title in bullets:
                short = html_lib.escape(title[:68] + ("…" if len(title) > 68 else ""))
                lbl   = html_lib.escape(label)
                rows += f"""<div class="item">
                  <div class="item-tag">{icon} {lbl}</div>
                  <div class="item-title">{short}</div>
                </div>"""
            return rows

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  width: 1200px; height: 630px; overflow: hidden;
  background: linear-gradient(145deg, #0a1628 0%, #0f2347 40%, #0d3060 100%);
  font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
  display: flex; flex-direction: column;
  position: relative;
}}
/* accent bar top */
.accent {{ height: 5px; background: linear-gradient(90deg, #e63946, #4361ee, #a0c4ff); }}
.header {{
  padding: 22px 52px 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}}
.logo {{ display: flex; align-items: center; gap: 14px; }}
.logo-badge {{
  background: linear-gradient(135deg, #e63946 0%, #c1121f 100%);
  color: white; font-weight: 900; font-size: 20px;
  padding: 7px 15px; border-radius: 9px; letter-spacing: 2px;
  box-shadow: 0 4px 14px rgba(230,57,70,0.4);
}}
.logo-right {{ }}
.logo-title {{ color: #ffffff; font-size: 19px; font-weight: 800; letter-spacing: -0.3px; }}
.logo-sub {{ color: #7eb8ff; font-size: 12px; font-weight: 400; margin-top: 1px; }}
.date-pill {{
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.13);
  color: #a0c4ff; font-size: 13px; padding: 7px 18px;
  border-radius: 24px; letter-spacing: 0.2px;
}}
/* 3-col grid */
.cols {{
  flex: 1; display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 0; overflow: hidden;
}}
.col {{
  padding: 16px 20px 12px;
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex; flex-direction: column; gap: 7px;
}}
.col:last-child {{ border-right: none; }}
.col-head {{
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}}
.col-icon {{
  font-size: 15px;
}}
.col-label {{
  color: #e63946; font-size: 10px; font-weight: 800;
  letter-spacing: 1.8px; text-transform: uppercase;
}}
.item {{
  background: rgba(255,255,255,0.055);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 8px 11px;
  display: flex; flex-direction: column; gap: 3px;
}}
.item-tag {{
  color: #7eb8ff; font-size: 10px; font-weight: 700;
  letter-spacing: 0.3px;
}}
.item-title {{
  color: #f0f4ff; font-size: 12px; font-weight: 500;
  line-height: 1.45;
}}
.footer {{
  padding: 10px 52px 14px;
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid rgba(255,255,255,0.07);
}}
.tags {{ color: rgba(160,196,255,0.45); font-size: 10.5px; letter-spacing: 0.3px; }}
.brand {{ color: rgba(255,255,255,0.2); font-size: 10.5px; }}
</style>
</head>
<body>
  <div class="accent"></div>
  <div class="header">
    <div class="logo">
      <div class="logo-badge">MAP</div>
      <div class="logo-right">
        <div class="logo-title">AI Daily Brief</div>
        <div class="logo-sub">Make AI Practical · makeaipractical.com</div>
      </div>
    </div>
    <div class="date-pill">📅 {today}</div>
  </div>

  <div class="cols">
    <div class="col">
      <div class="col-head">
        <span class="col-icon">🌟</span>
        <span class="col-label">Top Builders Say</span>
      </div>
      {render_bullets(builder_bullets)}
    </div>
    <div class="col">
      <div class="col-head">
        <span class="col-icon">💼</span>
        <span class="col-label">Knowledge Workers</span>
      </div>
      {render_bullets(work_bullets)}
    </div>
    <div class="col">
      <div class="col-head">
        <span class="col-icon">🏡</span>
        <span class="col-label">Daily Life</span>
      </div>
      {render_bullets(life_bullets)}
    </div>
  </div>

  <div class="footer">
    <div class="tags">#AI #FutureOfWork #MakeAIPractical #AINews #AIAustralia #VibeCoding</div>
    <div class="brand">Follow for daily AI insights →</div>
  </div>
</body>
</html>"""


def generate_wechat_card(people_items: dict, topic_items: dict, pod_items: list):
    """Render a 900x900 Chinese WeChat card PNG. Returns file path or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [WeChat Card] Playwright not installed — skipping.")
        return None

    today = datetime.now().strftime("%Y年%-m月%-d日")
    weekdays = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
    weekday  = weekdays[datetime.now().weekday()]

    def clean(title):
        return title.rsplit(" - ", 1)[0] if " - " in title else title

    def top_items(group_key, limit=3):
        results = []
        if group_key == GROUP_BUILDERS:
            for name, meta in PEOPLE.items():
                items = people_items.get(name, [])
                if items and len(results) < limit:
                    results.append((meta["icon"], name, clean(items[0]["title"])))
        else:
            for topic in TOPICS:
                if topic["group"] != group_key:
                    continue
                items = topic_items.get(topic["key"], [])
                if items and len(results) < limit:
                    results.append((topic["icon"], topic["label"].split("/")[0].strip(), clean(items[0]["title"])))
        return results

    def section_html(items):
        rows = ""
        for icon, label, title in items:
            short = html_lib.escape(title[:52] + ("…" if len(title) > 52 else ""))
            lbl   = html_lib.escape(label)
            rows += f"""<div class="item">
              <div class="item-label">{icon} {lbl}</div>
              <div class="item-title">{short}</div>
            </div>"""
        return rows

    builders = top_items(GROUP_BUILDERS, 3)
    workers  = top_items(GROUP_WORK, 3)
    life     = top_items(GROUP_LIFE, 3)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  width: 900px; height: 900px; overflow: hidden;
  background: linear-gradient(150deg, #0a1628 0%, #0f2347 45%, #0d3060 100%);
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
  display: flex; flex-direction: column;
}}
.accent {{ height: 5px; background: linear-gradient(90deg, #e63946, #4361ee, #a0c4ff); }}
.header {{
  padding: 22px 40px 18px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(255,255,255,0.09);
  flex-shrink: 0;
}}
.logo {{ display: flex; align-items: center; gap: 12px; }}
.logo-badge {{
  background: linear-gradient(135deg, #e63946, #c1121f);
  color: white; font-weight: 900; font-size: 18px;
  padding: 6px 13px; border-radius: 8px; letter-spacing: 2px;
  box-shadow: 0 4px 12px rgba(230,57,70,0.4);
}}
.logo-title {{ color: #ffffff; font-size: 17px; font-weight: 800; }}
.logo-sub {{ color: #7eb8ff; font-size: 11px; margin-top: 2px; }}
.date-box {{ text-align: right; }}
.date-main {{ color: #a0c4ff; font-size: 14px; font-weight: 600; }}
.date-day {{ color: #6b8cba; font-size: 11px; margin-top: 2px; }}
.body {{
  flex: 1; display: grid; grid-template-rows: 1fr 1fr 1fr;
  padding: 12px 28px; gap: 10px; overflow: hidden;
}}
.section {{ display: flex; flex-direction: column; gap: 6px; }}
.sec-header {{
  display: flex; align-items: center; gap: 8px;
  padding-bottom: 5px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}}
.sec-icon {{ font-size: 14px; }}
.sec-label {{
  color: #e63946; font-size: 10px; font-weight: 800;
  letter-spacing: 1.5px; text-transform: uppercase;
}}
.items {{ display: flex; flex-direction: column; gap: 5px; flex: 1; }}
.item {{
  background: rgba(255,255,255,0.055);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 7px 11px;
  display: flex; flex-direction: column; gap: 2px;
}}
.item-label {{ color: #7eb8ff; font-size: 10px; font-weight: 700; }}
.item-title {{ color: #f0f4ff; font-size: 12px; font-weight: 500; line-height: 1.45; }}
.footer {{
  padding: 8px 40px 14px;
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid rgba(255,255,255,0.07);
  flex-shrink: 0;
}}
.tags {{ color: rgba(160,196,255,0.4); font-size: 10px; letter-spacing: 0.5px; }}
.brand {{ color: rgba(255,255,255,0.2); font-size: 10px; }}
</style>
</head>
<body>
  <div class="accent"></div>
  <div class="header">
    <div class="logo">
      <div>
        <div class="logo-title">AI 每日简报</div>
        <div class="logo-sub">Make AI Practical · 让 AI 真正落地</div>
      </div>
    </div>
    <div class="date-box">
      <div class="date-main">📅 {today}</div>
      <div class="date-day">{weekday}</div>
    </div>
  </div>

  <div class="body">
    <div class="section">
      <div class="sec-header">
        <span class="sec-icon">🌟</span>
        <span class="sec-label">顶级 AI 大咖这样说</span>
      </div>
      <div class="items">{section_html(builders)}</div>
    </div>
    <div class="section">
      <div class="sec-header">
        <span class="sec-icon">💼</span>
        <span class="sec-label">知识工作者正在经历什么</span>
      </div>
      <div class="items">{section_html(workers)}</div>
    </div>
    <div class="section">
      <div class="sec-header">
        <span class="sec-icon">🏡</span>
        <span class="sec-label">日常生活正在改变</span>
      </div>
      <div class="items">{section_html(life)}</div>
    </div>
  </div>

  <div class="footer">
    <div class="tags">#AI日报 #人工智能 #知识工作者 #未来工作 #澳洲AI</div>
    <div class="brand">Make AI Practical</div>
  </div>
</body>
</html>"""

    card_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_card_wechat.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 900, "height": 900})
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
                tmp.write(html)
                tmp_path = tmp.name
            page.goto(f"file://{tmp_path}")
            page.wait_for_load_state("domcontentloaded")
            page.screenshot(path=card_path, full_page=False)
            browser.close()
            os.unlink(tmp_path)
        print(f"  ✅ WeChat card saved: {card_path}")
        return card_path
    except Exception as e:
        print(f"  [WeChat Card] Failed: {e}")
        return None


def generate_card_image(people_items: dict, topic_items: dict, pod_items: list):
    """Render a 1200x630 PNG for LinkedIn sharing. Returns file path or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Card] Playwright not installed — skipping PNG generation.")
        return None

    card_html = _build_card_html(people_items, topic_items, pod_items, clickable=False)
    card_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_card.png")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 630})
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as tmp:
                tmp.write(card_html)
                tmp_path = tmp.name
            page.goto(f"file://{tmp_path}")
            page.wait_for_load_state("domcontentloaded")
            page.screenshot(path=card_path, full_page=False)
            browser.close()
            os.unlink(tmp_path)
        print(f"  ✅ LinkedIn card saved: {card_path}")
        return card_path
    except Exception as e:
        print(f"  [Card] PNG generation failed: {e}")
        return None


def generate_card_html_file(people_items: dict, topic_items: dict, pod_items: list):
    """Generate a rich clickable HTML card. Returns file path or None."""
    card_html = _build_card_html(people_items, topic_items, pod_items, clickable=True)
    today_slug = datetime.now().strftime("%Y-%m-%d")
    html_path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"daily_card_{today_slug}.html")
    try:
        with open(html_path, "w") as f:
            f.write(card_html)
        print(f"  ✅ Clickable card saved: {html_path}")
        return html_path
    except Exception as e:
        print(f"  [Card] HTML generation failed: {e}")
        return None


# ─── Email sender ─────────────────────────────────────────────────────────────

def send_email(html_body: str, config: dict, card_png: str = None, card_html: str = None, **kwargs):
    msg = MIMEMultipart("mixed")
    today_short = datetime.now().strftime("%b %d")
    msg["Subject"] = f"🤖 AI Daily Brief — {today_short}"
    msg["From"]    = config["smtp_user"]
    msg["To"]      = ", ".join(config["recipients"])

    msg.attach(MIMEText(html_body, "html"))

    # Attach clickable HTML card (open in browser — all stories with links)
    if card_html and os.path.exists(card_html):
        today_slug = datetime.now().strftime("%Y-%m-%d")
        with open(card_html, "rb") as f:
            part = MIMEBase("text", "html")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment",
                            filename=f"AI_Brief_Card_{today_slug}.html")
            msg.attach(part)
        print("  📎 Clickable HTML card attached.")

    # Attach PNG for LinkedIn sharing
    if card_png and os.path.exists(card_png):
        with open(card_png, "rb") as f:
            part = MIMEBase("image", "png")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment",
                            filename="AI_Brief_LinkedIn.png")
            msg.attach(part)
        print("  📎 LinkedIn PNG attached.")

    # Attach WeChat card
    if "card_wechat" in kwargs:
        wechat_png = kwargs["card_wechat"]
        if wechat_png and os.path.exists(wechat_png):
            with open(wechat_png, "rb") as f:
                part = MIMEBase("image", "png")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment",
                                filename="AI_Brief_WeChat.png")
                msg.attach(part)
            print("  📎 WeChat card attached.")

    print(f"  Sending to: {config['recipients']}…")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config["smtp_user"], config["smtp_password"].replace(" ", ""))
        server.sendmail(config["smtp_user"], config["recipients"], msg.as_string())
    print("  ✅ Email sent!")


# ─── Deduplication ────────────────────────────────────────────────────────────

DIR_             = os.path.dirname(os.path.abspath(__file__))
LAST_SENT_FILE   = os.path.join(DIR_, ".last_sent")
SEEN_URLS_FILE   = os.path.join(DIR_, ".seen_urls")

def already_sent_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_SENT_FILE):
        with open(LAST_SENT_FILE) as f:
            return f.read().strip() == today
    return False

def mark_sent_today():
    today = datetime.now().strftime("%Y-%m-%d")
    with open(LAST_SENT_FILE, "w") as f:
        f.write(today)

def load_seen_urls() -> set:
    """Load URLs shown in the last brief to avoid repeats."""
    if os.path.exists(SEEN_URLS_FILE):
        with open(SEEN_URLS_FILE) as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_urls(people_items: dict, pod_items: list, topic_items: dict):
    """Save all URLs from this brief so tomorrow's run can skip them."""
    urls = set()
    for items in people_items.values():
        for it in items:
            urls.add(it.get("link", ""))
    for it in pod_items:
        urls.add(it.get("link", ""))
    for items in topic_items.values():
        for it in items:
            urls.add(it.get("link", ""))
    urls.discard("")
    with open(SEEN_URLS_FILE, "w") as f:
        f.write("\n".join(urls))


# ─── LinkedIn reminder email ──────────────────────────────────────────────────

def send_linkedin_reminder(config: dict, people_items: dict, topic_items: dict, pod_items: list):
    """Send a short plain-text email with ready-to-paste LinkedIn post text."""
    today = datetime.now().strftime("%B %d, %Y")

    def clean(title):
        return title.rsplit(" - ", 1)[0] if " - " in title else title

    lines = [f"🤖 AI Daily Brief — {today}", ""]
    lines.append("What's happening in AI today — stories that matter for knowledge workers and daily life.")
    lines.append("")

    lines.append("🌟 Top Builders")
    for name, meta in PEOPLE.items():
        items = people_items.get(name, [])
        if items:
            lines.append(f"• {name}: {clean(items[0]['title'])[:80]}")
    lines.append("")

    lines.append("💼 Knowledge Workers")
    for topic in TOPICS:
        if topic["group"] != GROUP_WORK:
            continue
        items = topic_items.get(topic["key"], [])
        if items:
            lines.append(f"• {topic['icon']} {clean(items[0]['title'])[:80]}")
    lines.append("")

    lines.append("🏡 Daily Life")
    for topic in TOPICS:
        if topic["group"] != GROUP_LIFE:
            continue
        items = topic_items.get(topic["key"], [])
        if items:
            lines.append(f"• {topic['icon']} {clean(items[0]['title'])[:80]}")
    lines.append("")
    lines.append("#AI #FutureOfWork #MakeAIPractical #AINews #AIAustralia #VibeCoding")

    post_text = "\n".join(lines)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📋 LinkedIn post ready — {today}"
        msg["From"]    = config["smtp_user"]
        msg["To"]      = config["smtp_user"]  # only to yourself
        body = f"Copy and paste this to LinkedIn:\n\n{post_text}"
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config["smtp_user"], config["smtp_password"].replace(" ", ""))
            server.sendmail(config["smtp_user"], [config["smtp_user"]], msg.as_string())
        print("  ✅ LinkedIn reminder sent to your inbox.")
    except Exception as e:
        print(f"  [LinkedIn Reminder] Failed: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 AI Daily Brief starting…")
    cfg = load_config()

    if cfg.get("smtp_user", "").startswith("YOUR_"):
        print("\n⚠️  Please fill in brief_config.json with your Gmail credentials first.")
        print("   See SETUP.md for instructions.\n")
        print("Building preview HTML instead…")
        people_items, pod_items, topic_items = fetch_all(cfg)
        body = build_email(cfg, people_items, pod_items, topic_items)
        preview_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview_brief.html")
        with open(preview_path, "w") as f:
            f.write(body)
        print(f"   Preview saved to: {preview_path}")
    elif already_sent_today():
        print("⏭️  Brief already sent today — skipping.")
    else:
        # Fetch once, reuse for email + LinkedIn + cards
        people_items, pod_items, topic_items = fetch_all(cfg)
        body = build_email(cfg, people_items, pod_items, topic_items)
        print("  Generating cards…")
        card_png    = generate_card_image(people_items, topic_items, pod_items)
        card_html   = generate_card_html_file(people_items, topic_items, pod_items)
        card_wechat = generate_wechat_card(people_items, topic_items, pod_items)
        send_email(body, cfg, card_png=card_png, card_html=card_html, card_wechat=card_wechat)
        send_linkedin_reminder(cfg, people_items, topic_items, pod_items)
        save_seen_urls(people_items, pod_items, topic_items)
        mark_sent_today()

    print("Done.")
