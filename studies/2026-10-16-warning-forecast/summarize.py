"""Detection, false alarms and warned area per rule against the desk, from score_warnings.py rows.

Rules are chosen on the tune weeks only (rk.cases.split): at least 80% detection with area false alarms
and mean warned area no worse than the desk on the same hours. The chosen rules are then read on the
held-out weeks, with a 90% interval from resampling whole weeks, and month by month.
Compared on hours where the desk text parsed completely (deskok == 1), so every rule meets the same events.

detection = events caught / events (ASCAT areas for gale and storm, archive HF lows for HF)
FA area   = warned cells with no verifying wind within ~60 nm / warned cells judged
            (cells ASCAT saw for gale and storm; for HF all warned cells, verifying = within HF_KM of an HF low)
FA areas  = warned areas with no verifying wind / warned areas judged
area      = mean warned area per case, nm2

usage: python3 summarize.py ROWS.csv [OUT.md]
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
    ev, hit = g["events"].sum(), g["hits"].sum()
    return pd.Series(dict(cases=len(g), events=ev, pod=hit / ev if ev else np.nan,
                          fa_area=g["bad_cells"].sum() / max(g["cells"].sum(), 1),
                          fa_obj=g["false"].sum() / max(g["judged"].sum(), 1), area=g["area_nm2"].mean()))


def week(run):
    return pd.to_datetime(run, format="%Y%m%d%H").map(lambda t: tuple(t.isocalendar()[:2]))


def boot(g, n=2000, seed=0):
    by = g.groupby(week(g["run"]))[["events", "hits"]].sum().values
    if len(by) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    s = [by[rng.integers(0, len(by), len(by))].sum(0) for _ in range(n)]
    p = [h / e for e, h in s if e]
    return np.percentile(p, [5, 95]) if p else (np.nan, np.nan)


def load(path):
    d = pd.read_csv(path, dtype={"run": str, "valid": str})
    d["split"] = pd.to_datetime(d["run"], format="%Y%m%d%H").map(cases.split)
    d["month"] = d["run"].str[:6]
    return d[d["deskok"] == 1]


def choose(d, L, top=6):
    dl = d[(d["L"] == L) & (d["split"] == "tune")]
    t = dl.groupby(["rule", "setting"]).apply(agg, include_groups=False).reset_index()
    desk = t[t["rule"] == "desk"].iloc[0]
    ok = t[(t["rule"] != "desk") & (t["pod"] >= 0.8) & (t["fa_area"] <= desk.fa_area) & (t["area"] <= desk.area)]
    return desk, t, ok.sort_values(["fa_area", "area"]).head(top)


def main(path, out=None):
    d = load(path)
    lines = ["Hours with a fully parsed desk text only. Tune weeks pick the rule; held-out weeks are read once.\n"]
    for L in (34, 48, 64):
        desk, t, best = choose(d, L)
        te = d[(d["L"] == L) & (d["split"] == "held_out")]
        lines.append("## %s (%d kt)\n" % (NAMES[L], L))
        lines.append("Desk, tune weeks: detection %.0f%% of %d events, FA area %.0f%%, FA areas %.0f%%, area %.0f nm2\n"
                     % (100 * desk.pod, desk.events, 100 * desk.fa_area, 100 * desk.fa_obj, desk.area))
        if best.empty:
            lines.append("No rule reaches 80% on the tune weeks within the desk's false alarms and area. Highest:")
            for _, r in t[t["rule"] != "desk"].sort_values("pod", ascending=False).head(5).iterrows():
                lines.append("- %s %s: %.0f%%, FA area %.0f%%, area %.0f" % (r["rule"], r["setting"], 100 * r["pod"],
                                                                         100 * r["fa_area"], r["area"]))
            lines.append("")
            continue
        lines.append("| rule | setting | tune detection | held-out detection [90%] | held-out FA area | held-out area nm2 |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in best.iterrows():
            g = te[(te["rule"] == r["rule"]) & (te["setting"] == r["setting"])]
            a = agg(g)
            lo, hi = boot(g)
            lines.append("| %s | %s | %.0f%% | %.0f%% [%.0f-%.0f] | %.0f%% | %.0f |" % (
                r["rule"], r["setting"], 100 * r["pod"], 100 * a.pod, 100 * lo, 100 * hi, 100 * a.fa_area, a.area))
        g = te[te["rule"] == "desk"]
        a = agg(g)
        lo, hi = boot(g)
        lines.append("| desk | | %.0f%% | %.0f%% [%.0f-%.0f] | %.0f%% | %.0f |\n" % (
            100 * desk.pod, 100 * a.pod, 100 * lo, 100 * hi, 100 * a.fa_area, a.area))
        r = best.iloc[0]
        lines.append("By month, all weeks (best rule %s %s vs desk): detection, events" % (r["rule"], r["setting"]))
        dl = d[d["L"] == L]
        for m, g in dl.groupby("month"):
            a1 = agg(g[(g["rule"] == r["rule"]) & (g["setting"] == r["setting"])])
            a2 = agg(g[g["rule"] == "desk"])
            lines.append("- %s: %.0f%% vs desk %.0f%%, %d events" % (m, 100 * a1.pod, 100 * a2.pod, a1.events))
        lines.append("")
    txt = "\n".join(lines)
    print(txt)
    if out:
        Path(out).write_text(txt + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
