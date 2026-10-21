"""Пачка шортсов из стендапа одной командой: конфиги -> чистка речи -> рендер по одному ->
проверка стыков -> музыка. Клод только пишет batch.json с диапазонами слов.

Запуск: venv/bin/python batch.py ПАПКА_ВЫПУСКА/batch.json [--plan - только длины] [--music - только музыка] [--only=N]
batch.json: {"shorts": [{"name", "ranges": [[a, b, "g"]], "yt", "fix_words"?, "cfg"?, "music"?}],
             "out"?: "Комик"              - подпапка в готовые/,
             "music"?: "трек.mp3"         - трек из НАРЕЗКИ/музыка/ (у ролика тоже можно "music");
                                            нет трека - ролики без музыки,
             "music_lufs"?: -20           - громкость музыки относительно голоса,
             "faces"?: [[сек, "big"], ...] - 2-3 момента исходника, где комик крупно (не обязательно)}
  yt - название ролика для YouTube (коротко, без мата, от третьего лица), им же называется файл.
  ranges - диапазоны индексов слов из words.json; "g" - говорит комик.
  cfg - правки ролика для make_short.py: fix_words, keep_pause, framing и т.п.
Папка нарезок - $NAREZKI_HOME или ~/Нарезки. Итог: готовые/<out>/ и готовые/<out>/с музыкой/.
Лог - ПАПКА_ВЫПУСКА/<batch>_log.txt.
"""
import json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

T = Path(__file__).resolve().parent
PY = str(T / "venv/bin/python")
spec_path = Path(sys.argv[1]).resolve(); ep = spec_path.parent
PLAN = "--plan" in sys.argv
MUSIC_ONLY = "--music" in sys.argv  # только заново положить музыку и баннер на готовые ролики
ONLY = [int(a[7:]) for a in sys.argv[2:] if a.startswith("--only=")]  # --only=0 - собрать только этот ролик
args = [a for a in sys.argv[2:] if a not in ("--plan", "--music") and not a.startswith("--only=")]
par = int(args[0]) if args else 1  # Мак на 8 ГБ: больше одного ролика за раз - зависает
spec = json.load(open(spec_path))
ROOT = Path(os.environ.get("NAREZKI_HOME", Path.home() / "Нарезки"))
READY = ROOT / "готовые" / spec.get("out", "")
for d in (READY, READY / "с музыкой"): d.mkdir(parents=True, exist_ok=True)
FIX = {}
prefix = spec.get("prefix", "Стендап")
FACES = spec.get("faces", [])
# стендап: шум зала выше обычного порога тишины, рамка плавно ведёт комика, без зумов
STANDUP = {"silence_db": -25, "silence_min": 0.15, "min_piece": 0.5, "track": True, "punch_in": False}
log = open(ep / f"{spec_path.stem}_log.txt", "w")

def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=T)
    out = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                    if not any(x in l for x in ("setPreferableTarget", "Warning", "Fetching", "WARN")))
    return r.returncode, out

def mix(i, s, title):
    """Музыка поверх готового ролика (видео не пересобирается)."""
    name = s.get("music", spec.get("music"))
    if not name:
        return ""
    track = ROOT / "музыка" / name
    if not track.exists():
        return f"!!! МУЗЫКА: нет файла {track}"
    vid = READY / f"{title}.mp4"; mus = READY / "с музыкой" / vid.name
    code, out = sh([PY, "add_music.py", str(vid), str(track), str(mus), str(spec.get("music_lufs", -20))])
    return "!!! МУЗЫКА: " + out[-500:] if code else ""


WORDS = None

def split_gaps(ranges, gap):
    """Режет кусок там, где между словами пауза дольше gap сек (на концерте шум зала
    громче порога тишины, silencedetect паузы не видит)."""
    global WORDS
    if WORDS is None:
        w = json.load(open(ep / "words.json")); WORDS = w if isinstance(w, list) else w["words"]
    out = []
    for a, b, who in ranges:
        st = a
        for k in range(a, b):
            if WORDS[k + 1]["s"] - WORDS[k]["e"] > gap:
                out.append([st, k, who]); st = k + 1
        out.append([st, b, who])
    return out


def one(i_s):
    i, s = i_s
    title = s.get("yt") or f"{prefix} - {s['name']}"  # yt - название для YouTube, им же называется файл
    gap = s.get("max_gap", spec.get("max_gap"))  # "max_gap": 0.4 - вырезать паузы между словами
    if gap: s = {**s, "ranges": split_gaps(s["ranges"], gap)}
    cfg = {"source": "source.mp4", "words": "words.json", "fixes": FIX,
           "out": str(READY / f"{title}.mp4"),
           "ranges": [[a, b] for a, b, _ in s["ranges"]],
           "host_ranges": [],
           "fix_words": s.get("fix_words", {}),
           **STANDUP}
    if FACES:
        cfg["faces"] = {"host": FACES, "guest": FACES}
    cfg.update(s.get("cfg", {}))  # ручные правки ролика: keep_pause, framing и т.п.
    cp = ep / f"{spec_path.stem}_{i:02d}.json"
    rep = [f"######## {title}"]
    if MUSIC_ONLY:
        return "\n".join(rep + [mix(i, s, title)])
    json.dump(cfg, open(cp, "w"), ensure_ascii=False, indent=1)
    if spec.get("clean", True) and s.get("clean", True):  # паразиты, запинки, оговорки
        code, out = sh([PY, "tidy.py", str(cp)]); rep.append(out)
    code, out = sh([PY, "make_short.py", str(cp)] + (["--plan"] if PLAN else [])); rep.append(out)
    if PLAN: return "\n".join(rep)
    if code: return "\n".join(rep + ["!!! РЕНДЕР УПАЛ"])
    code, out = sh([PY, "check_cuts.py", str(cp)]); rep.append(out)
    shutil.rmtree(ep / f"{title}_tmp", ignore_errors=True)  # рабочие кадры ~150 МБ на ролик
    rep.append(mix(i, s, title))
    return "\n".join(rep)

with ThreadPoolExecutor(par) as ex:
    for r in ex.map(one, [(i, x) for i, x in enumerate(spec["shorts"]) if not ONLY or i in ONLY]):
        log.write(r + "\n"); log.flush()
        head = [l for l in r.splitlines() if l.startswith(("####", "кусков", "!!!", "готово"))]
        print("\n".join(head), flush=True)
print("ВСЁ ГОТОВО")
