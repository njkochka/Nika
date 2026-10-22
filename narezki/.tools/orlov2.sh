#!/bin/bash
# Орлов 2 на Маке Ники, где папка нарезок не связана с GitHub. Ничего локального не меняет:
# скрипты с GitHub кладутся отдельно в .tools_o2/ и orlov-2-gh/, venv, модели лиц, музыка и баннер - свои.
# Проба (ролик про плинтус):  curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash
# Первые 5 роликов:          ... | bash -s 5
# 9 роликов для rezanina:     curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash -s all
# 9 роликов для нового ТТ:    ... | bash -s novyy
# Один ролик rezanina по порядку в batch.json (0 - плинтус, 1 - ворота): ... | bash -s one 1
# Обе половины по папкам «резанина» и «новый тт» (номер = номер темы; собранные не пересобираются): ... | bash -s papki
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
for f in words.json batch.json batch_novyy.json batch_proba.json; do curl -fsSL "$R/orlov-2/$f" -o "$E/$f"; done
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
[ -f "$E/frames/sheet.jpg" ] || ./venv/bin/python sheet.py "$E/" 60 </dev/null
if [ "$1" = papki ]; then ./venv/bin/python batch.py "$E/batch.json" --music </dev/null; ./venv/bin/python batch.py "$E/batch_novyy.json" --music </dev/null
  open ~/Desktop/"резанина"; open ~/Desktop/"новый тт"; exit
elif [ "$1" = all ]; then ./venv/bin/python batch.py "$E/batch.json" </dev/null; open ~/Desktop/"резанина"
elif [ "$1" = novyy ]; then ./venv/bin/python batch.py "$E/batch_novyy.json" </dev/null; open ~/Desktop/"новый тт"
elif [ "$1" = one ]; then ./venv/bin/python batch.py "$E/batch.json" --only="$2" </dev/null; open ~/Desktop/"резанина"
elif [ "$1" = 5 ]; then ./venv/bin/python batch.py "$E/batch.json" --only=0 --only=1 --only=2 --only=3 --only=4 </dev/null; open ~/Desktop/"резанина"
else ./venv/bin/python batch.py "$E/batch_proba.json" </dev/null; open ~/Desktop/"Орлов проба - с баннером"; fi
open "$E/frames/sheet.jpg"
