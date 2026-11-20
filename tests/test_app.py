"""跑法：.venv/bin/python -m unittest discover tests"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import ai
import app as diary


class AIGuardTest(unittest.TestCase):
    def test_keeps_valid_suggestion(self):
        self.assertEqual(ai.clean_suggestion('{"emotion": "平靜", "word": "暖"}'), {"emotion": "平靜", "word": "暖"})
        self.assertEqual(ai.clean_suggestion('```json\n{"emotion": "感恩", "word": "暖"}\n```'), {"emotion": "感恩", "word": "暖"})

    def test_drops_anything_off_the_whitelist(self):
        for raw in ['{"emotion": "rm -rf /", "word": "<script>"}', '{"emotion": "開心", "word": "很好"}',
                    'not json', '[1, 2]', '{"word": 5}']:
            out = ai.clean_suggestion(raw)
            self.assertTrue(out["emotion"] is None or out["emotion"] in ai.EMOTIONS)
            self.assertTrue(out["word"] is None or ai.is_one_han(out["word"]))
        self.assertEqual(ai.clean_suggestion('{"emotion": "rm -rf /", "word": "<script>"}'), {"emotion": None, "word": None})

    def test_ai_failure_never_raises(self):
        with mock.patch.object(ai, "_chat", side_effect=ConnectionError("ollama down")):
            self.assertEqual(ai.suggest({"small_win": "x"}), {"emotion": None, "word": None})
            self.assertIsNone(ai.weekly_review([{"day": "2026-01-01", "mood": 5, "emotion": "平靜", "small_win": "x"}], 0))


class LogicalDayTest(unittest.TestCase):
    def test_before_4am_counts_as_yesterday(self):
        self.assertEqual(str(diary.logical_today(datetime(2026, 11, 21, 3, 59))), "2026-11-20")
        self.assertEqual(str(diary.logical_today(datetime(2026, 11, 21, 4, 0))), "2026-11-21")


class AppTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp()
        os.close(fd)
        self.md = tempfile.mkdtemp()
        diary.app.config.update(DATABASE=self.db, TESTING=True)
        self.md_patch = mock.patch.object(diary, "DIARY_FOLDER", self.md)
        self.weather_patch = mock.patch.object(diary, "fetch_weather", return_value="☀️ 晴 25°C")
        self.md_patch.start(); self.weather_patch.start()
        with diary.app.app_context():
            from utils.database import init_db
            init_db()
        self.c = diary.app.test_client()
        self.today = str(diary.logical_today())

    def tearDown(self):
        self.md_patch.stop(); self.weather_patch.stop()
        os.remove(self.db)

    def entry(self, **kw):
        body = {"day": self.today, "small_win": "摺好衣服", "mood": 7, "emotion": "平靜", "word": "暖"}
        body.update(kw)
        return self.c.post("/api/entry", json=body)

    def test_save_edit_and_backup(self):
        self.assertEqual(self.entry().status_code, 200)
        self.assertEqual(self.entry(small_win="改過了").status_code, 200)   # 同一天再存 = 修改
        with diary.app.app_context():
            rows = diary.get_db().execute("SELECT small_win, weather FROM entries").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("改過了", "☀️ 晴 25°C")])
        with open(os.path.join(self.md, f"{self.today}.md"), encoding="utf-8") as f:
            self.assertIn("改過了", f.read())
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/calendar").status_code, 200)
        self.assertEqual(self.c.get(f"/day/{self.today}").status_code, 200)

    def test_rejects_bad_input(self):
        self.assertEqual(self.entry(day="2020-01-01").status_code, 400)
        self.assertEqual(self.entry(mood=11).status_code, 400)
        self.assertEqual(self.entry(emotion="快樂").status_code, 400)
        self.assertEqual(self.entry(word="ab").status_code, 400)
        self.assertEqual(self.entry(small_win="  ").status_code, 400)
        self.entry(song_artwork="https://evil.example.com/x.jpg")
        with diary.app.app_context():
            self.assertIsNone(diary.get_entry(self.today)["song_artwork"])

    def test_form_posts_are_blocked(self):
        self.assertEqual(self.c.post("/api/entry", data={"small_win": "x"}).status_code, 415)

    def test_letter_stays_sealed_until_delivery(self):
        r = self.c.post("/api/letters", json={"question": "還好嗎？", "after": "30"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/letters/1").status_code, 404)
        self.assertEqual(self.c.post("/api/letters/1/answer", json={"answer": "好"}).status_code, 404)
        with diary.app.app_context():
            db = diary.get_db()
            db.execute("UPDATE letters SET deliver_day = ?", (self.today,))
            db.commit()
        self.assertEqual(self.c.get("/letters/1").status_code, 200)
        self.assertEqual(self.c.post("/api/letters/1/answer", json={"answer": "好"}).status_code, 200)

    def test_plant_grows_and_fills_greenhouse(self):
        today = diary.logical_today()
        with diary.app.app_context():
            db = diary.get_db()
            for i in range(105):
                db.execute("INSERT INTO entries (day, small_win, mood, emotion, updated_at) VALUES (?, 'x', 7, '開心', '')",
                           (str(today - timedelta(days=i)),))
            db.commit()
            p = diary.plant_state(today)
        self.assertEqual((p["grown"], p["stage"], len(p["greenhouse"])), (5, 1, 1))
        self.assertEqual(p["greenhouse"][0]["color"], diary.EMOTION_COLORS["開心"])


if __name__ == "__main__":
    unittest.main()
