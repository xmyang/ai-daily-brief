#!/bin/bash
echo "====== AI Daily Brief Schedule Debug ======"
echo ""

PLIST="$HOME/Library/LaunchAgents/com.michelle.ai-daily-brief.plist"
SCRIPT="$HOME/Documents/Claude-Work/daily-brief/run_brief.sh"

# 1. Check plist exists in LaunchAgents
echo "1. Plist installed?"
if [ -f "$PLIST" ]; then
  echo "   ✅ Found: $PLIST"
else
  echo "   ❌ NOT found at $PLIST"
  echo "   Fix: cp ~/Documents/Claude-Work/daily-brief/com.michelle.ai-daily-brief.plist ~/Library/LaunchAgents/"
fi
echo ""

# 2. Check plist is loaded
echo "2. Loaded in launchctl?"
STATUS=$(launchctl list | grep "ai-daily-brief")
if [ -n "$STATUS" ]; then
  echo "   ✅ Loaded: $STATUS"
else
  echo "   ❌ NOT loaded"
  echo "   Fix: launchctl load ~/Library/LaunchAgents/com.michelle.ai-daily-brief.plist"
fi
echo ""

# 3. Check script path in plist
echo "3. Script path in plist?"
if [ -f "$PLIST" ]; then
  PLIST_PATH=$(grep -A1 "/bin/bash" "$PLIST" | grep "string" | sed 's/.*<string>//;s/<\/string>.*//' | tr -d ' ')
  echo "   Plist says: $PLIST_PATH"
  if [ -f "$PLIST_PATH" ]; then
    echo "   ✅ File exists"
  else
    echo "   ❌ File NOT found at that path"
    echo "   Fix: Update the path in the plist to match where run_brief.sh actually is"
    echo "   Your actual script is at: $(find $HOME -name 'run_brief.sh' 2>/dev/null | head -1)"
  fi
fi
echo ""

# 4. Check run_brief.sh is executable
echo "4. run_brief.sh executable?"
ACTUAL_SCRIPT=$(find $HOME -name "run_brief.sh" 2>/dev/null | head -1)
if [ -n "$ACTUAL_SCRIPT" ]; then
  if [ -x "$ACTUAL_SCRIPT" ]; then
    echo "   ✅ Executable: $ACTUAL_SCRIPT"
  else
    echo "   ❌ Not executable"
    echo "   Fix: chmod +x \"$ACTUAL_SCRIPT\""
  fi
else
  echo "   ❌ run_brief.sh not found on this Mac"
fi
echo ""

# 5. Check last sent file
echo "5. Dedup status?"
LAST_SENT=$(find $HOME -name ".last_sent" 2>/dev/null | head -1)
if [ -n "$LAST_SENT" ]; then
  echo "   Last sent: $(cat $LAST_SENT)"
  echo "   Today:     $(date +%Y-%m-%d)"
else
  echo "   No .last_sent file yet (never run via scheduler)"
fi
echo ""

# 6. Check log for errors
echo "6. Recent log output?"
LOG=$(find $HOME -name "brief.log" 2>/dev/null | head -1)
if [ -n "$LOG" ]; then
  echo "   --- Last 20 lines of $LOG ---"
  tail -20 "$LOG"
else
  echo "   No brief.log found yet"
fi
echo ""

echo "====== Done ======"
