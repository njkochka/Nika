"""Сжатая расшифровка для чтения Клодом: compact.py выпуск/ [мин_слов=8]
Строка = несколько предложений, в начале индекс первого слова и [мм] минута.
Уже нарезанное (диапазоны из short*.json и batch*.json выпуска) заменено на ~.
Пишет выпуск/compact.txt."""
import glob, json, sys
from pathlib import Path
ep = Path(sys.argv[1]); mn = int(sys.argv[2]) if len(sys.argv) > 2 else 8
w = json.load(open(ep / "words.json")); used = set()
for f in glob.glob(str(ep / "short*.json")) + glob.glob(str(ep / "batch*.json")):
    c = json.load(open(f))
    for sh in c.get("shorts", [c]):
        for r in sh.get("ranges", []): used.update(range(r[0], r[1] + 1))
out, cur, st = [], [], 0
def flush():
    if cur: out.append(f"{st} [{int(w[st]['s'] // 60)}] {' '.join(cur)}"); cur.clear()
for i, x in enumerate(w):
    if i in used:
        flush()
        if not out or out[-1] != "~": out.append("~")
        continue
    if not cur: st = i
    cur.append(x["w"].strip())
    if x["w"].rstrip()[-1:] in ".?!" and len(cur) >= mn: flush()
flush()
(ep / "compact.txt").write_text("\n".join(out)); print(len(out), "строк")
