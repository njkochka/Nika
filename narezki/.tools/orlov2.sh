#!/bin/bash
# Орлов 2 на Маке Ники, где папка нарезок не связана с GitHub. Ничего локального не меняет:
# скрипты с GitHub кладутся отдельно в .tools_o2/ и orlov-2-gh/, venv, модели лиц, музыка и баннер - свои.
# Проба (ролик про плинтус):  curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash
# Первые 5 роликов:          ... | bash -s 5
# 9 роликов для rezanina:     curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/orlov2.sh | bash -s all
# 9 роликов для нового ТТ:    ... | bash -s novyy
# Пересобрать ролики нового ТТ по порядку в batch_novyy.json (5 - стихи, 6 - прицеп, 7 - туфля): ... | bash -s novyy 5 6 7
# Сдвиг расшифровки words.json против звука source.mp4 (строка на каждые 5 минут): ... | bash -s sdvig; кусок с шагом 15 сек: ... | bash -s sdvig 15 4830 5140
# Починить расшифровку (сдвиг против видео) и пересобрать 33, 35, 37, 40: ... | bash -s ispravit (только стихи: ... | bash -s ispravit 5)
# Один ролик rezanina по порядку в batch.json (0 - плинтус, 1 - ворота): ... | bash -s one 1
# На ночь (всё сразу, Мак не засыпает): сверка расшифровки, пересборка 33, 35, 37, 40, недостающие и обрубленные
#   ролики обеих половин собираются, остальным - музыка и баннер заново; итог в orlov-2-gh/noch_log.txt: ... | bash -s noch
# Новые ролики на ночь (темы без ⭐: 8 для REZANINA, 10 для ttpremium), Мак не засыпает: ... | bash -s novye
#   (только REZANINA: ... | bash -s novye r; только ttpremium: ... | bash -s novye p)
# Обе половины по папкам «1 Berta - REZANINA» и «2 - ttpremium» (номер = номер темы; собранные не пересобираются): ... | bash -s papki
set -e
N=~/Desktop/brain/projects/narezki
R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
T=$N/.tools_o2; E=$N/orlov-2-gh
Q="?t=$(date +%s)"  # GitHub отдаёт старые файлы ещё минут 5 после правки - метка времени берёт свежие
mkdir -p "$T/fonts" "$E"
# убрать связь с GitHub, которую добавили в общую папку brain 22.10 (она там не нужна)
G=$(git -C "$N" rev-parse --show-toplevel 2>/dev/null || true)
if [ -n "$G" ] && [ "$(git -C "$G" remote get-url origin 2>/dev/null)" = "https://github.com/njkochka/Nika.git" ]; then
  git -C "$G" branch --unset-upstream 2>/dev/null || true; git -C "$G" remote remove origin
fi
for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py sheet.py sdvig.py; do curl -fsSL "$R/.tools/$f$Q" -o "$T/$f"; done
for f in Montserrat.ttf Rubik.ttf Unbounded.ttf; do curl -fsSL "$R/.tools/fonts/$f$Q" -o "$T/fonts/$f"; done
for f in batch.json batch_novyy.json batch_proba.json batch_rezanina2.json batch_premium2.json; do curl -fsSL "$R/orlov-2/$f$Q" -o "$E/$f"; done
curl -fsSL "$R/orlov-2/words.json$Q" -o "$E/words.json"  # в git уже сверен с видео (sdvig.py, 23.10.2026)
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
  ./venv/bin/python batch.py "$E/batch_novyy.json" $(for i in ${2:-5 6 7 8}; do echo --only=$i; done) </dev/null
  echo; grep -e "скачок" -e "ИСПРАВЛЕНО" -e "СДВИГА НЕТ" -e "!!!" -e "ПРОВЕРИТЬ" "$E/sdvig_log.txt"; open ~/Desktop/"2 - ttpremium"; exit
fi
if [ "$1" = novye ]; then  # новые ролики на ночь: caffeinate не даёт Маку уснуть
  caffeinate -dimsu -w $$ &
  L="$E/novye_log.txt"; : > "$L"
  [ "$2" != p ] && { ./venv/bin/python batch.py "$E/batch_rezanina2.json" </dev/null 2>&1 | tee -a "$L" || true; }
  [ "$2" != r ] && { ./venv/bin/python batch.py "$E/batch_premium2.json" </dev/null 2>&1 | tee -a "$L" || true; }
  echo; echo "======== ИТОГ"; grep -e "^!!!" -e "ВСЁ ГОТОВО" "$L" || true
  for d in "1 Berta - REZANINA новые" "2 - ttpremium новые"; do echo "в «$d»: $(ls ~/Desktop/"$d" 2>/dev/null | grep -c mp4) роликов"; open ~/Desktop/"$d" 2>/dev/null || true; done
  exit
fi
if [ "$1" = noch ]; then  # на ночь: caffeinate не даёт Маку уснуть, пока идёт сборка
  L="$E/noch_log.txt"; : > "$L"
  caffeinate -dimsu -w $$ & 
  echo "== сверка расшифровки с видео" | tee -a "$L"
  ./venv/bin/python sdvig.py "$E/" 300 --fix </dev/null 2>&1 | grep -v -i -e warn -e fetching | tee -a "$L" || true
  if grep -q '^!!!' "$L"; then
    echo "!!! расшифровку не починить само - 33, 35, 37, 40 НЕ пересобраны (иначе опять рассинхрон)" | tee -a "$L"
  else
    echo "== пересборка 33, 35, 37, 40" | tee -a "$L"
    ./venv/bin/python batch.py "$E/batch_novyy.json" --only=5 --only=6 --only=7 --only=8 </dev/null 2>&1 | tee -a "$L" || true
  fi
  echo "== остальные ролики обеих половин" | tee -a "$L"
  ./venv/bin/python batch.py "$E/batch.json" --music </dev/null 2>&1 | tee -a "$L" || true
  ./venv/bin/python batch.py "$E/batch_novyy.json" --music </dev/null 2>&1 | tee -a "$L" || true
  echo; echo "======== ИТОГ"; grep -e "скачок" -e "ИСПРАВЛЕНО" -e "СДВИГА НЕТ" -e "!!!" -e "ПРОВЕРИТЬ" -e "ВСЁ ГОТОВО" "$L" || true
  echo "в «1 Berta - REZANINA»: $(ls ~/Desktop/"1 Berta - REZANINA" 2>/dev/null | grep -c mp4) роликов, в «2 - ttpremium»: $(ls ~/Desktop/"2 - ttpremium" 2>/dev/null | grep -c mp4) (должно быть по 9)"
  open ~/Desktop/"1 Berta - REZANINA"; open ~/Desktop/"2 - ttpremium"; exit
fi
if [ "$1" = sdvig ]; then shift; ./venv/bin/python sdvig.py "$E/" "${@:-300}" </dev/null 2>&1 | grep -v -i warn; exit; fi
[ -f "$E/frames/sheet.jpg" ] || ./venv/bin/python sheet.py "$E/" 60 </dev/null
if [ "$1" = papki ]; then ./venv/bin/python batch.py "$E/batch.json" --music </dev/null; ./venv/bin/python batch.py "$E/batch_novyy.json" --music </dev/null
  open ~/Desktop/"1 Berta - REZANINA"; open ~/Desktop/"2 - ttpremium"; exit
elif [ "$1" = all ]; then ./venv/bin/python batch.py "$E/batch.json" </dev/null; open ~/Desktop/"1 Berta - REZANINA"
elif [ "$1" = novyy ]; then shift; ./venv/bin/python batch.py "$E/batch_novyy.json" "${@/#/--only=}" </dev/null; open ~/Desktop/"2 - ttpremium"
elif [ "$1" = one ]; then ./venv/bin/python batch.py "$E/batch.json" --only="$2" </dev/null; open ~/Desktop/"1 Berta - REZANINA"
elif [ "$1" = 5 ]; then ./venv/bin/python batch.py "$E/batch.json" --only=0 --only=1 --only=2 --only=3 --only=4 </dev/null; open ~/Desktop/"1 Berta - REZANINA"
elif [ -n "$1" ]; then echo "!!! не знаю команду «$1» - скрипт мог прийти старый, повторите через пару минут"; exit 1
else ./venv/bin/python batch.py "$E/batch_proba.json" </dev/null; open ~/Desktop/"Орлов проба - с баннером"; fi
open "$E/frames/sheet.jpg"
