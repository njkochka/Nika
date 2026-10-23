"""Замер: насколько таймкоды words.json разъехались со звуком source.mp4 по ходу выпуска.

Запуск: venv/bin/python sdvig.py выпуск/ [шаг_сек=300] [с_сек] [по_сек]
Каждые шаг секунд берёт 25 сек звука из source.mp4, заново расшифровывает и ищет
те же слова в words.json. Печатает строку на точку: время в source и сдвиг
(words.json минус source, сек). Сдвиг ноль везде - расшифровка совпадает с видео.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL = "mlx-community/whisper-large-v3-turbo"
WIN = float(__import__("os").environ.get("SDVIG_WIN", 25))

ep = Path(sys.argv[1])
step = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
src = ep / "source.mp4"
words = json.loads((ep / "words.json").read_text())
words = words if isinstance(words, list) else words["words"]
norm = lambda w: re.sub(r"[^\wё]", "", w.lower())
ws = [(norm(w["w"]), w["s"]) for w in words]
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                           capture_output=True, text=True).stdout)
print(f"source.mp4: {dur:.1f} сек, последнее слово words.json: {words[-1]['e']:.1f} сек")

t = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
stop = min(float(sys.argv[4]), dur - WIN) if len(sys.argv) > 4 else dur - WIN
while t < stop:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-t", str(WIN), "-i", str(src),
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
    if votes:
        best = max(votes, key=lambda d: sum(v for x, v in votes.items() if abs(x - d) <= 0.3))
        near = [(x, v) for x, v in votes.items() if abs(x - best) <= 0.3]
        d = sum(x * v for x, v in near) / sum(v for _, v in near)
        print(f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}  {t:7.1f}  сдвиг {d:+.2f}  ({sum(v for _, v in near)} совп.)", flush=True)
    else:
        print(f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}  {t:7.1f}  не нашёл", flush=True)
    t += step
