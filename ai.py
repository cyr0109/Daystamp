"""本機 AI（Ollama）。

安全原則：AI 的輸出只當「資料」，絕不執行。
- 標籤必須在白名單內，一字必須剛好是一個中文字，不合格就丟掉
- 回顧文字只當純文字顯示（模板不會用 |safe）
- AI 掛了就回傳 None，日記照樣存
"""
import os
import re
import json

import ollama

MODEL = os.environ.get("DIARY_MODEL", "qwen3.5:9b")
EMOTIONS = ["開心", "平靜", "感恩", "疲累", "焦慮", "難過", "生氣", "煩躁"]
REVIEW_MAX_CHARS = 1200

_client = ollama.Client(timeout=90)
_ONE_HAN = re.compile(r"^[一-鿿]$")

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "emotion": {"type": "string", "enum": EMOTIONS},
        "word": {"type": "string"},
    },
    "required": ["emotion", "word"],
}


def _chat(prompt, fmt=None):
    resp = _client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=fmt,
        think=False,
        options={"temperature": 0.4},
    )
    return resp.message.content or ""


def is_one_han(s):
    return isinstance(s, str) and bool(_ONE_HAN.match(s))


def clean_suggestion(raw):
    """把 AI 回傳的 JSON 字串過濾成安全的 {emotion, word}，不合格的欄位變 None。"""
    try:
        # 模型有時會把 JSON 包在 ```json ``` 裡，只取大括號那段
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (TypeError, ValueError, AttributeError):
        return {"emotion": None, "word": None}
    if not isinstance(data, dict):
        return {"emotion": None, "word": None}
    emotion = data.get("emotion")
    word = data.get("word")
    return {
        "emotion": emotion if emotion in EMOTIONS else None,
        "word": word.strip() if isinstance(word, str) and is_one_han(word.strip()) else None,
    }


def suggest(entry):
    """讀今天的紀錄，建議一個情緒標籤和一個字。"""
    lines = [f"今天做到的小事：{entry.get('small_win', '')}",
             f"心情分數（1-10）：{entry.get('mood', '')}"]
    for key, label in [("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐"),
                       ("song_title", "今天的歌"), ("note", "日記")]:
        if entry.get(key):
            lines.append(f"{label}：{entry[key]}")
    prompt = (
        "你是一個日記助手。讀完下面這個人今天的紀錄，回傳 JSON：\n"
        f"- emotion：只能從這 8 個詞裡原封不動挑一個，不可以用其他詞：{'、'.join(EMOTIONS)}\n"
        "- word：用「一個」繁體中文字形容這一天（例如：累、暖、爽、忙）\n\n"
        + "\n".join(lines)
    )
    try:
        return clean_suggestion(_chat(prompt, SUGGEST_SCHEMA))
    except Exception as e:  # 連不到 Ollama、超時、模型不存在……都不能擋住存檔
        print(f"[ai] suggest 失敗：{e}")
        return {"emotion": None, "word": None}


def weekly_review(entries, letters_answered):
    """寫一段每週回顧。entries 是這週的紀錄（dict list）。"""
    if not entries:
        return None
    days = []
    for e in entries:
        days.append(f"{e['day']}｜心情 {e['mood']}｜{e['emotion']}｜做到的事：{e['small_win']}"
                    + (f"｜日記：{e['note'][:200]}" if e.get("note") else ""))
    prompt = (
        "你是一個溫暖、不說教的日記助手。下面是一個人這週的紀錄。\n"
        "請用繁體中文、第二人稱「你」，寫 3 到 5 句的每週回顧：\n"
        "1. 點出這週做到的小事（具體提到幾件）\n"
        "2. 描述這週心情的樣子（不要評價好壞）\n"
        "3. 只有在紀錄裡真的有心情 5 分以下的日子時，才溫和地說那天也做到了什麼\n"
        "只能根據下面寫到的內容，不要猜測或補充紀錄裡沒有的事。紀錄很少就寫短一點。\n"
        "不要給建議、不要用條列、不要用 Markdown。\n"
        + (f"這週也回答了 {letters_answered} 封過去的自己留的問題，順帶提一句。\n" if letters_answered else "")
        + "\n" + "\n".join(days)
    )
    try:
        text = _chat(prompt).strip()
    except Exception as e:
        print(f"[ai] weekly_review 失敗：{e}")
        return None
    return text[:REVIEW_MAX_CHARS] or None
