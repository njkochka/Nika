"""Кусок сжатой расшифровки вместо чтения compact.txt целиком.
  find.py выпуск/ --map             по строке на минуту (начало), обзор всего интервью
  find.py выпуск/ --min 12-15       всё, что сказано с 12-й по 15-ю минуту
  find.py выпуск/ мама страшн       строки, где есть любое из слов (часть слова тоже), +-1 строка вокруг
  --all                             со словами: строки, где есть все слова сразу
  --max N                           не больше N строк (по умолчанию 40)
Строка: индекс первого слова [минута] текст; ~ - уже нарезано. Края кусков уточнять через sents.py.
Если compact.txt нет или он старый - сначала compact.py выпуск/."""
import sys
from pathlib import Path

a = sys.argv[1:]
if not a or a[0] in ("-h", "--help"): sys.exit(__doc__)
ep, a = Path(a[0]), a[1:]
mx = 40
if "--max" in a:
    k = a.index("--max"); mx = int(a[k + 1]); del a[k:k + 2]
every = "--all" in a
a = [x for x in a if x != "--all"]
lines = (ep / "compact.txt").read_text().splitlines()

def minute(s):
    p = s.split(" ", 2)
    return int(p[1].strip("[]")) if len(p) > 2 and p[1].startswith("[") else None

out = []
if a[:1] == ["--map"]:
    seen = set()
    for s in lines:
        m = minute(s)
        if m is not None and m not in seen:
            seen.add(m); out.append(s[:110])
    mx = max(mx, len(out))
elif a[:1] == ["--min"]:
    p = a[1].split("-"); lo, hi = int(p[0]), int(p[-1])
    out = [s for s in lines if (m := minute(s)) is not None and lo <= m <= hi]
else:
    keys = [x.lower() for x in a]
    test = all if every else any
    hit = [i for i, s in enumerate(lines) if s != "~" and test(k in s.lower() for k in keys)]
    keep = sorted({j for i in hit for j in (i - 1, i, i + 1) if 0 <= j < len(lines)})
    prev = None
    for j in keep:
        if prev is not None and j != prev + 1: out.append("...")
        out.append(("> " if j in hit else "  ") + lines[j]); prev = j
    print(f"# совпадений: {len(hit)}")
print("\n".join(out[:mx]))
if len(out) > mx: print(f"# ... ещё {len(out) - mx} строк, сузь запрос или --max")
