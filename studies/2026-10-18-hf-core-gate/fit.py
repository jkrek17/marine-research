#!/usr/bin/env python3
"""Which cores reach hurricane force: fit on tune weeks, score once on held-out weeks (design.md).

  python3 fit.py            tune weeks: univariate ROC, week-grouped CV of logistic and boosted -> tune_results.md,
                            FINAL_CHOICE.json
  python3 fit.py --final    held-out weeks, once -> final_results.md / .json (refuses to rerun)
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
from rk import cases, score  # noqa: E402

PREDICTORS = ["p_max", "p_mean", "area", "r10_max", "r10_p95", "mod_max", "s925_max", "p64_max", "gefs_p64_max",
              "ens_p64_max", "msl_min", "drop", "ens_msl_min", "ens_msl_sd", "lat", "step"]
N_BOOT = 2000


def load():
    d = pd.read_csv(HERE / "cores.csv", parse_dates=["valid", "cycle"])
    d = d[d.status == "ok"].copy()
    d["lat"] = d["lat"].abs()
    iso = d.valid.dt.isocalendar()
    d["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    d["split"] = [cases.split(v.to_pydatetime()) for v in d.valid]
    d[PREDICTORS] = d[PREDICTORS].fillna(d[PREDICTORS].median())
    d["lead"] = (d.step // 24) * 24
    return d.reset_index(drop=True)


def make(method):
    if method == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0))
    return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=20,
                                          random_state=0)


def cv_auc(t, method, k=5):
    weeks = np.array(sorted(t.week.unique()))
    f = t.week.map({w: i % k for i, w in enumerate(weeks)}).to_numpy()
    p = np.full(len(t), np.nan)
    for i in range(k):
        tr, te = f != i, f == i
        if t.hf[tr].nunique() < 2 or not te.any():
            continue
        p[te] = make(method).fit(t.loc[tr, PREDICTORS], t.hf[tr]).predict_proba(t.loc[te, PREDICTORS])[:, 1]
    ok = np.isfinite(p)
    return score.auc(p[ok], t.hf.to_numpy()[ok])


def boot_diff(t, a, b, seed=0):
    weeks = np.array(sorted(t.week.unique()))
    idx = t.week.map({w: i for i, w in enumerate(weeks)}).to_numpy()
    rng, y, out = np.random.default_rng(seed), t.hf.to_numpy(), []
    for _ in range(N_BOOT):
        w = np.bincount(rng.integers(0, len(weeks), len(weeks)), minlength=len(weeks))[idx].astype(float)
        if (w * y).sum() == 0 or (w * (1 - y)).sum() == 0:
            continue
        out.append(score.auc(t[a].to_numpy(), y, w) - score.auc(t[b].to_numpy(), y, w))
    return list(np.percentile(out, [2.5, 97.5]))


def counts(t):
    vt = t.drop_duplicates(["basin", "valid", "core"])
    return dict(cores=len(t), hf=int(t.hf.sum()), weeks=int(t.week.nunique()),
                valid_times=int(t[["basin", "valid"]].drop_duplicates().shape[0]),
                hf_valid_times=int(t[t.hf == 1][["basin", "valid"]].drop_duplicates().shape[0]),
                natl=int((t.basin == "natl").sum()), npac=int((t.basin == "npac").sum()),
                npac_hf=int(t[(t.basin == "npac")].hf.sum()), distinct_core_rows=len(vt))


def tune(t):
    tu = t[t.split == "tune"].reset_index(drop=True)
    y = tu.hf.to_numpy()
    lines = ["# Tune weeks", "", "Counts: %s" % counts(tu), "", "## Univariate ROC area (higher value -> HF)", "",
             "| Predictor | ROC area | Mean in HF cores | Mean in other cores |", "|---|---|---|---|"]
    for p in PREDICTORS:
        lines.append("| %s | %.3f | %.2f | %.2f |" % (p, score.auc(tu[p].to_numpy(), y), tu[p][y == 1].mean(),
                                                     tu[p][y == 0].mean()))
    res = {m: cv_auc(tu, m) for m in ("logistic", "boosted")}
    lines += ["", "## Week-grouped 5-fold CV ROC area", "", "| Method | CV ROC |", "|---|---|"]
    lines += ["| %s | %.3f |" % kv for kv in res.items()]
    lines += ["| p_max alone (no fit) | %.3f |" % score.auc(tu.p_max.to_numpy(), y)]
    lr = make("logistic").fit(tu[PREDICTORS], y)
    lines += ["", "## Logistic coefficients (standardised)", "", "| Predictor | Coefficient |", "|---|---|"]
    lines += ["| %s | %+.3f |" % (p, c) for p, c in zip(PREDICTORS, lr[-1].coef_[0])]
    choice = max(res, key=res.get)
    lines += ["", "Chosen: **%s**." % choice]
    (HERE / "tune_results.md").write_text("\n".join(lines) + "\n")
    (HERE / "FINAL_CHOICE.json").write_text(json.dumps({"method": choice, "cv_auc": res}, indent=1) + "\n")
    print("\n".join(lines))


def final(t):
    om, oj = HERE / "final_results.md", HERE / "final_results.json"
    if om.exists() or oj.exists():
        raise SystemExit("final results exist: the held-out score runs once")
    choice = json.loads((HERE / "FINAL_CHOICE.json").read_text())["method"]
    tu, ho = t[t.split == "tune"], t[t.split == "held_out"].reset_index(drop=True)
    if ho.hf.nunique() < 2:
        raise SystemExit("held-out weeks lack one class: refusing to score")
    m = make(choice).fit(tu[PREDICTORS], tu.hf)
    ho["model"] = m.predict_proba(ho[PREDICTORS])[:, 1]
    # flag as many tune cores as ASCAT found HF there -> threshold
    ptu = m.predict_proba(tu[PREDICTORS])[:, 1]
    thr = float(np.sort(ptu)[::-1][max(int(tu.hf.sum()) - 1, 0)])
    y = ho.hf.to_numpy()
    r = dict(method=choice, counts=counts(ho),
             auc={k: score.auc(ho[k].to_numpy(), y) for k in ("model", "p_max", "r10_max")},
             brier_skill=score.brier_skill(ho.model.to_numpy(), y), threshold=thr)
    r["diff_vs_p_max"] = [r["auc"]["model"] - r["auc"]["p_max"], *boot_diff(ho, "model", "p_max")]
    r["diff_vs_r10_max"] = [r["auc"]["model"] - r["auc"]["r10_max"], *boot_diff(ho, "model", "r10_max")]
    r["passed"] = bool(r["diff_vs_p_max"][1] > 0 and r["brier_skill"] > 0)
    lines = ["# Held-out weeks (scored once)", "", "Method: %s. Counts: %s" % (choice, r["counts"]), "",
             "| | ROC area |", "|---|---|"] + ["| %s | %.3f |" % kv for kv in r["auc"].items()]
    lines += ["", "Model minus p_max: %+.3f [%+.3f, %+.3f]" % tuple(r["diff_vs_p_max"]),
              "Model minus r10_max: %+.3f [%+.3f, %+.3f]" % tuple(r["diff_vs_r10_max"]),
              "Brier skill: %.3f" % r["brier_skill"], "",
              "## Flagging at the tune-matched threshold (%.2f)" % thr, "",
              "| Basin | Lead | Cores | HF cores | Flagged | Hits | Hit rate | False-alarm ratio |",
              "|---|---|---|---|---|---|---|---|"]
    ho["flag"] = ho.model >= thr
    tab = []
    for b in ("all", "natl", "npac"):
        for lead in ("all", 24, 48, 72):
            h = ho if b == "all" else ho[ho.basin == b]
            h = h if lead == "all" else h[h.lead == lead]
            hits = int((h.flag & (h.hf == 1)).sum())
            nf, nh = int(h.flag.sum()), int(h.hf.sum())
            row = dict(basin=b, lead=lead, cores=len(h), hf=nh, flagged=nf, hits=hits,
                       pod=hits / nh if nh else np.nan, far=1 - hits / nf if nf else np.nan)
            tab.append(row)
            lines.append("| %s | %s | %d | %d | %d | %d | %.2f | %.2f |" % (b, lead, len(h), nh, nf, hits,
                                                                          row["pod"], row["far"]))
    r["flagging"] = tab
    if choice == "logistic":
        r["coef"] = dict(zip(PREDICTORS, map(float, m[-1].coef_[0])))
    lines += ["", "Pass (ROC beats p_max with interval above 0, Brier skill > 0): %s" % r["passed"]]
    oj.write_text(json.dumps(r, indent=1, default=float) + "\n")
    om.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    t = load()
    final(t) if ap.parse_args().final else tune(t)
