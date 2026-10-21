"""Печать предложений с индексами первого слова: sents.py words.json a-b [a-b ...]"""
import json, sys
w = json.load(open(sys.argv[1]))
for r in sys.argv[2:]:
    a, b = map(int, r.split('-'))
    print(f"## {r}")
    cur, st = [], a
    for i in range(a, b + 1):
        if not cur: st = i
        cur.append(w[i]['w'].strip())
        if w[i]['w'].rstrip()[-1:] in '.?!' or i == b:
            print(f"{st}-{i} {' '.join(cur)}"); cur = []
