#!/bin/bash
# 每晚的提醒。由 launchd 叫起來（見 scripts/install_reminder.sh）。
DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://127.0.0.1:${DIARY_PORT:-5050}/"
TODAY=$(date -v-4H +%F)   # 跟網站一樣：凌晨 4 點前算前一天

LETTERS=$(sqlite3 "$DIR/diary.db" "SELECT COUNT(*) FROM letters WHERE deliver_day <= '$TODAY' AND answer IS NULL" 2>/dev/null)
if [ "${LETTERS:-0}" -gt 0 ]; then
  MSG="今天有一封過去的你寄來的信。"
else
  MSG="今天做到了什麼小事？"
fi

# 用對話框而不是通知，因為通知點了不能開網頁。60 秒沒按就自己消失。
ANSWER=$(osascript -e "display dialog \"$MSG\" with title \"日日\" buttons {\"晚點\", \"寫日記\"} default button \"寫日記\" giving up after 60" 2>/dev/null)
if [[ "$ANSWER" == *"寫日記"* ]]; then
  # 網站沒開就先開起來
  if ! curl -s -o /dev/null "$URL"; then
    (cd "$DIR" && nohup .venv/bin/python app.py >/tmp/diarybot.log 2>&1 &)
    sleep 2
  fi
  open "$URL"
fi
