"""Сборка вертикального шортса из интервью.

Запуск: venv/bin/python make_short.py config.json
config.json:
  source     - исходное видео 16:9
  words      - words.json из transcribe.py
  ranges     - список [первое_слово, последнее_слово] (индексы в words.json, включительно)
  host_ranges - диапазоны слов, которые говорит ведущий (камера на нём), остальное - гость
  cutaways   - вставки реакции: [{"word": индекс, "src": сек_в_исходнике, "dur": сек}]
               видео поверх звука, начиная со слова word
  fixes      - {"слово_как_услышал_whisper": "как писать в субтитрах"}
  fix_words  - {"индекс_слова": "ТЕКСТ"} - правка конкретного слова
  cut_at     - ручные точки реза после проверки на слух: {"start": {"индекс": сек}, "end": {...}}
  faces      - образцы лиц: {"host": [[сек, "big"|"left"|"right"], ...], "guest": [...]}
  caption_zones - титры шоу внизу кадра: [[с_сек, по_сек, верх_титра_px_из_1080], ...] -
               там кадр приближается и берёт верх, титр уходит за край
  framing    - ручное наведение: [{"src": [с, по], "who": "host"}, {"src": [с, по], "pan": [[сек, x], ...]}]
  silence_db, silence_min - порог тишины (дБ) и мин. длина паузы (сек), по умолчанию -32 и 0.3;
               min_piece - кусок короче не дробим (0.5)
  keep_pause - [[слово, слово], ...]: паузу между этими словами не вырезать (смех зала)
  track      - true: рамка плавно ведёт лицо, масштаб постоянный (концерты, стендап)
  sub_style  - "pill": новые субтитры (Montserrat Black, слово под голосом на цветной плашке
               с «прыжком»; Rubik Black, белое слово на чёрной плашке - Орлов 2); "neo": шрифт Unbounded, звучащее слово бирюзовое с «прыжком», строка выше
               (y 1150 вместо 1300); "neo_yellow": то же, звучащее слово жёлтое (Орлов 2, новый ТТ); "word": по одному слову, Rubik Black, белое с чёрной обводкой (Орлов 2);
               без него - старые (Arial Black, жёлтое слово)
  stage_torso - порог яркости одежды под лицом комика (100); 0 - не отсеивать (тёмная одежда, зала нет)
  punch_in   - "auto" (по умолчанию): приближение 115% только там, где голова прыгнула;
               true - на каждой склейке; false - никогда
  out        - итоговый файл

Камера: кадр всегда 9:16 во весь экран.
  Ведёт того, кто говорит. Если говорящий в профиль или со спины, а второй
  смотрит в камеру - показывает второго (реакция). Гость и ведущий различаются
  по цвету волос: у гостя тёмные (HOST_IS_LIGHTER).
"""
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOOLS = Path(__file__).parent
FPS = 25
FRAME = 1 / FPS
OUT_W, OUT_H = 1080, 1920
SRC_W, SRC_H = 1920, 1080
PUNCH_ZOOMS = [1.0, 1.15]
JUMP_MIN = 0.12             # сдвиг головы на склейке (в долях высоты лица), выше - приближаем
CUT_DIFF = 28               # разница соседних кадров, выше - смена камеры
CUT_DIFF_LOW, CUT_RATIO = 12, 5  # или выше 12 и в 5 раз больше, чем у соседних кадров
EDGE_SLIVER = 3             # хвост основного плана рядом со вставкой реакции короче 3 кадров
KEEP_PAUSES = []            # паузы, которые не вырезаем (config "keep_pause")
SPEECH_DB = 65              # громкость речи (зал шумит ~50-60 дБ)
SLIVER_MAX = 12             # план другой камеры на краю куска короче 12 кадров (0.5 сек) - отрезаем
EDGE_ZONE = 0.25            # где искать тихую точку для реза: не дальше 250 мс от нужного слова
CAPTION_WHITE = 0.5         # % белых пикселей у резких краёв в полосе: выше - там титр шоу
CAPTION_TOP = 860           # титры шоу внизу начинаются примерно с этой строки (из 1080)
PAD_IN, PAD_OUT = 0.08, 0.12
SILENCE_DB, SILENCE_MIN, SILENCE_KEEP = -32, 0.30, 0.10
MIN_PIECE = 0.5           # кусок короче - не дробим дальше: видна дёрганая склейка
SAMPLE_FPS = 5
TRACK_FPS = 10              # режим track: как часто искать лицо
TRACK_DEADZONE = 0.03       # доля ширины рамки: голова гуляет внутри - рамка стоит
TRACK_KEEP = 0.06           # лицо не дальше этой доли ширины рамки от центра
TRACK_SMOOTH = 0.15         # сек, сглаживание движения рамки
FACE_MATCH = 0.4            # похожесть лица на образец (0..1), выше - узнали
FRONTAL_EYES = 0.2          # расстояние между глазами / ширина лица: выше - анфас
WIDE_FACE = 0.15            # лицо ниже 15% кадра - общий план, приближаем
WIDE_ZOOM = 1.3
TRACK_MAX_ZOOM = 1.8        # режим track: предел приближения общего плана (дальше мыло)
STAGE_TORSO = 100           # яркость под лицом: выше - светлая одежда комика, ниже - тёмный зал
COVER_MAX = 1.5             # режим track: план без комика (шоу показало зал) не длиннее - стоп-кадр
STAGE_CLOSE = 0.25          # лицо выше этой доли кадра - крупный план, зрителей не бывает
HAIR_SPLIT = 80             # яркость волос: ниже - гость (тёмные), выше - ведущий
GUEST_DARK = True           # у гостя волосы темнее, чем у ведущего (config: guest_hair dark|light)
HOST_SIDE = "left"          # где сидит ведущий, когда в кадре двое (config: host_side)
FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
FONT_SIZE = 60
STROKE = 7
SUB_Y = 1320
YELLOW = (255, 214, 0)
# стиль "pill": слово, которое звучит, - белым на чёрной плашке и «прыгает» при появлении (Орлов 2)
PILL_FONT = Path(__file__).parent / "fonts" / "Rubik.ttf"  # OFL, с кириллицей (Ника выбрала Rubik для Орлова 2)
PILL_SIZE = 58
PILL_STROKE = 5
PILL_W = 480                         # ширина строки: 2-3 слова встают в две строки, как раньше
PILL_Y = 1300
PILL_COLOR = (0, 0, 0)               # плашка
PILL_TEXT = (255, 255, 255)          # слово на плашке
PILL_POP = [1.08, 1.04]              # масштаб активного слова в первые кадры, дальше 1.0
# стиль "neo": шрифт Unbounded, слова белые с мягкой тенью, звучащее - бирюзовое и «прыгает»,
# строка выше и уже, чем у остальных стилей (не залезает под кнопки ТикТока справа)
NEO_FONT = Path(__file__).parent / "fonts" / "Unbounded.ttf"  # OFL, с кириллицей
NEO_SIZE = 56
NEO_STROKE = 4
NEO_Y = 1150
NEO_W = 860                          # ширина строки, дальше перенос (кнопки ТикТока справа не задевает)
NEO_COLOR = (0, 236, 220)            # звучащее слово: на розовом и тёмном фоне видно, не жёлтое
NEO_JUMP = [-14, -7, -3]             # «прыжок» звучащего слова вверх (px) в первые кадры: шрифт широкий,
                                     # увеличение как у pill наезжало бы на соседние слова
# стиль "word": на экране только звучащее слово - белое с чёрной обводкой и мягкой тенью, по центру
WORD_FONT = Path(__file__).parent / "fonts" / "Rubik.ttf"  # OFL, с кириллицей
WORD_SIZE = 88
WORD_STROKE = 6
WORD_Y = 1150                        # центр слова: выше подписи и кнопок ТикТока
WORD_W = 900                         # длинное слово шире - шрифт уменьшается
SUB_STYLE = "classic"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def snap(t):
    return round(t / FRAME) * FRAME


# ---------- 1. куски и паузы ----------

def ranges_to_intervals(words, ranges, source, overrides=None):
    overrides = overrides or {}
    merged = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:  # соседние куски не склеиваем: между ними вырезано лишнее
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        s = words[a]["s"] - PAD_IN
        # рез - в самой тихой точке между соседними словами, но не дальше EDGE_ZONE от нужного:
        # таймкоды whisper врут на 50-100 мс, а между словами бывают слова, которых нет в расшифровке
        if a > 0:
            s = quietest(source, max(words[a - 1]["e"] - 0.04, words[a]["s"] - EDGE_ZONE),
                         words[a]["s"] + 0.04)
            if not starts_hissing(words[a]["w"]):  # не тащим хвост выкинутого слова ("ч", "с")
                while s < words[a]["s"] + 0.06 and hiss(pcm16k(source, s, 0.03)):
                    s += 0.01
        if str(a) in overrides.get("start", {}):  # ручная точка реза после проверки на слух
            s = overrides["start"][str(a)]
        e = words[b]["e"] + PAD_OUT
        if b + 1 < len(words):
            e = quietest(source, words[b]["e"] - 0.04,
                         max(min(words[b + 1]["s"] + 0.04, words[b]["e"] + EDGE_ZONE), words[b]["e"] + 0.06))
            if not ends_hissing(words[b]["w"]):  # не тащим начало выкинутого "с моим"
                while e > words[b]["e"] - 0.06 and hiss(pcm16k(source, e - 0.03, 0.03)):
                    e -= 0.01
        # Whisper часто ставит конец слова раньше, чем оно затихает («шато» обрезалось).
        # Если после слова пауза - продлеваем до места, где звук действительно стих.
        if b + 1 < len(words) and words[b + 1]["s"] - words[b]["e"] > 0.4:
            e = max(e, faded(source, words[b], words[b + 1]["s"]) or e)
        if str(b) in overrides.get("end", {}):
            e = overrides["end"][str(b)]
        out.append((s, e))
    return out


def faded(source, w, nxt):
    """Где слово w действительно стихло (не дальше 0.5 сек и следующего слова); None - не стихло."""
    if nxt - 0.05 - w["e"] < 0.1:  # следующее слово вплотную - смотреть негде
        return None
    lv = loudness(source, w["e"], min(w["e"] + 0.5, nxt - 0.05))
    peak = max(v for _, v in loudness(source, w["s"], max(w["e"], w["s"] + 0.03)))
    for k in range(len(lv) - 9):
        if all(v < peak - 25 for _, v in lv[k:k + 10]):
            return lv[k][0] + 0.05
    return None


def loudness(source, t0, t1, step=0.01, win=0.02):
    """Громкость (дБ) с шагом 10 мс: список (время, дБ)."""
    a = pcm16k(source, t0 - win / 2, t1 - t0 + win)
    n, w = int(step * 16000), int(win * 16000)
    res = []
    for k in range(0, max(1, len(a) - w + 1), n):
        seg = a[k:k + w]
        res.append((t0 + k / 16000, 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1)))
    return res


def quietest(source, lo, hi):
    if hi - lo < 0.04:
        lo, hi = lo - 0.03, hi + 0.03
    return min(loudness(source, lo, hi), key=lambda x: x[1])[0]


def snap_quiet(source, t, inward):
    """До кадра: из двух ближайших кадров берём тот, где тише.
    inward=+1 для начала куска, -1 для конца (при равенстве - внутрь)."""
    lo, hi = math.floor(t / FRAME + 1e-6) * FRAME, math.ceil(t / FRAME - 1e-6) * FRAME
    if lo == hi:
        return lo
    db = lambda x: loudness(source, x, x + 0.005)[0][1]  # окно 20 мс с центром в x
    dl, dh = db(lo), db(hi)
    if abs(dl - dh) < 1.5:
        return hi if inward > 0 else lo
    return lo if dl < dh else hi


HISSING = "сшщчфцзжх"


def starts_hissing(w):
    w = w.strip(" .,!?«»-").lower()
    return bool(w) and w[0] in HISSING


def ends_hissing(w):
    w = w.strip(" .,!?«»-").lower()
    return bool(w) and w[-1] in HISSING


def pcm16k(source, s, dur):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}", "-i", source,
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32)


def hiss(seg):
    """Шипящий звук (с, ш, ч, ф): громко и много пересечений нуля."""
    if len(seg) < 80:
        return False
    db = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1)
    zc = np.mean(np.abs(np.diff(np.sign(seg)))) / 2
    return db > 55 and zc > 0.35


def silences(source, s, e):
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", source,
         "-vn", "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"],
        capture_output=True, text=True)
    res, cur = [], None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            cur = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and cur is not None:
            res.append((s + cur, s + float(line.split("silence_end:")[1].split()[0])))
            cur = None
    return res


def split_by_silence(source, intervals, starts=(), ends=()):
    pieces = []
    for s, e in intervals:
        cur = s
        for ss, se in silences(source, s, e):
            if any(a - 0.15 <= ss < b for a, b in KEEP_PAUSES):
                continue  # пауза для смеха зала: оставляем целиком
            cut_s, cut_e = ss + SILENCE_KEEP, se - SILENCE_KEEP
            # тихое начало слова ниже порога тишины («не» в «нестабильная») - пауза
            # кончается уже внутри слова; режем не ближе 0.15 сек к началу слова по Whisper
            cut_e = min([cut_e] + [w - 0.15 for w in starts if ss < w < se])
            # и тихий конец слова: вопрос «...про микрофлору?» затихает ниже порога тишины,
            # пауза начинается внутри слова - режем только там, где слово действительно стихло
            for w, nxt in ends:
                if ss - 0.3 < w["e"] < se and nxt - w["e"] > 0.15:
                    cut_s = max(cut_s, faded(source, w, nxt) or min(w["e"] + 0.5, nxt - 0.05))
            # паузу вырезаем, только если по обе стороны остаётся не меньше MIN_PIECE:
            # обрывки по 0.2 сек дёргают картинку, а хвост короче 0.15 раньше выкидывался вместе со словом
            if cut_s - cur >= MIN_PIECE and e - cut_e >= MIN_PIECE and cut_e > cut_s:
                pieces.append((cur, cut_s))
                cur = cut_e
        pieces.append((cur, e))
    out = []
    for s, e in pieces:
        # до кадра округляем в ту сторону, где тише, чтобы не задеть звук слова
        s, e = snap_quiet(source, s, +1), snap_quiet(source, e, -1)
        if e - s >= 2 * FRAME:
            out.append((s, e))
    return out


# ---------- 2. кто в кадре ----------

def read_frames(source, s, dur, fps, w=960, h=540):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}", "-i", source,
         "-vf", (f"fps={fps}," if fps else "") + f"scale={w}:{h}",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True, check=True)
    n = len(p.stdout) // (w * h * 3)
    return np.frombuffer(p.stdout[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def detector():
    return cv2.FaceDetectorYN.create(str(TOOLS / "face_yunet.onnx"), "", (960, 540), 0.6)


def hair_brightness(frame, f):
    x, y, w, h = (float(v) for v in f[:4])
    reg = frame[int(max(0, y - 0.45 * h)):int(max(1, y + 0.05 * h)),
                int(max(0, x - 0.3 * w)):int(min(frame.shape[1], x + 1.3 * w))]
    return float(cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).mean()) if reg.size else 255.0


def is_frontal(f):
    """Анфас: глаза широко на лице. В профиль расстояние между глазами почти ноль."""
    return abs(float(f[6]) - float(f[4])) / max(float(f[2]), 1.0) >= FRONTAL_EYES


REFS = {}       # role -> список эмбеддингов лица (образцы из config "faces")
_REC = None


def recognizer():
    global _REC
    if _REC is None:
        _REC = cv2.FaceRecognizerSF.create(str(TOOLS / "face_sface.onnx"), "")
    return _REC


def load_refs(source, det, spec):
    """spec: {"host": [[сек, "big"|"left"|"right"], ...], "guest": [...]} - моменты,
    где лицо этого человека крупно. По ним скрипт узнаёт людей в любом кадре."""
    rec = recognizer()
    for role, items in spec.items():
        REFS[role] = []
        for t, pick in items:
            fr = read_frames(source, t, 0.05, None)[0]
            _, faces = det.detect(fr)
            if faces is None:
                print(f"образец {role} {t}: лицо не найдено")
                continue
            f = {"big": max(faces, key=lambda f: f[2] * f[3]),
                 "left": min(faces, key=lambda f: f[0]),
                 "right": max(faces, key=lambda f: f[0])}[pick]
            REFS[role].append(rec.feature(rec.alignCrop(fr, f)))


def identify(frame, f):
    """Кто это по лицу: (роль, похожесть) или (None, 0), если не уверены."""
    if not REFS:
        return None, 0.0
    rec = recognizer()
    e = rec.feature(rec.alignCrop(frame, f))
    sims = {role: max(rec.match(e, r, cv2.FaceRecognizerSF_FR_COSINE) for r in refs)
            for role, refs in REFS.items() if refs}
    role = max(sims, key=sims.get)
    return (role, sims[role]) if sims[role] >= FACE_MATCH else (None, 0.0)


def people(det, frame, host_side):
    """{'guest': лицо, 'host': лицо}; лицо = (cx, cy, h, анфас) в координатах 1920x1080.
    Сначала узнаём по лицу (образцы из config "faces"). Не узнали (профиль, далеко):
    двое в кадре - ведущий со стороны host_side; один - различаем по волосам."""
    _, faces = det.detect(frame)
    if faces is None:
        return {}
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[:2]
    face = lambda f: (float(f[0] + f[2] / 2) * 2, float(f[1] + f[3] / 2) * 2, float(f[3]) * 2,
                      bool(is_frontal(f)))
    if REFS:
        ids = [identify(frame, f) for f in faces]
        known = {}
        for f, (role, sim) in zip(faces, ids):
            if role and (role not in known or sim > known[role][1]):
                known[role] = (f, sim)
        if known:
            res = {role: face(f) for role, (f, _) in known.items()}
            if len(faces) == 2 and len(known) == 1:  # второго не узнали - он другой
                other = "guest" if "host" in known else "host"
                rest = [f for f in faces if f is not next(iter(known.values()))[0]]
                res[other] = face(rest[0])
            return res
    if len(faces) == 2:
        left, right = sorted(faces, key=lambda f: f[0])
        host, guest = (left, right) if host_side == "left" else (right, left)
        return {"guest": face(guest), "host": face(host)}
    f = faces[0]
    darker = hair_brightness(frame, f) < HAIR_SPLIT
    role = "guest" if darker == GUEST_DARK else "host"
    return {role: face(f)}


def frame_diff(a, b):
    ga = cv2.cvtColor(cv2.resize(a, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.int16)
    gb = cv2.cvtColor(cv2.resize(b, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.int16)
    return float(np.abs(ga - gb).mean())


def camera_cuts(frames):
    """Номера кадров, с которых начинается новая камера (кадры подряд, без пропусков)."""
    d = [0.0] + [frame_diff(frames[i - 1], frames[i]) for i in range(1, len(frames))] + [0.0]
    # похожие камеры (концерт на одном фоне) дают меньше CUT_DIFF: тогда смена - это
    # скачок в разы больше, чем у соседних кадров
    return [i for i in range(1, len(frames))
            if d[i] > CUT_DIFF or (d[i] > CUT_DIFF_LOW and d[i] > CUT_RATIO * max(d[i - 1], d[i + 1], 1.0))]


def face_track(per_frame, who):
    fs = [p[who] for p in per_frame if who in p]
    return (fs[0], fs[-1]) if fs else (None, None)


def choose_target(per_frame, speaker):
    """Кого показывать в этом плане и где его лицо."""
    other = "host" if speaker == "guest" else "guest"
    n = max(1, len(per_frame))

    def track(role, frontal):
        fs = [p[role] for p in per_frame if role in p and (not frontal or p[role][3])]
        return fs if len(fs) >= 0.5 * n else None

    for role, frontal in ((speaker, True), (other, True), (speaker, False), (other, False)):
        fs = track(role, frontal)
        if fs:
            return (float(np.median([f[0] for f in fs])), float(np.median([f[1] for f in fs])),
                    float(np.median([f[2] for f in fs])), role)
    return SRC_W / 2, SRC_H / 2, SRC_H, None


def wide_two_shot(per_frame, speaker, cx, who):
    """Общий план, где видны оба: камера на говорящем (не на слушающем - он и так в кадре),
    говорящий в боковой трети, свободное место - со стороны собеседника, куда он смотрит."""
    n = max(1, len(per_frame))
    other = "host" if speaker == "guest" else "guest"
    sp = [p[speaker] for p in per_frame if speaker in p]
    ot = [p[other] for p in per_frame if other in p]
    if not speaker or len(sp) < 0.5 * n or len(ot) < 0.5 * n:
        return cx, who
    sx, ox = float(np.median([f[0] for f in sp])), float(np.median([f[0] for f in ot]))
    if float(np.median([f[2] for f in sp])) > WIDE_FACE * SRC_H * 1.5:
        return cx, who  # не общий план: лица крупные
    third = SRC_H * 9 / 16 / 6  # сдвиг центра кадра, чтобы лицо встало на треть ширины
    return (sx + third if ox > sx else sx - third), speaker


def analyze_piece(source, det, s, e, speaker):
    """Делит кусок на планы по каждому кадру. Кадр i куска = время s + i/FPS,
    ровно так же, как его потом режет render_video, поэтому граница не уезжает."""
    frames = read_frames(source, s, e - s, None)
    n = round((e - s) / FRAME)
    if len(frames) == 0:
        return [dict(s=s, e=e, cx=SRC_W / 2, cy=SRC_H / 2, fh=SRC_H, who=None)]
    bounds = [0] + camera_cuts(frames) + [n]
    step = max(1, FPS // SAMPLE_FPS)
    shots = []
    for i0, i1 in zip(bounds, bounds[1:]):
        if i1 <= i0:
            continue
        sample = list(range(i0, min(i1, len(frames)), step)) or [min(i0, len(frames) - 1)]
        per_frame = [people(det, frames[i], HOST_SIDE) for i in sample]
        cx, cy, fh, who = choose_target(per_frame, speaker)
        cx, who = wide_two_shot(per_frame, speaker, cx, who)
        first, last = face_track(per_frame, who)
        caps = [captions(frames[i]) for i in sample]
        shots.append(dict(s=s + i0 * FRAME, e=s + i1 * FRAME, cx=cx, cy=cy, fh=fh, who=who,
                          first=first, last=last,
                          auto_caption=max(max(c) for c in caps) > CAPTION_WHITE))
    return shots


def captions(frame):
    """Титры самого шоу поверх видео: % белых пикселей у резких краёв (буквы)
    в нижней полосе кадра и в центре. Небо и белые подушки гладкие - не считаются. Кадр 960x540."""
    white = (frame.min(axis=2) > 215).astype(np.uint8)
    edges = (cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 80, 200) > 0).astype(np.uint8)
    text = white & cv2.dilate(edges, np.ones((3, 3), np.uint8))
    return float(text[430:530].mean() * 100), float(text[150:430].mean() * 100)


def set_zoom(shots, mode):
    """mode False - без приближения; True - чередовать на каждой склейке;
    "auto" - только на склейках, где та же камера и голова заметно прыгнула.
    Если голова почти не сдвинулась - рамка стоит на месте, как неподвижная камера."""
    prev, piece_k = None, -1
    for sh in shots:
        if sh.get("piece_start"):
            piece_k += 1
        if not mode:
            sh["zoom"] = 1.0
        elif mode is True:
            sh["zoom"] = PUNCH_ZOOMS[piece_k % 2]
        else:
            sh["zoom"] = 1.0
            same_camera = (prev is not None and sh.get("piece_start") and sh["who"]
                           and prev["who"] == sh["who"] and prev["last"] and sh["first"]
                           and abs(prev["fh"] - sh["fh"]) < 0.2 * prev["fh"])
            if same_camera:
                (px, py, ph, _), (nx, ny, _, _) = prev["last"], sh["first"]
                jump = math.hypot(nx - px, ny - py) / ph
                drift = abs(sh["cx"] - prev["cx"]) / prev["fh"]
                if jump > JUMP_MIN or drift > 0.5:
                    sh["zoom"] = PUNCH_ZOOMS[1] if prev["zoom"] == PUNCH_ZOOMS[0] else PUNCH_ZOOMS[0]
                else:
                    sh["zoom"], sh["cx"], sh["cy"] = prev["zoom"], prev["cx"], prev["cy"]
                sh["jump"] = round(jump, 2)
        prev = sh


def on_stage(frame, f):
    """Лицо комика, а не зрителя: под ним светлая одежда на сцене (медиана яркости
    торса 150-190), под лицами зала темнота (до 55). Крупный план - торса в кадре нет."""
    x, y, w, h = f[:4]
    if h > STAGE_CLOSE * frame.shape[0]:
        return True
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    x0, x1 = int(max(0, x + w / 2 - w)), int(min(g.shape[1], x + w / 2 + w))
    y0, y1 = int(min(g.shape[0], y + h * 1.6)), int(min(g.shape[0], y + h * 4))
    return y1 - y0 > h and x1 > x0 and float(np.median(g[y0:y1, x0:x1])) > STAGE_TORSO


def body(frame):
    """Комик в светлой одежде, когда лица не видно: (x верха фигуры, y верха, ширина) в 1280x720.
    Самое большое светлое пятно; x - по верхней четверти, там голова (и у согнувшегося)."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    m = cv2.morphologyEx((g > 150).astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    j = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = st[j]
    if area < 0.01 * g.size:
        return None
    top = lab[y:y + max(1, h // 4)] == j
    xs = np.nonzero(top)[1]
    return float(xs.mean()), float(y), float(w)


def track_camera(shots, source, det):
    """Рамка ведёт лицо плавно, как оператор (config "track": true, для концертов, где
    человек ходит по сцене). Масштаб внутри одной камеры постоянный, без зумов на склейках.
    Пока голова гуляет в мёртвой зоне - рамка стоит; вышла - рамка мягко догоняет.
    Склейка на той же камере (вырезана пауза) не прыгает: движение идёт сквозь стык."""
    det720 = cv2.FaceDetectorYN.create(str(TOOLS / "face_yunet.onnx"), "", (1280, 720), 0.6)
    ratios = []   # высота лица / ширина светлой фигуры - для планов, где лица не видно
    samples = []  # по плану: [(сек от начала плана, x, y, высота лица)] в пикселях 1920x1080
    for sh in shots:
        if sh.get("cutaway") or sh.get("who") == "graphic":
            samples.append(None)
            continue
        pts = []
        # 1280x720: на 960x540 комик в движении (размыт, в профиль) теряется, рамка отстаёт
        for i, fr in enumerate(read_frames(source, sh["s"], sh["e"] - sh["s"], TRACK_FPS, 1280, 720)):
            _, faces = det720.detect(fr)
            faces = [f for f in (faces if faces is not None else [])
                     if f[3] > 0.03 * 720 and on_stage(fr, f)]
            if faces:
                # лица зрителей уже отсеяны, из оставшихся - ближе к прошлому
                f = (min(faces, key=lambda f: abs(f[0] + f[2] / 2 - pts[-1][1] / 1.5)
                         + abs(f[1] + f[3] / 2 - pts[-1][2] / 1.5)) if pts
                     else max(faces, key=lambda f: f[2] * f[3]))
                pts.append((i / TRACK_FPS, float(f[0] + f[2] / 2) * 1.5,
                            float(f[1] + f[3] / 2) * 1.5, float(f[3]) * 1.5))
                b = body(fr) if STAGE_TORSO > 0 else None
                if b and abs(b[0] - pts[-1][1] / 1.5) < b[2]:
                    ratios.append(f[3] / b[2])
            elif STAGE_TORSO > 0:
                # лица нет (согнулся, отвернулся) - ведём по светлой одежде, размер лица
                # потом посчитаем по ширине фигуры
                b = body(fr)
                if b:
                    pts.append((i / TRACK_FPS, b[0] * 1.5, b[1] * 1.5, -b[2] * 1.5))
        samples.append(pts)
    # размер лица для точек по фигуре: из лиц этого плана, иначе соседних, иначе по ширине фигуры
    real = [[p[3] for p in s if p[3] > 0] if s else [] for s in samples]
    ratio = float(np.median(ratios)) if ratios else 0.4
    for k, pts in enumerate(samples):
        if not pts:
            continue
        near_fh = next((float(np.median(real[j])) for j in sorted(range(len(real)), key=lambda j: abs(j - k))
                        if real[j]), None)
        # голова согнувшегося - у верха фигуры: центр лица на полвысоты ниже верха
        pts = [(t, x, y, fh) if fh > 0 else (t, x, y + (near_fh or -fh * ratio) / 2, near_fh or -fh * ratio)
               for t, x, y, fh in pts]
        # выбросы (зритель вместо говорящего): далеко от соседних точек.
        # Сравниваем с медианой ближайших 0.5 сек, а не всего плана: на общем плане
        # комик маленький и быстро ходит, его настоящие шаги не выбрасываем
        mf = np.median([p[3] for p in pts])
        near = lambda j, c: np.median([q[c] for q in pts[max(0, j - 2): j + 3]])
        samples[k] = [p for j, p in enumerate(pts)
                      if abs(p[1] - near(j, 1)) < 2.5 * mf and abs(p[2] - near(j, 2)) < 1.5 * mf]

    # прогоны одной камеры: новая камера внутри куска или на склейке другой масштаб/место
    runs, prev = [], None
    for k, sh in enumerate(shots):
        pts = samples[k]
        cur = (float(np.median([p[3] for p in pts])), float(np.median([p[1] for p in pts]))) if pts else None
        same = (runs and prev and cur and sh.get("piece_start")
                and abs(cur[0] - prev[0]) < 0.3 * prev[0] and abs(cur[1] - prev[1]) < 0.35 * SRC_W)
        if same:
            runs[-1].append(k)
        else:
            runs.append([k])
        prev = cur

    ker_r = int(TRACK_SMOOTH * FPS * 2)
    def smooth(v, k=1.0):
        r = max(1, int(ker_r * k))
        g = np.exp(-0.5 * (np.arange(-r, r + 1) / (TRACK_SMOOTH * FPS * k)) ** 2)
        return np.convolve(np.pad(v, r, mode="edge"), g / g.sum(), mode="valid")

    def follow(v, dz):
        out, c = np.empty_like(v), v[0]
        for i, x in enumerate(v):
            c = x - dz if x - c > dz else x + dz if c - x > dz else c
            out[i] = c
        return out

    for run in runs:
        T, X, Y, F, lens = [], [], [], [], []
        off = 0
        for k in run:
            n = round((shots[k]["e"] - shots[k]["s"]) / FRAME)
            for t, x, y, fh in samples[k] or []:
                T.append(off * FRAME + t); X.append(x); Y.append(y); F.append(fh)
            lens.append(n)
            off += n
        if not T:
            continue  # лиц нет - рамка как выбрал автомат
        fh = float(np.median(F))
        # общий план: чем мельче комик, тем сильнее приближаем (зал в кадре не нужен)
        zoom = (min(max(WIDE_FACE * SRC_H / fh * 0.75, WIDE_ZOOM), TRACK_MAX_ZOOM)
                if fh < WIDE_FACE * SRC_H else 1.0)
        ch = SRC_H / zoom
        cw = ch * 9 / 16
        tg = np.arange(off) * FRAME
        # медиана по 0.2 сек убирает дрожь детектора, мёртвая зона - мелкие покачивания;
        # окно длиннее не успевает за резким выпадом комика, лицо уходит к краю
        med = lambda v: np.array([np.median(v[max(0, i - 2): i + 3]) for i in range(len(v))])
        # лицо по каждому плану отдельно: на склейке вырезано время, голова успела сдвинуться.
        # Рамка прыгает на склейке ровно на столько же, и на экране лицо стоит там же,
        # где было в последнем кадре прошлого куска
        gx, gy = np.interp(tg, T, X), np.interp(tg, T, Y)
        px, py, i = [], [], 0
        for k, n in zip(run, lens):
            pts = samples[k] or []
            if pts:
                tl = np.arange(n) * FRAME
                px.append(med(np.interp(tl, [p[0] for p in pts], [p[1] for p in pts])))
                py.append(med(np.interp(tl, [p[0] for p in pts], [p[2] for p in pts])))
            else:  # лица в плане не нашли - как у соседей
                px.append(med(gx[i:i + n])); py.append(med(gy[i:i + n]))
            i += n
        jx, jy = np.zeros(off), np.zeros(off)  # накопленный прыжок головы на склейках
        i, ax, ay, prev = 0, 0.0, 0.0, None
        for j, n in enumerate(lens):
            if prev is not None and n:
                ax += px[j][0] - px[prev][-1]
                ay += py[j][0] - py[prev][-1]
            jx[i:i + n], jy[i:i + n] = ax, ay
            prev = j if n else prev
            i += n
        fx, fy = np.concatenate(px) - jx, np.concatenate(py) - jy  # лицо на экране, без прыжков
        x = smooth(follow(fx, TRACK_DEADZONE * cw))
        y = smooth(follow(fy, TRACK_DEADZONE * ch * 0.6)) + jy
        # рамка не успела за быстрым шагом - подтягиваем, чтобы лицо не уходило к краю
        lim = TRACK_KEEP * cw
        x = smooth(np.clip(x, fx - lim, fx + lim), 0.4) + jx
        x = np.clip(x - cw / 2, 0, SRC_W - cw)
        y = np.clip(y - ch * 0.38, 0, SRC_H - ch)
        i = 0
        for k, n in zip(run, lens):
            shots[k].update(zoom=1.0, wide_zoom=zoom, fh=fh, cx=float(x[i] + cw / 2), cy=float(y[i] + ch * 0.38),
                            track=[[even(a), even(b)] for a, b in zip(x[i:i + n], y[i:i + n])])
            i += n
    # шоу на секунду показало зал (ни лица, ни фигуры комика) - стоп-кадр последнего кадра
    # с комиком, звук идёт дальше
    for k, sh in enumerate(shots):
        prev = shots[k - 1] if k else None
        if (samples[k] == [] and STAGE_TORSO > 0 and sh["e"] - sh["s"] <= COVER_MAX and prev
                and prev.get("track") and not prev.get("freeze")):
            n = round((sh["e"] - sh["s"]) / FRAME)
            shots[k] = dict(prev, s=prev["e"] - FRAME, e=prev["e"] - FRAME + n * FRAME, freeze=True,
                            track=[prev["track"][-1]] * n)
            shots[k].pop("piece_start", None)
    return shots


def split_shots_at(shots, t):
    """Режет план, внутри которого время исходника t, на два."""
    out = []
    for sh in shots:
        if sh["s"] + FRAME / 2 < t < sh["e"] - FRAME / 2:
            a, b = dict(sh, e=t), dict(sh, s=t)
            b.pop("piece_start", None)
            out += [a, b]
        else:
            out.append(sh)
    return out


def apply_framing(shots, framing, source, det):
    """Ручное наведение рамки (config "framing"):
    {"src": [с, по], "who": "host"|"guest"} - рамка на этого человека;
    {"src": [с, по], "pan": [[сек, x], ...]} - рамка на точку x (из 1920) и плавно
    переезжает между ключами - для картинок, где лиц нет (косметика, фото)."""
    for fr_cfg in framing:
        a, b = (snap(v) for v in fr_cfg["src"])
        shots = split_shots_at(split_shots_at(shots, a), b)
        for sh in shots:
            if sh["s"] >= a - 1e-6 and sh["e"] <= b + 1e-6:
                if "who" in fr_cfg:
                    frames = read_frames(source, sh["s"], sh["e"] - sh["s"], SAMPLE_FPS)
                    # рамка строго на этого человека, даже если он в профиль
                    only = [{k: v for k, v in people(det, f, HOST_SIDE).items() if k == fr_cfg["who"]}
                            for f in frames]
                    cx, cy, fh, who = choose_target(only, fr_cfg["who"])
                    sh.update(cx=cx, cy=cy, fh=fh, who=who)
                else:
                    keys = [(t - sh["s"], x) for t, x in fr_cfg["pan"]]
                    sh.update(cx=keys[0][1], cy=SRC_H / 2, fh=SRC_H, who="graphic", pan=keys,
                              first=None, last=None)
    return shots


def speaker_turns(words, keep_words, host_words, s, e, min_turn=0.6):
    """Делит кусок [s, e] на реплики: [(начало, конец, "host"|"guest"), ...].
    Граница - посередине паузы между репликами, по кадрам. Реплики короче min_turn
    сливаются с соседней, чтобы камера не дёргалась."""
    ws = [(i, w) for i, w in enumerate(words)
          if i in keep_words and s <= (w["s"] + w["e"]) / 2 <= e]
    if not ws:
        return [(s, e, "guest")]
    groups = []
    for i, w in ws:
        role = "host" if i in host_words else "guest"
        if groups and groups[-1][2] == role:
            groups[-1][1] = w["e"]
        else:
            groups.append([w["s"], w["e"], role])
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for k, g in enumerate(groups):
            if g[1] - g[0] < min_turn:
                j = k - 1 if k > 0 else k + 1
                groups[j][0], groups[j][1] = min(groups[j][0], g[0]), max(groups[j][1], g[1])
                del groups[k]
                changed = True
                break
        merged = [groups[0]]
        for g in groups[1:]:
            if g[2] == merged[-1][2]:
                merged[-1][1] = g[1]
            else:
                merged.append(g)
        groups = merged
    turns, cur = [], s
    for k, (gs, ge, role) in enumerate(groups):
        end = e if k == len(groups) - 1 else min(max(snap((ge + groups[k + 1][0]) / 2), cur + FRAME), e)
        turns.append((cur, end, role))
        cur = end
    return turns


def trim_edge_slivers(shots, spoken=()):
    """Как при ручной резке: если на краю куска остался огрызок другой камеры
    короче SLIVER_MAX кадров (0.5 сек), его картинку убираем, чтобы на стыке не мелькал
    «25-й кадр». Огрызок в паузе - режем вместе со звуком. Огрызок на слове - звук
    оставляем целиком (слово не обрезается), а картинку на это время даёт соседний
    кусок: возвращаем, сколько секунд звука в начале и в конце остаётся без своей картинки."""
    head = tail = 0.0
    while len(shots) > 1 and shots[0]["e"] - shots[0]["s"] < SLIVER_MAX * FRAME:
        sh, shots = shots[0], shots[1:]
        head = head + sh["e"] - sh["s"] if head or speaks(spoken, sh) else 0.0
    while len(shots) > 1 and shots[-1]["e"] - shots[-1]["s"] < SLIVER_MAX * FRAME:
        sh, shots = shots[-1], shots[:-1]
        tail = tail + sh["e"] - sh["s"] if tail or speaks(spoken, sh) else 0.0
    return shots, head, tail


def has_cut(source, s, e):
    """Есть ли смена камеры в кадрах исходника [s, e] (и на стыке с кадром до s)."""
    return bool(camera_cuts(read_frames(source, s - FRAME, e - s + 2 * FRAME, None)))


def speaks(spoken, sh):
    """Звучит ли в плане нужное слово (Whisper растягивает слова на паузы - проверяем и громкость)."""
    return any(ws + 0.03 < sh["e"] and we - 0.03 > sh["s"] for ws, we in spoken) and \
        max(d for _, d in loudness(SOURCE, sh["s"], sh["e"])) > SPEECH_DB


# ---------- 3. рендер ----------

def even(v):
    return int(v) // 2 * 2


def vf_for(shot):
    zoom = shot["zoom"] * shot.get("wide_zoom", WIDE_ZOOM if shot["fh"] < WIDE_FACE * SRC_H else 1.0)
    bottom = SRC_H
    if shot.get("caption_bottom"):  # плашка шоу внизу: приближаем и берём верх кадра
        bottom = shot.get("caption_top", CAPTION_TOP)
        zoom = max(zoom, SRC_H / bottom)
    ch = SRC_H / zoom
    cw = ch * 9 / 16
    x = min(max(shot["cx"] - cw / 2, 0), SRC_W - cw)
    y = min(max(shot["cy"] - ch * 0.38, 0), bottom - ch)
    if shot.get("track"):  # дальше рамку двигают команды sendcmd
        x, y = shot["track"][0]
    if shot.get("pan"):  # плавный переезд рамки между ключами (мягкий старт и стоп)
        expr = None
        keys = shot["pan"]
        clamp = lambda v: min(max(v - cw / 2, 0), SRC_W - cw)
        expr = f"{clamp(keys[-1][1]):.1f}"
        for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
            a, b = clamp(x0), clamp(x1)
            seg = f"{a:.1f}+({b - a:.1f})*(1-cos(PI*(t-{t0:.3f})/{max(t1 - t0, 0.04):.3f}))/2"
            expr = f"if(lt(t,{t0:.3f}),{a:.1f},if(lt(t,{t1:.3f}),{seg},{expr}))"
        return (f"crop={even(cw)}:{even(ch)}:'{expr}':{even(y)},"
                f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1")
    return (f"crop={even(cw)}:{even(ch)}:{even(x)}:{even(y)},"
            f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1")


def render_video(source, shots, tmp):
    lst = []
    for i, sh in enumerate(shots):
        f = tmp / f"seg_{i:03d}.mp4"
        vf = vf_for(sh)
        if sh.get("freeze"):  # стоп-кадр: первый кадр плана повторяется до конца
            vf = "trim=end_frame=1,tpad=stop_mode=clone:stop=-1," + vf
        if sh.get("track"):  # рамка едет покадрово: команды crop по времени кадра
            cmd = tmp / f"seg_{i:03d}.cmd"
            cmd.write_text("\n".join(f"{j * FRAME:.3f} crop x {x}, crop y {y};"
                                     for j, (x, y) in enumerate(sh["track"])))
            vf = f"sendcmd=f={cmd.name}," + vf  # путь без пробелов и запятых: ffmpeg идёт из tmp
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sh['s']:.3f}", "-i", source,
             "-frames:v", str(round((sh["e"] - sh["s"]) / FRAME)), "-an",
             "-vf", vf, "-r", str(FPS),
             "-c:v", "h264_videotoolbox", "-b:v", "20M", "-pix_fmt", "yuv420p", str(f)], cwd=tmp)
        lst.append(f"file '{f}'")
    (tmp / "list.txt").write_text("\n".join(lst))
    out = tmp / "video.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
         "-c", "copy", str(out)])
    return out


def render_audio(source, pieces, tmp):
    chunks = []
    fade = int(0.012 * 48000)
    for s, e in pieces:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", source,
             "-vn", "-ac", "2", "-ar", "48000", "-f", "s16le", "-"], capture_output=True, check=True)
        a = np.frombuffer(p.stdout, np.int16).reshape(-1, 2).astype(np.float32)
        need = round((e - s) * 48000)
        a = a[:need] if len(a) >= need else np.pad(a, ((0, need - len(a)), (0, 0)))
        ramp = np.linspace(0, 1, fade)[:, None]
        a[:fade] *= ramp
        a[-fade:] *= ramp[::-1]
        chunks.append(a)
    out = tmp / "audio.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(np.clip(np.concatenate(chunks), -32768, 32767).astype(np.int16).tobytes())
    return out


def out_time(pieces, src_t):
    t = 0.0
    for s, e in pieces:
        if s <= src_t <= e:
            return t + src_t - s
        if src_t < s:
            return t
        t += e - s
    return t


def apply_cutaways(shots, cutaways, words, pieces, source, det):
    """Подменяет видео на отрезке [T, T+dur] выхода кадром реакции из src."""
    for c in cutaways:
        T = snap(out_time(pieces, words[c["word"]]["s"]))
        src0, dur = snap(c["src"]), snap(c["dur"])
        n_req = round(dur / FRAME)
        frames = read_frames(source, src0, dur + 0.4, None)  # с запасом, чтобы было куда продлить
        # внутри вставки не должно быть смены камеры: берём самый длинный цельный отрезок
        b = [0] + camera_cuts(frames) + [len(frames)]
        runs = [(a, z) for a, z in zip(b, b[1:]) if a < n_req]
        i0, i1 = max(runs, key=lambda r: min(r[1], n_req) - r[0])
        src, dur = src0 + i0 * FRAME, (min(i1, n_req) - i0) * FRAME
        sample = frames[i0:i1:max(1, FPS // SAMPLE_FPS)]
        cx, cy, fh, who = choose_target([people(det, fr, HOST_SIDE) for fr in sample], c.get("who", "host"))
        cut = dict(s=src, e=src + dur, cx=cx, cy=cy, fh=fh, who=who, zoom=1.0, cutaway=True,
                   run_s=src, run_e=src0 + i1 * FRAME)
        new, t = [], 0.0
        for sh in shots:
            d = sh["e"] - sh["s"]
            a, b = t, t + d
            if b <= T or a >= T + dur:
                new.append(sh)
            else:
                if a < T:
                    new.append(dict(sh, e=sh["s"] + (T - a)))
                if not any(x.get("cutaway") and x["s"] == cut["s"] for x in new):
                    new.append(cut)
                if b > T + dur:
                    new.append(dict(sh, s=sh["s"] + (T + dur - a)))
            t = b
        shots = [sh for sh in new if sh["e"] - sh["s"] >= FRAME / 2]
    return absorb_slivers_near_cutaways(shots)


def absorb_slivers_near_cutaways(shots):
    """Хвост основного плана короче EDGE_SLIVER кадров рядом со вставкой
    мелькает. Продлеваем вставку на эти кадры (пока внутри её цельного плана)."""
    out = list(shots)
    i = 0
    while i < len(out):
        sh = out[i]
        d = sh["e"] - sh["s"]
        if not sh.get("cutaway") and d < EDGE_SLIVER * FRAME - FRAME / 2:
            prev = out[i - 1] if i > 0 else None
            nxt = out[i + 1] if i + 1 < len(out) else None
            if prev and prev.get("cutaway") and prev["e"] + d <= prev["run_e"] + 1e-6:
                prev["e"] += d
                del out[i]
                continue
            if nxt and nxt.get("cutaway") and nxt["s"] - d >= nxt["run_s"] - 1e-6:
                nxt["s"] -= d
                del out[i]
                continue
        i += 1
    return out


# ---------- 4. субтитры ----------

def clean(word, fixes):
    key = word.strip(".,!?…«»\"").lower()
    return fixes.get(key, word.strip(".,!…«»\"")).upper()


# маты в субтитрах - со звёздочкой в середине (П*ХУЙ, Б*Я), звук не трогаем: платформы читают
# текст в кадре и режут охват. Слово должно читаться, поэтому закрываем одну букву.
MAT = [
    (re.compile(r"ХУ(?=[ЙЕЁЯИЮ])"), "Х*"),
    (re.compile(r"П[ИЕЁ]З(?=[ДЖ])"), "П*З"),  # пизда, пизжу, подпездываю
    (re.compile(r"(?<![А-ЯЁ])(ВЫ)?БЛЯ"), r"\1Б*Я"),  # не трогаем влюбляться, употреблять
    (re.compile(r"(?<![А-ЯЁ])(ПОДНА|ПОНА|ЗА|ВЫ|ПО|НА|ОТ|У|ДО|ПЕРЕ|РАЗЪ|РАЗ|ПРО|ПРИ|ВЪ|ОБЪ|СЪ|ПОДЪ|ВЗЪ|ДОЛБО)?([ЕЁ])Б(?=[АЛУИЕНЫЮЯКТО]|(?![А-ЯЁ]))"), r"\1\2*"),
    (re.compile(r"МУДА?К|МУДИЛ"), lambda m: "М*" + m.group(0)[2:]),
    (re.compile(r"ПИД[ОА]?Р"), lambda m: "П*" + m.group(0)[2:]),
    (re.compile(r"Г[АО]НДОН"), lambda m: "Г*" + m.group(0)[2:]),
    (re.compile(r"(?<![А-ЯЁ])ХУЛИ(?![А-ЯЁ])"), "Х*ЛИ"),  # не трогаем хулиган
    (re.compile(r"(?<![А-ЯЁ])СУЧ(?=К|АР|ЕН|Ь)"), "С*Ч"),
    (re.compile(r"ЗАЛУП"), "ЗАЛ*П"),
    (re.compile(r"ДРОЧ"), "ДР*Ч"),
    (re.compile(r"(?<![А-ЯЁ])СУК(?=[АИУЕ]?(?![А-ЯЁ]))"), "С*К"),
]


# слова, за которые ТикТок и другие режут охват (смерть, убийство, суицид, секс, наркотики) -
# так же звёздочка вместо одной буквы, звук не трогаем. Число - какую букву корня закрыть.
_B = r"(?<![А-ЯЁ])(?:ПО|ВЫ|ЗА|ПРИ|ОТ|РАЗ|ПЕРЕ|САМО|НЕ)?"
RISK = [
    (re.compile(_B + r"(УМЕР(?!ЕН|И)|УМЁР|УМР(?=[УЕЁ])|УМИРА)"), 2),  # не трогаем умею, умеренно, умиротворение
    (re.compile(r"СМЕРТ"), 2),
    (re.compile(_B + r"(УБИЙ|УБИТ|УБИВА|УБЬ[ЮЁЕ])"), 2),
    (re.compile(r"СУИЦИД"), 2),
    (re.compile(r"(?<![А-ЯЁ])(КОНЧ)(?!ИЛОСЬ|ИЛИСЬ|ИЛАСЬ|ИЛСЯ|ЕН|ИК|АЕТСЯ|АЮТСЯ|ИТСЯ)"), 3),  # не трогаем «деньги кончились»
    (re.compile(r"СЕКС"), 2),
    (re.compile(r"НАРКО(?=[ТМШ])"), 2),
    (re.compile(r"(?<![А-ЯЁ])ТРУП"), 2),
    (re.compile(_B + r"(ТРАХ)"), 2),
    (re.compile(r"ПЕДОФИЛ"), 3),  # ПЕД*ФИЛ
    (re.compile(r"ИЗНАСИЛ"), 4),
    (re.compile(r"(?<![А-ЯЁ])НАСИЛЬНИК"), 2),
    (re.compile(r"(?<![А-ЯЁ])ПОРН"), 2),  # не трогаем страх, страховку
]


def censor(text):
    for pat, rep in MAT:
        text = pat.sub(rep, text)
    for pat, k in RISK:
        text = pat.sub(lambda m: m.group(0)[:m.start(m.lastindex) - m.start() + k] + "*"
                       + m.group(0)[m.start(m.lastindex) - m.start() + k + 1:] if m.lastindex
                       else m.group(0)[:k] + "*" + m.group(0)[k + 1:], text)
    return text


def subtitle_chunks(words, ranges, pieces, fixes, fix_words):
    keep = set()
    for a, b in ranges:
        keep.update(range(a, b + 1))
    timeline, t = [], 0.0
    for s, e in pieces:
        timeline.append((s, e, t))
        t += e - s
    placed = []
    for i in sorted(keep):
        w = words[i]
        if w["e"] - w["s"] < 0.05:  # Whisper даёт слову нулевую длину («у меня мать») - слово выпадало
            w = dict(w, e=w["s"] + 0.05)
        # кусок, где слова звучит больше всего: таймкоды Whisper часто захватывают паузу после
        # слова, и середина слова попадает в вырезанную паузу - раньше такое слово выпадало
        best = max(timeline, key=lambda p: min(w["e"], p[1]) - max(w["s"], p[0]))
        if min(w["e"], best[1]) - max(w["s"], best[0]) <= 0:
            continue
        for s, e, t0 in [best]:
            if True:
                ws, we = t0 + max(w["s"], s) - s, t0 + min(w["e"], e) - s
                if w["w"].startswith("-") and placed and str(i) not in fix_words:  # whisper отделяет "-то", "-либо"
                    prev = placed[-1]
                    prev["text"] += clean(w["w"], fixes)
                    prev["raw"] += w["w"]
                    prev["e"] = we
                else:
                    text = fix_words.get(str(i), clean(w["w"], fixes)).strip(".,!…«»\"").upper()  # ручные правки - как остальные: заглавными, без точек
                    if text:  # пустая правка = слово не показывать в субтитрах
                        # знак из ручной правки тоже делит фразы: «горло.» - дальше новая строка
                        placed.append(dict(text=text, raw=fix_words.get(str(i), w["w"]), s=ws, e=we))
                break
    for w in placed:
        w["text"] = censor(w["text"])
    chunks, cur = [], []
    for w in placed:
        if cur and (len(cur) >= 3 or len(" ".join(x["text"] for x in cur + [w])) > 18
                    or w["s"] - cur[-1]["e"] > 0.5):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w["raw"].rstrip()[-1:] in ".?!,":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    for k, c in enumerate(chunks):
        end = c[-1]["e"]
        if k + 1 < len(chunks) and chunks[k + 1][0]["s"] - end < 0.4:
            end = chunks[k + 1][0]["s"]
        c[-1]["chunk_end"] = end
    return chunks


def draw_chunk(chunk, active, font):
    img = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=font)
    lines, line, lw = [], [], 0
    for w in chunk:
        wd = d.textlength(w["text"], font=font)
        if line and lw + space + wd > OUT_W - 160:
            lines.append((line, lw))
            line, lw = [], 0
        lw = lw + (space if line else 0) + wd
        line.append((w, wd))
    lines.append((line, lw))
    y = SUB_Y
    for line, lw in lines:
        x = (OUT_W - lw) / 2
        for w, wd in line:
            color = YELLOW if w is active else (255, 255, 255)
            d.text((x, y), w["text"], font=font, fill=color, stroke_width=STROKE, stroke_fill=(0, 0, 0))
            x += wd + space
        y += FONT_SIZE + 14
    return img


def pill_font(size):
    f = ImageFont.truetype(str(PILL_FONT), size)
    f.set_variation_by_name("Black")
    return f


def draw_chunk_pill(chunk, active, font, phase):
    """Слова белые с обводкой и мягкой тенью, звучащее - чёрное на жёлтой плашке.
    phase - кадр от начала звучащего слова: первые кадры слово крупнее («прыжок»)."""
    img = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=font) + 16  # плашка с «прыжком» не наезжает на соседнее слово
    lines, line, lw = [], [], 0
    for w in chunk:
        wd = d.textlength(w["text"], font=font)
        if line and lw + space + wd > PILL_W:
            lines.append((line, lw))
            line, lw = [], 0
        lw = lw + (space if line else 0) + wd
        line.append((w, wd))
    lines.append((line, lw))
    if len(lines) > 2:  # не больше двух строк (Ника): делим слова на две строки поровнее
        ws = [(w, d.textlength(w["text"], font=font)) for w in chunk]
        width = lambda part: sum(wd for _, wd in part) + space * (len(part) - 1)
        k = min(range(1, len(ws)), key=lambda k: max(width(ws[:k]), width(ws[k:])))
        lines = [(ws[:k], width(ws[:k])), (ws[k:], width(ws[k:]))]
    asc, desc = font.getmetrics()
    step = asc + desc + 18
    shadow = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    y, act = PILL_Y, None
    for line, lw in lines:
        x = (OUT_W - lw) / 2
        for w, wd in line:
            if w is active:
                act = (x, y, wd)
            else:
                sd.text((x + 4, y + 7), w["text"], font=font, fill=(0, 0, 0, 170),
                        stroke_width=PILL_STROKE, stroke_fill=(0, 0, 0, 170))
                d.text((x, y), w["text"], font=font, fill=(255, 255, 255),
                       stroke_width=PILL_STROKE, stroke_fill=(0, 0, 0))
            x += wd + space
        y += step
    img = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), img)
    if act:
        x, y, wd = act
        pad_x, pad_y = 18, 10
        top = font.getbbox(active["text"])[1]
        box = Image.new("RGBA", (int(wd + 2 * pad_x), int(asc + desc - top + 2 * pad_y)), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle((0, 0, box.width - 1, box.height - 1), radius=22, fill=PILL_COLOR)
        bd.text((pad_x, pad_y - top), active["text"], font=font, fill=PILL_TEXT)
        k = PILL_POP[phase] if phase < len(PILL_POP) else 1.0
        if k != 1.0:
            box = box.resize((round(box.width * k), round(box.height * k)), Image.LANCZOS)
        cx, cy = x + wd / 2, y + top + (asc + desc - top) / 2
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.paste(Image.new("RGBA", box.size, (0, 0, 0, 150)), (round(cx - box.width / 2 + 4), round(cy - box.height / 2 + 8)), box)
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8)))
        img.paste(box, (round(cx - box.width / 2), round(cy - box.height / 2)), box)
    return img


def neo_font(size):
    f = ImageFont.truetype(str(NEO_FONT), size)
    f.set_variation_by_name("Black")
    return f


def draw_chunk_neo(chunk, active, font, phase):
    """Слова белые с тонкой обводкой и мягкой тенью, звучащее - бирюзовое.
    phase - кадр от начала звучащего слова: первые кадры слово подпрыгивает вверх."""
    img = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=font) + 8
    lines, line, lw = [], [], 0
    for w in chunk:
        wd = d.textlength(w["text"], font=font)
        if line and lw + space + wd > NEO_W:
            lines.append((line, lw))
            line, lw = [], 0
        lw = lw + (space if line else 0) + wd
        line.append((w, wd))
    lines.append((line, lw))
    asc, desc = font.getmetrics()
    step = asc + desc + 12
    shadow = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    y, act = NEO_Y, None
    for line, lw in lines:
        x = (OUT_W - lw) / 2
        for w, wd in line:
            sd.text((x + 3, y + 6), w["text"], font=font, fill=(0, 0, 0, 200),
                    stroke_width=NEO_STROKE + 2, stroke_fill=(0, 0, 0, 200))
            if w is active:
                act = (x, y, wd)
            else:
                d.text((x, y), w["text"], font=font, fill=(255, 255, 255),
                       stroke_width=NEO_STROKE, stroke_fill=(0, 0, 0))
            x += wd + space
        y += step
    img = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7)), img)
    if act:
        x, y, wd = act
        y += NEO_JUMP[phase] if phase < len(NEO_JUMP) else 0
        ImageDraw.Draw(img).text((x, y), active["text"], font=font, fill=NEO_COLOR,
                                 stroke_width=NEO_STROKE, stroke_fill=(0, 0, 0))
    return img


def word_font(size):
    f = ImageFont.truetype(str(WORD_FONT), size)
    f.set_variation_by_name("Black")
    return f


def draw_word(chunk, active, font, phase):
    """Только звучащее слово, по центру; не влезает в WORD_W - шрифт меньше."""
    img = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f, text = font, active["text"]
    if d.textlength(text, font=f) > WORD_W:
        f = word_font(int(WORD_SIZE * WORD_W / d.textlength(text, font=f)))
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=WORD_STROKE)
    x, y = (OUT_W - (r - l)) / 2 - l, WORD_Y - (b - t) / 2 - t
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((x + 4, y + 8), text, font=f, fill=(0, 0, 0, 150),
                            stroke_width=WORD_STROKE, stroke_fill=(0, 0, 0, 150))
    img = Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)), img)
    ImageDraw.Draw(img).text((x, y), text, font=f, fill=(255, 255, 255),
                             stroke_width=WORD_STROKE, stroke_fill=(0, 0, 0))
    return img


def burn_subtitles(video, audio, chunks, out):
    pill = SUB_STYLE in ("pill", "neo")  # оба стиля с «прыжком» звучащего слова
    font = {"pill": lambda: pill_font(PILL_SIZE), "neo": lambda: neo_font(NEO_SIZE),
            "word": lambda: word_font(WORD_SIZE)}.get(SUB_STYLE, lambda: ImageFont.truetype(FONT, FONT_SIZE))()
    draw = {"pill": draw_chunk_pill, "neo": draw_chunk_neo, "word": draw_word}.get(SUB_STYLE)
    events = []
    for c in chunks:
        for j, w in enumerate(c):
            end = c[j + 1]["s"] if j + 1 < len(c) else c[-1]["chunk_end"]
            events.append((c[0]["s"] if j == 0 else w["s"], end, c, w))
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
                            "-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                            str(out)], stdin=subprocess.PIPE)
    size = OUT_W * OUT_H * 3
    cache, n = {}, 0
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        t = n * FRAME + FRAME / 2
        ev = next((e for e in events if e[0] <= t < e[1]), None)
        if ev:
            phase = min(int((t - ev[3]["s"]) / FRAME), 3) if pill else 0  # дальше «прыжка» нет ни у pill, ни у neo
            key = (id(ev[2]), id(ev[3]), phase)
            if key not in cache:
                cache[key] = draw(ev[2], ev[3], font, max(phase, 0)) if draw \
                    else draw_chunk(ev[2], ev[3], font)
            frame = Image.frombuffer("RGB", (OUT_W, OUT_H), buf)
            frame.paste(cache[key], (0, 0), cache[key])
            buf = frame.tobytes()
        enc.stdin.write(buf)
        n += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()


def main():
    cfg_path = Path(sys.argv[1]).resolve()
    cfg = json.loads(cfg_path.read_text())
    global HOST_SIDE
    HOST_SIDE = cfg.get("host_side", HOST_SIDE)
    global GUEST_DARK
    GUEST_DARK = cfg.get("guest_hair", "dark") == "dark"
    global SUB_STYLE
    SUB_STYLE = cfg.get("sub_style", SUB_STYLE)
    global NEO_COLOR
    if SUB_STYLE == "neo_yellow":  # neo, но звучащее слово жёлтое (Орлов 2, вторая половина - новый ТТ)
        SUB_STYLE, NEO_COLOR = "neo", YELLOW
    global SILENCE_DB, SILENCE_MIN, MIN_PIECE  # концерт: шум зала выше -32 дБ, порог тишины свой
    SILENCE_DB, SILENCE_MIN = cfg.get("silence_db", SILENCE_DB), cfg.get("silence_min", SILENCE_MIN)
    MIN_PIECE = cfg.get("min_piece", MIN_PIECE)
    base = cfg_path.parent
    source = str(base / cfg["source"])
    global SOURCE
    SOURCE = source
    words = json.loads((base / cfg["words"]).read_text())
    ranges = cfg["ranges"]
    fixes = {k.lower(): v for k, v in cfg.get("fixes", {}).items()}
    host_words, keep_words = set(), set()
    for a, b in cfg.get("host_ranges", []):
        host_words.update(range(a, b + 1))
    for a, b in ranges:
        keep_words.update(range(a, b + 1))
    tmp = base / (Path(cfg["out"]).stem + "_tmp")
    tmp.mkdir(exist_ok=True)

    global KEEP_PAUSES  # "keep_pause": [[слово, слово], ...] - паузу между ними не вырезать
    KEEP_PAUSES = [(words[a]["e"], words[b]["s"]) for a, b in cfg.get("keep_pause", [])]
    pieces = split_by_silence(source, ranges_to_intervals(words, ranges, source, cfg.get("cut_at", {})),
                              [words[i]["s"] for i in keep_words],
                              [(words[i], words[i + 1]["s"]) for i in keep_words if i + 1 < len(words)])
    print(f"кусков: {len(pieces)}, длина: {sum(e - s for s, e in pieces):.1f} сек")

    spoken = [(words[i]["s"], words[i]["e"]) for i in sorted(keep_words)]
    det = detector()
    if cfg.get("faces"):
        load_refs(source, det, cfg["faces"])
    shots, trimmed_pieces, slivers = [], [], 0
    queue, tail = list(pieces), 0.0
    while queue:
        s, e = queue.pop(0)
        # внутри куска камера переключается, когда меняется говорящий
        raw = []
        for ts, te, speaker in speaker_turns(words, keep_words, host_words, s, e):
            raw += analyze_piece(source, det, ts, te, speaker)
        piece_shots, head, new_tail = trim_edge_slivers(raw, spoken)
        slivers += len(raw) - len(piece_shots)
        ps, pe = piece_shots[0]["s"], piece_shots[-1]["e"]
        if pe - ps < MIN_PIECE and queue and queue[0][0] - pe < 1.0:
            # после огрызка остался обрывок: две склейки подряд выглядят как лаг -
            # паузу до следующего куска не вырезаем, собираем их одним куском
            print(f"кусок {ps:.2f}-{pe:.2f} короче {MIN_PIECE} сек - склеен со следующим")
            queue[0] = (ps - head, queue[0][1])
            continue
        if pe - ps < MIN_PIECE - FRAME:
            print(f"ПРОВЕРИТЬ: кусок {ps:.2f}-{pe:.2f} короче {MIN_PIECE} сек")
        # огрызок на слове: звук целиком, картинку на это время даёт соседний план
        # (если в тех кадрах нет своей смены камеры - иначе режем вместе со звуком)
        if head and tail:  # огрызки по обе стороны стыка: картинку взять неоткуда
            print(f"ПРОВЕРИТЬ СТЫК: огрызки с двух сторон стыка {ps:.2f}, начало отрезано со звуком")
            head = 0.0
        if head and not (shots and not has_cut(source, shots[-1]["e"], shots[-1]["e"] + head)):
            print(f"ПРОВЕРИТЬ СТЫК: огрызок на слове {ps - head:.2f}-{ps:.2f} отрезан со звуком")
            head = 0.0
        if tail and has_cut(source, ps - tail, ps):
            print(f"ПРОВЕРИТЬ СТЫК: огрызок на слове {trimmed_pieces[-1][1] - tail:.2f} отрезан со звуком")
            trimmed_pieces[-1] = (trimmed_pieces[-1][0], trimmed_pieces[-1][1] - tail)
            tail = 0.0
        if head:
            shots[-1]["e"] += head  # предыдущий план идёт чуть дольше
            print(f"огрызок на слове {ps - head:.2f}-{ps:.2f}: звук целиком, картинка с прошлого плана")
        if tail:
            piece_shots[0]["s"] -= tail  # хвост прошлого куска: этот план начинается раньше
            print(f"огрызок на слове перед {ps:.2f}: звук целиком, картинка со следующего плана")
        piece_shots[0]["piece_start"] = True
        trimmed_pieces.append((ps - head, pe + new_tail))
        shots += piece_shots
        tail = new_tail
    if tail:  # конец ролика: следующего плана нет - режем со звуком
        trimmed_pieces[-1] = (trimmed_pieces[-1][0], trimmed_pieces[-1][1] - tail)
    pieces = trimmed_pieces
    print(f"огрызков другой камеры отрезано: {slivers}")
    shots = apply_framing(shots, cfg.get("framing", []), source, det)
    if "stage_torso" in cfg:  # комик в тёмной одежде и зала в кадре нет: 0 - не отсеивать лица
        global STAGE_TORSO
        STAGE_TORSO = cfg["stage_torso"]
    if cfg.get("track"):  # концерт: рамка плавно ведёт лицо, без зумов на склейках
        set_zoom(shots, False)
        shots = track_camera(shots, source, det)
    else:
        set_zoom(shots, cfg.get("punch_in", "auto"))
    shots = apply_cutaways(shots, cfg.get("cutaways", []), words, pieces, source, det)
    for a, b, top in cfg.get("caption_zones", []):  # титры шоу внизу: приблизить и взять верх
        for sh in shots:
            if sh["s"] < b and sh["e"] > a:
                sh["caption_bottom"], sh["caption_top"] = True, top
    (tmp / "shots.json").write_text(json.dumps(shots, indent=1, default=float))
    print("в кадре:", ", ".join(
        f"{sh['who']}{'*' if sh.get('cutaway') else ''}{'+' if sh['zoom'] > 1 else ''}" for sh in shots))
    t = 0.0
    for sh in shots:
        d = sh["e"] - sh["s"]
        if sh.get("auto_caption") and not sh.get("caption_bottom"):
            print(f"ПРОВЕРИТЬ: похоже на титр шоу {t:.1f}-{t + d:.1f} сек (исходник {sh['s']:.1f}-{sh['e']:.1f})")
        t += d
    if "--plan" in sys.argv:  # только план: без рендера
        return

    video = render_video(source, shots, tmp)
    audio = render_audio(source, pieces, tmp)
    chunks = subtitle_chunks(words, ranges, pieces, fixes, cfg.get("fix_words", {}))
    burn_subtitles(video, audio, chunks, base / cfg["out"])
    print("готово:", base / cfg["out"])


if __name__ == "__main__":
    main()
