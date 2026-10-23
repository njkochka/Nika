"""Баннер FloatUp в готовый шортс - то же, что делает их бот @floatupbanner_bot.

Запуск: venv/bin/python banner.py ролик.mp4 итог.mp4

Повторяет бота один в один (правила из бота и замеры его роликов в ТикТоке
polkovnikrostik, 21.10.2026):
- ролик до 60 сек включительно - один баннер ровно в середине; 60-80 сек - один на 0:20;
  длиннее 80 сек - 0:20, 1:20, 2:20... по исходнику, без учёта пауз на баннеры: в готовом
  ролике 1:30 второй на ~1:24, как у бота (Ника сверила через бота 23.10.2026);
- в момент баннера ролик стоит на паузе (стоп-кадр), звук ролика и музыки молчит,
  играет озвучка баннера с его родной громкостью, как у бота, потом ролик идёт
  с того же места;
- баннер ускорен в 1.4 раза (5.2 сек -> 3.7), ширина 928 из 1080, по центру экрана,
  углы скруглены.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

BANNER = Path(__file__).resolve().parents[1] / "bannery" / "FloatUp.mp4"
W, H = 1080, 1920
BW, BH, RADIUS = 928, 522, 40
SPEED = 1.4


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,r_frame_rate", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def points(length):
    if length <= 60:
        return [length / 2]
    return [20 + 60 * k for k in range(int(length // 60) + 1) if 20 + 60 * k < length]


def mask(path):
    """Маска со скруглёнными углами для баннера."""
    m = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, BW - 1, BH - 1), RADIUS, fill=255)
    m.save(path)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    info = probe(src)
    length = float(info["format"]["duration"])
    num, den = next(s["r_frame_rate"] for s in info["streams"] if s["codec_type"] == "video").split("/")
    fps = int(num) / int(den)
    t = [round(p * fps) / fps for p in points(length)]
    b_len = float(probe(BANNER)["format"]["duration"]) / SPEED

    bounds = [0.0] + t + [length]
    n = len(bounds) - 1
    f = [f"[0:v]setsar=1,split={n}" + "".join(f"[v{i}]" for i in range(n)),
         f"[0:a]aresample=48000,asplit={n}" + "".join(f"[a{i}]" for i in range(n)),
         f"[1:v]setpts=PTS/{SPEED},fps={fps},scale={BW}:{BH},setsar=1,format=yuva420p[bb]",
         f"[2:v]format=gray,scale={BW}:{BH}[bm]",
         f"[bb][bm]alphamerge,split={len(t)}" + "".join(f"[b{i}]" for i in range(len(t))),
         f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atempo={SPEED},asplit={len(t)}"
         + "".join(f"[ba{i}]" for i in range(len(t)))]
    cat = ""
    for i in range(n):
        s, e = bounds[i], bounds[i + 1]
        f.append(f"[v{i}]trim={s}:{e},setpts=PTS-STARTPTS[vt{i}]")
        f.append(f"[a{i}]atrim={s}:{e},asetpts=PTS-STARTPTS[at{i}]")
        if i < len(t):
            f.append(f"[vt{i}]tpad=stop_mode=clone:stop_duration={b_len}[vp{i}]")
            f.append(f"[b{i}]setpts=PTS-STARTPTS+{e - s}/TB[bs{i}]")
            f.append(f"[vp{i}][bs{i}]overlay={(W - BW) // 2}:{(H - BH) // 2}:eof_action=pass[vo{i}]")
            f.append(f"[ba{i}]asetpts=PTS-STARTPTS[bq{i}]")
            f.append(f"[at{i}][bq{i}]concat=n=2:v=0:a=1[ao{i}]")
            cat += f"[vo{i}][ao{i}]"
        else:
            cat += f"[vt{i}][at{i}]"
    f.append(f"{cat}concat=n={n}:v=1:a=1[v][a]")
    dst.parent.mkdir(parents=True, exist_ok=True)
    m = Path(tempfile.mkstemp(suffix=".png")[1]); mask(m)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(BANNER), "-loop", "1", "-i", str(m),
                    "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
                    "-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart",
                    str(dst)], check=True)
    m.unlink()
    print("Баннер FloatUp:", ", ".join(f"{int(x // 60)}:{x % 60:05.2f}" for x in t))


if __name__ == "__main__":
    main()
