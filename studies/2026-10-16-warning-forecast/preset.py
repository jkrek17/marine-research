#!/usr/bin/env python3
"""Standing scores for the warning-forecast study: model and ensemble warning rules against ASCAT.

    python3 studies/2026-10-16-warning-forecast/preset.py --start YYYY-MM-DD --end YYYY-MM-DD --out results.csv

One row per ISO week (of the forecast run) x basin x method x metric (columns in rk/preset.py). Cases are the
study's: 00 and 12 UTC runs, +24 and +48 h, both basins, scored inside the OPC high seas area over open water
(score_warnings.py: opc_area, analysis mask). Metrics, per level (gale 34 kt, storm 48 kt):
  gale_catch / storm_catch                events caught / ASCAT events (>= 2 connected cells at or above the
                                          level; hit = warned cell within 4 cells); n = events
  gale_fa_area / storm_fa_area            seen warned cells with no verifying wind within 4 cells / seen
                                          warned cells; n = seen warned cells
  gale_area_nm2 / storm_area_nm2          mean warned area per case, nm2; n = cases
Method names are `<rule>@<setting>`: `model_ifs@6` = IFS 10 m wind + 6 kt >= level; `pmem@0.05` = share of
all ensemble members (GEFS, ENS, AIFS ENS pooled) at or above the level >= 0.05.

Frozen values and where they come from:
  rules, thresholds, snapping, events, hit/false definitions   score_warnings.py and rk.score.warning_events
                                    with its defaults (design.md "Truth", "Cases"); the rules are score_warnings
                                    `model_<m>` and `pmem`, evaluated exactly as there (wind + d >= L; share of
                                    members >= L at the cell >= p)
  truth gale/storm                  rk.truth.ascat_grid (real 10 m wind, Metop-B/C intercalibrated, +-90 min)
  settings in RULES                 PROVISIONAL. The study is still running (STUDIES.md: "Running"), has no
                                    findings and no chosen rule. They are what summarize.choose() picks on the
                                    tune weeks (rk.cases.split) of the study's trial table
                                    /mnt/project-files/warning-experiment/results/trial.csv (Nov-Dec 2025, rows
                                    with a fully parsed desk text): >= 80% detection with false-alarm cells
                                    below the desk's, restricted to rules the store can compute. Gale: model_ifs
                                    +0 (tune 81% detection, FA 4%) and pmem 0.20 (86%, 8%); storm: model_ifs +6
                                    (82%, 9%) and pmem 0.05 (89%, 15%). Replace when the study freezes its rules.
  hurricane force                   not scored: no rule passed 80% on the tune weeks, so none is frozen
Checked against the study's trial table (Nov 1-25 2025, 78 cases) with the trial's own truth settings
(ASCAT_KW = +-180 min, equivalent-neutral, no intercalibration): model_ifs@0 gale catch 79.7% vs 80.0%, false-alarm
cells 6.3% vs 6.3%, warned area 120.2k vs 120.7k nm2; pmem@0.05 storm catch 76.4% vs 76.8%. The rule and scoring
path match; the frozen truth (+-90 min, real wind, intercalibrated) finds fewer events in the same cases
(253 gale events for model_ifs@0 against 411), so default-truth numbers are not comparable with the trial's.
Not available through rk (reported as missing inputs, nothing copied):
  * the desk (issued High Seas Forecast areas): masks come from the HSF archive and parser under
    /mnt/project-files/hsf and the study's desk_masks.py; there is no rk reader. So no `area_ratio` against the
    desk and no desk method.
  * `blend`, `lift*`, `pnbr`, `pmem-<dT>` rules: need every member's 10 m speed (the study's private cases
    under RK_DATA/extra/warning-experiment/cases); the store keeps member statistics, from which only `pmem`
    at the level itself (pooled p34/p48 weighted by member count) can be formed. Not scored.
Without --skip-missing these are errors; with it the rest is written.

CI (drift flag): the study published no intervals. CI below is computed from the trial table by resampling whole
ISO weeks (2000 draws, 2.5/97.5, seed 0) of the same rule rows, ALL trial weeks and all hours: it is a
reference band from 8 early weeks that include the tuning weeks, so it is optimistic, AND the trial used a
different truth (+-180 min, equivalent-neutral wind) than ASCAT_KW's frozen one, so the false-alarm and
catch flags are not trustworthy until the study freezes its rules and publishes intervals under its own truth. `--derive-ci PATH` prints it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

STUDY = "2026-10-16-warning-forecast"
TRUTH = "ASCAT real 10 m wind (rk.truth.ascat_grid), inside the OPC high seas area"
LEVELS = {"gale": 34, "storm": 48}
STEPS = (24, 48)
# rk.truth.ascat_grid keyword arguments: the rk defaults are the study's frozen truth (design.md). The check against
# the early trial table overrides them (that table used +-180 min and equivalent-neutral speeds).
ASCAT_KW = {}
ENSEMBLES = ("gefs", "ens", "aifs-ens")
# level -> [(rule, setting)], provisional (see docstring)
RULES = {34: [("model_ifs", 0.0), ("pmem", 0.20)], 48: [("model_ifs", 6.0), ("pmem", 0.05)]}
TRIAL = "trial.csv (/mnt/project-files/warning-experiment/results, Nov-Dec 2025, 8 weeks), week-resampled"
SRC = TRIAL

# (method, metric) -> (lo, hi, source). Generated by --derive-ci; do not edit by hand.
CI = {
    ("model_ifs@0", "gale_catch"): (0.7475, 0.8331, SRC),
    ("model_ifs@0", "gale_fa_area"): (0.0270, 0.0877, SRC),
    ("model_ifs@0", "gale_area_nm2"): (101415.2936, 172393.1297, SRC),
    ("pmem@0.2", "gale_catch"): (0.7905, 0.9043, SRC),
    ("pmem@0.2", "gale_fa_area"): (0.0584, 0.1312, SRC),
    ("pmem@0.2", "gale_area_nm2"): (206543.6231, 312013.9332, SRC),
    ("model_ifs@6", "storm_catch"): (0.6559, 0.8475, SRC),
    ("model_ifs@6", "storm_fa_area"): (0.0786, 0.2850, SRC),
    ("model_ifs@6", "storm_area_nm2"): (6604.4097, 17289.4400, SRC),
    ("pmem@0.05", "storm_catch"): (0.7017, 0.9213, SRC),
    ("pmem@0.05", "storm_fa_area"): (0.1160, 0.2534, SRC),
    ("pmem@0.05", "storm_area_nm2"): (19316.2603, 35666.8076, SRC),
}


def method_name(rule, setting):
    return "%s@%g" % (rule, setting)


def _warned(rule, setting, L, speed, pens):
    """Boolean warned grid for one rule at level L (score_warnings.py rules model_<m> and pmem)."""
    if rule.startswith("model_"):
        return speed[rule[6:]] + setting >= L
    if rule == "pmem":
        return pens >= setting
    raise ValueError(rule)


def run(start, end, skip_missing=False, only=None):
    """Rows and missing-input notes for cycles start..end. `only`: optional set of (basin, cycle, step) to score
    (used to compare with the study's trial table case by case)."""
    import datetime as dt
    import numpy as np
    from rk import cases, store, truth
    from rk.basins import BASINS, grid
    from rk.preset import iso_week
    from rk import score
    from score_warnings import opc_area

    acc = {}       # (week, basin, method, level) -> sums
    n_truth = n_fc = 0
    for basin in BASINS:
        lats, _ = grid(basin)
        cell_nm2 = 225 * np.cos(np.radians(lats))[:, None]
        for cyc0 in cases.cycles(basin, start, end, hour=0) + cases.cycles(basin, start, end, hour=12):
            for step in STEPS:
                if only is not None and (basin, cyc0, step) not in only:
                    continue
                valid = cyc0 + dt.timedelta(hours=step)
                an = store.analysis(basin, valid)
                if an is None:
                    continue
                seen, spd = truth.ascat_grid(basin, valid, **ASCAT_KW)
                n_truth += 1
                sea = opc_area(basin) & an["mask"].astype(bool)
                if seen is None:        # study: a case without ASCAT stays in with nothing seen
                    seen, spd = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
                seen = seen & sea
                need = sorted({r[6:] for L in RULES for r, _ in RULES[L] if r.startswith("model_")})
                dets = {m: store.load_det(basin, cyc0, m, step) for m in need}
                ens = [store.load_ens(basin, cyc0, e, step) for e in ENSEMBLES]
                if all(v is None for v in dets.values()) and any(e is None for e in ens):
                    continue
                n_fc += 1
                speed = {m: v["speed"] for m, v in dets.items() if v is not None}
                wk = iso_week(cyc0)
                for L in (34, 48):
                    pens = None
                    if all(e is not None for e in ens):
                        key = "p%d" % L
                        pens = sum(e[key] * float(e["n"]) for e in ens) / sum(float(e["n"]) for e in ens)
                    for rule, setting in RULES[L]:
                        if (rule == "pmem" and pens is None) or (rule.startswith("model_") and rule[6:] not in speed):
                            continue
                        w = _warned(rule, setting, L, speed, pens)
                        r = score.warning_events(w, spd, seen, L, mask=sea)
                        a = acc.setdefault((wk, basin, method_name(rule, setting), L), dict(
                            events=0, hits=0, cells=0, bad_cells=0, area=0.0, cases=0))
                        a["events"] += r["events"]; a["hits"] += r["hits"]
                        a["cells"] += r["cells"]; a["bad_cells"] += r["bad_cells"]
                        a["area"] += float((cell_nm2 * (w & sea)).sum()); a["cases"] += 1
    out = []
    names = {v: k for k, v in LEVELS.items()}
    for (wk, basin, method, L), a in sorted(acc.items()):
        lv = names[L]
        base = dict(study=STUDY, week=wk, basin=basin, method=method, truth=TRUTH)
        if a["events"]:
            out.append(dict(base, metric="%s_catch" % lv, value=a["hits"] / a["events"], n=a["events"]))
        if a["cells"]:
            out.append(dict(base, metric="%s_fa_area" % lv, value=a["bad_cells"] / a["cells"], n=a["cells"]))
        out.append(dict(base, metric="%s_area_nm2" % lv, value=a["area"] / a["cases"], n=a["cases"]))
    missing = []
    if not n_truth:
        missing.append("truth: no analyses for %s..%s through rk.store.analysis" % (start.date(), end.date()))
    elif not n_fc:
        missing.append("gfs/ifs/aifs 10 m wind at +24/+48 h not in the store for %s..%s" % (start.date(), end.date()))
    missing.append("desk (issued HSF warning areas): no rk reader; masks come from /mnt/project-files/hsf and "
                   "desk_masks.py, so there is no desk method and no area_ratio against it")
    missing.append("blend, lift*, pnbr and pmem-<dT> rules need every member's 10 m speed (private cases under "
                   "RK_DATA/extra/warning-experiment/cases); the store holds member statistics only")
    return out, missing


def derive_ci(path):
    """Print the CI block for this file from the study's trial table (see module docstring)."""
    import numpy as np
    import pandas as pd
    d = pd.read_csv(path, dtype={"run": str})
    d["wk"] = pd.to_datetime(d["run"], format="%Y%m%d%H").map(lambda t: t.isocalendar()[0] * 100 + t.isocalendar()[1])
    rng = np.random.default_rng(0)
    lines = []
    for L, lv in ((34, "gale"), (48, "storm")):
        for rule, setting in RULES[L]:
            g = d[(d.L == L) & (d.rule == rule) & (d.setting == setting)]
            by = g.groupby("wk")[["ev", "hit", "wseen", "wbad", "area"]].sum()
            by["cases"] = g.groupby("wk").size()
            for metric, num, den in (("catch", "hit", "ev"), ("fa_area", "wbad", "wseen"), ("area_nm2", "area", "cases")):
                a, b = by[num].to_numpy(float), by[den].to_numpy(float)
                idx = rng.integers(0, len(by), size=(2000, len(by)))
                lo, hi = np.percentile(a[idx].sum(1) / b[idx].sum(1), [2.5, 97.5])
                lines.append('    ("%s", "%s_%s"): (%.4f, %.4f, SRC),' % (method_name(rule, setting), lv, metric, lo, hi))
    print("CI = {\n" + "\n".join(lines) + "\n}")


if __name__ == "__main__":
    if "--derive-ci" in sys.argv:
        derive_ci(sys.argv[sys.argv.index("--derive-ci") + 1])
        sys.exit(0)
    from rk.preset import cli
    sys.exit(cli(STUDY, run))
