#!/usr/bin/env python3
"""Summarize run.py's case counts and apply the preset win line (design.md) mechanically.

  python3 summarize.py [--counts DIR/case_counts.csv] [--out DIR] [--boot 2000]

Writes summary.csv (pooled levels per split, basin, lead, variant, product), differences.csv (B - A and C - A
with whole-week 95% intervals from rk.compare.paired_counts) and verdict.md. Held-out weeks are the primary
result; tune weeks are a second look (nothing is fitted in this study) and are labelled as such.

Win line (design.md), per product, held-out weeks, BOTH basins, pooled over +24..+120 h: B or C replaces A only if
  1. gale-tile CSI (5x5 deg tiles, any ASCAT 34+) is higher than A's with the whole-week 95% interval above zero;
  2. storm-tile (48+) POD is not lower than A's by more than 2 points;
  3. the 34+ area ratio (forecast / ASCAT at seen cells) is not further from 1 than A's.
If both pass, the higher gale CSI wins; if neither, A stays. The question is about Core Lifted, so the verdict
that counts is the `corelift` product; the plain blend is run through the same rule and shown beside it.
Per-lead and buoy numbers are reported and do not decide.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from rk import compare, paths  # noqa: E402

COUNTS = ["nt34", "h34", "m34", "fa34", "nt48", "h48", "m48", "fa48", "fc34", "ob34", "fc48", "ob48",
          "b_n", "b_sum_err", "b_sum_abs"]
PRODUCTS = ("corelift", "blend")          # the decision product first
NAMES = {"A": "A  GFS+IFS+AIFS (live)", "B": "B  GFS+IFS", "C": "C  AIFS weight x0.5"}
POD_MARGIN = 0.02


def _r(n, d):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(d > 0, n / d, np.nan)


METRICS = {
    "csi34": lambda c: _r(c["h34"], c["h34"] + c["m34"] + c["fa34"]),
    "pod34": lambda c: _r(c["h34"], c["h34"] + c["m34"]),
    "far34": lambda c: _r(c["fa34"], c["h34"] + c["fa34"]),
    "csi48": lambda c: _r(c["h48"], c["h48"] + c["m48"] + c["fa48"]),
    "pod48": lambda c: _r(c["h48"], c["h48"] + c["m48"]),
    "far48": lambda c: _r(c["fa48"], c["h48"] + c["fa48"]),
    "area34": lambda c: _r(c["fc34"], c["ob34"]),
    "area48": lambda c: _r(c["fc48"], c["ob48"]),
    "area34_dev": lambda c: np.abs(_r(c["fc34"], c["ob34"]) - 1),
    "buoy_bias": lambda c: _r(c["b_sum_err"], c["b_n"]),
    "buoy_mae": lambda c: _r(c["b_sum_abs"], c["b_n"]),
}
LEVELS = [k for k in METRICS if k != "area34_dev"]


def load(path):
    d = pd.read_csv(path, dtype={"cycle": str})
    d["cycle"] = pd.to_datetime(d["cycle"], format="%Y%m%d%H")
    d["method"] = d["variant"] + "|" + d["product"]
    return d


def levels(d):
    rows = []
    for (split, basin), g in d.groupby(["split", "basin"]):
        for stp in ["all"] + sorted(g.step.unique().tolist()):
            gs = g if stp == "all" else g[g.step == stp]
            for (v, p), gp in gs.groupby(["variant", "product"]):
                c = {k: np.array(float(gp[k].sum())) for k in COUNTS}
                r = {"split": split, "basin": basin, "step": stp, "variant": v, "product": p,
                     "n_cases": len(gp), "n_weeks": gp.cycle.dt.isocalendar().week.nunique() if len(gp) else 0,
                     "tiles34": int(c["h34"] + c["m34"]), "tiles48": int(c["h48"] + c["m48"]),
                     "buoy_n": int(c["b_n"])}
                r.update({k: float(METRICS[k](c)) for k in LEVELS})
                rows.append(r)
    return pd.DataFrame(rows)


def differences(d, n_boot):
    rows = []
    for (split, basin), g in d.groupby(["split", "basin"]):
        for stp in ["all"] + sorted(g.step.unique().tolist()):
            gs = g if stp == "all" else g[g.step == stp]
            for p in PRODUCTS:
                for v in ("B", "C"):
                    for k in ("csi34", "pod34", "far34", "csi48", "pod48", "far48", "area34_dev", "buoy_bias",
                              "buoy_mae"):
                        if stp != "all" and k not in ("csi34", "pod48", "csi48"):
                            continue
                        r = compare.paired_counts(gs, v + "|" + p, "A|" + p, METRICS[k], COUNTS, n_boot=n_boot,
                                                  seed=0, case_cols=["basin", "step"])
                        x = r.iloc[0]
                        rows.append({"split": split, "basin": basin, "step": stp, "product": p, "variant": v,
                                     "metric": k, "A": x["baseline"], "variant_value": x["method"],
                                     "diff": x["diff"], "lo": x["lo"], "hi": x["hi"], "n_cases": x["n_cases"],
                                     "n_weeks": x["n_weeks"]})
    return pd.DataFrame(rows)


def win_line(lv, df, product, split="held_out"):
    """Apply the preset rule -> (winner 'A'|'B'|'C', checks DataFrame, reason str)."""
    basins = sorted(lv.basin.unique())
    checks, passed = [], {}
    for v in ("B", "C"):
        ok_all = True
        for b in basins:
            a = lv[(lv.split == split) & (lv.basin == b) & (lv["step"] == "all") & (lv["product"] == product)
                   & (lv.variant == "A")]
            x = lv[(lv.split == split) & (lv.basin == b) & (lv["step"] == "all") & (lv["product"] == product)
                   & (lv.variant == v)]
            dd = df[(df.split == split) & (df.basin == b) & (df["step"] == "all") & (df["product"] == product)
                    & (df.variant == v)].set_index("metric")
            if a.empty or x.empty or "csi34" not in dd.index:
                checks.append(dict(variant=v, basin=b, rule="0 no held-out data", value=np.nan, passed=False))
                ok_all = False
                continue
            a, x = a.iloc[0], x.iloc[0]
            c1 = dd.loc["csi34"]
            r1 = bool(c1["diff"] > 0 and c1["lo"] > 0)
            d2 = x["pod48"] - a["pod48"]
            r2 = bool(np.isfinite(d2) and d2 >= -POD_MARGIN)
            dev_a, dev_x = abs(a["area34"] - 1), abs(x["area34"] - 1)
            r3 = bool(np.isfinite(dev_a) and np.isfinite(dev_x) and dev_x <= dev_a)
            checks += [dict(variant=v, basin=b, rule="1 gale CSI higher, interval above 0",
                            value="%+.3f [%+.3f, %+.3f]" % (c1["diff"], c1["lo"], c1["hi"]), passed=r1),
                       dict(variant=v, basin=b, rule="2 storm POD not lower by > 2 pts",
                            value="%+.3f" % d2, passed=r2),
                       dict(variant=v, basin=b, rule="3 gale area ratio not further from 1",
                            value="%.3f vs A %.3f" % (x["area34"], a["area34"]), passed=r3)]
            ok_all &= r1 and r2 and r3
        passed[v] = ok_all
    ok = [v for v in ("B", "C") if passed[v]]
    if not ok:
        reason = "neither B nor C passes all three tests in both basins"
        failed = pd.DataFrame(checks)
        failed = failed[~failed.passed]
        if len(failed):
            reason += " (failed: " + "; ".join("%s %s %s" % (r.variant, r.basin, r.rule[:1]) for r in
                                               failed.itertuples()) + ")"
        return "A", pd.DataFrame(checks), reason
    if len(ok) == 1:
        return ok[0], pd.DataFrame(checks), "%s passes all three tests in both basins" % ok[0]
    csi = {v: lv[(lv.split == split) & (lv["step"] == "all") & (lv["product"] == product) & (lv.variant == v)]
           .groupby("basin").csi34.mean().mean() for v in ok}
    w = max(csi, key=csi.get)
    return w, pd.DataFrame(checks), "B and C both pass; %s has the higher gale CSI (mean over basins %s)" % (
        w, ", ".join("%s %.3f" % (k, x) for k, x in sorted(csi.items())))


def _md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join(("%.3f" % x if isinstance(x, float) else str(x)) for x in r) + " |")
    return "\n".join(out)


def level_table(lv, split, product):
    t = lv[(lv.split == split) & (lv["step"] == "all") & (lv["product"] == product)].copy()
    t["variant"] = t.variant.map(NAMES)
    t = t[["basin", "variant", "n_cases", "tiles34", "pod34", "far34", "csi34", "tiles48", "pod48", "far48",
           "csi48", "area34", "area48", "buoy_n", "buoy_bias", "buoy_mae"]]
    return t.sort_values(["basin", "variant"])


def diff_table(df, split, product):
    t = df[(df.split == split) & (df["step"] == "all") & (df["product"] == product)
           & df.metric.isin(["csi34", "pod48", "csi48", "buoy_bias"])].copy()
    t["diff (95% interval)"] = ["%+.3f [%+.3f, %+.3f]" % (a, b, c) for a, b, c in zip(t["diff"], t.lo, t.hi)]
    return t.pivot_table(index=["basin", "variant"], columns="metric", values="diff (95% interval)",
                         aggfunc="first").reset_index()


def lead_table(lv, split, product):
    t = lv[(lv.split == split) & (lv["step"] != "all") & (lv["product"] == product)]
    return t.pivot_table(index=["basin", "step"], columns="variant", values="csi34", aggfunc="first").reset_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--counts", default=None, help="case_counts.csv from run.py (default RK_DATA/extra/aifs-in-blend)")
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    cpath = Path(a.counts) if a.counts else paths.data("extra", "aifs-in-blend", "case_counts.csv")
    d = load(cpath)
    smoke = (d["mode"] == "smoke_gfs_only").any() if "mode" in d else False
    out = Path(a.out).resolve()
    if smoke and (out == HERE or HERE in out.parents):
        sys.exit("counts are from --smoke-gfs-only; give --out outside the study folder")
    out.mkdir(parents=True, exist_ok=True)
    lv, df = levels(d), differences(d, a.boot)
    lv.to_csv(out / "summary.csv", index=False, float_format="%.4f")
    df.to_csv(out / "differences.csv", index=False, float_format="%.4f")
    res = {p: win_line(lv, df, p) for p in PRODUCTS}
    n_hold = d[d.split == "held_out"].groupby("basin").apply(lambda g: g[["cycle", "step"]].drop_duplicates().shape[0])
    n_tune = d[d.split == "tune"].groupby("basin").apply(lambda g: g[["cycle", "step"]].drop_duplicates().shape[0])
    L = []
    if smoke:
        L += ["**SMOKE TEST (ifs = aifs = gfs): plumbing only, no AIFS result.**", ""]
    L += ["# AIFS in the blend: verdict", "",
          "Cases scored: held-out %s; tune %s (basin: cases of cycle x lead). Truth ASCAT real 10 m wind; tiles 5x5 deg "
          "with >= 150 seen cells; area ratio = forecast / ASCAT seen cells at 34+ and 48+; buoy columns are pairs "
          "where forecast or buoy >= 34 kt, bias = forecast - buoy (kt)." % (dict(n_hold), dict(n_tune)), ""]
    w, chk, why = res["corelift"]
    L += ["## Verdict (Core Lifted, held-out weeks, both basins, +24..+120 h)", "",
          "**%s.** %s." % ("AIFS stays as is (A)" if w == "A" else "Replace A with %s (%s)" % (w, NAMES[w]), why), "",
          "Same rule on the plain blend: **%s** (%s)." % (res["blend"][0], res["blend"][2]), "",
          "### Win-line checks, Core Lifted, held-out", "", _md(chk), ""]
    for split, label in (("held_out", "Held-out weeks (primary)"), ("tune", "Tune weeks (second look; nothing is fitted here)")):
        for p in PRODUCTS:
            L += ["## %s: %s" % (label, "Core Lifted" if p == "corelift" else "plain blend"), "",
                  _md(level_table(lv, split, p)), "", "Difference from A (whole-week 95% intervals):", "",
                  _md(diff_table(df, split, p)), "", "Gale-tile CSI by lead:", "", _md(lead_table(lv, split, p)), ""]
    (out / "verdict.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print("VERDICT corelift: %s | %s" % (w, why))
    print("VERDICT blend:    %s | %s" % (res["blend"][0], res["blend"][2]))


if __name__ == "__main__":
    main()
