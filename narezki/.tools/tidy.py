"""Чистка речи в конфиге ролика перед сборкой: tidy.py config.json

1. Слова-паразиты (ну, вот, типа, получается, как бы...) и повторы слов вырезаются,
   только если вокруг слова есть пауза. Слитно сказанные оставляем: иначе нож
   задевает соседнее слово и оно звучит обрезанным.
2. Запинки «эээ», «ммм», которых нет в words.json (Whisper их выкидывает), ищутся
   второй, дословной расшифровкой каждого куска и вырезаются по самой тихой точке.
   Так же вырезаются оговорки: «мы в большой... ты в большой опасности» - остаётся
   то, что человек хотел сказать (в words.json Whisper уже записал только итог).
Конфиг переписывается на месте: ranges режутся на части, точки реза - в cut_at.
"no_cut": [индексы слов] в cfg ролика - после этих слов паузы не вырезать.
"""
import difflib
import json
import re
import sys
from pathlib import Path

import mlx_whisper
import numpy as np

import make_short as m

MODEL = "mlx-community/whisper-large-v3-turbo"
CUT_GAP = 12         # дБ: для вырезания оговорки хватает провала громкости, полной тишины может не быть
GAP = 22             # дБ: точка реза должна быть настолько тише самого слова - тогда это пауза, слово не задеваем
FILLER1 = {"ну", "вот", "типа", "получается", "короче", "знаешь", "слушай", "таки", "допустим"}
FILLER2 = {("как", "бы"), ("то", "есть"), ("это", "самое"), ("как", "раз")}
HES = re.compile(r"^(э+м*|м+|а{2,}|хм+|эм+)$")
PROMPT = "Дословно, со всеми запинками и повторами: ээ... ну, мм... я, я пошла... мы в доме... то есть он в доме. Э-э, это самое, эм."


def norm(w):
    return w.lower().strip(" ,.!?…«»\"-").replace(" ", "")


def quiet_db(src, lo, hi):
    lo, hi = min(lo, hi), max(lo, hi)
    if hi - lo < 0.04:
        lo, hi = lo - 0.02, hi + 0.02
    return min(m.loudness(src, lo, hi), key=lambda x: x[1])


def fillers(words, src, a, b):
    """Индексы слов-паразитов внутри [a, b], которые можно вырезать чисто."""
    cand, i = [], a
    while i <= b:
        if i < b and (norm(words[i]["w"]), norm(words[i + 1]["w"])) in FILLER2:
            cand.append((i, i + 1)); i += 2; continue
        w = norm(words[i]["w"])
        if w in FILLER1 or (i > a and w == norm(words[i - 1]["w"]) and len(w) > 1):
            cand.append((i, i))
        i += 1
    drop = set()
    for x, y in cand:
        peak = max(v for _, v in m.loudness(src, words[x]["s"], words[y]["e"]))
        before = quiet_db(src, words[x - 1]["e"] - 0.05, words[x]["s"] + 0.05)[1] if x > a else -99
        after = quiet_db(src, words[y]["e"] - 0.05, words[y + 1]["s"] + 0.05)[1] if y < b else -99
        dur = words[y]["e"] - words[x]["s"]
        left = words[x]["s"] - words[a]["s"]; right = words[b]["e"] - words[y]["e"]
        if max(before, after) <= peak - GAP and (x == a or left >= m.MIN_PIECE) and (y == b or right >= m.MIN_PIECE):
            drop |= set(range(x, y + 1))
    return drop


def hesitations(words, src, a, b):
    """Лишнее внутри [a, b]: запинки, вставки («ну», «вот с...») и оговорки - то, что звучит,
    но чего нет в words.json (обычная расшифровка их выкидывает, дословная - пишет).
    Возвращает [(i, t_end, t_start)]: резать после слова i, конец куска t_end, начало следующего t_start.
    Точки реза берутся по дословной расшифровке: её таймкоды в таких местах точнее."""
    s, e = words[a]["s"] - 1.0, words[b]["e"] + 0.5  # секунда контекста: так Whisper пишет дословнее
    audio = m.pcm16k(src, s, e - s) / 32768.0
    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="ru", word_timestamps=True,
                               initial_prompt=PROMPT, condition_on_previous_text=False, verbose=None)
    vb = [w for seg in r["segments"] for w in seg.get("words", [])]
    vt = [re.sub(r"[^а-яёa-z0-9]", "", w["word"].lower()) for w in vb]
    keep_k = [k for k, t in enumerate(vt) if t]
    vb, vt = [vb[k] for k in keep_k], [vt[k] for k in keep_k]
    ct = [re.sub(r"[^а-яёa-z0-9]", "", words[i]["w"].lower()) for i in range(a, b + 1)]
    stem = lambda t: t[:5]  # «обвешанный»/«обвешенный», «оружии»/«оружие» - одно слово
    v2c = {}
    sm = difflib.SequenceMatcher(None, [stem(t) for t in vt], [stem(t) for t in ct], autojunk=False)
    for blk in sm.get_matching_blocks():
        for d in range(blk.size):
            v2c[blk.a + d] = blk.b + d
    # что выкинуть из дословной: слова без пары в обычной расшифровке и запинки
    bad = {k for k in range(len(vt)) if k not in v2c or HES.match(vt[k])}
    # оговорка = повтор: «мы в большой... ты в большой опасности», «я пошла, я пошла»:
    # первая попытка (и слово перед ней, если оно другое - «мы»/«ты») тоже лишняя
    for k in range(1, len(vt)):
        for q in range(k + 1, len(vt)):
            if vb[q]["start"] - vb[k]["start"] > 3:
                break
            L = 0
            while q + L < len(vt) and k + L < q and vt[k + L] == vt[q + L]:
                L += 1
            if L >= 2 or (L == 1 and len(vt[k]) > 3 and q == k + 1):
                first = k - 1 if q - k >= 2 and vt[k - 1] != vt[q - 1] else k
                last = q - 1 if first == k - 1 else q
                bad |= set(range(first, last))
                break
    out, k = [], 0
    while k < len(vt):
        if k not in bad:
            k += 1; continue
        k2 = k
        while k2 + 1 < len(vt) and k2 + 1 in bad:
            k2 += 1
        prev = next((x for x in range(k - 1, -1, -1) if x not in bad and x in v2c), None)
        nxt = next((x for x in range(k2 + 1, len(vt)) if x not in bad and x in v2c), None)
        if prev is not None and nxt is not None and v2c[nxt] == v2c[prev] + 1:
            out.append((a + v2c[prev], s + vb[prev]["end"], s + vb[k]["start"],
                        s + vb[k2]["end"], s + vb[nxt]["start"]))
        k = k2 + 1
    return out


def voiced_gaps(words, src, a, b):
    """Промежутки между соседними словами, где звучит голос, но слов в расшифровке нет:
    оговорки («мы в большой... ты в большой опасности») и протяжные «эээ»."""
    out = []
    for i in range(a, b):
        g0, g1 = words[i]["e"], words[i + 1]["s"]
        if g1 - g0 < 0.35:
            continue
        lv = m.loudness(src, g0, g1)
        peak = max(max(v for _, v in m.loudness(src, words[i]["s"], words[i]["e"])), max(v for _, v in lv))
        if sum(v > peak - 15 for _, v in lv) / len(lv) > 0.2:
            out.append((i, g0, g0, g1, g1))
    return out


def main():
    cp = Path(sys.argv[1]); cfg = json.load(open(cp)); base = cp.parent
    words = json.load(open(base / cfg["words"])); src = str(base / cfg["source"])
    cut = cfg.setdefault("cut_at", {}); cut.setdefault("start", {}); cut.setdefault("end", {})
    new, n_fill, n_hes = [], 0, 0
    no_cut = set(cfg.get("no_cut", []))  # слова, после которых не резать: склейка на том же плане выглядит как лаг
    keep = set(cfg.get("keep_words", []))  # индексы слов, которые не паразиты по смыслу ("четыре типа")
    for a, b in cfg["ranges"]:
        drop = fillers(words, src, a, b) - keep; n_fill += len(drop)
        pieces, cur = [], None
        for i in range(a, b + 1):
            if i in drop:
                if cur: pieces.append(cur); cur = None
            elif cur: cur[1] = i
            else: cur = [i, i]
        if cur: pieces.append(cur)
        for pa, pb in pieces:
            splits = []
            splits = {}  # слово -> (конец, начало); одно место реза на слово, берём самый широкий вырез
            for i, e0, h0, h1, s1 in hesitations(words, src, pa, pb) + voiced_gaps(words, src, pa, pb):
                if not pa <= i < pb or i in no_cut:
                    continue
                if any(c.isdigit() for c in words[i]["w"]):
                    continue  # Whisper даёт числу короткий таймкод: «911» звучит дольше, нож срезал «один-один»
                # конец куска - в самой тихой точке между словом и лишним, начало - между лишним и словом
                # окна с запасом, но не заходя за найденное лишнее: таймкоды и там, и там врут
                end, de = quiet_db(src, e0 - 0.04, min(max(h0, e0) + 0.35, h1))
                start, ds = quiet_db(src, max(min(h1, s1) - 0.5, end + 0.06), s1 + 0.04)
                peak = max(v for _, v in m.loudness(src, min(h0, h1 - 0.05), max(h1, h0 + 0.05)))
                if start <= end + 0.06 or max(de, ds) > peak - CUT_GAP:
                    continue  # нет провала громкости на краях - заденем слово, лучше оставить
                if i not in splits or start - end > splits[i][1] - splits[i][0]:
                    splits[i] = (round(end, 3), round(start, 3))
            splits = [(i, e_, s_) for i, (e_, s_) in sorted(splits.items())]
            # не оставлять обрывков короче MIN_PIECE: «просто» между двумя вырезами дёргает картинку
            kept, prev_start = [], words[pa]["s"]
            for k, (i, e_, s_) in enumerate(splits):
                nxt_end = splits[k + 1][1] if k + 1 < len(splits) else words[pb]["e"]
                if e_ - prev_start >= m.MIN_PIECE and nxt_end - s_ >= m.MIN_PIECE:
                    kept.append((i, e_, s_)); prev_start = s_
            splits = kept
            lo = pa
            for i, end, start in splits:
                new.append([lo, i])  # ручные точки реза из batch.json (после проверки на слух) главнее
                cut["end"].setdefault(str(i), end); cut["start"].setdefault(str(i + 1), start)
                lo = i + 1; n_hes += 1
            new.append([lo, pb])
    cfg["ranges"] = new
    json.dump(cfg, open(cp, "w"), ensure_ascii=False, indent=1)
    print(f"чистка: паразитов вырезано {n_fill}, запинок {n_hes}")


if __name__ == "__main__":
    main()
