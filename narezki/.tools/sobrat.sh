#!/bin/bash
# Собрать пачку нового выпуска на Маке Ники одной строкой (папка нарезок не связана с GitHub):
# скрипты и batch.json с GitHub, видео и расшифровка - свои, из папки выпуска (их кладёт novyy_vypusk.sh).
#   curl -fsSL "https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/sobrat.sh?t=1" | bash -s выпуск [batch.json] [plan|N...]
# Пример: ... | bash -s poperechny-mat-1          - вся пачка
#         ... | bash -s poperechny-mat-1 batch.json plan   - только длины;   ... batch.json 0 2 - ролики 0 и 2 (с 0)
main() {
  set -e
  V="$1"; B="${2:-batch.json}"; shift 2 2>/dev/null || shift $#
  [ -n "$V" ] || { echo "Нужно: имя выпуска"; exit 1; }
  N=~/Desktop/brain/projects/narezki
  R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
  T=$N/.tools_nv; E=$N/$V
  Q="?t=$(date +%s)"  # GitHub отдаёт старые файлы ещё минут 5 после правки - метка времени берёт свежие
  [ -f "$E/source.mp4" ] || { echo "Нет видео $E/source.mp4 - сначала novyy_vypusk.sh"; exit 1; }
  mkdir -p "$T/fonts"
  for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py; do curl -fsSL "$R/.tools/$f$Q" -o "$T/$f"; done
  for f in Montserrat.ttf Rubik.ttf Unbounded.ttf; do curl -fsSL "$R/.tools/fonts/$f$Q" -o "$T/fonts/$f"; done
  curl -fsSL "$R/$V/$B$Q" -o "$E/$B"
  ln -sfn "$N/.tools/venv" "$T/venv"
  ln -sf "$N"/.tools/*.onnx "$T/"
  cd "$T"
  if [ "$1" = plan ]; then ./venv/bin/python batch.py "$E/$B" --plan </dev/null 2>&1 | tail -40; return; fi
  caffeinate -dimsu -w $$ </dev/null &
  ./venv/bin/python batch.py "$E/$B" $(for i in "$@"; do echo --only=$i; done) </dev/null
  L="$E/${B%.json}_log.txt"; [ -f "$L" ] && grep -e "!!!" -e "ПРОВЕРИТЬ" "$L" | tail -20
  D=$(python3 -c "import json,sys;b=json.load(open(sys.argv[1]));print(b.get('desktop_dir') or (b.get('desktop') or b.get('prefix',''))+' - с баннером')" "$E/$B")
  open ~/Desktop/"$D" 2>/dev/null || true
}
main "$@"
