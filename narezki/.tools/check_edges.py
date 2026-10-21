"""Поиск обрезанных слов: рез посреди звучащего голоса.

Запуск: venv/bin/python check_edges.py config.json [config.json ...]
Для каждого куска смотрит громкость исходника прямо у реза (30 мс внутри и 60 мс снаружи).
Если снаружи реза голос ещё звучит почти так же громко, как речь, - слово, скорее всего,
обрезано. Печатает такие места с временем в готовом ролике и словами вокруг.
"""
import json
import sys
from pathlib import Path

import numpy as np

import make_short as m


def main():
    for arg in sys.argv[1:]:
        cfg_path = Path(arg).resolve()
        cfg = json.loads(cfg_path.read_text())
        base = cfg_path.parent
        source = str(base / cfg["source"])
        words = json.loads((base / cfg["words"]).read_text())
        shots = json.loads((base / (Path(cfg["out"]).stem + "_tmp") / "shots.json").read_text())
        pieces, t = [], 0.0
        for sh in shots:
            if sh.get("piece_start"):
                pieces.append([sh["s"], sh["e"], t])
            elif pieces and not sh.get("cutaway"):
                pieces[-1][1] = sh["e"]
            t += sh["e"] - sh["s"]
        speech = np.median([db for s, e, _ in pieces for _, db in m.loudness(source, s, e, 0.05)])
        print(f"## {Path(cfg['out']).stem}  (речь ~{speech:.0f} дБ)")
        out_t = 0.0
        for s, e, _ in pieces:
            for edge, side, t_out in (("начало", s, out_t), ("конец", e, out_t + e - s)):
                outside = (side - 0.06, side) if edge == "начало" else (side, side + 0.06)
                lvl = max(db for _, db in m.loudness(source, *outside, 0.01))
                if lvl > speech - 6:
                    near = [w["w"] for w in words if abs((w["s"] + w["e"]) / 2 - side) < 0.6]
                    print(f"  {edge} куска на {t_out:5.1f} сек: снаружи реза громко ({lvl:.0f} дБ) | {' '.join(near)}")
            out_t += e - s


if __name__ == "__main__":
    main()
