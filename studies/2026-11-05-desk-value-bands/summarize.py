"""Summaries of rows.csv.gz (score.py): desk minus blend (and desk minus Core Lifted on the held-out weeks) by basin,
day, band, situation and truth, with 95% intervals from resampling whole ISO weeks; gale catch and false-gale area.

Writes results/diff.csv, results/gale.csv and results/shares.csv. Usage: summarize.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import paths  # noqa: E402

ROWS = paths.data("extra", "desk-value-bands", "rows.csv.gz")
RES = HERE / "results"
NBOOT = 2000
SEED = 20261105
KEYS = ["basin", "truth", "band_by", "band", "situation"]


def boot(wk, a, b, n, rng):
    """Week-resampled 95% interval of sum(a)/sum(n) - sum(b)/sum(n); wk, a, b, n per-week arrays."""
    k = len(wk)
    idx = rng.integers(0, k, size=(NBOOT, k))
    d = a[idx].sum(1) / n[idx].sum(1) - b[idx].sum(1) / n[idx].sum(1)
    return np.percentile(d, [2.5, 97.5])


def diffs(df, other, subset, rng, day_groups):
    """desk minus `other` mean absolute error rows."""
    out = []
    w = df.pivot_table(index=KEYS + ["daygrp", "iso_week", "cycle", "valid"], columns="method",
                       values=["n", "sum_abs", "sum_err"], aggfunc="sum")
    w = w[w[("n", "desk")].notna() & w[("n", other)].notna()]
    w = w.groupby(level=KEYS + ["daygrp", "iso_week"]).sum()
    for key, g in w.groupby(level=KEYS + ["daygrp"]):
        n = g[("n", "desk")].to_numpy(float)
        a = g[("sum_abs", "desk")].to_numpy(float)
        b = g[("sum_abs", other)].to_numpy(float)
        if n.sum() == 0 or len(g) < 3:
            continue
        lo, hi = boot(g.index.get_level_values("iso_week"), a, b, n, rng)
        out.append(dict(zip(KEYS + ["day"], key), vs=other, subset=subset, n=int(n.sum()), weeks=len(g),
                        mae_desk=a.sum() / n.sum(), mae_other=b.sum() / n.sum(),
                        bias_desk=g[("sum_err", "desk")].sum() / n.sum(),
                        bias_other=g[("sum_err", other)].sum() / n.sum(),
                        diff=(a.sum() - b.sum()) / n.sum(), lo=lo, hi=hi))
    return out


def gale(df, rng):
    g = df[df.band_by == "gale"]
    out = []
    for subset, sub in (("all", g[g.method != "corelift"]), ("held_out", g[g.held_out & g.cycle.isin(
            g[g.method == "corelift"].cycle.unique())])):
        for key, x in sub.groupby(["basin", "truth", "situation", "daygrp", "method"]):
            wk = x.groupby("iso_week")[["hits", "fa", "miss"]].sum()
            h, fa, mi = wk.sum()
            if h + mi == 0:
                continue
            idx = rng.integers(0, len(wk), size=(NBOOT, len(wk)))
            H, F, M = (wk[c].to_numpy(float)[idx].sum(1) for c in ("hits", "fa", "miss"))
            pod = H / np.maximum(H + M, 1)
            ratio = (H + F) / np.maximum(H + M, 1)
            out.append(dict(zip(["basin", "truth", "situation", "day", "method"], key), subset=subset,
                            ob_cells=int(h + mi), caught=h / (h + mi), caught_lo=np.percentile(pod, 2.5),
                            caught_hi=np.percentile(pod, 97.5), area_ratio=(h + fa) / (h + mi),
                            ratio_lo=np.percentile(ratio, 2.5), ratio_hi=np.percentile(ratio, 97.5),
                            false_share=fa / max(h + fa, 1), weeks=len(wk)))
    return out


def main():
    RES.mkdir(exist_ok=True)
    df = pd.read_csv(ROWS)
    df["daygrp"] = df["day"].astype(str)
    both = df.copy()
    d13 = df[df.day <= 3].copy()
    d13["daygrp"] = "1-3"
    df = pd.concat([both, d13], ignore_index=True)
    rng = np.random.default_rng(SEED)
    sc = df[df.band_by != "gale"]
    rows = diffs(sc[sc.method != "corelift"], "blend", "all", rng, None)
    ho = sc[sc.cycle.isin(sc[sc.method == "corelift"].cycle.unique())]
    rows += diffs(ho, "corelift", "held_out", rng, None)
    rows += diffs(ho[ho.method != "corelift"], "blend", "held_out", rng, None)
    pd.DataFrame(rows).to_csv(RES / "diff.csv", index=False, float_format="%.3f")
    pd.DataFrame(gale(df, rng)).to_csv(RES / "gale.csv", index=False, float_format="%.3f")
    # share of scored water by band and situation (ASCAT, banded by the blend, all leads)
    s = both[(both.band_by == "blend") & (both.method == "desk")]
    sh = s.groupby(["basin", "truth", "situation", "band"]).n.sum().reset_index()
    tot = s[s.situation == "all"].groupby(["basin", "truth"]).n.sum().rename("tot")
    sh = sh.join(tot, on=["basin", "truth"])
    sh["share"] = sh.n / sh.tot
    sh.to_csv(RES / "shares.csv", index=False, float_format="%.4f")
    # ASCAT share of the scored water: ASCAT cells / analysis cells at 00/12Z
    v = both[(both.band_by == "blend") & (both.method == "desk") & (both.situation == "all") & both.hour.isin([0, 12])]
    cov = v.groupby(["basin", "truth"]).n.sum().unstack()
    cov["ascat_share"] = cov["ascat"] / cov["anl"]
    hrs = both[(both.band_by == "blend") & (both.method == "desk") & (both.situation == "all") & (both.truth == "ascat")]
    hrs = hrs.groupby(["basin", "hour"]).n.sum().unstack()
    print(cov, "\n", hrs)
    cov.to_csv(RES / "ascat_share.csv", float_format="%.3f")


if __name__ == "__main__":
    main()
