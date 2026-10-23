#!/bin/bash
# Пересборка 5 роликов Орлова 1 в субтитрах neo для повторной выкладки - на Маке Ники,
# где папка нарезок не связана с GitHub. Ничего локального не меняет: скрипты с GitHub
# кладутся отдельно в .tools_neo/ и orlov-1-neo/, исходник, venv и модели лиц берутся по ссылке.
# Запуск: curl -fsSL https://raw.githubusercontent.com/njkochka/Nika/main/narezki/.tools/neo_vylozhit.sh | bash
# Только баннер на уже собранные, без пересборки: ... | bash -s -- --music
# Только нужные ролики (номер по порядку в batch_vylozhit.json, с 0): ... | bash -s -- --only=5 --only=6
set -e
N=~/Desktop/brain/projects/narezki
R=https://raw.githubusercontent.com/njkochka/Nika/main/narezki
T=$N/.tools_neo; E=$N/orlov-1-neo
[ -f "$N/orlov-1/source.mp4" ] || { echo "Нет $N/orlov-1/source.mp4 - исходник Орлова 1 не найден"; exit 1; }
mkdir -p "$T/fonts" "$E"
for f in batch.py make_short.py tidy.py add_music.py check_cuts.py banner.py; do curl -fsSL "$R/.tools/$f" -o "$T/$f"; done
curl -fsSL "$R/.tools/fonts/Unbounded.ttf" -o "$T/fonts/Unbounded.ttf"
curl -fsSL "$R/orlov-1/words.json" -o "$E/words.json"  # с ним сверены номера слов в конфиге
curl -fsSL "$R/orlov-1/batch_vylozhit.json" -o "$E/batch_vylozhit.json"
ln -sfn "$N/.tools/venv" "$T/venv"
ln -sf "$N"/.tools/*.onnx "$T/"
ln -sf "$N/orlov-1/source.mp4" "$E/source.mp4"
cd "$T" && ./venv/bin/python batch.py "$E/batch_vylozhit.json" "$@" </dev/null
open ~/Desktop/"Выложить потом"
