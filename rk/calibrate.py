"""Chance calibration: reliability tables, the page's remap fitter, scores and threshold translation.

Plain numpy in, plain numpy out, so the marine wind page, the GFE tools and later studies can call it.
p is a forecast chance in 0-1, event is 0/1 (or bool); both are arrays of the same shape. Knots are in
percent, as in awips-tools marine_wind/pipeline/calibration.json.

A summed table (table(), add_tables()) holds n, events, sum_p, sum_p2 and sum_p_ev per bin. Tables add, so a
fit can pool many cycles without keeping any cell. Weighted input (w=counts) lets a caller accumulate exact
counts per distinct chance value (member fractions k/n) and expand them here.
"""
import json

import numpy as np

# Fine under 10%, where the storm and hurricane-force chances live.
EDGES = np.array([0, .01, .02, .05, .10, .15, .20, .30, .40, .50, .60, .70, .80, .90, 1.00001])
LEAD_GROUPS = {"le48": (24, 48), "72": (72,), "ge96": (96, 120)}
_FIELDS = ("n", "events", "sum_p", "sum_p2", "sum_p_ev")


def lead_group(step):
    """Lead hour -> page lead group: le48 (+24, +48), 72, ge96 (+96, +120)."""
    return "le48" if step <= 48 else ("72" if step == 72 else "ge96")


# ---- tables ----

def table(p, event, edges=EDGES, w=None):
    """Summed bin table of forecast chance p against event: dict of arrays per bin (n, events, sum_p,
    sum_p2, sum_p_ev). w: optional counts for each element (default 1)."""
    p = np.asarray(p, float).ravel()
    e = np.asarray(event, float).ravel()
    w = np.ones_like(p) if w is None else np.asarray(w, float).ravel()
    k = np.isfinite(p) & np.isfinite(e) & (w > 0)
    p, e, w = p[k], e[k], w[k]
    nb = len(edges) - 1
    b = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, nb - 1)

    def acc(x):
        return np.bincount(b, weights=x, minlength=nb)
    return {"n": acc(w), "events": acc(w * e), "sum_p": acc(w * p), "sum_p2": acc(w * p * p),
            "sum_p_ev": acc(w * p * e)}


def add_tables(*tabs):
    """Sum tables with the same edges."""
    return {f: sum(np.asarray(t[f], float) for t in tabs) for f in _FIELDS}


def reliability(p, event, edges=EDGES):
    """Reliability per bin -> dict: n, events, mean forecast (mean_fc), observed frequency (obs_freq, NaN when
    the bin is empty), edges."""
    t = table(p, event, edges)
    return _rel(t, edges)


def _rel(t, edges=EDGES):
    n = np.asarray(t["n"], float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mf = np.where(n > 0, np.asarray(t["sum_p"]) / n, np.nan)
        of = np.where(n > 0, np.asarray(t["events"]) / n, np.nan)
    return {"n": n, "events": np.asarray(t["events"], float), "mean_fc": mf, "obs_freq": of,
            "edges": np.asarray(edges)}


# ---- the remap ----

def fit(tab, nmin=2000):
    """Remap knots (raw_knots_pct, cal_knots_pct) from a summed table (or a reliability() dict, which has
    mean_fc instead of sum_p).

    Same method as the page's fitter, wind-focus/basins/code/fit_calibration.py fit() (Jason's marine wind
    page, PR #89): each bin's mean raw chance maps to its observed frequency, shrunk toward the raw chance by
    min(1, n / nmin); starts at (0, 0); runs on to (100, 100) when the data stop short; calibrated values
    forced non-decreasing. Unlike the original this takes one truth (the original averaged two analyses) and
    a table, so many cycles can be pooled."""
    n = np.asarray(tab["n"], float)
    ev = np.asarray(tab["events"], float)
    sp = np.asarray(tab["sum_p"], float) if "sum_p" in tab else np.asarray(tab["mean_fc"], float) * n
    xs, ys = [0.0], [0.0]
    for i in range(len(n)):
        if n[i] <= 0:
            continue
        raw, obs = sp[i] / n[i], ev[i] / n[i]
        w = min(1.0, n[i] / nmin)
        xs.append(raw)
        ys.append(w * obs + (1 - w) * raw)
    if xs[-1] < 1.0:
        xs.append(1.0)
        ys.append(1.0)
    ys = np.maximum.accumulate(ys)
    return [round(100 * float(x), 1) for x in xs], [round(100 * float(y), 1) for y in ys]


def apply(p, raw_knots, cal_knots):
    """Remap chances p (0-1) through the knots (percent); returns 0-1."""
    return np.interp(np.asarray(p, float) * 100.0, raw_knots, cal_knots) / 100.0


def cal_at(raw_pct, raw_knots, cal_knots):
    """Calibrated chance (percent) at a raw chance (percent)."""
    return np.interp(raw_pct, raw_knots, cal_knots)


def raw_for(target_pct, raw_knots, cal_knots):
    """Raw chance (percent) whose calibrated value is target_pct: 'which raw share is the 30% line'.
    The lowest raw share that reaches the target (the curve may be flat); NaN if the curve never gets there."""
    raw, cal = np.asarray(raw_knots, float), np.asarray(cal_knots, float)
    if target_pct > cal.max() + 1e-9:
        return float("nan")
    i = int(np.argmax(cal >= target_pct - 1e-9))
    if i == 0 or cal[i] == cal[i - 1]:
        return float(raw[i])
    f = (target_pct - cal[i - 1]) / (cal[i] - cal[i - 1])
    return float(raw[i - 1] + f * (raw[i] - raw[i - 1]))


# ---- scores ----

def brier(p, event, w=None):
    """Mean squared error of the chance against the 0/1 event (lower is better)."""
    p = np.asarray(p, float).ravel()
    e = np.asarray(event, float).ravel()
    w = np.ones_like(p) if w is None else np.asarray(w, float).ravel()
    return float(np.sum(w * (p - e) ** 2) / np.sum(w))


def brier_skill(p, event, clim, w=None):
    """1 - Brier / Brier of always forecasting the climatological frequency clim. 0 = no better than
    climate, 1 = perfect; negative = worse than climate. NaN if climate is perfect (no events or all)."""
    ref = brier(np.full(np.shape(np.ravel(p)), clim), event, w)
    return float("nan") if ref <= 0 else 1.0 - brier(p, event, w) / ref


def reliability_error(tab):
    """Reliability error of a table: sqrt of the n-weighted mean of (mean forecast - observed frequency)^2
    over bins, in 0-1 chance units (0.03 = three points off on average). Takes a table() or reliability()."""
    r = _rel(tab) if "sum_p" in tab else tab
    n = np.asarray(r["n"], float)
    k = n > 0
    if not k.any():
        return float("nan")
    d = (np.asarray(r["mean_fc"])[k] - np.asarray(r["obs_freq"])[k]) ** 2
    return float(np.sqrt(np.sum(n[k] * d) / n[k].sum()))


# ---- the page's file ----

def to_page_json(curves, note="", path=None):
    """Layout of awips-tools marine_wind/pipeline/calibration.json:
    {"note", "thresholds": {"48": {"natl": {"le48": {"raw": [...], "cal": [...]}, "72": ..., "ge96": ...},
    "npac": ...}, "64": ..., "34": ...}}. curves: {(thr, basin, group): (raw_knots, cal_knots)}. Written to
    path when given; returns the dict."""
    out = {"note": note, "thresholds": {}}
    for (thr, basin, group), (raw, cal) in sorted(curves.items(), key=lambda kv: (int(kv[0][0]), kv[0][1], kv[0][2])):
        out["thresholds"].setdefault(str(int(thr)), {}).setdefault(basin, {})[group] = {
            "raw": [float(x) for x in raw], "cal": [float(x) for x in cal]}
    if path is not None:
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    return out
