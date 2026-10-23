#!/bin/bash
# Новый выпуск на Маке Ники: скачать с YouTube, расшифровать и отдать расшифровку облачному Claude.
# Папка нарезок не связана с GitHub, поэтому расшифровка уходит архивом на рабочий стол - его перетащить в чат.
#   curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/novyy_vypusk.sh | bash -s ссылка выпуск
# Пример: ... | bash -s "https://www.youtube.com/watch?v=Hb8VMLYWP2E" poperechny-mat-1  (ссылка в кавычках - иначе zsh: no matches found)
# Сначала звук и расшифровка (архив готов раньше), потом видео source.mp4 и сверка расшифровки с ним (архив обновляется).
set -e
URL="$1"; V="$2"
[ -n "$URL" ] && [ -n "$V" ] || { echo "Нужно: ссылка и имя выпуска"; exit 1; }
N=~/Desktop/brain/projects/narezki
R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
T=$N/.tools_nv; E=$N/$V
Q="?t=$(date +%s)"  # GitHub отдаёт старые файлы ещё минут 5 после правки - метка времени берёт свежие
mkdir -p "$T" "$E"
caffeinate -dimsu -w $$ &
for f in fetch.sh transcribe.py sdvig.py; do curl -fsSL "$R/.tools/$f$Q" -o "$T/$f"; done
chmod +x "$T/fetch.sh"
ln -sfn "$N/.tools/venv" "$T/venv"
brew upgrade yt-dlp >/dev/null 2>&1 || true  # старый yt-dlp YouTube не пускает
Z=~/Desktop/"$V - расшифровка.zip"
pack() { rm -f "$Z"; (cd "$E" && zip -q "$Z" words.json transcript.txt); }
if [ ! -f "$E/words.json" ]; then
  echo "Скачиваю звук и расшифровываю (минут 10-20)..."
  zsh "$T/fetch.sh" "$URL" "$E" audio </dev/null
  rm -f "$E"/audio_src.*
fi
pack; echo "Расшифровка готова: $Z - перетащить в чат с Claude"
if [ ! -f "$E/source.mp4" ]; then
  echo "Скачиваю видео и сверяю расшифровку с ним..."
  zsh "$T/fetch.sh" "$URL" "$E" video </dev/null
  pack
fi
echo "Готово: видео $E/source.mp4, расшифровка $Z"
open -R "$Z"
