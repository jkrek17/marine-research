"""Head-to-head with the audit's two fixes, from fair_lines.py rows.

Audit 2026-10-17, items 2, 3 and 7: count the ~60 nm catching ring as warned area, ask that the warned cell
touch the event, score HF at 150 and 300 km as well as 500 km, and give the rule only the runs the desk had.

caught      = events with a warned cell within ~60 nm / events (the study's original test)
caught on   = events with a warned cell on the event itself / events
covered     = ASCAT cells at the level inside the warning / ASCAT cells at the level
false (on)  = seen warned cells with no wind at the level in that cell / seen warned cells
area        = mean warned area per case; reach = the same with the ~60 nm ring, over water

Tune weeks pick each line's offset; held-out weeks are read once.

usage: python3 fair_summary.py ROWS_FAIR.csv [OUT.md]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import cases  # noqa: E402

NAMES = {34: "Gale", 48: "Storm", 64: "Hurricane force"}


def agg(g):
    ev = g["events"].sum()
    out = dict(cases=len(g), events=int(ev), area=g["area_nm2"].mean(), reach=g["reach_nm2"].mean())
    if g["hits"].isna().all():
        for k in (500, 300, 150):
            out["c%d" % k] = g["hits%d" % k].sum() / ev if ev else np.nan
            out["f%d" % k] = g["false%d" % k].sum() / max(g["areas"].sum(), 1)
    else:
        out.update(caught=g["hits"].sum() / ev, on=g["hits_on"].sum() / ev,
                   covered=g["obs_in"].sum() / max(g["obs_cells"].sum(), 1),
                   false=g["bad_cells"].sum() / max(g["cells"].sum(), 1),
                   false_on=g["bad_on"].sum() / max(g["cells"].sum(), 1))
    return out


def table(d):
    return pd.DataFrame([dict(L=L, rule=r, setting=st, **agg(g)) for (L, r, st), g in d.groupby(["L", "rule", "setting"])])


def pick(t, L, rule):
    """The smallest offset that matches the desk's coverage (gale, storm) or 150 km catch (HF) on tune weeks."""
    desk = t[(t.L == L) & (t.rule == "desk")].iloc[0]
    rows = t[(t.L == L) & (t.rule == rule)].sort_values("setting")
    key = "c150" if L == 64 else "covered"
    ok = rows[rows[key] >= desk[key] - 0.005]
    return int((ok if len(ok) else rows.tail(1)).iloc[0]["setting"])


def fmt(r):
    if r["L"] == 64:
        return "%d / %d / %d%% | %d%% | %s / %s" % (
            100 * r.c500, 100 * r.c300, 100 * r.c150, 100 * r.f150, f"{r.area:,.0f}", f"{r.reach:,.0f}")
    return "%d%% / %d%% | %d%% | %d%% / %d%% | %s / %s" % (
        100 * r.caught, 100 * r.on, 100 * r.covered, 100 * r.false, 100 * r.false_on,
        f"{r.area:,.0f}", f"{r.reach:,.0f}")


def main(src, out=None):
    d = pd.read_csv(src)
    d = d[d.deskok == 1].copy()
    d["split"] = pd.to_datetime(d["run"].astype(str), format="%Y%m%d%H").map(cases.split)
    lines = [__doc__.split("\n\n")[1], ""]
    for name, sub, rules in (("All runs at 24 and 48 h (max3 = the runs valid at issuance)", d, ("max3",)),
                             ("24 h only, max3 vs the runs the desk had (avail)", d[(d.step == 24) & (d.has_avail == 1)],
                              ("max3", "avail"))):
        tune, held = table(sub[sub.split == "tune"]), table(sub[sub.split == "held_out"])
        whole = table(sub)
        lines += ["## " + name, ""]
        for L in (34, 48, 64):
            head = ("| line | setting | caught 500/300/150 km | false areas 150 km | area / reach nm2 |" if L == 64 else
                    "| line | setting | caught / caught on | covered | false / false on | area / reach nm2 |")
            lines += ["### %s (%d held-out events, %d whole winter)" % (
                NAMES[L], held[(held.L == L) & (held.rule == "desk")].events.iloc[0],
                whole[(whole.L == L) & (whole.rule == "desk")].events.iloc[0]), "", head,
                "|" + "---|" * (head.count("|") - 1)]
            choices = [("desk", 0)]
            for rule in rules:
                p = pick(tune, L, rule)
                nominal = {34: 1, 48: 7, 64: 12}[L]
                choices += [(rule, nominal)] + ([(rule, p)] if p != nominal else [])
            for rule, s in choices:
                for lab, t in (("held-out", held), ("whole", whole)):
                    r = t[(t.L == L) & (t.rule == rule) & (t.setting == s)].iloc[0]
                    lines.append("| %s %s | %s | %s |" % (rule, lab, "+%d" % s if rule != "desk" else "", fmt(r)))
            lines.append("")
    text = "\n".join(lines)
    print(text)
    if out:
        Path(out).write_text(text + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
