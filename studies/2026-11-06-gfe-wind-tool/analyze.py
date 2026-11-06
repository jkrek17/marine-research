#!/usr/bin/env python3
"""Pick on tune weeks, then report held-out (design.md).

  python3 analyze.py --pick     tune rows -> tune_pooled.csv, tune_picks.csv, tune_oof.csv, PICK.json
  python3 analyze.py --report   held-out rows + PICK.json -> heldout_pooled.csv, heldout_paired.csv, hf_flag.csv

Pick rule (Jason's choice; default "cap1"): per basin, among the GFE tool families S (strong-core lift), G (GEFS
P48 gated), W (two tier), X (strongest + lift), F (GEFS P48 >= 50% storm floor), keep products whose gale tile CSI >= #95's - 0.01 and gale area <= max(1.3, #95's +
0.01); then
  cap1   highest storm-tile catch with storm area (fc48/ob48) <= 1.0
  csi    highest storm-tile CSI (h / (h + m + fa))
  cap15  highest storm-tile catch with storm area <= 1.5 (the #73 line)
One tool for both basins is preferred: the "joint" pick maximises the mean of the two basins' catch (or CSI) among
products that pass in both. A and H families (AI-GFS) exist on held-out weeks only and are reported at the picked
L/T, never picked.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import compare, paths  # noqa: E402

DATA = paths.data("extra", "gfe-wind-tool")
CNT = ["h34", "m34", "fa34", "fc34", "ob34", "h48", "m48", "fa48", "fc48", "ob48", "nt48", "cau48", "fc64", "ob64",
       "cau64", "h64", "m64", "fa64"]
HFC = ["hf_fc", "hf_flag", "hf_flag_a64", "hf_flag_a48", "hf_unfl_a64"]
MET = {"storm_catch": (["h48", "m48"], lambda c: c["h48"] / (c["h48"] + c["m48"])),
       "storm_csi": (["h48", "m48", "fa48"], lambda c: c["h48"] / (c["h48"] + c["m48"] + c["fa48"])),
       "storm_area": (["fc48", "ob48"], lambda c: c["fc48"] / c["ob48"]),
       "false_storm_tiles": (["fa48"], lambda c: c["fa48"]),
       "gale_csi": (["h34", "m34", "fa34"], lambda c: c["h34"] / (c["h34"] + c["m34"] + c["fa34"])),
       "gale_area": (["fc34", "ob34"], lambda c: c["fc34"] / c["ob34"]),
       "hf_tile_catch": (["h64", "m64"], lambda c: c["h64"] / (c["h64"] + c["m64"])),
       "hf_area": (["fc64", "ob64"], lambda c: c["fc64"] / c["ob64"])}
TOOL = ("S", "G", "W", "X", "F")


def load(split):
    d = pd.read_csv(DATA / ("rows_%s.csv.gz" % split), parse_dates=["cycle"])
    d["kind"] = d["product"].str.split("_").str[0]
    return d


def paired_cases(d, products):
    """Keep only (basin, cycle, step) cases where every product in `products` exists."""
    x = d[d["product"].isin(products)]
    n = x.groupby(["basin", "cycle", "step"])["product"].transform("nunique")
    return x[n == len(set(products))]


def pooled(d):
    g = d.groupby(["basin", "product"])[CNT + HFC].sum()
    g["n_cases"] = d.groupby(["basin", "product"]).size()
    for m, (_, f) in MET.items():
        g[m] = f(g)
    return g.reset_index()


def passes(p, base):
    gale_ok = (p.gale_csi >= base.gale_csi - 0.01) & (p.gale_area <= max(1.3, base.gale_area + 0.01))
    return gale_ok


def pick_one(pool, rule):
    """pool: pooled rows of one basin incl. D. -> picked product row (or None) and the eligible table."""
    base = pool[pool["product"] == "D"].iloc[0]
    t = pool[pool["product"].str.split("_").str[0].isin(TOOL)].copy()
    t = t[passes(t, base)]
    if rule == "cap1":
        t = t[t.storm_area <= 1.0].sort_values(["storm_catch", "storm_csi"], ascending=False)
    elif rule == "cap15":
        t = t[t.storm_area <= 1.5].sort_values(["storm_catch", "storm_csi"], ascending=False)
    else:
        t = t.sort_values(["storm_csi", "storm_catch"], ascending=False)
    return (t.iloc[0] if len(t) else None), t


def joint_pick(pools, rule):
    key = "storm_csi" if rule == "csi" else "storm_catch"
    elig = [set(pick_one(pools[b], rule)[1]["product"]) for b in pools]
    both = set.intersection(*elig)
    if not both:
        return None
    score = {p: np.mean([pools[b].set_index("product").loc[p, key] for b in pools]) for p in both}
    return max(score, key=score.get)


def do_pick(a):
    d = load("tune")
    d = d[d["product"].str.split("_").str[0].isin(TOOL + ("D", "DG", "CL", "CL8"))]
    # pair on cases with the #95 blend (every GFE product needs it); page rows are reported where they exist
    gfe = d[d["product"].str.split("_").str[0].isin(TOOL + ("D", "DG"))]
    keys = gfe[gfe["product"] == "D"][["basin", "cycle", "step"]]
    gfe = gfe.merge(keys, on=["basin", "cycle", "step"])
    pool = pooled(gfe)
    pool.to_csv(HERE / "tune_pooled.csv", index=False)
    pools = {b: pool[pool.basin == b] for b in ("natl", "npac")}
    picks, oof = [], []
    for rule in ("cap1", "csi", "cap15"):
        for b in pools:
            r, _ = pick_one(pools[b], rule)
            picks.append(dict(rule=rule, basin=b, product=None if r is None else r["product"],
                              **({} if r is None else {m: r[m] for m in MET})))
            for fam in TOOL:
                sub = pools[b][pools[b]["product"].str.split("_").str[0].isin((fam, "D"))]
                rf, _ = pick_one(sub, rule)
                picks.append(dict(rule=rule, basin=b, family=fam, product=None if rf is None else rf["product"],
                                  **({} if rf is None else {m: rf[m] for m in MET})))
            for k in sorted(gfe.fold.unique()):
                pk = pooled(gfe[(gfe.basin == b) & (gfe.fold != k)])
                rk_, _ = pick_one(pk, rule)
                oof.append(dict(rule=rule, basin=b, left_out=k, product=None if rk_ is None else rk_["product"]))
        picks.append(dict(rule=rule, basin="joint", product=joint_pick(pools, rule)))
    pk = pd.DataFrame(picks)
    pk.to_csv(HERE / "tune_picks.csv", index=False)
    pd.DataFrame(oof).to_csv(HERE / "tune_oof.csv", index=False)
    out = {rule: {r.basin + ("" if pd.isna(r.get("family")) else "_" + r.family): r["product"]
                  for _, r in pk[pk.rule == rule].iterrows()} for rule in pk.rule.unique()}
    json.dump(out, open(HERE / "PICK.json", "w"), indent=1)
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(pk.round(3).to_string())


def lt(product):
    p = {s[0]: s[1:] for s in product.split("_")[1:]}
    return "L%s_T%s" % (p["L"], p["T"])


def do_report(a):
    picks = json.load(open(HERE / "PICK.json"))[a.rule]
    d = load("held_out")
    chosen = {v for v in picks.values() if v}
    extra = set()
    for v in chosen:
        extra |= {"A_" + lt(v), "H_" + lt(v), "S_" + lt(v)}
    show = ["D", "DG", "S_L6_T44", "CL", "CL8"] + sorted(chosen | extra)
    x = d[d["product"].isin(show)]
    pool = pooled(x)
    pool.to_csv(HERE / "heldout_pooled.csv", index=False)
    rows = []
    for b in ("natl", "npac"):
        xb = x[x.basin == b]
        for m in sorted(chosen | extra):
            for base in ("D", "DG", "S_L6_T44", "CL"):
                if m == base:
                    continue
                y = paired_cases(xb, [m, base])
                if y.empty:
                    continue
                for name, (cols, f) in MET.items():
                    r = compare.paired_counts(y[["cycle", "step", "product"] + cols], m, base, f, cols,
                                              method_col="product", case_cols=["step"])
                    r.insert(0, "metric", name)
                    r.insert(0, "baseline", base)
                    r.insert(0, "product", m)
                    r.insert(0, "basin", b)
                    r["n_cases"] = y.groupby(["cycle", "step"]).ngroups
                    rows.append(r)
    res = pd.concat(rows, ignore_index=True)
    res.to_csv(HERE / "heldout_paired.csv", index=False)
    hf = pool[["basin", "product"] + HFC + ["ob64"]].copy()
    hf["flag_share"] = hf.hf_flag / hf.hf_fc.replace(0, np.nan)
    hf["flag_right"] = 1 - hf.hf_flag_a64 / hf.hf_flag.replace(0, np.nan)
    hf.to_csv(HERE / "hf_flag.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_rows", 400):
        print(pool[["basin", "product", "n_cases"] + list(MET)].round(3).to_string())
        print(hf.round(3).to_string())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--rule", default="cap1", choices=("cap1", "csi", "cap15"))
    a = ap.parse_args()
    if a.pick:
        do_pick(a)
    if a.report:
        do_report(a)


if __name__ == "__main__":
    main()
