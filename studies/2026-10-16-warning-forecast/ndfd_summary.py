"""Strongest-model lines against the desk's grids, a GFS/ECMWF average and ASCAT, from ndfd_lines.py rows.

Each gale and storm line is read at the offset where it first covers 80% and 90% of the ASCAT cells at the
level on the tune weeks, and at its own offset 0. Area is then compared at equal coverage, as a multiple of the
ASCAT area at the level (seen warned cells / ASCAT cells at the level), so the bar does not depend on the desk.
HF lines are read at offset 0 and at the max3 +12 kt pick, at 150 and 500 km.

Scope "ndfd": the HSF water where the desk grid has a value, 13 Jan to 31 Mar 2026, every hour with an NDFD
update (the text, complete or not, is shown where it exists). Scope "all": the whole winter, desk text hours
complete vs all (the lower bound from partly parsed hours).

usage: python3 ndfd_summary.py ROWS_NDFD.csv [OUT.md]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import cases  # noqa: E402

NAMES = {34: "Gale", 48: "Storm", 64: "Hurricane force"}
LABEL = {"desk": "HSF text", "ndfd": "Desk grids (NDFD)", "mean2": "GFS/ECMWF average", "max3": "Strongest model"}


def agg(g):
    ev = g["events"].sum()
    out = dict(cases=len(g), events=int(ev), area=g["area_nm2"].mean(), reach=g["reach_nm2"].mean())
    if g["hits"].isna().all():
        for k in (500, 150):
            out["c%d" % k] = g["hits%d" % k].sum() / ev if ev else np.nan
            out["f%d" % k] = g["false%d" % k].sum() / max(g["areas"].sum(), 1)
    else:
        out.update(caught=g["hits"].sum() / max(ev, 1), on=g["hits_on"].sum() / max(ev, 1),
                   covered=g["obs_in"].sum() / max(g["obs_cells"].sum(), 1),
                   false=g["bad_on"].sum() / max(g["cells"].sum(), 1),
                   xascat=g["cells"].sum() / max(g["obs_cells"].sum(), 1))
    return out


def table(d):
    return pd.DataFrame([dict(L=L, rule=r, setting=s, **agg(g))
                         for (L, r, s), g in d.groupby(["L", "rule", "setting"])])


def first_at(t, L, rule, key, bar):
    rows = t[(t.L == L) & (t.rule == rule)].sort_values("setting")
    ok = rows[rows[key] >= bar]
    return None if not len(ok) else int(ok.iloc[0]["setting"])


def line(r, L):
    if L == 64:
        return "%d%% | %d%% | %d%% | %s / %s" % (100 * r.c150, 100 * r.c500, 100 * r.f150,
                                               f"{r.area:,.0f}", f"{r.reach:,.0f}")
    return "%d%% | %d%% | %d%% | %.1f | %s / %s" % (100 * r.covered, 100 * r.on, 100 * r.false, r.xascat,
                                                    f"{r.area:,.0f}", f"{r.reach:,.0f}")


def main(src, out=None):
    d = pd.read_csv(src)
    d["split"] = pd.to_datetime(d["run"].astype(str), format="%Y%m%d%H").map(cases.split)
    lines = []
    nd = d[d.scope == "ndfd"]
    tune, held, whole = (table(nd[nd.split == "tune"]), table(nd[nd.split == "held_out"]), table(nd))
    lines += ["## Same water, 13 Jan to 31 Mar 2026 (%d case-hours, %d held-out)" % (
        nd.groupby(["dom", "run", "step"]).ngroups, nd[nd.split == "held_out"].groupby(["dom", "run", "step"]).ngroups), ""]
    for L in (34, 48, 64):
        ev_h = held[(held.L == L) & (held.rule == "max3")].events.iloc[0]
        ev_w = whole[(whole.L == L) & (whole.rule == "max3")].events.iloc[0]
        head = ("| line | offset | caught 150 km | caught 500 km | false areas 150 km | area / reach nm2 |" if L == 64
                else "| line | offset | covered | caught on | false (in cell) | area / ASCAT area | area / reach nm2 |")
        lines += ["### %s (%d events held-out, %d all)" % (NAMES[L], ev_h, ev_w), "", head,
                  "|" + "---|" * (head.count("|") - 1)]
        picks = []
        for rule in ("desk", "ndfd", "mean2", "max3"):
            if rule == "desk":
                picks.append((rule, 0, ""))
                continue
            picks.append((rule, 0, "own"))
            if L == 64:
                if rule != "ndfd":
                    picks.append((rule, 12, "+12"))
                continue
            for bar in (0.8, 0.9):
                s = first_at(tune, L, rule, "covered", bar)
                if s is not None and s != 0:
                    picks.append((rule, s, "%d%% bar" % (100 * bar)))
        seen = set()
        for rule, s, why in picks:
            if (rule, s) in seen:
                continue
            seen.add((rule, s))
            for lab, t in (("held-out", held), ("all", whole)):
                r = t[(t.L == L) & (t.rule == rule) & (t.setting == s)]
                if not len(r):
                    continue
                lines.append("| %s, %s | %s | %s |" % (LABEL[rule], lab, ("%+d kt (%s)" % (s, why)) if rule != "desk" else "",
                                                     line(r.iloc[0], L)))
        lines.append("")
    a = d[(d.scope == "all") & (d.rule == "desk")]
    lines += ["## HSF text, complete hours vs every hour with a text (whole winter)", "",
              "| level | hours | events | caught | caught on / within 150 km |", "|---|---|---|---|---|"]
    for L in (34, 48, 64):
        for lab, g in (("complete", a[(a.L == L) & (a.complete == 1)]), ("all", a[a.L == L])):
            r = agg(g)
            if L == 64:
                lines.append("| %s %s | %d | %d | %d%% (500 km) | %d%% |" % (NAMES[L], lab, r["cases"], r["events"],
                                                                         100 * r["c500"], 100 * r["c150"]))
            else:
                lines.append("| %s %s | %d | %d | %d%% | %d%% |" % (NAMES[L], lab, r["cases"], r["events"],
                                                                 100 * r["caught"], 100 * r["on"]))
    text = "\n".join(lines)
    print(text)
    if out:
        Path(out).write_text(text + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
