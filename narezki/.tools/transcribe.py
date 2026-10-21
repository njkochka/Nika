"""Расшифровка аудио с таймкодом каждого слова.

Запуск: venv/bin/python transcribe.py audio.wav out_dir
На выходе: words.json (все слова с временем) и transcript.txt (текст по фразам с таймкодами).
"""
import json
import sys
from pathlib import Path

import mlx_whisper

MODEL = "mlx-community/whisper-large-v3-turbo"


def fmt(t):
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def main():
    audio, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        language="ru",
        word_timestamps=True,
        condition_on_previous_text=False,
        verbose=False,
    )

    words = []
    lines = []
    for seg in result["segments"]:
        lines.append(f"[{fmt(seg['start'])}] {seg['text'].strip()}")
        for w in seg.get("words", []):
            words.append({
                "w": w["word"].strip(),
                "s": round(w["start"], 2),
                "e": round(w["end"], 2),
                "p": round(w.get("probability", 0), 2),
            })

    (out_dir / "words.json").write_text(json.dumps(words, ensure_ascii=False))
    (out_dir / "transcript.txt").write_text("\n".join(lines))
    print(f"слов: {len(words)}, фраз: {len(lines)}")


if __name__ == "__main__":
    main()
