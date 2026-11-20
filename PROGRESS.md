# PROGRESS

給下一個 session 接手用。最後更新：2026-11-21。
決定和待辦清單在 `PLAN.md`，功能和心理學依據在 `README.md`。

## 現在的狀態

- Repo：https://github.com/cyr0109/Daystamp （branch `main`，全部推上去了）
- 名字：中文「日日」，英文 Daystamp
- 跑法：`.venv/bin/python app.py` → http://127.0.0.1:5050
  - 不用 5000：macOS 的 AirPlay 接收器會佔用 5000
- 模型：`qwen3.5:4b`（`ai.py` 的 `MODEL`，可以用 `DIARY_MODEL` 覆蓋）
  - `think=False`：思考模式會跑超過 90 秒
  - `keep_alive="1m"`，並限制 `num_predict`，避免電腦卡
  - 9b 也還在本機，但 4b 快一倍、記憶體減半，修好 prompt 之後品質夠用
- 測試：`.venv/bin/python -m unittest discover tests`（9 個，全過）

## 設計（已經定案）

- 字體：全站只用 **jf 粉圓（Huninn）**，從 Google Fonts 載入
- 風格：和風手帳。生成り色的方格紙；今日一字做成**朱色的日付印**（字 + `YY.MM.DD` 日期帶，有かすれ效果，用 `base.html` 裡的 SVG filter `#kasure`）；日曆的心情用藍色，分數越高越濃
- 今日一字：**1～2 個中文字**，2 個字時套 `.two` class 縮小
- AI 建議如果跟你已經填的不一樣，會顯示「換成『X』」按鈕，不會偷偷蓋掉

## Prompt 的教訓（`ai.py`）

1. **不要在 prompt 裡給例子**：小模型會直接抄（之前例子寫「爽」，4b 就一直回「爽」）
2. 「一到兩個字」會被理解成「兩個詞」→ 要寫「只回一個詞（字串，不是陣列）」
3. 要說「形容感覺」，不然會回「電話」、「考試」這種事件
4. **條件判斷交給程式**：低分的日子由 Python 先挑出來再告訴模型；句數跟著天數走（最多 天數+1 句）。小模型會為了湊句數編內容
5. 日期給 `11/17`，不要給 `11-17`（會被唸成「十一十七日」）
6. Ollama 的 `format`（JSON schema）對 qwen3.5 不一定有效，會包 ```json。所以 `clean_suggestion` 會先取出 `{...}` 那段，再用白名單檢查

## 資料

- `diary.db` 是新的資料庫。舊的改名成 `diary.backup-2025-04-22.db`（裡面是 2 篇測試資料，可以刪）
- 2026-11-20 有一篇測試紀錄（「把拖了兩週的報告交出去了」），使用者會自己改掉
- `diary.db`、`diaries_md/`、`diary.backup-*.db` 都在 `.gitignore` 裡，不會上傳

## 還沒做 / 下一步

- [ ] **GitHub Pages 互動 demo**（討論過、還沒開始）：用假資料把現有 Jinja 模板產生成靜態 HTML，再加一個小 JS 把 `/api/...` 換成假回應（AI 回答預先寫好，寫的東西存在 localStorage）。歌曲搜尋先試瀏覽器能不能直接連 iTunes。頁面上要標明「這是展示版」
- [ ] 沒實際看過的：**淺色模式**、**手機寬度**的畫面
- [ ] 每晚提醒還沒安裝，也沒實際跳出來過：`scripts/install_reminder.sh`
- [ ] 回顧有時會多寫一句沒必要的話（例如「這段時間沒有特別焦慮」），還可以再調
- [ ] `PLAN.md` 裡「之後再做」的項目：年度回顧、輪替小問題、拍照、出門用（要先做登入）
