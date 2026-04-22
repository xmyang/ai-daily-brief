# AI Daily Brief — Sources

## People to Track

| Person | Role | Social / Feed |
|--------|------|---------------|
| **Dario Amodei** | Anthropic CEO & Co-founder | [X @darioamodei](https://x.com/darioamodei) · [Anthropic Blog](https://www.anthropic.com/news) |
| **Daniela Amodei** | Anthropic President & Co-founder | [X @danielaamodei](https://x.com/danielaamodei) |
| **Sam Altman** | OpenAI CEO | [X @sama](https://x.com/sama) · [Blog](https://blog.samaltman.com) · [YouTube](https://www.youtube.com/@sama) |
| **Naval Ravikant** | AngelList Co-founder, Investor | [X @naval](https://x.com/naval) · [NavalManifesto](https://nav.al) |

---

## Podcasts & Newsletters

| Source | Platform | RSS / Link |
|--------|----------|------------|
| **The AI Daily Brief** | Podcast (Nathaniel Whittemore) | [Apple Podcasts](https://podcasts.apple.com/us/podcast/the-ai-daily-brief-artificial-intelligence-news/id1680633614) · [Spotify](https://open.spotify.com/show/7gKwwMLFLc6RmjmRpbMtEO) · Newsletter RSS: `https://aidailybrief.beehiiv.com/feed` |

> **To find podcast RSS**: Open Apple Podcasts → Search "AI Daily Brief" → Share → Copy Link. Then paste at [getrssfeed.com](https://getrssfeed.com) to get the direct RSS URL.

---

## Topics Monitored

| Topic | Search Keywords Used |
|-------|---------------------|
| 🤖 Claude / Agents / Cowork | `Claude AI agent cowork`, `Anthropic Claude` |
| 💻 Vibe Coding | `vibe coding`, `AI coding tools` |
| ⚙️ Engineering & PM | `engineering AI product management`, `AI developer tools` |
| 👨‍👩‍👧 Parenting in AI Era | `parenting children AI era`, `kids AI education` |
| 🔮 Future of Work | `future of work AI`, `AI jobs automation` |

---

## News Sources Used

- **Google News RSS** — free, no API key needed, searches across all publishers
- **Podcast RSS feeds** — direct from podcast host
- **Beehiiv Newsletter RSS** — for AI Daily Brief newsletter

---

## High-Signal AI Feeds

Pooled under the 🔥 **High-Signal Feeds** section in the brief. All items pass the same freshness + relevance scoring as other sources.

| Source | Feed |
|--------|------|
| **Anthropic Blog** | `https://www.anthropic.com/news/rss.xml` |
| **Simon Willison** | `https://simonwillison.net/atom/everything/` |
| **Hacker News (AI, 100+ points)** | `https://hnrss.org/newest?q=AI&points=100` |
| **Ethan Mollick — One Useful Thing** | `https://www.oneusefulthing.org/feed` |
| **Latent Space** | `https://www.latent.space/feed` |

---

## Freshness & Relevance Filters

- **Fresh** (≤48h) — always shown.
- **Recent** (48h–7d) — up to 5 if fresh <4 items, else up to 3.
- **Stale** (>7d) — dropped, logged as a count.
- **Relevance scoring** — items with score >0 (weighted keywords in `RELEVANCE_KEYWORDS`) are ranked and the top 15 get Claude-generated "why it matters" summaries.

Tune thresholds in `daily_brief.py` under *Tunable thresholds*.

---

## Setup Notes

1. Clone this folder to your machine
2. Fill in `brief_config.json` with your Gmail app password
3. Run `python3 daily_brief.py` to test
4. The scheduled task runs at **7:00 AM Melbourne time** daily
