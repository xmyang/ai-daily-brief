#!/usr/bin/env python3
"""
AI Daily Brief — v2 (quality-first rewrite)
Backbone = direct RSS from curated premium sources (influencers, AI-native
companies, mainstream media). Google News is only used for niche topics that
RSS can't cover, with a hard `when:` freshness operator.

Freshness: 24h window by default; widens to 72h only when the day is quiet.
Nothing older than 72h is ever shown. Undated items are dropped.
Run daily at 5:00 AM Melbourne time via GitHub Actions.
"""

import os
import json
import smtplib
import calendar
import urllib.parse
import html as html_lib
import tempfile
import re
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

# ─── Tunable thresholds ───────────────────────────────────────────────────────
FRESH_HOURS      = 24   # primary window: last 24h
FALLBACK_HOURS   = 72   # widen to 72h only if the 24h harvest is thin
MIN_TOTAL_FRESH  = 8    # "thin" = fewer than this many items across the whole brief
MAX_SEEN_URLS    = 1500 # rolling dedupe memory (~30 days of briefs)

# Relevance scoring — weighted keywords matched against title+summary (lowercased).
RELEVANCE_KEYWORDS = {
    # +3: core audience topics
    "claude":              3,
    "anthropic":           3,
    "cowork":              3,
    "agent skill":         3,
    "practical ai":        3,
    "ai adoption":         3,
    # +2: adjacent professional topics
    "ai coding":           2,
    "vibe coding":         2,
    "non-technical":       2,
    "product management":  2,
    "ai agents":           2,
    # +1: lifestyle / community angles
    "parenting":           1,
    "future of work":      1,
    "coaching":            1,
    "chinese":             1,
    "bilingual":           1,
    # negative: low-signal finance noise
    "stock price":        -2,
    "market cap":         -2,
    "layoffs":            -1,
}
MAX_SCORED_FOR_SUMMARY = 15   # only the top-N scored items get sent to Claude

# ─── Sources ──────────────────────────────────────────────────────────────────
# Backbone: direct RSS from people/companies worth reading, verified 2026-08.
# (Anthropic has NO public RSS — covered via the Google News topic below.)

PEOPLE = {
    "Simon Willison": {
        "icon": "🧰",
        "role": "Independent AI Researcher · simonwillison.net",
        "rss": ["https://simonwillison.net/atom/everything/"],
    },
    "Ethan Mollick": {
        "icon": "🎓",
        "role": "Wharton Professor · One Useful Thing",
        "rss": ["https://www.oneusefulthing.org/feed"],
    },
    "Nathan Lambert": {
        "icon": "🔬",
        "role": "AI Researcher · Interconnects",
        "rss": ["https://www.interconnects.ai/feed"],
    },
    "Jack Clark": {
        "icon": "📡",
        "role": "Anthropic Co-founder · Import AI",
        "rss": ["https://importai.substack.com/feed"],
    },
    "Latent Space": {
        "icon": "🎙️",
        "role": "swyx & Alessio · AI Engineer newsletter",
        "rss": ["https://www.latent.space/feed"],
    },
    "Andrej Karpathy": {
        "icon": "🧠",
        "role": "AI Researcher & Educator (ex-OpenAI, ex-Tesla)",
        "rss": ["https://karpathy.github.io/feed.xml"],
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

# Topics: "feeds" = direct RSS pool (preferred); "queries" = Google News fallback
# for coverage RSS can't provide. Google News queries get a `when:Nd` operator
# appended automatically — no stale results, ever.
TOPICS = [
    {
        "key": "companies",
        "label": "AI-Native Companies",
        "icon": "🏢",
        "group": GROUP_WORK,
        "feeds": [
            ("OpenAI",       "https://openai.com/news/rss.xml"),
            ("DeepMind",     "https://deepmind.google/blog/rss.xml"),
            ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
        ],
        "queries": [],
    },
    {
        # Anthropic has no RSS feed (verified: /news/rss.xml → 404).
        "key": "anthropic",
        "label": "Anthropic / Claude",
        "icon": "🤖",
        "group": GROUP_WORK,
        "feeds": [],
        "queries": ["Anthropic OR Claude AI"],
        "gn_days": 1,
    },
    {
        "key": "media",
        "label": "Mainstream Media on AI",
        "icon": "📰",
        "group": GROUP_WORK,
        "feeds": [
            ("MIT Tech Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
            ("TechCrunch",      "https://techcrunch.com/category/artificial-intelligence/feed/"),
            ("The Verge",       "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
            ("The Guardian",    "https://www.theguardian.com/technology/artificialintelligenceai/rss"),
        ],
        "queries": [],
    },
    {
        "key": "high_signal",
        "label": "Community Radar",
        "icon": "🔥",
        "group": GROUP_WORK,
        "feeds": [
            ("Hacker News AI", "https://hnrss.org/newest?q=AI&points=100"),
        ],
        "queries": [],
    },
    # ── Group: Daily Life (RSS can't cover these — Google News with when:3d) ──
    {
        "key": "parenting_ai",
        "label": "Parenting in the AI Era",
        "icon": "👨‍👩‍👧",
        "group": GROUP_LIFE,
        "feeds": [],
        "queries": ["parenting children AI education family",
                    "kids growing up AI generation school"],
        "gn_days": 3,
    },
    {
        "key": "australia_ai",
        "label": "AI in Australia",
        "icon": "🦘",
        "group": GROUP_LIFE,
        "feeds": [],
        "queries": ["artificial intelligence Australia business impact",
                    "AI Australia workers jobs education policy"],
        "gn_days": 3,
    },
]

# ─── Fetchers ─────────────────────────────────────────────────────────────────

def _entry_datetime(entry):
    """Robust date extraction: use feedparser's parsed structs (handles RSS
    pubDate AND Atom published/updated). Returns naive UTC datetime or None."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = entry.get(attr)
        if parsed:
            try:
                return datetime.utcfromtimestamp(calendar.timegm(parsed))
            except Exception:
                continue
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def fetch_rss(rss_url: str, max_items: int = 6, source_name: str = "",
              seen_urls: set = None) -> list[dict]:
    """Pull latest items from an RSS/Atom feed.
    - Undated entries are DROPPED (they can't be freshness-checked).
    - Dedupes against seen_urls.
    - Returns newest-first, each item carrying a real datetime in '_dt'.
    """
    seen_urls = seen_urls or set()
    try:
        feed = feedparser.parse(rss_url)
        items = []
        for entry in feed.entries[:30]:
            dt = _entry_datetime(entry)
            if dt is None:
                continue                      # undated → cannot verify freshness → drop
            link = entry.get("link", "")
            if not link or link in seen_urls:
                continue
            items.append({
                "title":     entry.get("title", "Untitled"),
                "link":      link,
                "source":    source_name or feed.feed.get("title", ""),
                "summary":   _strip_html(entry.get("summary", ""))[:400],
                "published": entry.get("published", entry.get("updated", "")),
                "_dt":       dt,
            })
        items.sort(key=lambda x: x["_dt"], reverse=True)
        return items[:max_items]
    except Exception as e:
        print(f"  [WARN] RSS fetch failed for '{rss_url}': {e}")
        return []


def fetch_google_news(query: str, max_items: int = 4, days: int = 1,
                      seen_urls: set = None) -> list[dict]:
    """Pull items from Google News RSS with a hard `when:Nd` operator so Google
    only returns items from the last N days (no relevance-ranked stale results,
    no fallback to old articles). Undated entries are dropped."""
    seen_urls = seen_urls or set()
    encoded = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:30]:
            dt = _entry_datetime(entry)
            if dt is None:
                continue
            link = entry.get("link", "#")
            if link in seen_urls:
                continue
            items.append({
                "title":     entry.get("title", "Untitled"),
                "link":      link,
                "source":    entry.get("source", {}).get("title", "Google News"),
                "published": entry.get("published", ""),
                "_dt":       dt,
            })
        items.sort(key=lambda x: x["_dt"], reverse=True)
        return items[:max_items]
    except Exception as e:
        print(f"  [WARN] Google News fetch failed for '{query}': {e}")
        return []


# ─── Freshness window ─────────────────────────────────────────────────────────

def apply_freshness_window(people_items: dict, topic_items: dict) -> tuple[dict, dict, int]:
    """Global two-tier window:
    - Count items across the whole brief that are <= FRESH_HOURS old.
    - If >= MIN_TOTAL_FRESH, use the 24h window; otherwise widen to 72h.
    - Anything older than the chosen window is dropped. No exceptions.
    Returns (people_items, topic_items, window_hours).
    """
    now = datetime.utcnow()
    fresh_cutoff = now - timedelta(hours=FRESH_HOURS)

    all_items = [it for lst in people_items.values() for it in lst] + \
                [it for lst in topic_items.values() for it in lst]
    n_fresh = sum(1 for it in all_items if it["_dt"] >= fresh_cutoff)

    window = FRESH_HOURS if n_fresh >= MIN_TOTAL_FRESH else FALLBACK_HOURS
    cutoff = now - timedelta(hours=window)
    print(f"  [freshness] {n_fresh} items within {FRESH_HOURS}h → using {window}h window.")

    def _filter(lst):
        kept = [it for it in lst if it["_dt"] >= cutoff]
        if len(kept) < len(lst):
            print(f"    dropped {len(lst) - len(kept)} items older than {window}h")
        return kept

    people_items = {k: _filter(v) for k, v in people_items.items()}
    topic_items  = {k: _filter(v) for k, v in topic_items.items()}
    return people_items, topic_items, window


def score_item(item: dict) -> int:
    """Sum RELEVANCE_KEYWORDS matches on lowercased title + summary."""
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return sum(weight for kw, weight in RELEVANCE_KEYWORDS.items() if kw in text)


# Audience profile for the Claude summariser. Depersonalised — safe to share externally.
SUMMARY_SYSTEM_PROMPT = (
    "You are writing for a reader who is a Technical PM at a design-software company, "
    "an ACC-credentialed life coach, and founder of a community for Chinese-speaking "
    "professionals in Australia focused on practical AI adoption. They care about: "
    "practical AI adoption for non-technical users, the intersection of AI + coaching + "
    "community, parenting in the AI era, and the future of work.\n\n"
    "For each item, write:\n"
    "- **What happened** (1 sentence, neutral)\n"
    "- **Why it matters** (1 sentence tying to practical AI adoption, coaching, or a "
    "Chinese-speaking professional community. If genuinely irrelevant, return 'skip' "
    "and the item will be excluded.)\n"
    "- **Share angle** (optional — only if obviously shareable on Xiaohongshu/WeChat, "
    "phrased as a hook)\n\n"
    "Tone: warm, precise, peer-to-peer — not expert-signalling."
)


def summarise_item(item: dict, context: str, api_key: str) -> str:
    """Call Claude API with the audience-aware prompt.
    Returns a multi-line summary string, or "" on error.
    If Claude replies starting with 'skip', sets item['_skip'] = True.
    """
    if not api_key:
        return ""
    try:
        import urllib.request
        user_msg = (
            f"Headline: {item.get('title', '')}\n"
            f"Source context: {context}\n"
            f"Summary/excerpt: {item.get('summary', '')[:400]}\n\n"
            "Respond in the 3-field format. Keep each field to one short sentence."
        )
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 220,
            "system": SUMMARY_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}]
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
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            if text.lower().lstrip("*_- ").startswith("skip"):
                item["_skip"] = True
                return ""
            return text
    except Exception:
        return ""


def fetch_all(config: dict) -> tuple:
    """Fetch all news data. Returns (people_items, pod_items, topic_items).

    Pipeline:
      1. Direct RSS per influencer (backbone) + per topic feed pool.
      2. Google News (with when:Nd) only for topics without RSS coverage.
      3. Global freshness window: 24h, widening to 72h on quiet days.
      4. Score every item; top MAX_SCORED_FOR_SUMMARY get Claude summaries.
      5. Drop items Claude flagged as 'skip'.
    """
    max_items = config.get("max_items_per_section", 4)
    gn_days   = config.get("days_lookback", 3)
    seen      = load_seen_urls()
    api_key   = config.get("claude_api_key", "")
    if seen:
        print(f"  Skipping {len(seen)} URLs shown in recent briefs.")

    # ── 1. Influencer feeds (direct RSS only — no keyword search) ──
    people_items = {}
    for name, meta in PEOPLE.items():
        print(f"  Fetching {name}…")
        items = []
        for rss_url in meta["rss"]:
            items = fetch_rss(rss_url, max_items=max_items,
                              source_name=name, seen_urls=seen)
            if items:
                break
        people_items[name] = items

    # ── 2. Topic pools ──
    topic_items = {}
    for topic in TOPICS:
        print(f"  Fetching topic: {topic['label']}…")
        pooled = []
        for src_name, url in topic.get("feeds", []):
            pooled.extend(fetch_rss(url, max_items=6,
                                    source_name=src_name, seen_urls=seen))
        for q in topic.get("queries", []):
            got = fetch_google_news(q, max_items=max_items,
                                    days=topic.get("gn_days", gn_days),
                                    seen_urls=seen)
            pooled.extend(got)
            if got:
                break    # first query that returns fresh items wins
        # newest first, dedupe by link within the pool
        pooled.sort(key=lambda x: x["_dt"], reverse=True)
        unique, links = [], set()
        for it in pooled:
            if it["link"] not in links:
                unique.append(it)
                links.add(it["link"])
        topic_items[topic["key"]] = unique[:max_items * 2]

    # ── 3. Global freshness window (24h → 72h) ──
    people_items, topic_items, window = apply_freshness_window(people_items, topic_items)
    topic_items = {k: v[:max_items] for k, v in topic_items.items()}

    # Podcast: same freshness rule as everything else (a daily pod should be daily).
    print("  Fetching AI Daily Brief podcast…")
    pod_all = fetch_rss(config.get("podcast_rss", "https://aidailybrief.beehiiv.com/feed"),
                        max_items=3, source_name="AI Daily Brief", seen_urls=seen)
    pod_cutoff = datetime.utcnow() - timedelta(hours=window)
    pod_items = [it for it in pod_all if it["_dt"] >= pod_cutoff]

    # ── 4-5. Relevance-gated Claude summaries ──
    if api_key:
        scored: list[tuple[int, dict, str]] = []
        for name, items in people_items.items():
            role = PEOPLE[name]["role"]
            for it in items:
                scored.append((score_item(it), it, f"{name}, {role}"))
        for topic in TOPICS:
            for it in topic_items.get(topic["key"], []):
                scored.append((score_item(it), it, topic["label"]))

        relevant = [s for s in scored if s[0] > 0]
        relevant.sort(key=lambda x: x[0], reverse=True)
        relevant = relevant[:MAX_SCORED_FOR_SUMMARY]
        print(f"  Scoring: {len(relevant)} of {len(scored)} items passed relevance gate (>0).")

        for _score, it, ctx in relevant:
            it["summary"] = summarise_item(it, ctx, api_key)

        def _keep(lst): return [it for it in lst if not it.get("_skip")]
        people_items = {k: _keep(v) for k, v in people_items.items()}
        topic_items  = {k: _keep(v) for k, v in topic_items.items()}

    return people_items, pod_items, topic_items



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


def build_email(config: dict, people_items: dict = None, pod_items: list = None, topic_items: dict = None) -> str:
    today_str = datetime.now().strftime("%A, %B %d %Y")

    # Allow pre-fetched data to be passed in (avoids double fetching)
    if people_items is None or pod_items is None or topic_items is None:
        people_items, pod_items, topic_items = fetch_all(config)

    # ── Key Takeaways block ──
    takeaway_rows = ""
    for name, meta in PEOPLE.items():
        items = people_items.get(name, [])
        if items:
            takeaway_rows += build_takeaway_row(meta["icon"], name.split()[0], items[0])
    if pod_items:
        takeaway_rows += build_takeaway_row("🎙️", "AI Podcast", pod_items[0])
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
      <p>AI Daily Brief · Generated automatically · Sources: curated RSS + Google News</p>
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
    """Load URLs shown in recent briefs (rolling window) to avoid repeats."""
    if os.path.exists(SEEN_URLS_FILE):
        with open(SEEN_URLS_FILE) as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_urls(people_items: dict, pod_items: list, topic_items: dict):
    """APPEND this brief's URLs to the rolling seen-list (capped at MAX_SEEN_URLS).
    v1 overwrote the file with only yesterday's URLs, so an article blocked today
    could come back the day after tomorrow. Now the memory is cumulative."""
    new_urls = []
    for items in people_items.values():
        for it in items:
            new_urls.append(it.get("link", ""))
    for it in pod_items:
        new_urls.append(it.get("link", ""))
    for items in topic_items.values():
        for it in items:
            new_urls.append(it.get("link", ""))
    new_urls = [u for u in new_urls if u]

    old_lines = []
    if os.path.exists(SEEN_URLS_FILE):
        with open(SEEN_URLS_FILE) as f:
            old_lines = [line.strip() for line in f if line.strip()]

    combined, seen_set = [], set()
    for u in old_lines + new_urls:            # oldest first; newest at the end
        if u not in seen_set:
            combined.append(u)
            seen_set.add(u)
    combined = combined[-MAX_SEEN_URLS:]      # keep the newest MAX_SEEN_URLS

    with open(SEEN_URLS_FILE, "w") as f:
        f.write("\n".join(combined))


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
