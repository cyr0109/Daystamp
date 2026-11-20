#!/bin/bash
# 安裝每晚 22:00 的提醒。移除：launchctl bootout gui/$(id -u)/com.diarybot.remind
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.diarybot.remind.plist"
HOUR="${1:-22}"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.diarybot.remind</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/scripts/remind.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>0</integer></dict>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.diarybot.remind" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "裝好了：每天 $HOUR:00 提醒。"
