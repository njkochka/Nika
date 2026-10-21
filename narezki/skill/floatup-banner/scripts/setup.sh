#!/bin/zsh
# Установка для баннера FloatUp: zsh setup.sh
set -e
T="$(cd "$(dirname "$0")" && pwd)"
command -v brew >/dev/null || { echo "Сначала поставь Homebrew: https://brew.sh"; exit 1; }
for p in ffmpeg python@3.11; do brew list $p >/dev/null 2>&1 || brew install $p; done
PY="$(brew --prefix python@3.11)/bin/python3.11"
[[ -x "$T/venv/bin/python" ]] || "$PY" -m venv "$T/venv"
"$T/venv/bin/pip" install -q --upgrade pip
"$T/venv/bin/pip" install -q Pillow
echo "Готово."
