"""實驗：每週回顧開思考模式，品質有沒有比較好、要等多久。很慢，用背景跑。
用法：.venv/bin/python -u scripts/eval_review_think.py"""
import os, sys, time, re, ollama
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, ".."), HERE]
sys.argv = [sys.argv[0], "0"]
import ai
import eval_review as ev   # 0 次 → 只載入 WEEKS 和 BAD
client = ollama.Client(timeout=900)
OPTS = {
 "思考+官方(1.0/0.95/20/p1.5)": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 1.5},
 "思考+p0": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 0},
}
for name, o in OPTS.items():
    stats = []
    def chat(prompt, fmt=None, max_tokens=80):
        t = time.time()
        r = client.chat(model=ai.MODEL, messages=[{"role": "user", "content": prompt}], think=True, keep_alive="5m",
                        options={**o, "num_predict": 8000, "num_ctx": 16384})
        stats.append((time.time() - t, len(r.message.thinking or "")))
        return r.message.content or ""
    ai._chat = chat
    print("####", name); bad = 0; n = 0
    for wk, es in ev.WEEKS.items():
        for i in range(2):
            t = ai.weekly_review(es, 1 if wk == "起伏" else 0) or ""
            hits = [k for k, p in ev.BAD.items() if re.search(p, t, re.M)]
            bad += bool(hits); n += 1
            print(f"[{wk}#{i}] {stats[-1][0]:.0f}s 思考{stats[-1][1]}字{' ⚠ '+','.join(hits) if hits else ''}\n{t}\n")
    print(f"有問題 {bad}/{n}，平均 {sum(s[0] for s in stats)/len(stats):.0f}s，最久 {max(s[0] for s in stats):.0f}s\n")
