"""Наложение фоновой музыки на готовый шортс.

Запуск: venv/bin/python add_music.py видео.mp4 трек.mp3 итог.mp4 [громкость_музыки_LUFS] [старт_трека_сек]

- музыка выводится на заданную громкость (level - в пересчёте на голос -14 LUFS);
- в музыке приглушены частоты речи (около 2 кГц на 5 дБ), чтобы голос не тонул;
- пока человек говорит, музыка мягко приглушается на 2-3 дБ (sidechain по голосу);
- громкость самой музыки выровнена (без нарастаний к концу трека);
- плавное появление 1 сек и затухание 3 сек в конце, последняя фраза почти без музыки;
- звук самого ролика (голос) не меняется вообще: ни громкость, ни тембр. Громкость музыки
  считается относительно голоса (level -20 при голосе -14 LUFS = музыка на 6 дБ тише);
- у музыки срезаны басы, чтобы не гудела под голосом;
- главы и метаданные трека в ролик не переносятся (иначе плеер показывает длину трека).
Видео не перекодируется, меняется только звук.
"""
import subprocess
import sys
import tempfile
from pathlib import Path


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout)


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float([l for l in r.splitlines() if l.strip().startswith("I:")][-1].split()[1])


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def main():
    video, track, out = sys.argv[1], sys.argv[2], sys.argv[3]
    level = float(sys.argv[4]) if len(sys.argv) > 4 else -24
    start = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    d = duration(video)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1. кусок трека нужной длины, с вырезом частот речи и плавными краями
        ff("-stream_loop", "-1", "-i", track, "-t", f"{start + d:.3f}", "-af",
           f"atrim={start}:{start + d},asetpts=PTS-STARTPTS,aresample=48000,"
           f"equalizer=f=2200:t=q:w=1.2:g=-5,"
           f"highpass=f=60,bass=g=-9:f=180,"  # басы тише: под голосом не гудят
           f"dynaudnorm=f=500:g=9:m=10,"  # ровная громкость самой музыки, без нарастаний к концу
           f"afade=t=in:d=1,afade=t=out:st={max(d - 3, 0):.2f}:d=3",
           "-ac", "2", "-map_metadata", "-1", str(tmp / "music.wav"))
        # громкость музыки задаётся относительно голоса: level -20 при голосе -14 = музыка на 6 дБ тише
        music_gain = level - lufs(tmp / "music.wav") + (lufs(video) + 14)
        # 2. смесь голоса и музыки, музыка мягко уступает голосу
        ff("-i", video, "-i", str(tmp / "music.wav"), "-filter_complex",
           f"[1:a]volume={music_gain:.2f}dB[m];"
           f"[0:a]aresample=48000,asplit[v1][v2];"
           f"[m][v1]sidechaincompress=threshold=0.1:ratio=2:attack=30:release=500[md];"
           f"[v2][md]amix=inputs=2:normalize=0:duration=first[a]",
           "-map", "[a]", str(tmp / "mix.wav"))
        # 3. звук ролика не меняем: только кладём смесь обратно к видео (без выравнивания и ограничителя)
        ff("-i", video, "-i", str(tmp / "mix.wav"),
           "-map", "0:v", "-map", "1:a", "-map_chapters", "-1", "-map_metadata", "-1",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest",
           "-movflags", "+faststart", out)
    print("готово:", out)


if __name__ == "__main__":
    main()
