"""Огрызки в готовом ролике: планы короче 0.5 сек между двумя сменами картинки
(«25-й кадр» на стыке). Запуск: venv/bin/python check_shots.py ролик.mp4 [...]"""
import subprocess, sys
import numpy as np

W, H, FPS, MIN = 160, 284, 25, 13
for v in sys.argv[1:]:
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", v, "-vf", f"scale={W}:{H},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, H, W).astype(np.int16)
    # верх кадра: субтитры внизу меняются на каждом слове
    d = [float(np.abs(fr[i] - fr[i - 1])[:180].mean()) for i in range(1, len(fr))]
    # смена картинки - скачок в разы больше, чем у соседних кадров (быстрое движение не считается)
    d = [0.0] + d + [0.0]
    b = [0] + [i for i in range(1, len(d) - 1)
               if d[i] > 18 and d[i] > 4 * max(d[i - 1], d[i + 1], 1.0)] + [len(fr)]
    bad = [(a / FPS, c - a) for a, c in zip(b, b[1:]) if c - a < MIN]
    print(f"{v.split('/')[-1]}: склеек {len(b) - 2}, огрызков {len(bad)}",
          *[f"  {t:.2f} сек: {n} кадров" for t, n in bad], sep="\n")
