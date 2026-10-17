"""HF vs storm force from IR features: the design's three methods, tuned on tuning weeks, scored once on the
held-out weeks. Reads features.csv; writes results.csv (per-fix probabilities) and scores.csv.

    python3 studies/2026-10-17-hf-satellite/run.py            # tuning weeks only (grouped 5-fold by storm)
    python3 studies/2026-10-17-hf-satellite/run.py --final    # adds the one-time held-out score

Methods (design.md): base = logistic on central pressure and latitude; ir = base + the seven IR features
(logistic); gbm = gradient boosting on the same, kept only if ir passes. Positives HF fixes, negatives S fixes,
both with status ok (>= 90% of the crop within 1000 km seen).
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import HERE
from features import FEATURES
from rk import compare, score

BASE = ["hpa", "lat"]
METHODS = {"base": BASE, "ir": BASE + FEATURES, "gbm": BASE + FEATURES}
WIN_AUC = 0.05


def model(name):
    if name == "gbm":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0)
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))


def table():
    d = pd.read_csv(HERE / "features.csv", parse_dates=["valid"])
    d = d[(d["status"] == "ok") & d["category"].isin(["HF", "S"])].dropna(subset=BASE + FEATURES).copy()
    d["y"] = (d["category"] == "HF").astype(int)
    return d.reset_index(drop=True)


def week_boot_auc(g, a, b, n=2000, seed=0):
    """AUC(a) - AUC(b) with 95% interval from resampling whole ISO weeks."""
    rng = np.random.default_rng(seed)
    wk = g["valid"].dt.isocalendar()
    wid = (wk["year"].astype(int) * 100 + wk["week"].astype(int)).to_numpy()
    u = np.unique(wid)
    idx = {w: np.nonzero(wid == w)[0] for w in u}
    diff = []
    for _ in range(n):
        take = np.concatenate([idx[w] for w in rng.choice(u, len(u))])
        s = g.iloc[take]
        diff.append(score.auc(s[a], s["y"]) - score.auc(s[b], s["y"]))
    diff = np.array(diff)
    return float(np.nanpercentile(diff, 2.5)), float(np.nanpercentile(diff, 97.5)), len(u)


def scores(g, label):
    rows = []
    for m in METHODS:
        if "p_" + m not in g:
            continue
        rows.append({"set": label, "method": m, "n": len(g), "n_hf": int(g["y"].sum()),
                     "n_s": int((1 - g["y"]).sum()), "storms": g["event_id"].nunique(),
                     "auc": score.auc(g["p_" + m], g["y"]),
                     "brier": float(np.mean((g["p_" + m] - g["y"]) ** 2))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    d = table()
    tune, held = d[d["split"] == "tune"].copy(), d[d["split"] == "held_out"].copy()
    print("tune %d fixes (%d HF, %d S, %d storms); held out %d (%d HF, %d S, %d storms)" % (
        len(tune), tune.y.sum(), (1 - tune.y).sum(), tune.event_id.nunique(),
        len(held), held.y.sum(), (1 - held.y).sum(), held.event_id.nunique()))
    for m, cols in METHODS.items():                 # out-of-fold on tuning weeks, grouped by storm
        p = np.zeros(len(tune))
        for tr, te in GroupKFold(5).split(tune, tune["y"], tune["event_id"]):
            p[te] = model(m).fit(tune.iloc[tr][cols], tune.iloc[tr]["y"]).predict_proba(tune.iloc[te][cols])[:, 1]
        tune["p_" + m] = p
    rows = scores(tune, "tune (5-fold by storm)")
    for b in ("natl", "npac"):
        rows += scores(tune[tune.basin == b], "tune " + b)
    lo, hi, nw = week_boot_auc(tune, "p_ir", "p_base")
    print("tune AUC ir - base 95%%: %.3f to %.3f (%d weeks)" % (lo, hi, nw))
    out = [tune]
    if a.final:
        for m, cols in METHODS.items():
            held["p_" + m] = model(m).fit(tune[cols], tune["y"]).predict_proba(held[cols])[:, 1]
        rows += scores(held, "held out")
        for b in ("natl", "npac"):
            rows += scores(held[held.basin == b], "held out " + b)
        lo, hi, nw = week_boot_auc(held, "p_ir", "p_base")
        long = pd.concat([pd.DataFrame({"cycle": held["valid"], "fix": held["event_id"] + held["valid"].astype(str),
                                        "method": m, "brier": (held["p_" + m] - held["y"]) ** 2})
                          for m in ("ir", "base")])
        pb = compare.paired(long, "ir", "base", "brier", case_cols=["fix"], n_boot=10000)
        # 10,000 draws: with the default 2,000 the upper end sat on zero and flipped with the seed (check, 10-17)
        gain = score.auc(held["p_ir"], held["y"]) - score.auc(held["p_base"], held["y"])
        print("HELD OUT AUC ir - base %.3f (95%% %.3f to %.3f, %d weeks); Brier ir - base %.4f (95%% %.4f to %.4f)"
              % (gain, lo, hi, nw, pb["mean"][0], pb["lo"][0], pb["hi"][0]))
        win = gain >= WIN_AUC and pb["hi"][0] < 0
        print("design rule (AUC gain >= %.2f and Brier interval below 0): %s" % (WIN_AUC, "PASSED" if win else "not passed"))
        rows.append({"set": "held out", "method": "ir - base", "auc": gain, "auc_lo": lo, "auc_hi": hi,
                     "brier": pb["mean"][0], "brier_lo": pb["lo"][0], "brier_hi": pb["hi"][0],
                     "weeks": nw, "passed": win})
        out.append(held)
    s = pd.DataFrame(rows)
    print(s.to_string(index=False, float_format="%.3f"))
    s.to_csv(HERE / "scores.csv", index=False, float_format="%.4f")
    keep = ["basin", "event_id", "valid", "lat", "lon", "hpa", "category", "split", "vza", "y"] + \
        [c for c in out[-1].columns if c.startswith("p_")]
    pd.concat(out)[keep].to_csv(HERE / "results.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
