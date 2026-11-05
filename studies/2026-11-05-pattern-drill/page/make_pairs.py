"""Contrasting pairs: deck/pairs.json.

Two lows that started in the same category, with ingredient vectors (standardized, keys from
manifest.ingredients.ingredients, value = case.ing[key][0]) among the closest in the deck, but where one grew
over 24 h and the other held or decayed. Grew = the category went up AND the peak rose by the dead band or more
(manifest.ingredients.dead_band_kt, 5 kt), the same rule as the ingredient statistics. Up to 40 pairs, each case
used at most twice; benchmark cases (make_bench.py) are left out.

    python3 make_pairs.py
"""
import json
import math
from pathlib import Path

from make_bench import select as bench_select

here = Path(__file__).resolve().parent
MAX_PAIRS, MAX_USE, N_DIFF = 40, 2, 3


def grew(c, band):
    return c["t24"]["cat"] > c["t0"]["cat"] and c["ing"]["dpeak"] >= band


def main():
    m = json.loads((here / "deck" / "manifest.json").read_text())
    ing = m["ingredients"]
    band = ing["dead_band_kt"]
    meta = {i["key"]: i for i in ing["ingredients"]}
    keys = list(meta)
    bench = {c["id"] for c in bench_select(m)}
    cases = [c for c in m["cases"] if c["id"] not in bench and c.get("ing") and all(c["ing"].get(k) for k in keys)]
    stat = {}
    for k in keys:
        v = [c["ing"][k][0] for c in cases]
        mu = sum(v) / len(v)
        sd = math.sqrt(sum((x - mu) ** 2 for x in v) / len(v)) or 1.0
        stat[k] = (mu, sd)
    z = {c["id"]: [(c["ing"][k][0] - stat[k][0]) / stat[k][1] for k in keys] for c in cases}
    cand = []
    for i, a in enumerate(cases):
        for b in cases[i + 1:]:
            if a["t0"]["cat"] != b["t0"]["cat"] or grew(a, band) == grew(b, band):
                continue
            d = math.sqrt(sum((x - y) ** 2 for x, y in zip(z[a["id"]], z[b["id"]])))
            cand.append((d, a["id"], b["id"]))
    cand.sort()
    byid = {c["id"]: c for c in cases}
    used, pairs = {}, []
    for d, ia, ib in cand:
        if len(pairs) >= MAX_PAIRS:
            break
        if used.get(ia, 0) >= MAX_USE or used.get(ib, 0) >= MAX_USE:
            continue
        used[ia] = used.get(ia, 0) + 1
        used[ib] = used.get(ib, 0) + 1
        # which side is A alternates, so "A grew" is not always the answer
        g, h = (ia, ib) if grew(byid[ia], band) else (ib, ia)
        a, b = (g, h) if len(pairs) % 2 == 0 else (h, g)
        order = sorted(range(len(keys)), key=lambda j: -abs(z[a][j] - z[b][j]))[:N_DIFF]
        diff = [{"key": keys[j], "name": meta[keys[j]]["name"], "units": meta[keys[j]]["units"],
                 "a": byid[a]["ing"][keys[j]][0], "b": byid[b]["ing"][keys[j]][0],
                 "z": round(z[a][j] - z[b][j], 2)} for j in order]
        pairs.append({"a": a, "b": b, "grew": "a" if a == g else "b", "start": byid[a]["t0"]["cat"],
                      "dist": round(d, 2), "diff": diff})
    out = {"version": 1, "dead_band_kt": band, "keys": keys, "pairs": pairs}
    (here / "deck" / "pairs.json").write_text(json.dumps(out, separators=(",", ":")))
    print(len(pairs), "pairs from", len(cand), "candidates; distance %.2f to %.2f; cases used %d; start cats %s" % (
        pairs[0]["dist"], pairs[-1]["dist"], len(used), sorted({p["start"] for p in pairs})))


if __name__ == "__main__":
    main()
