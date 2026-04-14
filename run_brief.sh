#!/bin/bash
# AI Daily Brief runner
# This script is called by the macOS LaunchAgent at 7:00am daily

# Directory of this script (must be first)
DIR="$(cd "$(dirname "$0")" && pwd)"

# Find Python 3 — try all common macOS locations (LaunchAgents have no PATH)
PYTHON=""
for p in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /opt/local/bin/python3; do
  if [ -x "$p" ]; then
    PYTHON="$p"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 not found" >> "$DIR/brief.log"
  exit 1
fi

# Install feedparser if missing
"$PYTHON" -c "import feedparser" 2>/dev/null || "$PYTHON" -m pip install feedparser -q

# Run the brief
"$PYTHON" "$DIR/daily_brief.py" >> "$DIR/brief.log" 2>&1
