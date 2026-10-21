"""Проверка склеек готового шортса на слух (через Whisper).

Запуск: venv/bin/python check_cuts.py config.json
Для каждой склейки между кусками: что должно звучать (слова по краям)
и что реально слышно в готовом ролике в окне ±0.9 сек.
"""
import json
import subprocess
import sys
from pathlib import Path

import mlx_whisper
import numpy as np

import make_short as m

MODEL = "mlx-community/whisper-large-v3-turbo"


def main():
    cfg_path = Path(sys.argv[1]).resolve()
    cfg = json.loads(cfg_path.read_text())
    base = cfg_path.parent
    words = json.loads((base / cfg["words"]).read_text())
    shots = json.loads((base / (Path(cfg["out"]).stem + "_tmp") / "shots.json").read_text())
    out = str(base / cfg["out"])

    # куски = последовательные планы с piece_start
    t, bounds = 0.0, []
    for sh in shots:
        if sh.get("piece_start") and t > 0:
            bounds.append(t)
        t += sh["e"] - sh["s"]

    keep = set()
    for a, b in cfg["ranges"]:
        keep.update(range(a, b + 1))
    kept = sorted(keep)

    for t in bounds:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t - 0.9):.2f}", "-t", "1.8",
                            "-i", out, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                           capture_output=True, check=True)
        audio = np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="ru")
        print(f"{t:6.2f}с  слышно: {r['text'].strip()}")


if __name__ == "__main__":
    main()
