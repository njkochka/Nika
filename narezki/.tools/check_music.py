"""Проверка роликов с музыкой против версий без музыки.

Запуск: venv/bin/python check_music.py папка_без_музыки папка_с_музыкой
Для каждого ролика: насколько музыка тише голоса, есть ли места, где её не слышно,
пики, длина, разборчивость речи (Whisper).
"""
import difflib
import subprocess
import sys
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL = "mlx-community/whisper-large-v3-turbo"
SR = 16000


def pcm(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                        "-f", "s16le", "-"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.split()
    return out


def peak(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    lines = [l for l in r.splitlines() if "Peak:" in l]
    return lines[-1].split("Peak:")[1].strip() if lines else "?"


def text(a):
    return mlx_whisper.transcribe(a, path_or_hf_repo=MODEL, language="ru")["text"].lower().split()


def main():
    dry_dir, wet_dir = Path(sys.argv[1]), Path(sys.argv[2])
    for wet in sorted(wet_dir.glob("*.mp4")):
        dry = dry_dir / wet.name
        o, m = pcm(dry), pcm(wet)
        n = min(len(o), len(m))
        o, m = o[:n], m[:n]
        g = float(np.dot(m, o) / np.dot(o, o))          # голос в итоговом миксе = g * исходный голос
        music = m - g * o                                 # остаток = музыка
        win = SR
        rows = []
        for k in range(0, n - win, win):
            v, mu = g * o[k:k + win], music[k:k + win]
            rows.append((k / SR, db(v), db(mu)))
        speech = [(t, v, mu) for t, v, mu in rows if v > -40]
        rel = np.median([mu - v for t, v, mu in speech]) if speech else float("nan")
        quiet = [t for t, v, mu in rows if mu < -45 and 1.5 < t < n / SR - 2]
        match = difflib.SequenceMatcher(None, text(o), text(m)).ratio() * 100
        d_dry, d_wet = float(info(dry)[-1]), float(info(wet)[-1])
        print(f"{wet.stem}")
        print(f"  музыка тише голоса на {-rel:.1f} дБ | пик {peak(wet)} | "
              f"длина {d_wet:.2f} (без музыки {d_dry:.2f}) | речь совпадает {match:.0f}%")
        if quiet:
            print(f"  музыку почти не слышно на секундах: {quiet}")


if __name__ == "__main__":
    main()
