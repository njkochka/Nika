"""Лист кадров исходника с подписями секунд - выбрать образцы лиц.
Запуск: venv/bin/python sheet.py выпуск/ шаг_сек [ширина_кадра=240] -> выпуск/frames/sheet.jpg"""
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ep = Path(sys.argv[1]); step = float(sys.argv[2]); W = int(sys.argv[3]) if len(sys.argv) > 3 else 240
src = ep / "source.mp4"
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                           capture_output=True, text=True).stdout)
H = W * 9 // 16; ts = [step / 2 + k * step for k in range(int(dur // step))]
cols = 8; sheet = Image.new("RGB", (cols * W, ((len(ts) + cols - 1) // cols) * H))
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
for k, t in enumerate(ts):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                          "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    im = Image.frombytes("RGB", (W, H), raw); d = ImageDraw.Draw(im)
    d.text((4, 2), f"{t:.0f}", fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    sheet.paste(im, ((k % cols) * W, (k // cols) * H))
(ep / "frames").mkdir(exist_ok=True); sheet.save(ep / "frames/sheet.jpg", quality=80); print(len(ts), "кадров")
