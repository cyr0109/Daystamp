# Daystamp 日日

一個在本機跑、繁體中文的 30 秒日常紀錄。每天記一件做到的小事、心情和三餐，AI 每週幫你回顧。每個功能都有心理學研究支持。

日記只存在你自己的電腦上。AI 用 [Ollama](https://ollama.com) 在本機跑，不會把日記送到雲端。

## 每天記什麼

| 欄位 | 必填 | 為什麼 |
|---|---|---|
| 今天做到的一件小事 | ✅ | **Three Good Things**（Seligman et al., 2005）：每天寫下做到的好事，幸福感能維持好幾個月。**Progress Principle**（Amabile & Kramer, 2011）：看見小進步是最強的動力來源。 |
| 心情 1–10 + 情緒標籤 | ✅ | **Affect Labeling**（Lieberman et al., 2007）：替情緒取名字，會降低杏仁核的反應。AI 先建議一個標籤，你自己決定。 |
| 三餐 | | 日常的細節是回想一天最好的線索。 |
| 今天的歌 | | **音樂喚起的自傳式記憶**（Janata, 2009；Belfi et al., 2016）：音樂是很強的回憶線索。用 iTunes 搜尋，存下封面和 30 秒試聽。 |
| 自由日記 | | **Expressive Writing**（Pennebaker, 1997）。 |
| 今日一字 | | AI 讀完今天的紀錄，建議一個字，你可以改。日曆上每天蓋一個印章。 |
| 天氣 | 自動 | **編碼特定性原則**（Tulving & Thomson, 1973）：記得當時的情境，比較容易想起那天。用 Open-Meteo。 |

一天一筆，晚上回想整天的事，是 **Day Reconstruction Method**（Kahneman et al., 2004）的做法：準確度接近一天問好幾次，但輕鬆很多。凌晨 4 點前寫的算前一天。

## 其他功能

- **一題一頁**：一次只問一題，按 Enter 就跳到下一題。設計依據是 **Fogg 行為模型**（Fogg, 2009）：降低做一件事的難度，最能讓行為發生。
- **以前的今天**：隨機出現一則以前的小勝利，心情 ≥ 7 分的優先。**Savoring**（Bryant & Veroff, 2007）。
- **給未來的信**：留一個問題給 1 個月到 1 年後的自己，送到之前是封起來的。送到時，左右對照當時和現在。**Future Self-Continuity**（Hershfield, 2011）、**End of History Illusion**（Quoidbach, Gilbert & Wilson, 2013）：人總是低估自己會變多少。
- **植物**：寫越多天，植物長越高，花色跟著這週最常出現的情緒。不會死，也不看連續天數；很久沒寫，它只會睡覺。每 100 天結一次種子，那一盆就搬進溫室。刻意不做懲罰，是為了避開 **過度辯護效應**（Lepper et al., 1973）：外在獎勵太強，會蓋過原本想寫的理由。
- **每週回顧**：AI 讀完這週的紀錄，寫一段溫和的回顧。
- **每晚提醒**：macOS `launchd` 每晚 10 點跳出提醒。
- **Markdown 備份**：每次存檔都會在 `diaries_md/` 寫一份 `.md`。

## AI 安全

AI 的輸出只當資料，絕不執行：
- 情緒標籤必須在 8 個的白名單內；今日一字必須剛好是一個中文字。不合格就丟掉。
- 回顧文字一律當純文字顯示（Jinja 自動轉義）。
- 不拿 AI 的輸出去跑 `eval`、shell 或 SQL；SQL 全部用參數。
- AI 連不上或超時，日記照樣存得起來。
- 所有寫入都只收 JSON，擋掉其他網站偷送表單（CSRF）。

## 怎麼跑

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ollama pull qwen3.5:9b                 # 想換模型：DIARY_MODEL=其他模型
.venv/bin/flask --app app init-db      # ⚠️ 會清空 diary.db
.venv/bin/python app.py                # 打開 http://127.0.0.1:5050
```

- 每晚提醒：`scripts/install_reminder.sh`（預設 22 點，可以傳別的小時，例如 `scripts/install_reminder.sh 21`）
- 手機（同一個 Wi-Fi）：`DIARY_HOST=0.0.0.0 .venv/bin/python app.py`。⚠️ 沒有登入功能，同一個網路的人都看得到，只在家裡用。
- 天氣的城市：`DIARY_LAT`、`DIARY_LON`（預設台北）
- 測試：`.venv/bin/python -m unittest discover tests`

## 技術

Flask + SQLite + Jinja + 原生 JS，不用打包工具。Ollama（預設 `qwen3.5:9b`）。
