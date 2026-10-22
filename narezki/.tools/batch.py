"""Пачка шортсов одной командой: конфиги -> рендер (параллельно) -> проверка стыков ->
музыка. Клод только пишет batch.json с диапазонами слов.

Запуск: venv/bin/python batch.py ../выпуск/batch.json [параллельно=1] [--plan - только длины, без рендера] [--music - только музыка] [--only=N]
batch.json: {"shorts": [{"name", "ranges": [[a, b, "h"|"g"]], "who"?, "fix_words"?}],
             "out"?: "часть 2"            - подпапка в готовые/ (по умолчанию сама готовые/),
             "music"?: "ремиксы/snowfall (slowed).mp3" - трек из музыка/ (у ролика тоже можно "music"),
             "music_lufs"?: -20           - громкость музыки, тише = меньше (-20 - слышно, но под голосом),
             "banner"?: false             - без баннера FloatUp (по умолчанию ставится, banner.py, копия в готовые/<out>/с баннером/),
             "prefix"?: "Самойлова",
             "host"?: [[сек, "big"|"left"|"right"], ...]   - образцы лица ведущей в этом исходнике,
             "sub_style"?: "pill"          - стиль субтитров на всю пачку (см. make_short.py),
             "people"?: {"имя": {"guest": [[сек, ...]], "guest_hair": "dark"|"light", "host_side": "left"|"right"}}}
  yt - название ролика для YouTube (коротко, без мата), им же называется файл.
  who - ключ из people (кто гость в этом ролике); mom: true - старый ключ для пачки 2.
Итог: готовые/<out>/ - ролики с музыкой с номером («12 - название.mp4»), без подпапок; без музыки - выпуск/без музыки/. Лог - выпуск/<batch>_log.txt.
"""
import json, shutil, subprocess, sys
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
ROOT = T.parent; READY = ROOT / "готовые" / spec.get("out", ""); RAW = ep / "без музыки"
for d in (READY, RAW): d.mkdir(parents=True, exist_ok=True)
FIX = {"жиган": "Джиган", "жигану": "Джигану", "жиганом": "Джиганом", "жигана": "Джигана"}
HOST = [[1664, "big"], [8643, "big"], [2610.8, "left"], [2813.5, "left"], [7265, "left"]]
OKSANA = {"guest": [[1586, "big"], [2833, "big"], [10053.5, "big"], [7265, "right"]]}
MOM = {"guest": [[1750, "big"], [8849, "big"], [6561, "big"]]}
prefix = spec.get("prefix", "Самойлова")
HOST = spec.get("host", HOST)
PEOPLE = {"oksana": OKSANA, "mom": {**MOM, "guest_hair": "light", "host_side": "right"}, **spec.get("people", {})}
log = open(ep / f"{spec_path.stem}_log.txt", "w")

def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=T)
    out = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                    if not any(x in l for x in ("setPreferableTarget", "Warning", "Fetching", "WARN")))
    return r.returncode, out

def numbered(title):
    """Имя готового ролика с номером: «12 - название.mp4». Уже был - тот же номер, новый - следующий."""
    nums = []
    for f in READY.glob("* - *.mp4"):
        n, _, rest = f.name.partition(" - ")
        if not n.isdigit(): continue
        if rest == f"{title}.mp4": return f.name
        nums.append(int(n))
    return f"{max(nums, default=0) + 1:02d} - {title}.mp4"

def mix(i, s, title):
    """Музыка и баннер поверх готового ролика (видео не пересобирается)."""
    rep = []
    vid = RAW / f"{title}.mp4"; mus = READY / numbered(title); ban = READY / "с баннером" / mus.name
    track = ROOT / "музыка" / s.get("music", spec.get("music", "ремиксы/snowfall (slowed).mp3"))
    code, out = sh([PY, "add_music.py", str(vid), str(track), str(mus), str(spec.get("music_lufs", -20))])
    if code: rep.append("!!! МУЗЫКА: " + out[-500:])
    if not s.get("banner", spec.get("banner", True)): return "\n".join(rep)
    code, out = sh([PY, "banner.py", str(mus), str(ban)]); rep.append(out)
    if code: rep.append("!!! БАННЕР: " + out[-500:])
    return "\n".join(rep)


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
    cfg = {"source": "source.mp4", "words": "words.json", "punch_in": "auto", "fixes": FIX,
           "out": str(RAW / f"{title}.mp4"),
           "ranges": [[a, b] for a, b, _ in s["ranges"]],
           "host_ranges": [[a, b] for a, b, w in s["ranges"] if w == "h"],
           "fix_words": s.get("fix_words", {}),
           "faces": {"host": HOST}}
    if spec.get("sub_style"): cfg["sub_style"] = spec["sub_style"]  # стиль субтитров на всю пачку
    cfg.update(s.get("cfg", {}))  # ручные правки ролика: punch_in, framing (камера на нужного человека) и т.п.
    p = PEOPLE[s.get("who", "mom" if s.get("mom") else "oksana")]
    cfg["faces"]["guest"] = p["guest"]
    cfg.update({k: v for k, v in p.items() if k != "guest"})
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
