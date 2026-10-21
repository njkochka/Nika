"""Дословная расшифровка готового ролика кусками по 15 сек - проверить запинки и обрезанные слова.
Запуск: venv/bin/python verbatim.py ролик.mp4"""
import subprocess, sys
import mlx_whisper, numpy as np
f = sys.argv[1]
a = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                                 capture_output=True).stdout, np.int16).astype(np.float32) / 32768
for k in range(0, len(a), 15 * 16000):
    r = mlx_whisper.transcribe(a[k:k + 16 * 16000], path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language="ru",
                               initial_prompt="Ээ... ну, мм, это самое... э-э, а-а, ну вот, эм.", condition_on_previous_text=False)
    print(f"{k // 16000:3d}с", r["text"].strip())
