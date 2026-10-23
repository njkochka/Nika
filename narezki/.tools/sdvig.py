"""Сверка words.json со звуком source.mp4: расшифровку делают со звука, скачанного отдельно
(fetch.sh audio), и он может не совпасть с видео - например, в нём лишние секунды
(Орлов 2: с 1:21 расшифровка на 6 сек впереди, субтитры не те, что он говорит).

Запуск: venv/bin/python sdvig.py выпуск/ [шаг_сек=300] [с_сек] [по_сек] [--fix]
Каждые шаг секунд берёт 25 сек звука из source.mp4, заново расшифровывает и ищет
те же слова в words.json. Печатает строку на точку: время в source и сдвиг
(words.json минус source, сек). Сдвиг ноль везде - расшифровка совпадает с видео.
--fix: где сдвиг меняется, сам находит место скачка (пауза между словами) и правит
таймкоды words.json (номера слов те же, конфиги роликов не меняются). Старый файл -
words_do_sdviga.json, что поправлено - sdvig.txt.
"""
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL = "mlx-community/whisper-large-v3-turbo"
WIN = 25.0
SAME = 0.15  # сдвиги ближе этого - один и тот же

FIX = "--fix" in sys.argv
argv = [a for a in sys.argv if a != "--fix"]
ep = Path(argv[1])
step = float(argv[2]) if len(argv) > 2 else 300.0
src = ep / "source.mp4"
words = json.loads((ep / "words.json").read_text())
words = words if isinstance(words, list) else words["words"]
norm = lambda w: re.sub(r"[^\wё]", "", w.lower())
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                           capture_output=True, text=True).stdout)
hms = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def measure(t, win=WIN):
    """Сдвиг words.json против source.mp4 на отрезке [t, t+win] исходника: (сдвиг, совпадений) или None."""
    ws = [(norm(w["w"]), w["s"]) for w in words]
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-t", str(win), "-i", str(src),
                          "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="ru", word_timestamps=True,
                               condition_on_previous_text=False, verbose=None)
    got = [(norm(w["word"]), t + w["start"]) for s in r["segments"] for w in s.get("words", [])]
    got = [g for g in got if len(g[0]) > 2]
    votes = Counter()
    for k in range(len(got) - 2):  # три слова подряд должны совпасть
        tri = [g[0] for g in got[k:k + 3]]
        for j, (w, s) in enumerate(ws):
            if abs(s - got[k][1]) > 60 or w != tri[0]:
                continue
            rest = [x for x, _ in ws[j + 1:j + 8] if len(x) > 2][:2]
            if rest == tri[1:]:
                votes[round(s - got[k][1], 1)] += 1
    if not votes:
        return None
    best = max(votes, key=lambda d: sum(v for x, v in votes.items() if abs(x - d) <= 0.3))
    near = [(x, v) for x, v in votes.items() if abs(x - best) <= 0.3]
    return sum(x * v for x, v in near) / sum(v for _, v in near), sum(v for _, v in near)


def show(t, m):
    print(f"{hms(t)}  {t:7.1f}  " + (f"сдвиг {m[0]:+.2f}  ({m[1]} совп.)" if m else "не нашёл"), flush=True)


print(f"source.mp4: {dur:.1f} сек, последнее слово words.json: {words[-1]['e']:.1f} сек")
t = float(argv[3]) if len(argv) > 3 else 30.0
stop = min(float(argv[4]), dur - WIN) if len(argv) > 4 else dur - WIN
points = []
while t < stop:
    m = measure(t)
    show(t, m)
    if m:
        points.append((t, round(m[0], 2)))
    t += step
if not FIX:
    sys.exit()

# где сдвиг меняется - сужаем отрезок пополам до 20 сек, потом ищем паузу между словами
fixes = []  # (номер первого слова после скачка, на сколько сдвинуть его и все дальше)
if points and abs(points[0][1]) > SAME:  # вся расшифровка смещена с самого начала
    fixes.append((0, -points[0][1]))
for (a, da), (b, db) in zip(points, points[1:]):
    if abs(db - da) <= SAME:
        continue
    lo, hi = a, b
    while hi - lo > 20:
        mid = (lo + hi) / 2
        m = measure(mid, 10) or measure(mid + 5, 10)
        if not m:
            break
        show(mid, m)
        if abs(m[0] - da) <= abs(m[0] - db):
            lo = mid
        else:
            hi = mid
    jump = db - da  # >0: в звуке расшифровки лишние секунды, слова после скачка раньше на jump
    w0, w1 = lo + min(da, db) - 2, hi + 10 + max(da, db) + 2  # отрезок на шкале words.json
    cand = [i for i in range(len(words) - 1) if w0 <= words[i]["e"] and words[i + 1]["s"] <= w1]
    if not cand:
        print(f"!!! не нашёл слов около {hms(lo)} - поправить руками")
        continue
    gap = lambda i: words[i + 1]["s"] - words[i]["e"]
    i = max(cand, key=gap)
    if jump > 0 and gap(i) < jump - 1:
        print(f"ПРОВЕРИТЬ: у {hms(lo)} нет паузы на {jump:.1f} сек, скачок поставлен в самую длинную ({gap(i):.1f} сек)")
    fixes.append((i + 1, -jump))
    print(f"скачок {jump:+.2f} сек после слова {i} «{words[i]['w']}» ({hms(words[i]['e'])} в words.json)", flush=True)

if not fixes:
    print("СДВИГА НЕТ: words.json совпадает с видео")
    sys.exit()
bak = ep / "words_do_sdviga.json"
if not bak.exists():
    shutil.copy2(ep / "words.json", bak)
for k, d in fixes:
    for w in words[k:]:
        w["s"], w["e"] = round(w["s"] + d, 2), round(w["e"] + d, 2)
(ep / "words.json").write_text(json.dumps(words, ensure_ascii=False))
with open(ep / "sdvig.txt", "a") as f:
    for k, d in fixes:
        f.write(f"слово {k} и дальше: {d:+.2f} сек\n")
print("ИСПРАВЛЕНО:", "; ".join(f"слово {k} и дальше {d:+.2f} сек" for k, d in fixes))
