#!/usr/bin/env python3
"""Adversarial audit 2026-10-17, hole 4(b): does the core likelihood hold up within the winter, Nov-Dec 2025
vs Jan-Mar 2026? Separates season from over-fit in the drop from ~49% storm catch in the training winter to
~38% outside it.

  python3 season_split.py TABLE_DIR OOF_PARQUET CASE_SCORES_CSV [--out DIR] [--boot 1000]

Inputs are the tune-week outputs of this study: the storm table (build_table.py), the retrained model's
out-of-fold chances (train.py, oof/<set>.parquet) and the tune case scores (score.py, case_scores.csv).
Per basin and half: (1) core likelihood as a chance at candidate cells ASCAT saw: BSS, AUC, reliability
(10 bins), for the LIVE model (trained on the Atlantic winter itself, so in-sample there) and the retrained
model's out-of-fold chance; (2) Core Lifted (live_lift) and the retrained lift5@0.35 on storm tiles: POD,
FAR, CSI. Whole-week bootstrap intervals. Writes season_split.csv, season_reliability.csv, season_split.md."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
from rk import score  # noqa: E402


def half(cycle):
    m = int(str(cycle)[4:6])
    return "Nov-Dec" if m in (11, 12) else "Jan-Mar"


def week(cycle):
    d = C.cycle_dt(str(cycle))
    return "%d-%02d" % d.isocalendar()[:2]


def boot(df, fn, n, seed=0):
    wk = df["wk"].to_numpy()
    u = np.unique(wk)
    idx = {k: np.flatnonzero(wk == k) for k in u}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = np.concatenate([idx[k] for k in rng.choice(u, len(u))])
        out.append(fn(df.iloc[pick]))
    return np.nanpercentile(out, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table_dir")
    ap.add_argument("oof")
    ap.add_argument("case_scores")
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    out = Path(a.out)

    d = C.load_table(a.table_dir)
    d = d[d["split"] == "tune"].reset_index(drop=True)
    d["p_live"] = C.live_predict_table(d)
    o = pd.read_parquet(a.oof)[["basin", "cycle", "step", "row", "col", "p"]]
    d["cycle"] = d["cycle"].astype(str)
    o["cycle"] = o["cycle"].astype(str)
    d = d.merge(o.rename(columns={"p": "p_new"}), on=["basin", "cycle", "step", "row", "col"], how="inner")
    d["half"] = d["cycle"].map(half)
    d["wk"] = d["cycle"].map(week)
    rows, rel = [], []
    for (b, h), g in d.groupby(["basin", "half"]):
        for name in ("p_live", "p_new"):
            fb = lambda s, n=name: score.brier_skill(s[n], s["y"], s["w"])
            fa = lambda s, n=name: score.auc(s[n], s["y"], s["w"])
            lo, hi = boot(g, fb, a.boot)
            alo, ahi = boot(g, fa, max(200, a.boot // 5))
            rows.append({"basin": b, "half": h, "what": "chance", "model": name[2:], "n_cells": len(g),
                         "n_weeks": g["wk"].nunique(), "base_rate": float(np.average(g["y"], weights=g["w"])),
                         "bss": fb(g), "bss_lo": lo, "bss_hi": hi, "auc": fa(g), "auc_lo": alo, "auc_hi": ahi})
            r = score.reliability(g[name], g["y"], g["w"])
            r.insert(0, "model", name[2:]); r.insert(0, "half", h); r.insert(0, "basin", b)
            rel.append(r)
    cs = pd.read_csv(a.case_scores, dtype={"cycle": str})
    cs = cs[cs["product"].isin(["live_lift", "lift5@0.35"])].copy()
    cs["half"] = cs["cycle"].map(half)
    cs["wk"] = cs["cycle"].map(week)

    def pod(s):
        return s.h48.sum() / max(s.h48.sum() + s.m48.sum(), 1)

    def far(s):
        return s.fa48.sum() / max(s.h48.sum() + s.fa48.sum(), 1)

    def csi(s):
        return s.h48.sum() / max(s.h48.sum() + s.m48.sum() + s.fa48.sum(), 1)

    for (b, h, p), g in cs.groupby(["basin", "half", "product"]):
        lo, hi = boot(g, pod, a.boot)
        rows.append({"basin": b, "half": h, "what": "storm tiles", "model": p, "n_cases": len(g),
                     "n_weeks": g["wk"].nunique(), "tiles": int(g.h48.sum() + g.m48.sum()),
                     "pod": pod(g), "pod_lo": lo, "pod_hi": hi, "far": far(g), "csi": csi(g)})
    res = pd.DataFrame(rows)
    res.to_csv(out / "season_split.csv", index=False, float_format="%.4f")
    pd.concat(rel).to_csv(out / "season_reliability.csv", index=False, float_format="%.4f")
    print(res.to_string())


if __name__ == "__main__":
    main()
