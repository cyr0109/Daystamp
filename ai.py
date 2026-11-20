"""本機 AI（Ollama）。

安全原則：AI 的輸出只當「資料」，絕不執行。
- 標籤必須在白名單內，不合格就丟掉
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
SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {"emotion": {"type": "string", "enum": EMOTIONS}},
    "required": ["emotion"],
}


def _chat(prompt, fmt=None, max_tokens=80):
    resp = _client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=fmt,
        think=False,                       # 思考模式會跑超過 90 秒，關掉
        keep_alive="1m",                   # 用完 1 分鐘就釋放記憶體（預設 5 分鐘）
        # 官方非思考模式建議值。presence_penalty 要明確設 0：模型預設 1.5，會連標點都不敢重複用
        options={"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0,
                 "num_predict": max_tokens},  # 限制長度，GPU 少忙一點
    )
    return resp.message.content or ""


def clean_suggestion(raw):
    """把 AI 回傳的 JSON 字串過濾成安全的 {emotion}，不合格就是 None。"""
    try:
        # 模型有時會把 JSON 包在 ```json ``` 裡，只取大括號那段
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (TypeError, ValueError, AttributeError):
        return {"emotion": None}
    emotion = data.get("emotion") if isinstance(data, dict) else None
    return {"emotion": emotion if emotion in EMOTIONS else None}


def suggest(entry):
    """讀今天的紀錄，建議一個情緒標籤。"""
    lines = [f"今天做到的小事：{_wins(entry.get('small_win'))}",
             f"心情分數（1-10）：{entry.get('mood', '')}"]
    for key, label in [("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐"),
                       ("song_title", "今天的歌"), ("note", "日記")]:
        if entry.get(key):
            lines.append(f"{label}：{entry[key]}")
    prompt = (
        "你是一個日記助手。讀完下面這個人今天的紀錄，回傳 JSON：\n"
        f"- emotion：只能從這 8 個詞裡原封不動挑一個，不可以用其他詞：{'、'.join(EMOTIONS)}\n\n"
        + "\n".join(lines)
    )
    try:
        return clean_suggestion(_chat(prompt, SUGGEST_SCHEMA))
    except Exception as e:  # 連不到 Ollama、超時、模型不存在……都不能擋住存檔
        print(f"[ai] suggest 失敗：{e}")
        return {"emotion": None}


def _wins(small_win):
    """小事一行一件 → 「a」、「b」"""
    return "、".join(f"「{w}」" for w in (small_win or "").split("\n") if w)


def _first_sentences(text, n):
    """只留前 n 句：小模型講完重點愛補一句「就這樣」「你做得很好」，叫它不要沒用，直接剪。
    順便去掉換行和句子之間多打的空白。"""
    text = re.sub(r"\s*\n\s*", "", text or "")
    text = re.sub(r"(?<=[。！？，、；])\s+", "", text).strip()
    return "".join(re.findall(r"[^。！？]+[。！？]?", text)[:n])


def _md(day):
    """2026-11-17 → 11/17（模型會把 11-17 唸成「十一十七日」）"""
    return f"{int(day[5:7])}/{int(day[8:10])}"


def weekly_review(entries, letters_answered):
    """寫一段每週回顧。entries 是這週的紀錄（dict list）。"""
    if not entries:
        return None
    # 模型只講分數不低的日子做到的事。不給情緒和分數：給了它會替人下結論（「心情真開心」）
    # 低分的日子由程式自己寫：交給模型，它一定會加評語（「也算挺過了」「算不錯了」）
    low = [e for e in entries if e["mood"] <= 4]
    wins = [e for e in entries if e not in low]
    text = ""
    if wins:
        days = [f"{_md(e['day'])}｜做到的事：{_wins(e['small_win'])}"
                + (f"｜日記：{e['note'][:200]}" if e.get("note") else "") for e in wins]
        prompt = ("下面是一個人這週的日記：\n\n" + "\n".join(days)
                  + "\n\n請你像一個溫柔的朋友，在他的手帳旁邊留一句話，講他這週做到了哪些事。"
                    "用台灣繁體中文，稱呼他「你」，口語、自然，一句就好。"
                    "只能寫上面有的事，不要自己加原因、感受或沒發生的事。"
                    "你不知道他的心情，不要寫他開不開心、累不累，也不要用「心情」這個詞。"
                    "不要把他做到的事講小，不要用「只是」「也算」「雖然」。"
                    "講完事情就停，不要加總結、評語或誇獎，也不要給建議或祝福。")
        try:
            text = _first_sentences(_chat(prompt, max_tokens=300), 1)
        except Exception as e:
            print(f"[ai] weekly_review 失敗：{e}")
            return None
    # 小事放在引號裡：小事本身常常就有「還是」，不加引號會變成「還是還是去上班了」
    if low:
        text += "分數比較低的日子，你也做到了：" + "；".join(f"{_md(e['day'])} {_wins(e['small_win'])}" for e in low) + "。"
    if text and letters_answered:   # 固定內容，程式自己寫比模型穩
        text += f"這週你回了 {letters_answered} 封過去的自己寄來的信。"
    return text[:REVIEW_MAX_CHARS] or None
