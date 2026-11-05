"""Pattern drill: how well each ingredient tells growth from decay over the next 24 h, across every candidate low
(ingredients.csv from `ingredients.py measure`). Writes ingredients_score.csv and ingredients.json (study
folder and rk.paths.data extra/pattern-drill), and adds each deck case's ingredients to the deck manifest.

Per ingredient: terciles over all lows; in each, the share that grew (ASCAT category up at +24 h), decayed
(category down) and the mean pressure change. The signal is the growth share in the top tercile minus the
bottom one, taken within lows of the same starting category (none / gale / storm; a low already at HF
cannot grow) and averaged with their counts as weights, so a low being weak now does not pass for a
favourable ingredient. 90% interval: 2000 bootstrap draws resampling whole days (lows on one day are not
independent). Verdict: strong if |signal| >= 15 points and the interval excludes 0, weak if the interval
excludes 0, none otherwise.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
import ingredients as I  # noqa: E402

KEYS = I.ING + ["peak0"]
RNG = np.random.default_rng(7)


def load():
    rows = list(csv.DictReader(open(I.ROOT / "ingredients.csv")))
    num = lambda v: float(v) if v not in ("", "None", "nan") else np.nan
    d = {k: np.array([num(r[k]) for r in rows]) for k in KEYS + ["cat0", "cat24", "hpa0", "hpa24"]}
    d["jet_pos"] = np.array([r["jet_pos"] for r in rows])
    d["day"] = np.array([r["t0"][:8] for r in rows])
    d["key"] = [(r["basin"], r["t0"], round(float(r["lat"]), 2), round(float(r["lon"]), 2)) for r in rows]
    d["grew"] = (d["cat24"] > d["cat0"]).astype(float)
    d["decayed"] = (d["cat24"] < d["cat0"]).astype(float)
    d["dp"] = d["hpa24"] - d["hpa0"]
    return d


def signal(x, grew, cat0, idx=None):
    """Growth share, top minus bottom tercile, within starting categories 0-2 (count-weighted)."""
    if idx is not None:
        x, grew, cat0 = x[idx], grew[idx], cat0[idx]
    tot, w = 0.0, 0.0
    for c in (0, 1, 2):
        m = (cat0 == c) & np.isfinite(x)
        if m.sum() < 15:
            continue
        lo, hi = np.nanpercentile(x[m], [100 / 3, 200 / 3])
        b, t = m & (x <= lo), m & (x > hi)
        if b.sum() < 3 or t.sum() < 3:
            continue
        tot += m.sum() * (grew[t].mean() - grew[b].mean())
        w += m.sum()
    return 100 * tot / w if w else np.nan


def main():
    d = load()
    n = len(d["grew"])
    days = np.unique(d["day"])
    by_day = {k: np.where(d["day"] == k)[0] for k in days}
    out, table = [], []
    for k in KEYS:
        x = d[k]
        ok = np.isfinite(x)
        cuts = np.nanpercentile(x, [100 / 3, 200 / 3])
        terc = np.digitize(x, cuts)
        grow = [100 * d["grew"][ok & (terc == i)].mean() for i in range(3)]
        decay = [100 * d["decayed"][ok & (terc == i)].mean() for i in range(3)]
        dp = [float(np.nanmean(d["dp"][ok & (terc == i)])) for i in range(3)]
        s = signal(x, d["grew"], d["cat0"])
        boots = []
        for _ in range(2000):
            pickd = RNG.choice(days, len(days))
            idx = np.concatenate([by_day[p] for p in pickd])
            boots.append(signal(x, d["grew"], d["cat0"], idx))
        lo, hi = np.nanpercentile(boots, [5, 95])
        excl = lo > 0 or hi < 0
        verdict = "strong" if excl and abs(s) >= 15 else "weak" if excl else "none"
        name, units = I.NAMES[k]
        rec = {"key": k, "name": name, "units": units, "n": int(ok.sum()), "cuts": [round(float(c), 3) for c in cuts],
               "grow": [round(g, 1) for g in grow], "decay": [round(v, 1) for v in decay],
               "dp": [round(v, 1) for v in dp], "signal": round(float(s), 1), "lo": round(float(lo), 1),
               "hi": round(float(hi), 1), "verdict": verdict, "favour": 1 if s > 0 else -1}
        out.append(rec)
        table.append([name, units, int(ok.sum())] + rec["cuts"] + grow + decay + dp + [rec["signal"], rec["lo"], rec["hi"], verdict])
    jp = {}
    for cls in ("left exit", "right entrance", "other", "weak jet"):
        m = d["jet_pos"] == cls
        if m.sum():
            jp[cls] = {"n": int(m.sum()), "grow": round(100 * d["grew"][m].mean(), 1),
                       "decay": round(100 * d["decayed"][m].mean(), 1), "dp": round(float(np.nanmean(d["dp"][m])), 1)}
    res = {"n": n, "days": len(days), "base_grow": round(100 * d["grew"].mean(), 1),
           "base_decay": round(100 * d["decayed"].mean(), 1), "ingredients": out, "jet_pos": jp}
    for p in (HERE / "ingredients.json", I.ROOT / "ingredients.json"):
        p.write_text(json.dumps(res, indent=1))
    with open(HERE / "ingredients_score.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ingredient", "units", "n", "cut1", "cut2", "grow_lo", "grow_mid", "grow_hi", "decay_lo",
                    "decay_mid", "decay_hi", "dp_lo", "dp_mid", "dp_hi", "signal_pts", "ci90_lo", "ci90_hi", "verdict"])
        w.writerows(table)
    print("lows", n, "days", len(days), "grew %.0f%% decayed %.0f%%" % (res["base_grow"], res["base_decay"]))
    for r in out:
        print("%-28s n %4d  grow by tercile %5.1f %5.1f %5.1f  dp %5.1f %5.1f %5.1f  signal %+5.1f [%+5.1f, %+5.1f] %s"
              % (r["name"], r["n"], *r["grow"], *r["dp"], r["signal"], r["lo"], r["hi"], r["verdict"]))
    for cls, v in jp.items():
        print("jet %-15s n %4d grew %5.1f decayed %5.1f dp %5.1f" % (cls, v["n"], v["grow"], v["decay"], v["dp"]))
    add_to_manifest(d, res)


def add_to_manifest(d, res, deck=HERE / "page" / "deck"):
    """Each deck case's start-time ingredients and their tercile (0 low, 1 mid, 2 high) -> manifest."""
    mp = deck / "manifest.json"
    if not mp.exists():
        return
    m = json.loads(mp.read_text())
    keyrows = {r["id"]: r for r in csv.DictReader(open(I.ROOT / "key.csv"))}
    index = {k: i for i, k in enumerate(d["key"])}
    hit = 0
    for c in m["cases"]:
        r = keyrows[c["id"]]
        i = index.get((r["basin"], r["t0"], round(float(r["lat0"]), 2), round(float(r["lon0"]), 2)))
        if i is None:
            continue
        ing = {"jet_pos": str(d["jet_pos"][i])}
        for g in res["ingredients"]:
            v = d[g["key"]][i]
            if np.isfinite(v):
                ing[g["key"]] = [round(float(v), 2), int(np.digitize(v, g["cuts"]))]
        c["ing"] = ing
        hit += 1
    m["ingredients"] = res
    mp.write_text(json.dumps(m, separators=(",", ":")))
    print("manifest: ingredients for", hit, "of", len(m["cases"]), "cases")


if __name__ == "__main__":
    main()
