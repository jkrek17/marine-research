"""Tables and verdict inputs for the GEFS-only HF line from run_hf.py rows.

Win line (design card section 3, preset): Atlantic held-out, the GEFS-gated line catches >= 75% of archive HF lows
within 150 km AND its HF area is <= 1.2x the live pooled gate's on the same cases. If it fails, gates of 1, 2, 3
members are tried in order and the smallest passing on TUNE weeks (Atlantic, same two tests) is the one scored on
held-out; if none passes on tune, 3 is carried and reported as failing. Held-out is read once for that choice
(the other gates are printed only as sensitivity, labelled).

usage: python3 summarize_hf.py ROWS.csv OUT.csv
"""
import sys

import numpy as np
import pandas as pd

CATCH, AREA = 0.75, 1.2


def agg(g, ref=None):
    ev, ar = g["events"].sum(), g["areas"].sum()
    out = dict(cases=len(g), lows=int(ev), caught150=int(g.hits150.sum()),
               catch150=g.hits150.sum() / ev if ev else np.nan,
               catch300=g.hits300.sum() / ev if ev else np.nan, catch500=g.hits500.sum() / ev if ev else np.nan,
               area_nm2=g.area_nm2.mean(), reach_nm2=g.reach_nm2.mean(), hf_areas=int(ar),
               areas_no_low150=int(g.false150.sum()), share_no_low150=g.false150.sum() / ar if ar else np.nan)
    if ref is not None:
        out["area_ratio"] = out["area_nm2"] / ref["area_nm2"] if ref["area_nm2"] else np.nan
        out["reach_ratio"] = out["reach_nm2"] / ref["reach_nm2"] if ref["reach_nm2"] else np.nan
    return out


def table(d):
    out = []
    for dom in ("natl", "npac", "both"):
        for sp in ("tune", "held_out"):
            x = d[d.split == sp]
            x = x if dom == "both" else x[x.dom == dom]
            ref = agg(x[x.rule == "live_pooled"])
            for (rule, res, k), g in x.groupby(["rule", "res", "k"], sort=False):
                out.append(dict(dom=dom, split=sp, rule=rule, res=res, k=k, **agg(g, ref)))
    return pd.DataFrame(out)


def passes(r):
    return r.catch150 >= CATCH and r.area_ratio <= AREA


def main(rows, out):
    d = pd.read_csv(rows, dtype={"run": str})
    d = d[d.rule != "MISSING"]
    t = table(d)
    t.to_csv(out, index=False, float_format="%.4f")
    print(t[t.rule.isin(["live_pooled", "live_noaifs", "gfe_ungated"])].to_string())
    for res in ("0.25", "0.5"):
        print("\n=== resolution", res)
        pick = None
        for k in (1, 2, 3):
            r = t[(t.dom == "natl") & (t.split == "tune") & (t.rule == "gfe_k%d" % k) & (t.res == res)].iloc[0]
            print("tune natl k=%d catch150 %.3f area_ratio %.2f -> %s" % (k, r.catch150, r.area_ratio, "pass" if passes(r) else "fail"))
            if pick is None and passes(r):
                pick = k
        chosen = pick or 3
        print("chosen on tune:", chosen, "(passed)" if pick else "(none passed; 3 carried)")
        for dom in ("natl", "npac", "both"):
            for k in (1, 2, 3):
                r = t[(t.dom == dom) & (t.split == "held_out") & (t.rule == "gfe_k%d" % k) & (t.res == res)].iloc[0]
                print("held-out %-4s k=%d%s lows %d catch150 %.3f area %.0f ratio %.2f reach_ratio %.2f areas %d no-low %d (%.2f)" % (
                    dom, k, "*" if k == chosen else " ", r.lows, r.catch150, r.area_nm2, r.area_ratio, r.reach_ratio,
                    r.hf_areas, r.areas_no_low150, r.share_no_low150))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
