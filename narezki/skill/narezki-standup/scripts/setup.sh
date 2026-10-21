#!/bin/zsh
# Установка окружения для нарезок: zsh setup.sh
# Нужен Мак на Apple Silicon (M1 и новее) - расшифровка идёт через mlx-whisper.
set -e
T="$(cd "$(dirname "$0")" && pwd)"
[[ $(uname -m) == arm64 ]] || { echo "Нужен Мак на Apple Silicon (M1 и новее)"; exit 1; }
command -v brew >/dev/null || { echo "Сначала поставь Homebrew: https://brew.sh"; exit 1; }
for p in ffmpeg yt-dlp python@3.11; do brew list $p >/dev/null 2>&1 || brew install $p; done
PY="$(brew --prefix python@3.11)/bin/python3.11"
[[ -x "$T/venv/bin/python" ]] || "$PY" -m venv "$T/venv"
"$T/venv/bin/pip" install -q --upgrade pip
"$T/venv/bin/pip" install -q -r "$T/requirements.txt"
chmod +x "$T/fetch.sh"
# модели лиц OpenCV Zoo (Apache 2.0): поиск лица и узнавание
Z=https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models
[[ -s "$T/face_yunet.onnx" ]] || curl -fsSL -o "$T/face_yunet.onnx" "$Z/face_detection_yunet/face_detection_yunet_2023mar.onnx"
[[ -s "$T/face_sface.onnx" ]] || curl -fsSL -o "$T/face_sface.onnx" "$Z/face_recognition_sface/face_recognition_sface_2021dec.onnx"
H="${NAREZKI_HOME:-$HOME/Нарезки}"; mkdir -p "$H/готовые" "$H/музыка"
echo "Готово. Папка нарезок: $H (музыку для фона положи в $H/музыка)"
