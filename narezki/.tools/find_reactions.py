"""Поиск кадров для вставки реакции: один человек крупно, анфас, без титров шоу.

Запуск: venv/bin/python find_reactions.py config.json host|guest начало-конец [начало-конец ...]
Людей узнаёт по образцам лиц из config "faces". Печатает отрезки >= 1.2 сек.
Губы проверять глазами: реакция - когда человек молчит.
"""
import json
import sys
from pathlib import Path

import make_short as m


def main():
    cfg_path = Path(sys.argv[1])
    cfg = json.loads(cfg_path.read_text())
    source = str(cfg_path.parent / cfg["source"])
    role = sys.argv[2]
    m.HOST_SIDE = cfg.get("host_side", "left")
    m.GUEST_DARK = cfg.get("guest_hair", "dark") == "dark"
    det = m.detector()
    m.load_refs(source, det, cfg["faces"])
    for rng in sys.argv[3:]:
        a, b = (float(x) for x in rng.split("-"))
        frames = m.read_frames(source, a, b - a, 2)
        run = None
        for i, fr in enumerate(list(frames) + [None]):
            t = a + i / 2
            ok = False
            if fr is not None:
                p = m.people(det, fr, m.HOST_SIDE)
                bottom, center = m.captions(fr)
                ok = (len(p) == 1 and role in p and p[role][3] and p[role][2] >= 0.12 * m.SRC_H
                      and bottom < m.CAPTION_WHITE and center < m.CAPTION_WHITE)
            if ok and run is None:
                run = t
            if not ok and run is not None:
                if t - run >= 1.2:
                    print(f"{role}: {run:.1f}-{t:.1f} ({t - run:.1f} сек)")
                run = None


if __name__ == "__main__":
    main()
