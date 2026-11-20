"""調每週回顧 prompt 用：5 種假的一週各跑 n 次，用 regex 抓常見毛病。要開著 Ollama。
用法：.venv/bin/python scripts/eval_review.py [每種跑幾次，預設 3]"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ai

D = lambda d, m, emo, win, note=None: dict(day=f"2026-11-{d:02d}", mood=m, emotion=emo, small_win=win, note=note)
WEEKS = {
    "好週": [D(16, 7, "開心", "早起去跑步"), D(17, 8, "平靜", "把房間整理好", "下午在咖啡店看書"), D(18, 6, "疲累", "準時下班")],
    "起伏": [D(16, 3, "焦慮", "還是去上班了\n回了主管的信", "主管開會念了很久"), D(17, 5, "煩躁", "吃了一頓好的晚餐"),
             D(18, 7, "感恩", "朋友打電話來關心"), D(19, 8, "開心", "把拖了兩週的報告交出去了")],
    "一天": [D(20, 6, "平靜", "把拖了兩週的報告交出去了")],
    "低潮": [D(16, 2, "難過", "有起床吃早餐"), D(17, 3, "疲累", "洗了衣服", "整天都很累，什麼都不想做"), D(19, 4, "焦慮", "出門散步十分鐘")],
    "滿週": [D(16 + i, m, e, w) for i, (m, e, w) in enumerate([
        (6, "平靜", "讀了二十頁書"), (7, "開心", "跟家人吃飯"), (5, "疲累", "加班但有準時吃飯"), (8, "感恩", "同事幫我解決 bug"),
        (6, "平靜", "去運動"), (9, "開心", "跟朋友去爬山"), (7, "平靜", "整理照片")])],
}
BAD = {
    "總結/廢話": r"整體|總之|總的來說|沒有特別|這段時間|這些是",
    "評語": r"真棒|很棒|真是|確實|旅程|好好照顧|了不起|很厲害",
    "編因果": r"因為|讓你|而感到|來紓|使你|所以",
    "整週": r"整週",
    "建議/祝福": r"希望|加油|繼續|記得要|別忘|願你|祝",
    "收尾廢話": r"就這樣|照時間|順序|就這麼|算是|只記了|記下了|每當|手裡",
    "分數": r"\d+\s*分|心情\s*\d",
    "替人講心情": r"心情|開心|快樂|平靜|感恩|疲累|焦慮|難過|煩躁|生氣|愉快|輕鬆",
    "還是還是": r"還是「?還是",
    "講小": r"只是|也算|算不錯|雖然",
    "漏指令": r"第\s*\d\s*句|規則|紀錄裡",
    "簡體字": r"[还这们时说个过发对么为没样里让觉经开实动应头学关]",
    "換行/條列": r"\n|^\s*[-•*]",
}
n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
bad_total = 0
for name, es in WEEKS.items():
    for i in range(n):
        t = ai.weekly_review(es, 1 if name == "起伏" else 0) or ""
        hits = [k for k, p in BAD.items() if re.search(p, t, re.M)]
        bad_total += bool(hits)
        print(f"[{name}#{i}]{' ⚠ ' + ','.join(hits) if hits else ''}\n{t}\n")
print(f"有問題的：{bad_total}/{n * len(WEEKS)}")
