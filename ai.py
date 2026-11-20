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
    # 小模型給它空間就會補廢話、編因果：所以每一句要寫什麼、用哪些材料，都由程式排好
    emotions = list(dict.fromkeys(e["emotion"] for e in entries))
    low = [e for e in entries if e["mood"] <= 4]
    wins = [e for e in entries if e not in low]   # 低分那天的事留到後面講，不重複
    plan = []
    if wins:
        plan.append("說出這週的這些事：" + "、".join(f"「{e['small_win']}」" for e in wins)
                    + "。為了句子通順可以改幾個字，但不要加原因、結果或感受。")
    plan.append("說出這週的心情：" + "、".join(emotions) + "。只用這幾個詞，不加形容。")
    plan += [f"說 {_md(e['day'])} 心情比較低，那天你還是「{e['small_win']}」。" for e in low]
    prompt = ("下面是一個人這週的日記紀錄：\n\n" + "\n".join(days)
              + f"\n\n請用台灣繁體中文、第二人稱「你」，剛好寫 {len(plan)} 句話，一句做一件事：\n"
              + "\n".join(f"第 {i} 句：{p}" for i, p in enumerate(plan, 1))
              + "\n\n寫完就停。不要多加任何一句，不要總結，不要提分數，"
                "不要寫建議或祝福，不要換行、條列或 Markdown。")
    try:
        text = _chat(prompt, max_tokens=600).replace("\n", "").strip()
    except Exception as e:
        print(f"[ai] weekly_review 失敗：{e}")
        return None
    if text and letters_answered:   # 固定內容，程式自己寫比模型穩
        text += f"這週你回了 {letters_answered} 封過去的自己寄來的信。"
    return text[:REVIEW_MAX_CHARS] or None
