"""Pattern drill: how well each ingredient tells growth from decay over the next 24 h, across every candidate low
(ingredients.csv from `ingredients.py measure`). Writes ingredients_score.csv and ingredients.json (study
folder and rk.paths.data extra/pattern-drill), and adds each deck case's ingredients to the deck manifest.

Version 2 (after the expert review of 2026-11-05):
- Outcome with a dead band: grew = category up AND ASCAT peak up >= DEAD kt; decayed = category down AND peak
  down >= DEAD kt; anything else held. A 2 kt crossing of a category line is ASCAT noise, not growth.
- Everything is compared within the starting category (none / gale / storm / HF): terciles are cut within it,
  and the bars on the page are per starting category, so how strong the low is now never passes for an
  ingredient.
- Two signals per ingredient: growth (top minus bottom third, lows that can grow: none, gale, storm) and decay
  (top minus bottom third, lows that can decay: gale, storm, HF), each count-weighted over the categories.
  99% interval from 2000 bootstrap draws of whole days (lows on one day are not independent; 99% because ten
  ingredients are tested). Verdict: strong if |signal| >= 15 points and the interval excludes 0, weak if the
  interval excludes 0, none otherwise.
- One number per case instead of a vote: logistic models of growth and of decay on the starting category, the
  gap to the next category line, and the ingredients, fitted with 10-fold cross-validation by contiguous day
  blocks. Each low's chance comes from the fold that did not see it. Skill = Brier skill score against the
  per-category base rate.
- Persistence and base rates per starting category, so the game can show what "no change" would have scored.
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

DEAD = 5.0                       # kt: smaller peak changes count as held
EDGES = np.array([34.0, 48.0, 64.0])
KEYS = I.ING
RNG = np.random.default_rng(7)
DRAWS = 2000
FOLDS = 10
CATS = ["none", "gale", "storm", "HF"]


def load():
    rows = list(csv.DictReader(open(I.ROOT / "ingredients.csv")))
    num = lambda v: float(v) if v not in ("", "None", "nan") else np.nan
    d = {k: np.array([num(r.get(k, "")) for r in rows]) for k in KEYS + ["peak0", "peak24", "cat0", "cat24", "hpa0", "hpa24"]}
    d["jet_pos"] = np.array([r["jet_pos"] for r in rows])
    d["basin"] = np.array([r["basin"] for r in rows])
    d["day"] = np.array([r["t0"][:8] for r in rows])
    d["key"] = [(r["basin"], r["t0"], round(float(r["lat"]), 2), round(float(r["lon"]), 2)) for r in rows]
    dpk = d["peak24"] - d["peak0"]
    d["dpeak"] = dpk
    d["grew"] = ((d["cat24"] > d["cat0"]) & (dpk >= DEAD)).astype(float)
    d["decayed"] = ((d["cat24"] < d["cat0"]) & (dpk <= -DEAD)).astype(float)
    d["grew_cat"] = (d["cat24"] > d["cat0"]).astype(float)
    d["dp"] = d["hpa24"] - d["hpa0"]
    c = d["cat0"].astype(int)
    up = np.where(c < 3, EDGES[np.minimum(c, 2)], np.nan)
    down = np.where(c > 0, EDGES[np.maximum(c - 1, 0)], np.nan)
    d["gap_up"] = up - d["peak0"]          # kt to the next category line
    d["gap_down"] = d["peak0"] - down      # kt above the line below
    return d


def cuts_by_cat(x, cat0):
    """Tercile cuts within each starting category (pooled cuts where a category has under 15 lows)."""
    pooled = np.nanpercentile(x, [100 / 3, 200 / 3])
    out = {}
    for c in range(4):
        m = (cat0 == c) & np.isfinite(x)
        out[c] = np.nanpercentile(x[m], [100 / 3, 200 / 3]) if m.sum() >= 15 else pooled
    return out


def terc(x, cat0, cuts):
    t = np.full(len(x), -1)
    for c in range(4):
        m = (cat0 == c) & np.isfinite(x)
        t[m] = np.digitize(x[m], cuts[c])
    return t


def signal(x, y, cat0, cats, idx=None):
    """Outcome share, top minus bottom third within each starting category in cats (count-weighted), points."""
    if idx is not None:
        x, y, cat0 = x[idx], y[idx], cat0[idx]
    tot = w = 0.0
    for c in cats:
        m = (cat0 == c) & np.isfinite(x)
        if m.sum() < 15:
            continue
        lo, hi = np.nanpercentile(x[m], [100 / 3, 200 / 3])
        b, t = m & (x <= lo), m & (x > hi)
        if b.sum() < 3 or t.sum() < 3:
            continue
        tot += m.sum() * (y[t].mean() - y[b].mean())
        w += m.sum()
    return 100 * tot / w if w else np.nan


def boot(fn, days, by_day):
    out = []
    for _ in range(DRAWS):
        pickd = RNG.choice(days, len(days))
        out.append(fn(np.concatenate([by_day[p] for p in pickd])))
    return np.nanpercentile(out, [0.5, 99.5])


def verdict(s, lo, hi):
    excl = lo > 0 or hi < 0
    return "strong" if excl and abs(s) >= 15 else "weak" if excl else "none"


# ---------------------------------------------------------------- logistic chance of growth / decay
def logit_fit(X, y, l2=1.0, iters=50):
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1:]]
        h = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(h, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def design(d, idx, feats, mu=None, sd=None):
    cols = [np.ones(len(idx))]
    for c in (1, 2):
        cols.append((d["cat0"][idx] == c).astype(float))
    raw = np.column_stack([d[f][idx] for f in feats]) if feats else np.zeros((len(idx), 0))
    if mu is None:
        mu, sd = np.nanmean(raw, 0), np.nanstd(raw, 0) + 1e-9
    z = np.nan_to_num((raw - mu) / sd)          # a missing ingredient counts as typical
    return np.column_stack(cols + [z]), mu, sd


def cv_chance(d, y, rows, feats):
    """Out-of-fold chance for each row; folds = contiguous blocks of days."""
    days = np.unique(d["day"][rows])
    fold_of_day = {dd: i * FOLDS // len(days) for i, dd in enumerate(days)}
    fold = np.array([fold_of_day[dd] for dd in d["day"][rows]])
    p = np.full(len(rows), np.nan)
    for k in range(FOLDS):
        tr, te = rows[fold != k], rows[fold == k]
        Xtr, mu, sd = design(d, tr, feats)
        w = logit_fit(Xtr, y[tr])
        Xte, _, _ = design(d, te, feats, mu, sd)
        p[fold == k] = 1 / (1 + np.exp(-Xte @ w))
    return p


def base_by_cat(d, y, rows):
    """Out-of-fold per-category base rate (the reference forecast)."""
    days = np.unique(d["day"][rows])
    fold_of_day = {dd: i * FOLDS // len(days) for i, dd in enumerate(days)}
    fold = np.array([fold_of_day[dd] for dd in d["day"][rows]])
    p = np.full(len(rows), np.nan)
    for k in range(FOLDS):
        tr, te = rows[fold != k], rows[fold == k]
        for c in range(4):
            m = d["cat0"][te] == c
            mt = d["cat0"][tr] == c
            p[np.where(fold == k)[0][m]] = y[tr][mt].mean() if mt.any() else y[tr].mean()
    return p


def bss(p, ref, y):
    return 1 - np.mean((p - y) ** 2) / np.mean((ref - y) ** 2)


def model(d, y, rows, feats, gapkey, days, by_day):
    allf = [gapkey] + feats
    p = cv_chance(d, y, rows, allf)
    p_gap = cv_chance(d, y, rows, [gapkey])
    ref = base_by_cat(d, y, rows)
    yy = y[rows]
    s, s_gap = bss(p, ref, yy), bss(p_gap, ref, yy)
    pos = {r: i for i, r in enumerate(rows)}
    lo, hi = boot(lambda idx: (lambda k: bss(p[k], ref[k], yy[k]))(np.array([pos[i] for i in idx if i in pos])),
                  days, by_day) if DRAWS else (np.nan, np.nan)
    X, mu, sd = design(d, rows, allf)
    w = logit_fit(X, yy)
    full = np.full(len(y), np.nan)
    full[rows] = p
    return full, {"features": allf, "bss": round(float(s), 3), "bss_gap_only": round(float(s_gap), 3),
                  "ci99": [round(float(lo), 3), round(float(hi), 3)],
                  "coef_per_sd": {f: round(float(c), 2) for f, c in zip(allf, w[3:])}}


def main():
    d = load()
    n = len(d["grew"])
    cat0 = d["cat0"]
    days = np.unique(d["day"])
    by_day = {k: np.where(d["day"] == k)[0] for k in days}
    out, table = [], []
    for k in KEYS:
        x = d[k]
        ok = np.isfinite(x)
        cuts = cuts_by_cat(x, cat0)
        t = terc(x, cat0, cuts)
        bars = {}
        for c in range(4):
            m = (cat0 == c) & ok
            bars[CATS[c]] = {"n": int(m.sum()), "cuts": [round(float(v), 3) for v in cuts[c]],
                             "grow": [round(100 * d["grew"][m & (t == i)].mean(), 1) if (m & (t == i)).any() else None for i in range(3)],
                             "decay": [round(100 * d["decayed"][m & (t == i)].mean(), 1) if (m & (t == i)).any() else None for i in range(3)]}
        sg = signal(x, d["grew"], cat0, (0, 1, 2))
        sd_ = signal(x, d["decayed"], cat0, (1, 2, 3))
        glo, ghi = boot(lambda idx: signal(x, d["grew"], cat0, (0, 1, 2), idx), days, by_day)
        dlo, dhi = boot(lambda idx: signal(x, d["decayed"], cat0, (1, 2, 3), idx), days, by_day)
        basin = {b: {"grow": round(float(signal(x[d["basin"] == b], d["grew"][d["basin"] == b], cat0[d["basin"] == b], (0, 1, 2))), 1),
                     "decay": round(float(signal(x[d["basin"] == b], d["decayed"][d["basin"] == b], cat0[d["basin"] == b], (1, 2, 3))), 1)}
                 for b in ("natl", "npac")}
        name, units = I.NAMES[k]
        rec = {"key": k, "name": name, "units": units, "n": int(ok.sum()), "bars": bars,
               "grow": {"signal": round(float(sg), 1), "lo": round(float(glo), 1), "hi": round(float(ghi), 1),
                        "verdict": verdict(sg, glo, ghi)},
               "decay": {"signal": round(float(sd_), 1), "lo": round(float(dlo), 1), "hi": round(float(dhi), 1),
                         "verdict": verdict(sd_, dlo, dhi)},
               "basin": basin}
        out.append(rec)
        table.append([name, units, int(ok.sum()), rec["grow"]["signal"], rec["grow"]["lo"], rec["grow"]["hi"],
                      rec["grow"]["verdict"], rec["decay"]["signal"], rec["decay"]["lo"], rec["decay"]["hi"],
                      rec["decay"]["verdict"], basin["natl"]["grow"], basin["npac"]["grow"],
                      basin["natl"]["decay"], basin["npac"]["decay"]])
    # starting-category base rates and persistence
    rates = {}
    for c in range(4):
        m = cat0 == c
        rates[CATS[c]] = {"n": int(m.sum()), "grew": round(100 * d["grew"][m].mean(), 1),
                          "decayed": round(100 * d["decayed"][m].mean(), 1),
                          "same_cat": round(100 * (d["cat24"][m] == c).mean(), 1),
                          "grew_cat": round(100 * d["grew_cat"][m].mean(), 1)}
    persist = round(100 * float((d["cat24"] == cat0).mean()), 1)
    # jet position, raw and at the overall starting-category mix
    jp = {}
    mix = np.array([(cat0 == c).mean() for c in range(4)])
    for cls in np.unique(d["jet_pos"]):
        m = d["jet_pos"] == cls
        per = [d["grew"][m & (cat0 == c)].mean() if (m & (cat0 == c)).sum() >= 5 else np.nan for c in range(3)]
        okc = np.isfinite(per)
        adj = float(np.nansum(np.array(per)[okc] * mix[:3][okc]) / mix[:3][okc].sum()) if okc.any() else np.nan
        jp[str(cls)] = {"n": int(m.sum()), "grow": round(100 * d["grew"][m].mean(), 1),
                        "decay": round(100 * d["decayed"][m].mean(), 1), "dp": round(float(np.nanmean(d["dp"][m])), 1),
                        "grow_same_mix": round(100 * adj, 1) if np.isfinite(adj) else None}
    # chance models on the ingredients with a real signal
    gfeat = [r["key"] for r in out if r["grow"]["verdict"] != "none"]
    dfeat = [r["key"] for r in out if r["decay"]["verdict"] != "none"]
    rows_g = np.where(cat0 <= 2)[0]
    rows_d = np.where(cat0 >= 1)[0]
    p_g, mg = model(d, d["grew"], rows_g, gfeat, "gap_up", days, by_day)
    p_d, md = model(d, d["decayed"], rows_d, dfeat, "gap_down", days, by_day)
    res = {"version": 2, "n": n, "days": len(days), "dead_band_kt": DEAD,
           "base_grow": round(100 * d["grew"].mean(), 1), "base_decay": round(100 * d["decayed"].mean(), 1),
           "persistence_exact": persist, "by_start": rates, "ingredients": out, "jet_pos": jp,
           "model_grow": mg, "model_decay": md}
    for p in (HERE / "ingredients.json", I.ROOT / "ingredients.json"):
        p.write_text(json.dumps(res, indent=1))
    with open(HERE / "ingredients_score.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ingredient", "units", "n", "grow_signal_pts", "grow_ci99_lo", "grow_ci99_hi", "grow_verdict",
                    "decay_signal_pts", "decay_ci99_lo", "decay_ci99_hi", "decay_verdict",
                    "grow_natl", "grow_npac", "decay_natl", "decay_npac"])
        w.writerows(table)
    print("lows", n, "days", len(days), "grew %.0f%% decayed %.0f%% (dead band %g kt); persistence exact %.0f%%"
          % (res["base_grow"], res["base_decay"], DEAD, persist))
    for c, v in rates.items():
        print("start %-5s n %4d grew %5.1f decayed %5.1f same %5.1f" % (c, v["n"], v["grew"], v["decayed"], v["same_cat"]))
    for r in out:
        g, dd = r["grow"], r["decay"]
        print("%-38s n %4d  grow %+5.1f [%+5.1f, %+5.1f] %-6s  decay %+5.1f [%+5.1f, %+5.1f] %-6s  Atl/Pac grow %+5.1f %+5.1f"
              % (r["name"], r["n"], g["signal"], g["lo"], g["hi"], g["verdict"], dd["signal"], dd["lo"], dd["hi"],
                 dd["verdict"], r["basin"]["natl"]["grow"], r["basin"]["npac"]["grow"]))
    for cls, v in jp.items():
        print("jet %-15s n %4d grew %5.1f (same mix %s) decayed %5.1f" % (cls, v["n"], v["grow"], v["grow_same_mix"], v["decay"]))
    print("growth model", mg)
    print("decay model ", md)
    add_to_manifest(d, res, p_g, p_d)


def add_to_manifest(d, res, p_g, p_d, deck=HERE / "page" / "deck"):
    """Each deck case's start-time ingredients, tercile within its starting category, and the out-of-fold
    chances of growth and decay -> manifest."""
    mp = deck / "manifest.json"
    if not mp.exists():
        return
    m = json.loads(mp.read_text())
    keyrows = {r["id"]: r for r in csv.DictReader(open(I.ROOT / "key.csv"))}
    index = {k: i for i, k in enumerate(d["key"])}
    cuts = {g["key"]: {c: np.array(g["bars"][CATS[c]]["cuts"]) for c in range(4)} for g in res["ingredients"]}
    hit = 0
    for c in m["cases"]:
        r = keyrows[c["id"]]
        i = index.get((r["basin"], r["t0"], round(float(r["lat0"]), 2), round(float(r["lon0"]), 2)))
        if i is None:
            continue
        c0 = int(d["cat0"][i])
        ing = {"jet_pos": str(d["jet_pos"][i]), "dpeak": round(float(d["dpeak"][i]), 1)}
        for g in res["ingredients"]:
            v = d[g["key"]][i]
            if np.isfinite(v):
                ing[g["key"]] = [round(float(v), 2), int(np.digitize(v, cuts[g["key"]][c0]))]
        if np.isfinite(p_g[i]):
            ing["p_grow"] = round(100 * float(p_g[i]))
        if np.isfinite(p_d[i]):
            ing["p_decay"] = round(100 * float(p_d[i]))
        c["ing"] = ing
        hit += 1
    m["ingredients"] = res
    mp.write_text(json.dumps(m, separators=(",", ":")))
    print("manifest: ingredients for", hit, "of", len(m["cases"]), "cases")


if __name__ == "__main__":
    main()
