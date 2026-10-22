#!/bin/bash
# Айрапетов, пачка 6 на Маке Ники, где папка нарезок не связана с GitHub. Ничего локального не меняет:
# скрипты с GitHub кладутся отдельно в .tools_a6/ и ayrapetov-1-gh/, venv, модели лиц, музыка, баннер и видео - свои.
# Длины:        curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/ayrapetov6.sh | bash -s plan
# Вся пачка:    curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/ayrapetov6.sh | bash
# Один ролик:   ... | bash -s 3   (номер в batch6.json, с 0)
set -e
N=~/Desktop/brain/projects/narezki
R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
T=$N/.tools_a6; E=$N/ayrapetov-1-gh
[ -f "$N/ayrapetov-1/source.mp4" ] || { echo "Нет видео $N/ayrapetov-1/source.mp4"; exit 1; }
mkdir -p "$T/fonts" "$E"
for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py; do curl -fsSL "$R/.tools/$f" -o "$T/$f"; done
for f in Montserrat.ttf Rubik.ttf Unbounded.ttf; do curl -fsSL "$R/.tools/fonts/$f" -o "$T/fonts/$f"; done
for f in words.json batch6.json; do curl -fsSL "$R/ayrapetov-1/$f" -o "$E/$f"; done
ln -sfn "$N/.tools/venv" "$T/venv"
ln -sf "$N"/.tools/*.onnx "$T/"
ln -sf "$N/ayrapetov-1/source.mp4" "$E/source.mp4"
cd "$T"
if [ "$1" = plan ]; then ./venv/bin/python batch.py "$E/batch6.json" --plan </dev/null 2>&1 | tail -40; exit
elif [ -n "$1" ]; then ./venv/bin/python batch.py "$E/batch6.json" --only="$1" </dev/null
else ./venv/bin/python batch.py "$E/batch6.json" </dev/null; fi
open ~/Desktop/"Айрапетов - с баннером"
