#!/usr/bin/env python3
"""Tables from score_cells.py output (design.md).

  python3 summarize.py --split tune|held_out

Writes into this folder (<s> = tune / heldout):
  bands_<s>.csv     basin product cut band n bias mae rmse   (cut truth = ASCAT band, fc = grid band, all, dec)
  steps_<s>.csv     basin product step: all-water and decision-cell (ASCAT or any candidate >= 30) bias / MAE
  catch_<s>.csv     basin product: tile catch / area / false tiles at 34, 48, 64 kt; cell area ratio; equal-area
                    cell catch at 34 / 48 / 64 (grid threshold set so its seen area equals ASCAT's)
  paired_<s>.csv    basin product ref metric diff lo hi: whole-week bootstrap (2000) of product minus ref for
                    mae_all, mae_dec (decision cells) and storm tile catch, refs best and blend
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import paths  # noqa: E402

DATA = paths.data("extra", "most-likely-wind")
REFS = ("best", "blend")
N_BOOT = 2000


def stats(g):
    return pd.Series({"n": g.n.sum(), "bias": g.sum_err.sum() / g.n.sum(), "mae": g.sum_abs.sum() / g.n.sum(),
                      "rmse": np.sqrt(g.sum_sq.sum() / g.n.sum())})


def eq_area(h, k):
    """Equal-area catch: hist rows (seen, ob34, ob48, ob64) summed; k = 1/2/3. Threshold T (fractional, linear
    within a 1 kt bin) where grid count >= T equals the ASCAT count; catch = ASCAT cells caught above T."""
    target = h[k].sum()
    if target == 0:
        return np.nan, np.nan
    cf = np.cumsum(h[0][::-1])[::-1]     # cells with grid >= bin
    co = np.cumsum(h[k][::-1])[::-1]
    i = int(np.searchsorted(-cf, -target, side="right")) - 1    # last bin with cf >= target
    i = max(min(i, len(cf) - 1), 0)
    nxt = cf[i + 1] if i + 1 < len(cf) else 0
    frac = 0 if cf[i] == nxt else (cf[i] - target) / (cf[i] - nxt)
    nco = co[i + 1] if i + 1 < len(co) else 0
    return i + frac, (co[i] - frac * (co[i] - nco)) / target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=("tune", "held_out"))
    ap.add_argument("--tag", default="", help="'_gfe' for gfe_score.py output")
    ap.add_argument("--refs", default="best,blend")
    a = ap.parse_args()
    global REFS
    REFS = tuple(a.refs.split(","))
    s = ("heldout" if a.split == "held_out" else "tune") + a.tag
    a.split = a.tag + "_" + a.split if a.tag else a.split
    e = pd.read_csv(DATA / ("err%s.csv.gz" % ("_" + a.split if not a.split.startswith("_") else a.split)))
    t = pd.read_csv(DATA / ("tiles%s.csv.gz" % ("_" + a.split if not a.split.startswith("_") else a.split)))
    order = list(dict.fromkeys(e["product"]))

    b = e.groupby(["basin", "product", "cut", "band"]).apply(stats, include_groups=False).reset_index()
    b["product"] = pd.Categorical(b["product"], order)
    b.sort_values(["basin", "cut", "band", "product"]).round(3).to_csv(HERE / ("bands_%s.csv" % s), index=False)

    st = e[e.cut.isin(["all", "dec"])].groupby(["basin", "product", "cut", "step"]).apply(
        stats, include_groups=False).reset_index()
    st = st.pivot_table(index=["basin", "product", "step"], columns="cut", values=["bias", "mae", "n"])
    st.columns = ["%s_%s" % c for c in st.columns]
    st.reset_index().round(3).to_csv(HERE / ("steps_%s.csv" % s), index=False)

    c = t.groupby(["basin", "product"])[[x for x in t.columns if x[:2] in ("nt", "h3", "h4", "h6", "m3", "m4",
                                                                            "m6", "fa", "fc", "ob", "ca")]].sum()
    for k in (34, 48, 64):
        c["tile_catch%d" % k] = c["h%d" % k] / (c["h%d" % k] + c["m%d" % k])
        c["false_tiles%d" % k] = c["fa%d" % k]
        c["area%d" % k] = c["fc%d" % k] / c["ob%d" % k]
        c["cell_catch%d" % k] = c["cau%d" % k] / c["ob%d" % k]
    z = np.load(DATA / ("hist%s.npz" % ("_" + a.split if not a.split.startswith("_") else a.split)))
    keys = [k.split("|") for k in z["keys"]]
    hs = {}
    for (bn, wk, pr), h in zip(keys, z["hist"]):
        hs[(bn, pr)] = hs.get((bn, pr), 0) + h
    for (bn, pr), h in hs.items():
        for j, k in ((1, 34), (2, 48), (3, 64)):
            T, ca = eq_area(h, j)
            c.loc[(bn, pr), "eqT%d" % k] = T
            c.loc[(bn, pr), "eq_catch%d" % k] = ca
    keep = [x for x in c.columns if x.startswith(("tile_", "false_", "area", "cell_", "eq"))]
    c = c[keep].reset_index()
    c["product"] = pd.Categorical(c["product"], order)
    c.sort_values(["basin", "product"]).round(3).to_csv(HERE / ("catch_%s.csv" % s), index=False)

    # whole-week bootstrap, product minus ref
    rng = np.random.default_rng(0)
    rows = []
    ew = e[e.cut.isin(["all", "dec"])].groupby(["basin", "week", "product", "cut"])[["n", "sum_abs"]].sum()
    tw = t.groupby(["basin", "week", "product"])[["h48", "m48", "h64", "m64"]].sum()
    for bn in ("natl", "npac"):
        weeks = sorted(set(e[e.basin == bn].week))
        idx = rng.integers(0, len(weeks), (N_BOOT, len(weeks)))

        def arr(df, pr, col, cut=None):
            sub = df.xs((bn, pr) + ((cut,) if cut else ()), level=["basin", "product"] + (["cut"] if cut else []))
            return sub.reindex(weeks)[col].fillna(0).to_numpy()

        for ref in REFS:
            for pr in order:
                if pr == ref:
                    continue
                for cut in ("all", "dec"):
                    n, sa = arr(ew, pr, "n", cut), arr(ew, pr, "sum_abs", cut)
                    nr, sr = arr(ew, ref, "n", cut), arr(ew, ref, "sum_abs", cut)
                    d0 = sa.sum() / n.sum() - sr.sum() / nr.sum()
                    bs = sa[idx].sum(1) / n[idx].sum(1) - sr[idx].sum(1) / nr[idx].sum(1)
                    rows.append([bn, pr, ref, "mae_" + cut, d0, *np.percentile(bs, [2.5, 97.5])])
                for k in (48, 64):
                    h, m = arr(tw, pr, "h%d" % k), arr(tw, pr, "m%d" % k)
                    hr, mr = arr(tw, ref, "h%d" % k), arr(tw, ref, "m%d" % k)
                    d0 = h.sum() / (h + m).sum() - hr.sum() / (hr + mr).sum()
                    with np.errstate(invalid="ignore", divide="ignore"):
                        bs = h[idx].sum(1) / (h + m)[idx].sum(1) - hr[idx].sum(1) / (hr + mr)[idx].sum(1)
                    rows.append([bn, pr, ref, "tile_catch%d" % k, d0, *np.nanpercentile(bs, [2.5, 97.5])])
    pd.DataFrame(rows, columns=["basin", "product", "ref", "metric", "diff", "lo", "hi"]).round(4).to_csv(
        HERE / ("paired_%s.csv" % s), index=False)
    print("wrote bands/steps/catch/paired_%s.csv" % s)


if __name__ == "__main__":
    main()
