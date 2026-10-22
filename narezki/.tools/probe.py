"""Замер: что сборка делает со звуком вокруг слов. Для правок, которые не слышно в облаке.
Запуск: venv/bin/python probe.py ../выпуск/batchN_MM.json слово [слово ...]
Печатает по каждому слову: таймкоды Whisper, где слово стихло (faded), паузы ffmpeg,
куски, которые идут в ролик, и громкость каждые 50 мс (дБ от пика слова, * - в ролике)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_short as m

cp = Path(sys.argv[1]).resolve()
cfg = json.loads(cp.read_text())
base = cp.parent
src = str(base / cfg["source"])
words = json.loads((base / cfg["words"]).read_text())
m.SILENCE_DB, m.SILENCE_MIN = cfg.get("silence_db", m.SILENCE_DB), cfg.get("silence_min", m.SILENCE_MIN)
m.MIN_PIECE = cfg.get("min_piece", m.MIN_PIECE)
m.KEEP_PAUSES = [(words[a]["e"], words[b]["s"]) for a, b in cfg.get("keep_pause", [])]
keep = set()
for a, b in cfg["ranges"]:
    keep.update(range(a, b + 1))
pieces = m.split_by_silence(src, m.ranges_to_intervals(words, cfg["ranges"], src, cfg.get("cut_at", {})),
                            [words[i]["s"] for i in keep],
                            [(words[i], words[i + 1]["s"]) for i in keep if i + 1 < len(words)])
inside = lambda t: any(s <= t < e for s, e in pieces)

for i in map(int, sys.argv[2:]):
    w, nxt = words[i], words[i + 1]
    t0, t1 = w["s"] - 0.1, min(nxt["s"] + 0.1, w["e"] + 1.0)
    print(f"== {i} «{w['w']}» {w['s']:.2f}-{w['e']:.2f}, дальше «{nxt['w']}» {nxt['s']:.2f}, "
          f"в ролике: {i in keep}, стихло: {m.faded(src, w, nxt['s'])}")
    print("  паузы:", [(round(a, 2), round(b, 2)) for a, b in m.silences(src, t0, t1)])
    print("  куски:", [(round(a, 2), round(b, 2)) for a, b in pieces if b > t0 and a < t1])
    lv = m.loudness(src, t0, t1, step=0.05)
    peak = max(v for _, v in m.loudness(src, w["s"], w["e"]))
    for k in range(0, len(lv), 8):
        print(f"  {lv[k][0]:.2f}: " + " ".join(f"{v - peak:4.0f}{'*' if inside(t) else ' '}"
                                               for t, v in lv[k:k + 8]))
