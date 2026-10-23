#!/bin/bash
# Орлов 2 на Маке Ники, где папка нарезок не связана с GitHub. Ничего локального не меняет:
# скрипты с GitHub кладутся отдельно в .tools_o2/ и orlov-2-gh/, venv, модели лиц, музыка и баннер - свои.
# Проба (ролик про плинтус):  curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash
# Первые 5 роликов:          ... | bash -s 5
# 9 роликов для rezanina:     curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash -s all
# 9 роликов для нового ТТ:    ... | bash -s novyy
# Пересобрать ролики нового ТТ по порядку в batch_novyy.json (5 - стихи, 6 - прицеп, 7 - туфля): ... | bash -s novyy 5 6 7
# Сдвиг расшифровки words.json против звука source.mp4 (строка на каждые 5 минут): ... | bash -s sdvig; кусок с шагом 15 сек: ... | bash -s sdvig 15 4830 5140
# Починить расшифровку (сдвиг против видео) и пересобрать 33, 35, 37, 40: ... | bash -s ispravit
# Один ролик rezanina по порядку в batch.json (0 - плинтус, 1 - ворота): ... | bash -s one 1
# Обе половины по папкам «1 Berta - REZANINA» и «2 - ttpremium» (номер = номер темы; собранные не пересобираются): ... | bash -s papki
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
for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py sheet.py sdvig.py; do curl -fsSL "$R/.tools/$f" -o "$T/$f"; done
for f in Montserrat.ttf Rubik.ttf Unbounded.ttf; do curl -fsSL "$R/.tools/fonts/$f" -o "$T/fonts/$f"; done
for f in batch.json batch_novyy.json batch_proba.json; do curl -fsSL "$R/orlov-2/$f" -o "$E/$f"; done
# words.json, поправленный sdvig.py --fix (есть sdvig.txt), не затирать версией с GitHub
[ -f "$E/sdvig.txt" ] || curl -fsSL "$R/orlov-2/words.json" -o "$E/words.json"
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
if [ "$1" = ispravit ]; then  # починить расшифровку и пересобрать ролики, где она съехала
  ./venv/bin/python sdvig.py "$E/" 300 --fix </dev/null 2>&1 | grep -v -i -e warn -e fetching | tee "$E/sdvig_log.txt"
  ./venv/bin/python batch.py "$E/batch_novyy.json" --only=5 --only=6 --only=7 --only=8 </dev/null
  echo; grep -e "скачок" -e "ИСПРАВЛЕНО" -e "СДВИГА НЕТ" -e "!!!" -e "ПРОВЕРИТЬ" "$E/sdvig_log.txt"; open ~/Desktop/"2 - ttpremium"; exit
fi
if [ "$1" = sdvig ]; then shift; ./venv/bin/python sdvig.py "$E/" "${@:-300}" </dev/null 2>&1 | grep -v -i warn; exit; fi
[ -f "$E/frames/sheet.jpg" ] || ./venv/bin/python sheet.py "$E/" 60 </dev/null
if [ "$1" = papki ]; then ./venv/bin/python batch.py "$E/batch.json" --music </dev/null; ./venv/bin/python batch.py "$E/batch_novyy.json" --music </dev/null
  open ~/Desktop/"1 Berta - REZANINA"; open ~/Desktop/"2 - ttpremium"; exit
elif [ "$1" = all ]; then ./venv/bin/python batch.py "$E/batch.json" </dev/null; open ~/Desktop/"1 Berta - REZANINA"
elif [ "$1" = novyy ]; then shift; ./venv/bin/python batch.py "$E/batch_novyy.json" "${@/#/--only=}" </dev/null; open ~/Desktop/"2 - ttpremium"
elif [ "$1" = one ]; then ./venv/bin/python batch.py "$E/batch.json" --only="$2" </dev/null; open ~/Desktop/"1 Berta - REZANINA"
elif [ "$1" = 5 ]; then ./venv/bin/python batch.py "$E/batch.json" --only=0 --only=1 --only=2 --only=3 --only=4 </dev/null; open ~/Desktop/"1 Berta - REZANINA"
else ./venv/bin/python batch.py "$E/batch_proba.json" </dev/null; open ~/Desktop/"Орлов проба - с баннером"; fi
open "$E/frames/sheet.jpg"
