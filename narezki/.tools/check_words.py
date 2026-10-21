"""Проверка краёв кусков на обрезанные слова.

Запуск: venv/bin/python check_words.py config.json [config.json ...]
Каждый кусок готового ролика отдельно расшифровывается Whisper. Первое и последнее
слово сравниваются с тем, что должно звучать. Если слово распознано не целиком или
другое - печатает место.
"""
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import mlx_whisper
import numpy as np

MODEL = "mlx-community/whisper-large-v3-turbo"
norm = lambda w: re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def main():
    for arg in sys.argv[1:]:
        cfg_path = Path(arg).resolve()
        cfg = json.loads(cfg_path.read_text())
        base = cfg_path.parent
        words = json.loads((base / cfg["words"]).read_text())
        shots = json.loads((base / (Path(cfg["out"]).stem + "_tmp") / "shots.json").read_text())
        out = str(base / cfg["out"])
        keep = set()
        for a, b in cfg["ranges"]:
            keep.update(range(a, b + 1))
        pieces, t = [], 0.0
        for sh in shots:
            d = sh["e"] - sh["s"]
            if sh.get("piece_start"):
                pieces.append([sh["s"], sh["e"], t, t + d])
            elif pieces and not sh.get("cutaway"):
                pieces[-1][1], pieces[-1][3] = sh["e"], t + d
            elif pieces:
                pieces[-1][3] = t + d
            t += d
        print(f"## {Path(cfg['out']).stem}")
        bad = 0
        for s, e, ts, te in pieces:
            exp = [words[i]["w"] for i in sorted(keep) if s <= (words[i]["s"] + words[i]["e"]) / 2 <= e]
            exp = [w for w in exp if norm(w)]
            if not exp:
                continue
            p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-t", f"{te - ts:.3f}", "-i", out,
                                "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
            a = np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768
            got = [w for w in mlx_whisper.transcribe(a, path_or_hf_repo=MODEL, language="ru")["text"].split() if norm(w)]
            if not got:
                print(f"  {ts:5.1f} сек: ничего не распознано, ждали «{' '.join(exp)}»")
                bad += 1
                continue
            first_ok = max(sim(exp[0], g) for g in got[:2]) >= 0.75
            last_ok = max(sim(exp[-1], g) for g in got[-2:]) >= 0.75
            if not (first_ok and last_ok):
                bad += 1
                print(f"  {ts:5.1f}-{te:5.1f} сек: ждали «{' '.join(exp)}»\n"
                      f"                     слышно «{' '.join(got)}»")
        print(f"  подозрительных кусков: {bad} из {len(pieces)}")


if __name__ == "__main__":
    main()
