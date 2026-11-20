-- schema.sql：`flask --app app init-db` 會整個重建（舊資料會被刪掉）

DROP TABLE IF EXISTS diaries;
DROP TABLE IF EXISTS entries;
DROP TABLE IF EXISTS weekly_reviews;
DROP TABLE IF EXISTS letters;

-- 一天一筆。day 是「邏輯上的日期」：凌晨 4 點前算前一天
CREATE TABLE entries (
    day          TEXT PRIMARY KEY,                        -- YYYY-MM-DD
    small_win    TEXT NOT NULL,
    mood         INTEGER NOT NULL CHECK (mood BETWEEN 1 AND 10),
    emotion      TEXT NOT NULL,
    word         TEXT,                                    -- 今日一字
    breakfast    TEXT,
    lunch        TEXT,
    dinner       TEXT,
    song_title   TEXT,
    song_artist  TEXT,
    song_artwork TEXT,
    song_preview TEXT,
    weather      TEXT,
    note         TEXT,
    updated_at   TEXT NOT NULL
);

CREATE TABLE weekly_reviews (
    week_start TEXT PRIMARY KEY,                          -- 那週的星期一
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 給未來自己的問題
CREATE TABLE letters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    asked_day    TEXT NOT NULL,
    deliver_day  TEXT NOT NULL,
    question     TEXT NOT NULL,
    answer       TEXT,
    answered_day TEXT
);
