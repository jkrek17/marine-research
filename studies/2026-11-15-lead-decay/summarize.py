#!/usr/bin/env python3
"""Pool score.py's per-case counts into the lead tables (design.md).

  python3 summarize.py

Leads are grouped as 24 (steps 24, 30), 48 (48, 54), 72 (72, 78), 96 (96, 102), 120 (120): the 06/18Z-valid steps
carry most of the Pacific's ASCAT. 90% intervals on the change from 24 h resample whole ISO weeks (2,000 draws).
Writes grid_by_lead.csv, lines_by_lead.csv, change_from_24.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LEAD = {24: 24, 30: 24, 48: 48, 54: 48, 72: 72, 78: 72, 96: 96, 102: 96, 120: 120}
THRS = (34, 48, 64)
RNG = np.random.default_rng(15)
NB = 2000


def grid_metrics(s):
    out = {}
    for t in THRS:
        out["area%d" % t] = s["fc%d" % t] / s["ob%d" % t]
        out["catch%d" % t] = s["cau%d" % t] / s["ob%d" % t]
        out["tile%d" % t] = s["h%d" % t] / (s["h%d" % t] + s["m%d" % t])
        out["false_tiles%d" % t] = s["fa%d" % t]
        out["events_tiles%d" % t] = s["h%d" % t] + s["m%d" % t]
    return out


def line_metrics(s):
    return {"covered": s.obs_in / s.obs_cells, "area": s.cells / s.obs_cells, "caught": s.hits / s.events,
            "caught_on": s.hits_on / s.events, "empty": s.bad_cells / s.cells, "events": s.events}


def equal_area(hist_path):
    z = np.load(hist_path)
    rows = {}
    for k, h in zip(z["keys"], z["hist"]):
        b, st, prod = k.split("|")
        key = (b, LEAD[int(st)], prod)
        rows[key] = rows[key] + h if key in rows else h.copy()
    out = []
    for (b, lead, prod), h in rows.items():
        r = dict(basin=b, lead=lead, product=prod)
        for i, t in enumerate(THRS, 1):
            ob_area = h[i].sum()
            above = np.cumsum(h[0][::-1])[::-1]      # grid cells >= T kt, T = 0..119
            caught = np.cumsum(h[i][::-1])[::-1]
            if ob_area == 0:
                r["eq%d" % t] = np.nan
                continue
            T = int(np.argmin(np.abs(above - ob_area)))
            r["eqT%d" % t], r["eq%d" % t] = T, caught[T] / ob_area
        out.append(r)
    return pd.DataFrame(out)


def change(df, keys, group_cols, metrics_fn, metric, base=24, at=(48, 72, 96, 120)):
    rows = []
    for g, sub in df.groupby(group_cols):
        leads = sorted(sub.lead.unique())
        weeks = sorted(sub.week.unique())
        cube = (sub.groupby(["week", "lead"])[keys].sum()
                .reindex(pd.MultiIndex.from_product([weeks, leads]), fill_value=0).to_numpy()
                .reshape(len(weeks), len(leads), len(keys)))
        m = metrics_fn(pd.DataFrame(cube.sum(0), index=leads, columns=keys))[metric]
        pick = RNG.integers(0, len(weeks), (NB, len(weeks)))
        cnt = np.stack([np.bincount(p, minlength=len(weeks)) for p in pick])        # [NB, weeks]
        tot = np.einsum("bw,wlk->blk", cnt, cube)                                     # [NB, leads, keys]
        flat = pd.DataFrame(tot.reshape(-1, len(keys)), columns=keys)
        dr = np.asarray(metrics_fn(flat)[metric], float).reshape(NB, len(leads))
        for L in at:
            if L not in leads or base not in leads:
                continue
            d = dr[:, leads.index(L)] - dr[:, leads.index(base)]
            d = d[np.isfinite(d)]
            gg = g if isinstance(g, tuple) else (g,)
            rows.append(dict(zip(group_cols, gg), metric=metric, lead=L, at24=m[base], value=m[L],
                             change=m[L] - m[base], lo=np.quantile(d, 0.05) if len(d) else np.nan,
                             hi=np.quantile(d, 0.95) if len(d) else np.nan))
    return rows


def main():
    g = pd.read_csv(HERE / "grid_cases.csv.gz")
    g["lead"] = g.step.map(LEAD)
    L = pd.read_csv(HERE / "line_cases.csv.gz")
    L["lead"] = L.step.map(LEAD)
    # Best Wind needs the core chances; score every product on the same cases (those that have them)
    g = g[g.core == 1]
    gkeys = [c for c in g.columns if c[:-2] in ("nt", "h", "m", "fa", "fc", "ob", "cau")]
    gs = g.groupby(["basin", "product", "lead"])[gkeys].sum()
    gt = pd.DataFrame(grid_metrics(gs)).reset_index()
    gt = gt.merge(equal_area(HERE / "hist.npz"), on=["basin", "lead", "product"], how="left")
    gt["cases"] = g.groupby(["basin", "product", "lead"]).size().values
    gt.to_csv(HERE / "grid_by_lead.csv", index=False, float_format="%.4g")
    lkeys = ["events", "hits", "hits_on", "obs_cells", "obs_in", "cells", "bad_cells", "warned_cells"]
    ls = L.groupby(["basin", "line", "lead"])[lkeys].sum()
    lt = pd.DataFrame(line_metrics(ls)).reset_index()
    lt["cases"] = L.groupby(["basin", "line", "lead"]).size().values
    lt.to_csv(HERE / "lines_by_lead.csv", index=False, float_format="%.4g")
    rows = []
    for met in ("covered", "area", "caught", "empty"):
        rows += change(L, lkeys, ["basin", "line"], line_metrics, met)
    for met in ("area34", "area48", "area64", "catch48", "tile48", "tile64"):
        rows += change(g[g["product"].isin(["best", "gfs", "ifs", "aifs", "blend"])], gkeys, ["basin", "product"],
                       grid_metrics, met)
    pd.DataFrame(rows).to_csv(HERE / "change_from_24.csv", index=False, float_format="%.4g")
    pd.set_option("display.width", 250)
    print(lt.round(3).to_string())
    print(gt[gt["product"] == "best"].round(3).to_string())


if __name__ == "__main__":
    main()
