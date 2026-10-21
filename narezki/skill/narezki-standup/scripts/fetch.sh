#!/bin/zsh
# Скачать выпуск с YouTube и расшифровать: fetch.sh ссылка папка_выпуска [audio|video]
#   audio - только звук + расшифровка (быстро, текст готов раньше видео)
#   video - только видео source.mp4 (1080p)
set -e
T="$(cd "$(dirname "$0")" && pwd)"; url="$1"; dir="$2"; what="${3:-audio}"; mkdir -p "$dir"
if [[ $what == video ]]; then
  yt-dlp -q --no-warnings -N 8 -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]" \
    --merge-output-format mp4 -o "$dir/source.%(ext)s" "$url"
else
  yt-dlp -q --no-warnings -N 8 -f "ba[ext=m4a]/ba" -o "$dir/audio_src.%(ext)s" "$url"
  ffmpeg -v error -y -i "$dir"/audio_src.* -ac 1 -ar 16000 "$dir/audio.wav"
  "$T/venv/bin/python" "$T/transcribe.py" "$dir/audio.wav" "$dir" 2>&1 | grep -v Warning | tail -1
fi
echo "готово $what: $dir"
