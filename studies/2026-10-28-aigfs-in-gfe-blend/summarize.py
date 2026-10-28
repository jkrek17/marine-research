#!/usr/bin/env python3
"""Summarize run.py's case counts and apply the preset win line (design.md) mechanically.

  python3 summarize.py [--counts DIR/case_counts.csv] [--out DIR] [--boot 2000] [--no-copy]

Writes to --out (default RK_DATA/extra/aigfs-in-gfe-blend) and copies the small files to the study folder:
  summary.csv      pooled levels per split, basin, group and product (CSI/POD/FAR at 34 and 48, area ratios, buoy
                   bias). Groups: all (every scored lead pooled), lead24..lead126 (per step) and, for npac,
                   valid0012 / valid0618 (valid hour 00/12 UTC vs 06/18 UTC).
  differences.csv  G1-N, Gh-N, A-N, G1-A, Gh-A with whole-week 95% intervals (rk.compare.paired_counts, the same
                   weeks for both). Per-group rows carry csi34, pod48, csi48 only.
  singles.csv      gfs, ifs, aifs, aigfs alone: mean error (forecast - ASCAT) at ASCAT >= 34 kt, all / cold air /
                   not cold air, and storm-tile (48+) POD, by split, basin and day group (1-2: steps 24, 30, 48;
                   3-5: 54..126; day = ceil(step / 24)). Cold air = GFS t2 - skt < 0 (see run.py); the split
                   columns exist only where GFS low-level fields exist (steps 24..120), n_cold + n_notcold < n_all.
  verdict.md       the win line applied, then the tables.

Win line (design.md), G1 or Gh against N, held-out weeks, BOTH basins, pooled over all scored leads:
  1. gale-tile CSI (5x5 deg tiles, any ASCAT 34+) higher than N's with the whole-week 95% interval above zero;
  2. storm-tile (48+) POD not lower than N's by more than 2 points;
  3. 34+ area ratio (forecast / ASCAT at seen cells) not further from 1 than N's.
If both pass, the higher gale CSI (mean over the two basins) wins; if neither passes, GFE runs GFS + ECMWF (N).
A is scored beside them and does not decide. Tune weeks are a second look (nothing is fitted). Per-lead and buoy
numbers do not decide.
"""
import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from rk import compare, paths  # noqa: E402

COUNTS = ["nt34", "h34", "m34", "fa34", "nt48", "h48", "m48", "fa48", "fc34", "ob34", "fc48", "ob48",
          "b_n", "b_sum_err", "b_sum_abs"]
BIAS = ["g_n", "g_sum", "gc_n", "gc_sum", "gw_n", "gw_sum"]
BLENDS = ("N", "A", "G1", "Gh")
SINGLES = ("gfs", "ifs", "aifs", "aigfs")
NAMES = {"N": "N  GFS+ECMWF", "A": "A  +AIFS x0.5", "G1": "G1  +AI-GFS x1", "Gh": "Gh  +AI-GFS x0.5",
         "gfs": "GFS", "ifs": "ECMWF", "aifs": "AIFS", "aigfs": "AI-GFS"}
PAIRS = [("G1", "N"), ("Gh", "N"), ("A", "N"), ("G1", "A"), ("Gh", "A")]
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


def groups(g, basin):
    """[(label, subset)]: all, per lead, and for npac the valid-hour halves."""
    out = [("all", g)]
    out += [("lead%d" % s, g[g.step == s]) for s in sorted(g.step.unique())]
    if basin == "npac":
        out += [("valid0012", g[g.valid_hr.isin([0, 12])]), ("valid0618", g[g.valid_hr.isin([6, 18])])]
    return out


def levels(d):
    rows = []
    for (split, basin), g in d.groupby(["split", "basin"]):
        for lab, gs in groups(g, basin):
            for (v, p), gp in gs.groupby(["variant", "product"]):
                c = {k: np.array(float(gp[k].sum())) for k in COUNTS}
                r = {"split": split, "basin": basin, "group": lab, "variant": v, "product": p,
                     "n_cases": len(gp), "n_weeks": gp.cycle.dt.isocalendar().week.nunique(),
                     "tiles34": int(c["h34"] + c["m34"]), "tiles48": int(c["h48"] + c["m48"]),
                     "buoy_n": int(c["b_n"])}
                r.update({k: float(METRICS[k](c)) for k in LEVELS})
                rows.append(r)
    return pd.DataFrame(rows)


def differences(d, n_boot):
    d = d[d["product"] == "blend"]
    rows = []
    for (split, basin), g in d.groupby(["split", "basin"]):
        for lab, gs in groups(g, basin):
            for v, base in PAIRS:
                for k in ("csi34", "pod34", "far34", "csi48", "pod48", "far48", "area34_dev", "buoy_bias",
                          "buoy_mae"):
                    if lab != "all" and k not in ("csi34", "pod48", "csi48"):
                        continue
                    r = compare.paired_counts(gs, v + "|blend", base + "|blend", METRICS[k], COUNTS,
                                              n_boot=n_boot, seed=0, case_cols=["basin", "step"])
                    x = r.iloc[0]
                    rows.append({"split": split, "basin": basin, "group": lab, "variant": v, "baseline": base,
                                 "metric": k, "baseline_value": x["baseline"], "variant_value": x["method"],
                                 "diff": x["diff"], "lo": x["lo"], "hi": x["hi"], "n_cases": x["n_cases"],
                                 "n_weeks": x["n_weeks"]})
    return pd.DataFrame(rows)


def singles(d):
    """Bias at ASCAT >= 34 (all, cold, not cold) and storm-tile POD of the four single models."""
    d = d[d["product"] == "single"].copy()
    d["day"] = np.where(np.ceil(d.step / 24) <= 2, "1-2", "3-5")
    rows = []
    for (split, basin), g in d.groupby(["split", "basin"]):
        for lab, gs in [("all", g)] + [("day " + k, x) for k, x in g.groupby("day")]:
            for m, gp in gs.groupby("variant"):
                s = gp[BIAS + ["h48", "m48", "h34", "m34"]].sum()      # NaN split counts are skipped
                rows.append({"split": split, "basin": basin, "days": lab, "model": m, "n_cases": len(gp),
                             "n_all": int(s.g_n), "bias_all": s.g_sum / s.g_n if s.g_n else np.nan,
                             "n_cold": int(s.gc_n), "bias_cold": s.gc_sum / s.gc_n if s.gc_n else np.nan,
                             "n_notcold": int(s.gw_n), "bias_notcold": s.gw_sum / s.gw_n if s.gw_n else np.nan,
                             "tiles48": int(s.h48 + s.m48),
                             "pod48": s.h48 / (s.h48 + s.m48) if s.h48 + s.m48 else np.nan,
                             "pod34": s.h34 / (s.h34 + s.m34) if s.h34 + s.m34 else np.nan})
    return pd.DataFrame(rows)


def win_line(lv, df, split="held_out"):
    """Apply the preset rule -> (winner 'N'|'G1'|'Gh', checks DataFrame, reason str)."""
    basins = sorted(lv.basin.unique())
    checks, passed = [], {}
    for v in ("G1", "Gh"):
        ok_all = True
        for b in basins:
            sel = (lv.split == split) & (lv.basin == b) & (lv.group == "all") & (lv["product"] == "blend")
            a, x = lv[sel & (lv.variant == "N")], lv[sel & (lv.variant == v)]
            dd = df[(df.split == split) & (df.basin == b) & (df.group == "all") & (df.variant == v)
                    & (df.baseline == "N")].set_index("metric")
            if a.empty or x.empty or "csi34" not in dd.index:
                checks.append(dict(variant=v, basin=b, rule="0 no held-out data", value="", passed=False))
                ok_all = False
                continue
            a, x = a.iloc[0], x.iloc[0]
            c1 = dd.loc["csi34"]
            r1 = bool(c1["diff"] > 0 and c1["lo"] > 0)
            d2 = x["pod48"] - a["pod48"]
            r2 = bool(np.isfinite(d2) and d2 >= -POD_MARGIN)
            dev_a, dev_x = abs(a["area34"] - 1), abs(x["area34"] - 1)
            r3 = bool(np.isfinite(dev_a) and np.isfinite(dev_x) and dev_x <= dev_a)
            checks += [dict(variant=v, basin=b, rule="1 gale CSI higher than N, interval above 0",
                            value="%+.3f [%+.3f, %+.3f]" % (c1["diff"], c1["lo"], c1["hi"]), passed=r1),
                       dict(variant=v, basin=b, rule="2 storm POD not lower by > 2 pts",
                            value="%+.3f" % d2, passed=r2),
                       dict(variant=v, basin=b, rule="3 gale area ratio not further from 1",
                            value="%.3f vs N %.3f" % (x["area34"], a["area34"]), passed=r3)]
            ok_all &= r1 and r2 and r3
        passed[v] = ok_all
    chk = pd.DataFrame(checks)
    ok = [v for v in ("G1", "Gh") if passed[v]]
    if not ok:
        reason = "neither G1 nor Gh passes all three tests in both basins"
        f = chk[~chk.passed]
        if len(f):
            reason += " (failed: " + "; ".join("%s %s %s" % (r.variant, r.basin, r.rule[:1])
                                               for r in f.itertuples()) + ")"
        return "N", chk, reason
    if len(ok) == 1:
        return ok[0], chk, "%s passes all three tests in both basins" % ok[0]
    csi = {v: lv[(lv.split == split) & (lv.group == "all") & (lv["product"] == "blend") & (lv.variant == v)]
           .groupby("basin").csi34.mean().mean() for v in ok}
    w = max(csi, key=csi.get)
    return w, chk, "G1 and Gh both pass; %s has the higher gale CSI (mean over basins %s)" % (
        w, ", ".join("%s %.3f" % (k, x) for k, x in sorted(csi.items())))


def _md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join(("%.3f" % x if isinstance(x, float) else str(x)) for x in r) + " |")
    return "\n".join(out)


def level_table(lv, split):
    t = lv[(lv.split == split) & (lv.group == "all") & (lv["product"] == "blend")].copy()
    t["variant"] = t.variant.map(NAMES)
    t = t[["basin", "variant", "n_cases", "tiles34", "pod34", "far34", "csi34", "tiles48", "pod48", "far48",
           "csi48", "area34", "area48", "buoy_n", "buoy_bias"]]
    return t.sort_values(["basin", "variant"])


def diff_table(df, split):
    t = df[(df.split == split) & (df.group == "all") & df.metric.isin(["csi34", "pod48", "csi48", "buoy_bias"])].copy()
    t["pair"] = t.variant + " - " + t.baseline
    t["d"] = ["%+.3f [%+.3f, %+.3f]" % (a, b, c) for a, b, c in zip(t["diff"], t.lo, t.hi)]
    return t.pivot_table(index=["basin", "pair"], columns="metric", values="d", aggfunc="first").reset_index()


def lead_table(lv, split):
    t = lv[(lv.split == split) & lv.group.str.startswith("lead") & (lv["product"] == "blend")].copy()
    if t.empty:
        return t[["basin"]]
    t["lead"] = t.group.str[4:].astype(int)
    return t.pivot_table(index=["basin", "lead"], columns="variant", values="csi34", aggfunc="first")[
        [v for v in BLENDS]].reset_index()


def singles_table(sg, split):
    t = sg[sg.split == split].copy()
    t["model"] = t.model.map(NAMES)
    t = t[["basin", "days", "model", "n_all", "bias_all", "n_cold", "bias_cold", "n_notcold", "bias_notcold",
           "tiles48", "pod48"]]
    return t.sort_values(["basin", "days", "model"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--counts", default=None, help="case_counts.csv from run.py "
                    "(default RK_DATA/extra/aigfs-in-gfe-blend/case_counts.csv)")
    ap.add_argument("--out", default=None, help="default RK_DATA/extra/aigfs-in-gfe-blend")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--no-copy", action="store_true", help="do not copy the small files into the study folder")
    a = ap.parse_args()
    cpath = Path(a.counts) if a.counts else paths.data("extra", "aigfs-in-gfe-blend", "case_counts.csv")
    out = Path(a.out) if a.out else paths.data("extra", "aigfs-in-gfe-blend")
    out.mkdir(parents=True, exist_ok=True)
    d = load(cpath)
    lv, df, sg = levels(d), differences(d, a.boot), singles(d)
    lv.to_csv(out / "summary.csv", index=False, float_format="%.4f")
    df.to_csv(out / "differences.csv", index=False, float_format="%.4f")
    sg.to_csv(out / "singles.csv", index=False, float_format="%.4f")
    w, chk, why = win_line(lv, df)
    bl = d[d["product"] == "blend"]
    n = {s: {b: len(g[["cycle", "step"]].drop_duplicates()) for b, g in bl[bl.split == s].groupby("basin")}
         for s in ("held_out", "tune")}
    L = ["# AI-GFS in the GFE blend: verdict", "",
         "Cases scored (basin: cycle x lead; every case has all four blends and all four single models): "
         "held-out %s; tune %s. Truth ASCAT real 10 m wind; tiles 5x5 deg with >= 150 seen cells; area ratio = "
         "forecast / ASCAT seen cells at 34+ and 48+; buoy bias = forecast - buoy (kt) where either is >= 34 kt. "
         "Pooled over all scored leads (Pacific: +24..+120 and +30..+126)." % (n["held_out"], n["tune"]), "",
         "## Verdict (held-out weeks, both basins)", "",
         "**%s.** %s." % ("GFE runs GFS + ECMWF (N)" if w == "N" else
                          "AI-GFS goes into the GFE blend as %s (%s)" % (w, NAMES[w]), why), "",
         "### Win-line checks, held-out", "", _md(chk), ""]
    for split, label in (("held_out", "Held-out weeks (primary)"), ("tune", "Tune weeks (second look; nothing is fitted)")):
        if lv[lv.split == split].empty:
            L += ["## %s" % label, "", "No cases in this split.", ""]
            continue
        L += ["## %s" % label, "", _md(level_table(lv, split)), "",
              "Differences (whole-week 95% intervals):", "", _md(diff_table(df, split)), "",
              "Gale-tile CSI by lead:", "", _md(lead_table(lv, split)), "",
              "Single models: mean error (kt, forecast - ASCAT) at ASCAT >= 34, all / cold air (GFS t2 - skt < 0) / "
              "not cold; storm-tile POD:", "", _md(singles_table(sg, split)), ""]
    (out / "verdict.md").write_text("\n".join(L) + "\n")
    if not a.no_copy and out.resolve() != HERE:
        for f in ("summary.csv", "differences.csv", "singles.csv", "verdict.md"):
            shutil.copy(out / f, HERE / f)
    print("\n".join(L))
    print("VERDICT: %s | %s" % (w, why))


if __name__ == "__main__":
    main()
