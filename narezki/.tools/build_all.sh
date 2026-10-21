#!/bin/zsh
# Собирает все шортсы выпуска по очереди и проверяет каждый стык.
# Запуск: build_all.sh папка_выпуска конфиг1.json конфиг2.json ...
cd "$(dirname "$0")"
dir="$1"; shift
for cfg in "$@"; do
  echo "######## $cfg"
  ./venv/bin/python make_short.py "$dir/$cfg" 2>&1 | grep -v setPreferableTarget
  ./venv/bin/python check_cuts.py "$dir/$cfg" 2>&1 | grep -vE "Warning|Fetching|WARN"
done
echo "ВСЁ ГОТОВО"
