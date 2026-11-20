"""本機 AI（Ollama）。

安全原則：AI 的輸出只當「資料」，絕不執行。
- 標籤必須在白名單內，今日一字必須是 1～2 個中文字，不合格就丟掉
- 回顧文字只當純文字顯示（模板不會用 |safe）
- AI 掛了就回傳 None，日記照樣存
"""
import os
import re
import json

import ollama

MODEL = os.environ.get("DIARY_MODEL", "qwen3.5:4b")   # 4b：比 9b 快一倍、記憶體減半，品質夠用
EMOTIONS = ["開心", "平靜", "感恩", "疲累", "焦慮", "難過", "生氣", "煩躁"]
REVIEW_MAX_CHARS = 1200

_client = ollama.Client(timeout=90)
_WORD = re.compile(r"^[一-鿿]{1,2}$")   # 今日一字：1～2 個中文字（日付印塞得下）

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "emotion": {"type": "string", "enum": EMOTIONS},
        "word": {"type": "string"},
    },
    "required": ["emotion", "word"],
}


def _chat(prompt, fmt=None, max_tokens=80):
    resp = _client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=fmt,
        think=False,                       # 思考模式會跑超過 90 秒，關掉
        keep_alive="1m",                   # 用完 1 分鐘就釋放記憶體（預設 5 分鐘）
        options={"temperature": 0.4, "num_predict": max_tokens},  # 限制長度，GPU 少忙一點
    )
    return resp.message.content or ""


def is_word(s):
    return isinstance(s, str) and bool(_WORD.match(s))


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
        "word": word.strip() if isinstance(word, str) and is_word(word.strip()) else None,
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
        "- word：只回「一個」詞（字串，不是陣列），長度 1 或 2 個繁體中文字，"
        "形容這個人今天整體的感覺（是感覺，不是發生的事情或物品）。要從下面的紀錄去體會\n\n"
        + "\n".join(lines)
    )
    try:
        return clean_suggestion(_chat(prompt, SUGGEST_SCHEMA))
    except Exception as e:  # 連不到 Ollama、超時、模型不存在……都不能擋住存檔
        print(f"[ai] suggest 失敗：{e}")
        return {"emotion": None, "word": None}


def _md(day):
    """2026-11-17 → 11/17（模型會把 11-17 唸成「十一十七日」）"""
    return f"{int(day[5:7])}/{int(day[8:10])}"


def weekly_review(entries, letters_answered):
    """寫一段每週回顧。entries 是這週的紀錄（dict list）。"""
    if not entries:
        return None
    days = []
    for e in entries:
        days.append(f"{_md(e['day'])}｜心情 {e['mood']}｜{e['emotion']}｜做到的事：{e['small_win']}"
                    + (f"｜日記：{e['note'][:200]}" if e.get("note") else ""))
    # 小模型不會自己判斷條件，也會為了湊句數編內容：所以句數、低分的日子都由程式先算好
    sentences = min(len(entries) + 1, 5)
    low = [e for e in entries if e["mood"] <= 4]
    rules = [
        f"用繁體中文、第二人稱「你」，最多 {sentences} 句話。說完就停，不要寫「整體而言」這種總結句。",
        "說出這週做到的小事，用紀錄裡的原話。",
        "用一句話描述這週的心情，不評價好壞。",
    ]
    if low:
        rules.append("、".join(_md(e["day"]) for e in low) + " 心情比較低，溫和地提那天還是做到了什麼。")
    if letters_answered:
        rules.append(f"這週回答了 {letters_answered} 封過去的自己寄來的信，提一句。")
    rules += [
        "只能寫紀錄裡有的事。紀錄沒寫到的感受、事件、天數都不要寫。",
        "不要寫建議、期許或祝福（例如「希望」、「加油」、「繼續」開頭的句子）。",
        "不要條列，不要 Markdown。",
    ]
    prompt = ("下面是一個人這週的日記紀錄：\n\n" + "\n".join(days)
              + "\n\n請照這些規則寫一段每週回顧：\n" + "\n".join(f"- {r}" for r in rules))
    try:
        text = _chat(prompt, max_tokens=600).strip()
    except Exception as e:
        print(f"[ai] weekly_review 失敗：{e}")
        return None
    return text[:REVIEW_MAX_CHARS] or None
