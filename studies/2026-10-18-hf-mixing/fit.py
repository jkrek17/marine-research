#!/usr/bin/env python3
"""Fit and score: which >= 64 kt-aloft cells have >= 64 kt at the surface (ASCAT)?

  python3 fit.py            tune weeks: univariate ROC areas, 5-fold week-grouped CV of the two methods,
                            writes tune_results.md and FINAL_CHOICE.json (the method with the higher CV ROC area)
  python3 fit.py --final    held-out weeks, once: refits the chosen method on all tune weeks, scores it against
                            s925 alone and the live P; writes final_results.md / final_results.json and refuses
                            to run if they exist.

Design and pass rule: design.md. Cells: cells.py (RK_CACHE/extra/hf-mixing/cells.parquet).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import cases, paths, score  # noqa: E402

PREDICTORS = ["s925", "s925_minus_r10", "sst_t850", "sst_t925", "dT", "tadv850", "tadv925", "gradT850",
              "dist_km", "sin_b", "cos_b", "r10"]
MONOTONE = {"s925": 1, "sst_t850": 1}          # more momentum, more instability -> more hurricane force
N_BOOT = 2000


def load():
    t = pd.read_parquet(paths.cache("extra", "hf-mixing", "cells.parquet"))
    t["valid"] = pd.to_datetime(t["valid"])
    t["sin_b"], t["cos_b"] = np.sin(np.radians(t.bearing)), np.cos(np.radians(t.bearing))
    t["y"] = (t.ascat >= 64).astype(int)
    iso = t.valid.dt.isocalendar()
    t["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    t["split"] = [cases.split(v.to_pydatetime()) for v in t.valid]
    return t


def make(method):
    if method == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    cst = [MONOTONE.get(p, 0) for p in PREDICTORS]
    return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=50,
                                          monotonic_cst=cst, random_state=0)


def cv_auc(t, method, k=5):
    weeks = np.array(sorted(t.week.unique()))
    fold = {w: i % k for i, w in enumerate(weeks)}
    f = t.week.map(fold).to_numpy()
    p = np.full(len(t), np.nan)
    for i in range(k):
        tr, te = f != i, f == i
        if t.y[tr].sum() == 0 or te.sum() == 0:
            continue
        m = make(method).fit(t.loc[tr, PREDICTORS], t.y[tr])
        p[te] = m.predict_proba(t.loc[te, PREDICTORS])[:, 1]
    ok = np.isfinite(p)
    return score.auc(p[ok], t.y.to_numpy()[ok]), p


def boot_auc_diff(t, a, b, n=N_BOOT, seed=0):
    """Whole-week bootstrap of AUC(a) - AUC(b) (columns of t), weights = times each week is drawn."""
    weeks = np.array(sorted(t.week.unique()))
    idx = t.week.map({w: i for i, w in enumerate(weeks)}).to_numpy()
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        cnt = np.bincount(rng.integers(0, len(weeks), len(weeks)), minlength=len(weeks))
        w = cnt[idx].astype(float)
        if (w * t.y).sum() == 0 or (w * (1 - t.y)).sum() == 0:
            continue
        out.append(score.auc(t[a].to_numpy(), t.y.to_numpy(), w) - score.auc(t[b].to_numpy(), t.y.to_numpy(), w))
    return np.percentile(out, [2.5, 97.5])


def counts(t):
    return dict(cells=len(t), cells64=int(t.y.sum()), weeks=int(t.week.nunique()),
                storms=int(t.groupby(["basin", "event_id"]).ngroups),
                storms64=int(t[t.y == 1].groupby(["basin", "event_id"]).ngroups))


def tune(t):
    tu = t[t.split == "tune"].reset_index(drop=True)
    lines = ["# Tune weeks", "", "Counts: %s" % counts(tu), "",
             "## Univariate ROC area (higher value -> hurricane force at the surface)", "",
             "| Predictor | ROC area |", "|---|---|"]
    for p in PREDICTORS + ["P"]:
        lines.append("| %s | %.3f |" % (p, score.auc(tu[p].to_numpy(), tu.y.to_numpy())))
    res = {}
    for m in ("logistic", "boosted"):
        res[m], _ = cv_auc(tu, m)
    lines += ["", "## 5-fold week-grouped CV ROC area", "", "| Method | CV ROC area |", "|---|---|"]
    lines += ["| %s | %.3f |" % (m, v) for m, v in res.items()]
    lr = make("logistic").fit(tu[PREDICTORS], tu.y)
    coef = lr[-1].coef_[0]
    lines += ["", "## Logistic coefficients (standardised; + means more hurricane force)", "",
              "| Predictor | Coefficient |", "|---|---|"]
    lines += ["| %s | %+.3f |" % (p, c) for p, c in zip(PREDICTORS, coef)]
    choice = max(res, key=res.get)
    lines += ["", "Chosen for the held-out score: **%s** (higher CV ROC area)." % choice]
    (HERE / "tune_results.md").write_text("\n".join(lines) + "\n")
    (HERE / "FINAL_CHOICE.json").write_text(json.dumps({"method": choice, "cv_auc": res}, indent=1) + "\n")
    print("\n".join(lines))


def final(t):
    out_md, out_js = HERE / "final_results.md", HERE / "final_results.json"
    if out_md.exists() or out_js.exists():
        raise SystemExit("final results exist: the held-out score runs once")
    choice = json.loads((HERE / "FINAL_CHOICE.json").read_text())["method"]
    tu, ho = t[t.split == "tune"], t[t.split == "held_out"].reset_index(drop=True)
    if ho.y.sum() == 0:
        raise SystemExit("no held-out hurricane-force cells: refusing to score")
    m = make(choice).fit(tu[PREDICTORS], tu.y)
    ho["model"] = m.predict_proba(ho[PREDICTORS])[:, 1]
    y = ho.y.to_numpy()
    r = dict(method=choice, counts=counts(ho),
             auc={k: score.auc(ho[k].to_numpy(), y) for k in ("model", "s925", "P")},
             brier_skill=score.brier_skill(ho.model.to_numpy(), y))
    r["diff_vs_s925"] = [r["auc"]["model"] - r["auc"]["s925"], *boot_auc_diff(ho, "model", "s925")]
    r["diff_vs_P"] = [r["auc"]["model"] - r["auc"]["P"], *boot_auc_diff(ho, "model", "P")]
    if choice == "logistic":
        r["coef"] = dict(zip(PREDICTORS, map(float, m[-1].coef_[0])))
    passed = (r["diff_vs_s925"][1] > 0 and r["diff_vs_P"][1] > 0 and r["brier_skill"] > 0)
    r["passed_scores"] = bool(passed)
    out_js.write_text(json.dumps(r, indent=1, default=float) + "\n")
    lines = ["# Held-out weeks (scored once)", "", "Method: %s. Counts: %s" % (choice, r["counts"]), "",
             "| | ROC area |", "|---|---|"] + ["| %s | %.3f |" % (k, v) for k, v in r["auc"].items()]
    lines += ["", "Model minus s925: %+.3f [%+.3f, %+.3f]" % tuple(r["diff_vs_s925"]),
              "Model minus live P: %+.3f [%+.3f, %+.3f]" % tuple(r["diff_vs_P"]),
              "Brier skill (vs held-out base rate): %.3f" % r["brier_skill"],
              "", "Scores pass: %s (signs are judged in findings.md)" % passed]
    out_md.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    t = load()
    final(t) if a.final else tune(t)
