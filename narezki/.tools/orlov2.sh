#!/bin/bash
# Орлов 2 на Маке Ники, где папка нарезок не связана с GitHub. Ничего локального не меняет:
# скрипты с GitHub кладутся отдельно в .tools_o2/ и orlov-2-gh/, venv, модели лиц, музыка и баннер - свои.
# Проба (ролик про плинтус):  curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash
# Все 18 роликов:             curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash -s all
set -e
N=~/Desktop/brain/projects/narezki
R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
T=$N/.tools_o2; E=$N/orlov-2-gh
mkdir -p "$T/fonts" "$E"
# убрать связь с GitHub, которую добавили в общую папку brain 22.10 (она там не нужна)
G=$(git -C "$N" rev-parse --show-toplevel 2>/dev/null || true)
if [ -n "$G" ] && [ "$(git -C "$G" remote get-url origin 2>/dev/null)" = "https://github.com/njkochka/Nika.git" ]; then
  git -C "$G" branch --unset-upstream 2>/dev/null || true; git -C "$G" remote remove origin
fi
for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py sheet.py; do curl -fsSL "$R/.tools/$f" -o "$T/$f"; done
for f in Montserrat.ttf Rubik.ttf Unbounded.ttf; do curl -fsSL "$R/.tools/fonts/$f" -o "$T/fonts/$f"; done
for f in words.json batch.json batch_proba.json; do curl -fsSL "$R/orlov-2/$f" -o "$E/$f"; done
ln -sfn "$N/.tools/venv" "$T/venv"
ln -sf "$N"/.tools/*.onnx "$T/"
if [ ! -f "$E/source.mp4" ]; then
  if [ -f "$N/orlov-2/source.mp4" ]; then ln -sf "$N/orlov-2/source.mp4" "$E/source.mp4"
  else echo "Скачиваю видео Орлова 2..."
    yt-dlp -q --no-warnings -N 8 -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]" \
      --merge-output-format mp4 -o "$E/source.%(ext)s" https://www.youtube.com/watch?v=QZ_KnPxeqgU
  fi
fi
cd "$T"
[ -f "$E/frames/sheet.jpg" ] || ./venv/bin/python sheet.py "$E/" 60
if [ "$1" = all ]; then ./venv/bin/python batch.py "$E/batch.json"; open ~/Desktop/"Орлов - с баннером"
else ./venv/bin/python batch.py "$E/batch_proba.json"; open ~/Desktop/"Орлов проба - с баннером"; fi
open "$E/frames/sheet.jpg"
