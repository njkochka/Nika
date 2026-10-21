"""Где в готовом ролике лицо уходит от центра или пропадает.

Запуск: venv/bin/python check_face.py ролик.mp4
Печатает секунды, где лица нет или его центр дальше 25% ширины от середины кадра.
"""
import sys
from pathlib import Path

import cv2

det = cv2.FaceDetectorYN.create(str(Path(__file__).parent / "face_yunet.onnx"), "", (270, 480))
cap = cv2.VideoCapture(sys.argv[1])
fps = cap.get(cv2.CAP_PROP_FPS)
k, bad = 0, []
while True:
    ok, fr = cap.read()
    if not ok:
        break
    if k % round(fps / 5) == 0:
        _, faces = det.detect(cv2.resize(fr, (270, 480)))
        t = k / fps
        if faces is None:
            bad.append(f"{t:.1f} нет лица")
        else:
            f = max(faces, key=lambda f: f[2] * f[3])
            off = (f[0] + f[2] / 2) / 270 - 0.5
            if abs(off) > 0.25:
                bad.append(f"{t:.1f} лицо {'слева' if off < 0 else 'справа'} {abs(off):.0%}")
    k += 1
print("\n".join(bad) if bad else "лицо всё время в центре")
