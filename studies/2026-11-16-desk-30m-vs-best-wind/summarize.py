#!/usr/bin/env python3
"""Tables from score.py's rows (design.md). Writes into this folder:
  summary.csv      basin lead product: cases, area ratio at 34/48/64, tile catch and false tiles at 48/64, equal-area storm
                   catch (all leads only), MAE and bias on decision cells (ASCAT or any grid >= 30 kt) and all seen cells,
                   bias by the grid's own value (<20, 20-33, 34-47, 48-63, 64+), lifted-cell columns for the stability products.
                   lead = all (pooled), 24, 48. Common cases only (every product built).
  paired.csv       desk practice (sh_avg) and the 6 Nov tool-on-blend minus Best Wind and other refs: storm-tile catch, gale
                   area ratio, decision-cell MAE; whole-week resampling (rk.compare.paired_counts), pooled and at +24 / +48.
  continuity.csv   the 6 Nov and 7 Nov published numbers beside this run's, on the committed case sets.
  case_picks.csv.gz  per case (date, basin, lead): gale area ratio and storm-tile catch for every product, to pick worked cases.
"""
import gzip
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import compare, paths  # noqa: E402

OUT = paths.data("extra", "desk-30m-vs-best-wind")
BANDS = ["<20", "20-33", "34-47", "48-63", "64+"]
CT = [c + str(t) for t in (34, 48, 64) for c in ("nt", "h", "m", "fa", "fc", "ob", "cau")]
SUMS = CT + ["n_all", "err_all", "abs_all", "n_dec", "err_dec", "abs_dec"] + ["nb%d" % i for i in range(5)] + \
       ["eb%d" % i for i in range(5)] + ["n_lift", "n_lift_seen", "n_lift_a34", "n_lift_a48", "sum_err_low", "n_err_low"]
PAIRS = [("sh_avg", "best"), ("sh_avg", "gfe_best"), ("sh_blend_strict", "best"), ("sh_avg", "avg10"),
         ("sh_blend_strict", "det")]
LEADS = ("all", 24, 48)


def eq_area_fn():
    spec = importlib.util.spec_from_file_location("mlw_summarize", HERE.parent / "2026-11-07-most-likely-wind" / "summarize.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.eq_area


def metrics(g):
    s = g[[c for c in SUMS if c in g.columns]].sum()
    r = {"cases": len(g)}
    for t in (34, 48, 64):
        r["area%d" % t] = s["fc%d" % t] / s["ob%d" % t] if s["ob%d" % t] else np.nan
        r["cell_catch%d" % t] = s["cau%d" % t] / s["ob%d" % t] if s["ob%d" % t] else np.nan
    for t in (48, 64):
        den = s["h%d" % t] + s["m%d" % t]
        r["ascat_tiles%d" % t] = int(den)
        r["tile_catch%d" % t] = s["h%d" % t] / den if den else np.nan
        r["false_tiles%d" % t] = int(s["fa%d" % t])
    r["tile_catch34"] = s["h34"] / (s["h34"] + s["m34"])
    r["false_tiles34"] = int(s["fa34"])
    r.update(mae_dec=s["abs_dec"] / s["n_dec"], bias_dec=s["err_dec"] / s["n_dec"], n_dec=int(s["n_dec"]),
             mae_all=s["abs_all"] / s["n_all"], bias_all=s["err_all"] / s["n_all"])
    for i, b in enumerate(BANDS):
        r["bias_own_" + b] = s["eb%d" % i] / s["nb%d" % i] if s["nb%d" % i] else np.nan
        r["n_own_" + b] = int(s["nb%d" % i])
    if s["n_lift_seen"] > 0:
        r.update(lifted_cells_seen=int(s["n_lift_seen"]), lifted_share_gale=s["n_lift_a34"] / s["n_lift_seen"],
                 lifted_share_storm=s["n_lift_a48"] / s["n_lift_seen"],
                 lifted_err_base_lt34=s["sum_err_low"] / s["n_err_low"] if s["n_err_low"] else np.nan)
    return pd.Series(r)


def main():
    df = pd.read_csv(OUT / "case_rows.csv.gz")
    df["cycle"] = pd.to_datetime(df["cycle"])
    com = df[df["common"]]
    order = list(dict.fromkeys(df["product"]))
    eq_area = eq_area_fn()
    z = np.load(OUT / "hist.npz")
    hs = {tuple(k.split("|")): h for k, h in zip(z["keys"], z["hist"])}
    rows = []
    for basin in ("natl", "npac"):
        for lead in LEADS:
            sub = com[(com.basin == basin) & ((com.step == lead) if lead != "all" else True)]
            for pr in order:
                g = sub[sub["product"] == pr]
                if g.empty:
                    continue
                r = metrics(g)
                r["basin"], r["lead"], r["product"] = basin, lead, pr
                if lead == "all" and (basin, pr) in hs:
                    for j, k in ((2, 48), (3, 64)):
                        T, ca = eq_area(hs[(basin, pr)], j)
                        r["eq_catch%d" % k] = ca
                rows.append(r)
    summ = pd.DataFrame(rows)
    first = ["basin", "lead", "product", "cases"]
    summ = summ[first + [c for c in summ.columns if c not in first]]
    summ.round(4).to_csv(HERE / "summary.csv", index=False)

    # paired differences (whole-week resampling), common cases
    key = ["basin", "cycle", "step"]
    prow = []
    metr = {"storm_tile_catch": (["h48", "m48"], lambda c: c["h48"] / (c["h48"] + c["m48"])),
            "gale_area_ratio": (["fc34", "ob34"], lambda c: c["fc34"] / c["ob34"]),
            "mae_dec_kt": (["abs_dec", "n_dec"], lambda c: c["abs_dec"] / c["n_dec"]),
            "gale_tile_catch": (["h34", "m34"], lambda c: c["h34"] / (c["h34"] + c["m34"]))}
    for m, ref in PAIRS:
        for mname, (cnt, fn) in metr.items():
            for scope in ("all", 24, 48):
                d = com[com["product"].isin([m, ref]) & ((com.step == scope) if scope != "all" else True)]
                r = compare.paired_counts(d, m, ref, fn, cnt, by=["basin"], method_col="product", case_cols=key)
                r["metric"], r["product"], r["minus"], r["lead"] = mname, m, ref, scope
                prow.append(r)
    pr = pd.concat(prow, ignore_index=True).rename(columns={"method": "product_value", "baseline": "minus_value"})
    pr = pr[["basin", "lead", "product", "minus", "metric", "product_value", "minus_value", "diff", "lo", "hi", "n_cases",
             "n_weeks", "significant"]]
    pr.round(4).to_csv(HERE / "paired.csv", index=False)

    # per-case picks
    cp = com.assign(gale_area=com.fc34 / com.ob34, storm_catch=com.h48 / (com.h48 + com.m48),
                    storm_tiles_seen=com.h48 + com.m48, ob34_cells=com.ob34)
    keep = ["basin", "cycle", "step", "product", "gale_area", "storm_catch", "storm_tiles_seen", "ob34_cells", "h48", "m48", "fa48"]
    cp = cp[keep]
    wide = cp.pivot_table(index=["basin", "cycle", "step"], columns="product",
                          values=["gale_area", "storm_catch", "fa48"], aggfunc="first")
    wide.columns = ["%s__%s" % c for c in wide.columns]
    meta = com[com["product"] == "best"].set_index(key)[["ob34", "ob48", "ob64"]].add_prefix("ascat_cells")
    wide = wide.join(meta).reset_index()
    wide["valid"] = wide["cycle"] + pd.to_timedelta(wide["step"], unit="h")
    num = wide.select_dtypes("number").columns
    wide[num] = wide[num].round(3)
    wide.to_csv(HERE / "case_picks.csv.gz", index=False)

    # continuity with the committed 6 Nov / 7 Nov held-out numbers
    cont = []
    sc = pd.read_csv("/mnt/project-files/research-data/extra/strong-core-lift/final_summary.csv") if False else None
    sc = pd.read_csv(paths.data("extra", "strong-core-lift", "final_summary.csv"))
    for basin in ("natl", "npac"):
        for mine, theirs in (("sh_blend_strict", "SHs"), ("sh_blend_loose", "SHl"), ("sh_entire", "SHe"), ("det", "D")):
            ref = sc[(sc.basin == basin) & (sc["product"] == theirs)].iloc[0]
            for set_name, sub in (("own-input cases", df[df["product"] == mine]), ("common cases", com[com["product"] == mine])):
                g = sub[sub.basin == basin]
                r = metrics(g)
                cont.append(dict(basin=basin, product=mine, vs="6 Nov " + theirs, cases_here=len(g), cases_6nov=int(ref.n_cases),
                                 set=set_name, storm_tile_catch=r.tile_catch48, storm_tile_catch_6nov=ref.pod48,
                                 gale_area=r.area34, gale_area_6nov=ref.area34, storm_area=r.area48,
                                 storm_area_6nov=ref.area48, hf_area=r.area64, hf_area_6nov=ref.area64,
                                 lifted_share_gale=r.get("lifted_share_gale", np.nan), lifted_share_gale_6nov=ref.share_a34))
    cm = pd.read_csv(HERE.parent / "2026-11-07-most-likely-wind" / "catch_heldout.csv")
    cg = pd.read_csv(HERE.parent / "2026-11-07-most-likely-wind" / "catch_heldout_gfe.csv")
    for basin in ("natl", "npac"):
        for mine, theirs, tab in (("best60", "best", cm), ("blend", "blend", cm), ("det", "det", cg), ("gfe_best", "gfe_best", cg),
                                  ("gfe_best_hf", "gfe_best_hf", cg)):
            ref = tab[(tab.basin == basin) & (tab["product"] == theirs)].iloc[0]
            for set_name, sub in (("common cases", com[com["product"] == mine]),):
                g = sub[sub.basin == basin]
                r = metrics(g)
                cont.append(dict(basin=basin, product=mine, vs="7 Nov " + theirs, cases_here=len(g), set=set_name,
                                 storm_tile_catch=r.tile_catch48, storm_tile_catch_6nov=ref.tile_catch48,
                                 gale_area=r.area34, gale_area_6nov=ref.area34, storm_area=r.area48, storm_area_6nov=ref.area48,
                                 hf_area=r.area64, hf_area_6nov=ref.area64))
    pd.DataFrame(cont).round(4).to_csv(HERE / "continuity.csv", index=False)
    print("wrote summary.csv paired.csv continuity.csv case_picks.csv.gz")


if __name__ == "__main__":
    main()
