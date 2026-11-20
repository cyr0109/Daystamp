import os
import calendar as cal
from collections import Counter
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, render_template, abort

import ai
from utils import database
from utils.database import get_db

app = Flask(__name__)
app.config["DATABASE"] = os.path.join(app.root_path, "diary.db")
database.init_app(app)

DIARY_FOLDER = os.path.join(app.root_path, "diaries_md")
LAT = float(os.environ.get("DIARY_LAT", "25.04"))   # 預設台北
LON = float(os.environ.get("DIARY_LON", "121.56"))
DAY_STARTS_AT_HOUR = 4                               # 凌晨 4 點前算前一天
POT_DAYS = 100                                       # 一盆植物寫滿幾天會結種子
PLANT_STAGES = [(0, "種子"), (1, "發芽"), (8, "小苗"), (25, "長葉"), (50, "結苞"), (75, "開花")]
EMOTION_COLORS = {
    "開心": "#E9B92F", "平靜": "#7DB4D6", "感恩": "#F09A4E", "疲累": "#A39E95",
    "焦慮": "#9886C6", "難過": "#4F78A8", "生氣": "#C8463A", "煩躁": "#6F9C76",
}
LETTER_DELAYS = {"30": "1 個月", "90": "3 個月", "180": "半年", "365": "1 年"}


# ---------- 小工具 ----------

def logical_today(now=None):
    return ((now or datetime.now()) - timedelta(hours=DAY_STARTS_AT_HOUR)).date()


def week_start(d):
    return d - timedelta(days=d.weekday())


def parse_day(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def text(data, key, limit, required=False):
    """從 JSON 取一個字串欄位：去空白、限制長度。空字串變 None。"""
    v = data.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        abort(400, f"{key} 格式不對")
    v = v.strip()
    if required and not v:
        abort(400, f"{key} 是必填")
    if len(v) > limit:
        abort(400, f"{key} 太長了（最多 {limit} 字）")
    return v or None


def apple_url(v):
    """只接受 Apple 的 https 網址（歌曲封面、試聽）。"""
    if not v:
        return None
    u = urlparse(v)
    if u.scheme == "https" and (u.hostname or "").endswith((".mzstatic.com", ".apple.com")):
        return v
    return None


def fetch_weather():
    code_map = [((0,), "☀️ 晴"), ((1, 2, 3), "⛅ 多雲"), ((45, 48), "🌫️ 霧"),
                (tuple(range(51, 58)), "🌦️ 毛毛雨"), (tuple(range(61, 68)) + (80, 81, 82), "🌧️ 雨"),
                (tuple(range(71, 78)) + (85, 86), "❄️ 雪"), (tuple(range(95, 100)), "⛈️ 雷雨")]
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=4, params={
            "latitude": LAT, "longitude": LON,
            "current": "temperature_2m,weather_code", "timezone": "auto"})
        cur = r.json()["current"]
        label = next((name for codes, name in code_map if cur["weather_code"] in codes), "")
        return f"{label} {round(cur['temperature_2m'])}°C".strip()
    except Exception as e:  # 抓不到天氣不影響存檔
        print(f"[weather] {e}")
        return None


def write_markdown(e):
    """每次存檔都寫一份 Markdown 備份，diary.db 壞了也還有。"""
    os.makedirs(DIARY_FOLDER, exist_ok=True)
    lines = [f"# {e['day']}" + (f"　{e['word']}" if e.get("word") else ""), ""]
    lines.append(f"- 心情：{e['mood']}/10　{e['emotion']}")
    if e.get("weather"):
        lines.append(f"- 天氣：{e['weather']}")
    lines.append(f"- 今天做到的小事：{e['small_win']}")
    for k, label in [("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐")]:
        if e.get(k):
            lines.append(f"- {label}：{e[k]}")
    if e.get("song_title"):
        lines.append(f"- 今天的歌：{e['song_title']}" + (f" – {e['song_artist']}" if e.get("song_artist") else ""))
    if e.get("note"):
        lines += ["", e["note"]]
    with open(os.path.join(DIARY_FOLDER, f"{e['day']}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def get_entry(day):
    row = get_db().execute("SELECT * FROM entries WHERE day = ?", (str(day),)).fetchone()
    return dict(row) if row else None


def plant_state(today):
    db = get_db()
    rows = db.execute("SELECT day, emotion FROM entries ORDER BY day").fetchall()
    total = len(rows)
    grown = total % POT_DAYS
    stage = max(i for i, (need, _) in enumerate(PLANT_STAGES) if grown >= need)
    week_ago = str(today - timedelta(days=6))
    recent = Counter(r["emotion"] for r in rows if r["day"] >= week_ago)
    color = EMOTION_COLORS.get(recent.most_common(1)[0][0]) if recent else EMOTION_COLORS["平靜"]
    # 寫滿的每一盆，用那 100 天最常出現的情緒當花色
    done = []
    for i in range(total // POT_DAYS):
        chunk = rows[i * POT_DAYS:(i + 1) * POT_DAYS]
        top = Counter(r["emotion"] for r in chunk).most_common(1)[0][0]
        done.append({"color": EMOTION_COLORS.get(top), "from": chunk[0]["day"], "to": chunk[-1]["day"]})
    asleep = total > 0 and rows[-1]["day"] < str(today - timedelta(days=3))
    return {"total": total, "grown": grown, "stage": stage, "stage_name": PLANT_STAGES[stage][1],
            "color": color, "asleep": asleep, "greenhouse": done}


# ---------- 安全：所有 POST 都必須是 JSON ----------
# 別的網站用 <form> 偷送資料到 localhost 時不能帶 application/json，這樣就擋掉了（CSRF）。

@app.before_request
def require_json_for_writes():
    if request.method == "POST" and not request.is_json:
        abort(415)


@app.errorhandler(400)
def bad_request(e):
    return jsonify(error=e.description), 400


@app.template_filter("weekday")
def weekday_filter(day):
    d = day if isinstance(day, date) else date.fromisoformat(day)
    return "星期" + "一二三四五六日"[d.weekday()]


@app.context_processor
def inject_globals():
    return {"emotion_colors": EMOTION_COLORS, "emotions": ai.EMOTIONS}


# ---------- 頁面 ----------

@app.route("/")
def today_page():
    today = logical_today()
    db = get_db()
    due = db.execute("SELECT * FROM letters WHERE deliver_day <= ? AND answer IS NULL ORDER BY deliver_day",
                     (str(today),)).fetchall()
    # 以前的今天：7 天前以前，心情 ≥ 7 的優先
    memory = db.execute("SELECT * FROM entries WHERE day < ? ORDER BY mood >= 7 DESC, RANDOM() LIMIT 1",
                        (str(today - timedelta(days=7)),)).fetchone()
    memory_days_ago = (today - date.fromisoformat(memory["day"])).days if memory else None
    # 這週一～日的印章列
    start = week_start(today)
    words = {r["day"]: r["word"] for r in db.execute("SELECT day, word FROM entries WHERE day BETWEEN ? AND ?",
                                                     (str(start), str(start + timedelta(days=6))))}
    week = [{"day": str(d), "has": str(d) in words, "word": words.get(str(d)), "future": d > today}
            for d in (start + timedelta(days=i) for i in range(7))]
    return render_template("today.html", day=str(today), entry=get_entry(today), due=due, week=week,
                           memory=memory, memory_days_ago=memory_days_ago, plant=plant_state(today),
                           saved=request.args.get("saved") == "1")


@app.route("/calendar")
def calendar_page():
    today = logical_today()
    try:
        first = datetime.strptime(request.args.get("month", ""), "%Y-%m").date()
    except ValueError:
        first = today.replace(day=1)
    last_day = cal.monthrange(first.year, first.month)[1]
    rows = get_db().execute("SELECT * FROM entries WHERE day BETWEEN ? AND ?",
                            (str(first), str(first.replace(day=last_day)))).fetchall()
    by_day = {r["day"]: dict(r) for r in rows}
    weeks = []
    for week in cal.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        weeks.append([{"date": d, "in_month": d.month == first.month, "is_today": d == today,
                       "entry": by_day.get(str(d))} for d in week])
    prev_m = (first - timedelta(days=1)).replace(day=1)
    next_m = first.replace(day=last_day) + timedelta(days=1)
    return render_template("calendar.html", first=first, weeks=weeks, count=len(rows),
                           prev=prev_m.strftime("%Y-%m"), next=next_m.strftime("%Y-%m"),
                           plant=plant_state(today))


@app.route("/day/<day>")
def day_page(day):
    d = parse_day(day)
    entry = get_entry(d) if d else None
    if not entry:
        abort(404)
    db = get_db()
    prev = db.execute("SELECT day FROM entries WHERE day < ? ORDER BY day DESC LIMIT 1", (str(d),)).fetchone()
    nxt = db.execute("SELECT day FROM entries WHERE day > ? ORDER BY day LIMIT 1", (str(d),)).fetchone()
    return render_template("day.html", entry=entry, is_today=d == logical_today(),
                           prev=prev and prev["day"], next=nxt and nxt["day"])


@app.route("/review")
def review_page():
    today = logical_today()
    start = week_start(parse_day(request.args.get("week")) or today)
    end = start + timedelta(days=6)
    db = get_db()
    entries = db.execute("SELECT * FROM entries WHERE day BETWEEN ? AND ? ORDER BY day",
                         (str(start), str(end))).fetchall()
    review = db.execute("SELECT * FROM weekly_reviews WHERE week_start = ?", (str(start),)).fetchone()
    return render_template("review.html", start=start, end=end, entries=entries, review=review,
                           prev=str(start - timedelta(days=7)), next=str(start + timedelta(days=7)),
                           is_current=start == week_start(today))


def split_hit(text, q, room=18):
    """找到 q 就切成 (前, 命中, 後)，前後各留 room 個字；找不到回傳 None。
    分三段交給模板，模板只包 <mark>，日記內容照樣自動轉義。"""
    i = (text or "").lower().find(q.lower())
    if i < 0:
        return None
    before, after = text[max(0, i - room):i], text[i + len(q):i + len(q) + room]
    return (("…" if i > room else "") + before, text[i:i + len(q)],
            after + ("…" if i + len(q) + room < len(text) else ""))


HIT_FIELDS = [("note", "日記"), ("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐"),
              ("song_title", "歌"), ("song_artist", "歌手")]


@app.route("/search")
def search_page():
    q = request.args.get("q", "").strip()[:50]
    rows = []
    if q:
        like = f"%{q}%"
        rows = get_db().execute(
            """SELECT * FROM entries WHERE small_win LIKE ? OR note LIKE ? OR breakfast LIKE ?
               OR lunch LIKE ? OR dinner LIKE ? OR song_title LIKE ? OR song_artist LIKE ?
               OR word = ? OR emotion = ? ORDER BY day DESC LIMIT 100""",
            (like, like, like, like, like, like, like, q, q)).fetchall()
    hits = []
    for r in rows:
        win = split_hit(r["small_win"], q)
        # 「做到的小事」沒命中，就找出是哪一欄命中的，顯示那一小段
        other = None if win else next(((label, h) for k, label in HIT_FIELDS
                                       if (h := split_hit(r[k], q))), None)
        hits.append({"e": r, "win": win, "other": other})
    return render_template("search.html", q=q, rows=hits)


@app.route("/letters")
def letters_page():
    today = str(logical_today())
    db = get_db()
    in_transit = db.execute("SELECT deliver_day FROM letters WHERE deliver_day > ? ORDER BY deliver_day",
                            (today,)).fetchall()
    arrived = db.execute("SELECT * FROM letters WHERE deliver_day <= ? ORDER BY deliver_day DESC",
                         (today,)).fetchall()
    return render_template("letters.html", in_transit=in_transit, arrived=arrived, delays=LETTER_DELAYS,
                           min_date=str(logical_today() + timedelta(days=1)))


@app.route("/letters/<int:letter_id>")
def letter_page(letter_id):
    letter = get_db().execute("SELECT * FROM letters WHERE id = ?", (letter_id,)).fetchone()
    if not letter or letter["deliver_day"] > str(logical_today()):
        abort(404)  # 還沒送到就是封著的
    asked = date.fromisoformat(letter["asked_day"])
    return render_template("letter.html", letter=letter, then=get_entry(letter["asked_day"]),
                           days=(logical_today() - asked).days)


# ---------- API（都是 JSON） ----------

@app.post("/api/entry")
def save_entry():
    data = request.get_json(silent=True) or {}
    today = logical_today()
    day = parse_day(data.get("day"))
    if day not in (today, today - timedelta(days=1)):  # 容許跨過凌晨 4 點才按送出
        abort(400, "只能寫今天的日記")
    mood = data.get("mood")
    if not isinstance(mood, int) or not 1 <= mood <= 10:
        abort(400, "心情要是 1 到 10")
    emotion = data.get("emotion")
    if emotion not in ai.EMOTIONS:
        abort(400, "請選一個情緒")
    word = text(data, "word", 2)
    if word and not ai.is_word(word):
        abort(400, "今日一字要是 1～2 個中文字")

    old = get_entry(day)
    e = {
        "day": str(day), "small_win": text(data, "small_win", 200, required=True), "mood": mood,
        "emotion": emotion, "word": word,
        "breakfast": text(data, "breakfast", 100), "lunch": text(data, "lunch", 100),
        "dinner": text(data, "dinner", 100),
        "song_title": text(data, "song_title", 200), "song_artist": text(data, "song_artist", 200),
        "song_artwork": apple_url(text(data, "song_artwork", 500)),
        "song_preview": apple_url(text(data, "song_preview", 500)),
        "note": text(data, "note", 5000),
        "weather": (old or {}).get("weather") or (fetch_weather() if day == today else None),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    cols = list(e)
    db = get_db()
    db.execute(f"INSERT OR REPLACE INTO entries ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
               [e[c] for c in cols])
    db.commit()
    write_markdown(e)
    return jsonify(ok=True)


@app.post("/api/suggest")
def suggest():
    data = request.get_json(silent=True) or {}
    entry = {k: str(data.get(k, ""))[:1000] for k in
             ("small_win", "mood", "breakfast", "lunch", "dinner", "song_title", "note")}
    return jsonify(ai.suggest(entry))


@app.get("/api/song")
def song_search():
    q = request.args.get("q", "").strip()[:100]
    if not q:
        return jsonify([])
    try:
        r = requests.get("https://itunes.apple.com/search", timeout=5, params={
            "term": q, "media": "music", "entity": "song", "country": "TW", "limit": 6})
        results = r.json().get("results", [])
    except Exception as e:
        print(f"[itunes] {e}")
        return jsonify(error="現在搜不到歌，可以直接打歌名"), 502
    return jsonify([{
        "title": s.get("trackName"), "artist": s.get("artistName"),
        "artwork": apple_url((s.get("artworkUrl100") or "").replace("100x100bb", "300x300bb")),
        "preview": apple_url(s.get("previewUrl")),
    } for s in results if s.get("trackName")])


@app.post("/api/review")
def make_review():
    start = parse_day((request.get_json(silent=True) or {}).get("week"))
    if not start:
        abort(400, "週別不對")
    start = week_start(start)
    end = start + timedelta(days=6)
    db = get_db()
    entries = [dict(r) for r in db.execute("SELECT * FROM entries WHERE day BETWEEN ? AND ? ORDER BY day",
                                           (str(start), str(end)))]
    if not entries:
        abort(400, "這週還沒有紀錄")
    answered = db.execute("SELECT COUNT(*) FROM letters WHERE answered_day BETWEEN ? AND ?",
                          (str(start), str(end))).fetchone()[0]
    content = ai.weekly_review(entries, answered)
    if not content:
        return jsonify(error="AI 沒有回應。確認 Ollama 有開，再按一次。"), 503
    db.execute("INSERT OR REPLACE INTO weekly_reviews (week_start, content, created_at) VALUES (?, ?, ?)",
               (str(start), content, datetime.now().isoformat(timespec="seconds")))
    db.commit()
    return jsonify(ok=True)


@app.post("/api/letters")
def create_letter():
    data = request.get_json(silent=True) or {}
    today = logical_today()
    question = text(data, "question", 300, required=True)
    after = str(data.get("after", ""))
    if after in LETTER_DELAYS:
        deliver = today + timedelta(days=int(after))
    else:
        deliver = parse_day(data.get("date"))
        if not deliver or deliver <= today:
            abort(400, "送達日期要在明天以後")
    db = get_db()
    db.execute("INSERT INTO letters (asked_day, deliver_day, question) VALUES (?, ?, ?)",
               (str(today), str(deliver), question))
    db.commit()
    return jsonify(ok=True, deliver_day=str(deliver))


@app.post("/api/letters/<int:letter_id>/answer")
def answer_letter(letter_id):
    answer = text(request.get_json(silent=True) or {}, "answer", 3000, required=True)
    today = str(logical_today())
    db = get_db()
    cur = db.execute("UPDATE letters SET answer = ?, answered_day = ? WHERE id = ? AND deliver_day <= ?",
                     (answer, today, letter_id, today))
    if cur.rowcount == 0:
        abort(404)
    db.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    # 預設只有這台電腦連得到。要用手機（同一個 Wi-Fi）就設 DIARY_HOST=0.0.0.0
    # shortcut: 沒有登入，開 0.0.0.0 時同網路的人都看得到日記；只在家裡的 Wi-Fi 用，要出門用再加登入
    app.run(host=os.environ.get("DIARY_HOST", "127.0.0.1"), port=int(os.environ.get("DIARY_PORT", "5050")))
