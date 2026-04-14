# Setup Guide — AI Daily Brief

## Step 1: Get a Gmail App Password

You need a **Gmail App Password** (not your normal password).

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Make sure **2-Step Verification** is ON
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Create a new app → name it `AI Daily Brief`
5. Copy the 16-character password

---

## Step 2: Fill in `brief_config.json`

Open `brief_config.json` and replace the placeholders:

```json
{
  "smtp_user": "your_gmail@gmail.com",
  "smtp_password": "xxxx xxxx xxxx xxxx",
  "recipients": ["xmyang1221@gmail.com", "michelle.yang@leonardo.ai"],
  "podcast_rss": "https://aidailybrief.beehiiv.com/feed"
}
```

---

## Step 3: Install Python dependency

Open Terminal and run:

```bash
pip3 install feedparser
```

---

## Step 4: Test run

In Terminal:

```bash
python3 /path/to/daily-brief/daily_brief.py
```

If credentials are not set yet, it saves a `preview_brief.html` — open it in your browser to check the layout.

---

## Step 5: Schedule at 7:00 AM daily (macOS)

### 5a. Edit the plist file

Open `com.michelle.ai-daily-brief.plist` in a text editor.
Find this line and update the path to match your folder:

```xml
<string>/Users/YOURUSERNAME/Claude-Work/daily-brief/run_brief.sh</string>
```

Replace `YOURUSERNAME` with your actual Mac username (check in Finder → your home folder name).

### 5b. Install the LaunchAgent

```bash
# Copy the plist to LaunchAgents
cp /path/to/daily-brief/com.michelle.ai-daily-brief.plist ~/Library/LaunchAgents/

# Make the run script executable
chmod +x /path/to/daily-brief/run_brief.sh

# Load the agent (starts scheduling)
launchctl load ~/Library/LaunchAgents/com.michelle.ai-daily-brief.plist
```

### 5c. Verify it's loaded

```bash
launchctl list | grep ai-daily-brief
```

You should see `com.michelle.ai-daily-brief` in the list.

### To uninstall / stop

```bash
launchctl unload ~/Library/LaunchAgents/com.michelle.ai-daily-brief.plist
rm ~/Library/LaunchAgents/com.michelle.ai-daily-brief.plist
```

---

## Optional: Update the podcast RSS

The default uses the AI Daily Brief **newsletter** RSS.
To use the **podcast** feed instead:
1. Open Apple Podcasts → search "AI Daily Brief" → right-click → Copy RSS Feed URL
2. Paste that URL into `brief_config.json` under `"podcast_rss"`

---

## Files overview

| File | Purpose |
|------|---------|
| `daily_brief.py` | Main script — fetches news and sends email |
| `brief_config.json` | Your credentials and settings |
| `sources.md` | Reference list of all sources and topics |
| `run_brief.sh` | Shell wrapper called by the scheduler |
| `com.michelle.ai-daily-brief.plist` | macOS LaunchAgent (7am daily schedule) |
| `brief.log` | Run log (created after first run) |
| `preview_brief.html` | Email preview (generated if no credentials yet) |
