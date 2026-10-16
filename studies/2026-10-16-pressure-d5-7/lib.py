"""Shared pieces for the day 5-7 lows study: store path, grids, and the scoring rules in preregistration.md.

Low finding, distances, matching and false lows come from the research kit (jkrek17/marine-research,
rk.score, rk.cases), so this study's numbers and the kit's agree. This file adds only the study's headline
form: position error capped at 1000 km (a miss costs 1000 km) and depth error at the nearest low or, if
none within 1000 km, at the analysed centre.
"""
import os, sys, datetime as dt
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root, for rk
from rk import score as rks, cases as rkc, paths as rkp

# the full-member MSLP set is study-specific: local cache, RK_CACHE/extra/mslp-d5-7 (README there)
CACHE = os.environ.get("PCACHE") or str(rkp.cache("extra", "mslp-d5-7", "x").parent)
RECORDS = str(rkp.cache("extra", "mslp-d5-7-records", "x").parent)       # per-case score records (pickles, local)
RESULTS = str(Path(__file__).resolve().parent / "results")               # small tables, in git
DOMS = {"natl": (67.0, 30.0, 285.0, 359.75), "npac": (67.0, 30.0, 160.0, 245.0)}
LAT = {k: np.linspace(n, s, int((n - s) * 4) + 1) for k, (n, s, w, e) in DOMS.items()}
LON = {k: np.arange(int(w * 4), int(e * 4) + 1) * 0.25 for k, (n, s, w, e) in DOMS.items()}
LAT2 = {k: v[::2] for k, v in LAT.items()}
LON2 = {k: v[::2] for k, v in LON.items()}
STEPS = (120, 144, 168)
R_EARTH = 6371.0


def dec(a):
    return a.astype(np.float32) / 10.0 + 1000.0      # stored hPa*10 - 10000 -> hPa


km = rks.km


def find_lows(f, dom, thresh, half=False, inset_deg=0.0, size=13):
    """rk.score.find_lows as an array (k, 3) lat, lon, hPa; a 0.5 deg field is first put on the 0.25 deg grid."""
    if half:
        f = to_quarter(f, dom)
    return rks.find_lows(f, dom, below=thresh, size=size, inset_deg=inset_deg)[["lat", "lon", "hpa"]].to_numpy()


def to_quarter(f, dom):
    """0.5 deg field (every 2nd 0.25 point) -> 0.25 deg grid by linear interpolation"""
    ny, nx = len(LAT[dom]), len(LON[dom])
    yi, xi = np.arange(ny) / 2.0, np.arange(nx) / 2.0
    y0 = np.clip(np.floor(yi).astype(int), 0, f.shape[0] - 1); y1 = np.clip(y0 + 1, 0, f.shape[0] - 1); wy = (yi - y0)[:, None]
    x0 = np.clip(np.floor(xi).astype(int), 0, f.shape[1] - 1); x1 = np.clip(x0 + 1, 0, f.shape[1] - 1); wx = (xi - x0)[None, :]
    g = f[y0] * (1 - wy) + f[y1] * wy
    return g[:, x0] * (1 - wx) + g[:, x1] * wx


def dedupe(L, sep=150.0):
    """keep the deepest of minima closer than sep km (same rule as rk.score.find_lows), for member low lists"""
    if len(L) < 2:
        return L
    L = L[np.argsort(L[:, 2])]
    keep = []
    for i in range(len(L)):
        if all(km(L[i, 0], L[i, 1], L[j, 0], L[j, 1]) > sep for j in keep):
            keep.append(i)
    return L[keep]


def value_at(f, dom, lat, lon, half=False):
    la, lo = (LAT2[dom], LON2[dom]) if half else (LAT[dom], LON[dom])
    return f[np.abs(la - lat).argmin(), np.abs(lo - lon).argmin()]


def analysed_lows(an, dom):
    return find_lows(an, dom, 1000.0, inset_deg=3.0)


def score(truth, fc_lows, fc_field, dom, half=False):
    """truth (k,3) analysed lows; fc_lows (m,3) forecast lows (any < 1010).
    Per analysed low: pos error (cap 1000), depth error, hit300. Plus false lows count, n forecast lows < 1000."""
    rows = []
    for la, lo, p in truth:
        if len(fc_lows):
            d = km(la, lo, fc_lows[:, 0], fc_lows[:, 1])
            j = int(d.argmin())
            dist = float(d[j])
        else:
            dist = 1e9
        if dist <= 1000:
            dp = fc_lows[j, 2] - p
        else:
            dp = value_at(fc_field, dom, la, lo, half) - p if fc_field is not None else np.nan
        rows.append((min(dist, 1000.0), dp, dist <= 300, p))
    return np.array(rows, np.float64).reshape(-1, 4)


def false_lows(truth_all, fc_lows):
    """forecast lows < 1000 with no analysed low < 1005 within 500 km (rk.score.false_lows, 500 km radius)."""
    f = fc_lows[fc_lows[:, 2] < 1000] if len(fc_lows) else np.zeros((0, 3))
    return rks.false_lows(truth_all, f, radius_km=500.0), len(f)


def held_week(d):
    """research-kit held-out set (rk.cases.held_out): ISO week w of year y with (y*53 + w) % 5 == 0."""
    return rkc.held_out(d)


def held_out(cycle):
    """judged on the cycle date (forecast start), as the kit defines it"""
    return held_week(cycle)


def tune_ok(cycle, valid):
    """tuning cases: neither the run nor its valid time falls in a held-out week (no shared weather)"""
    return not held_week(cycle) and not held_week(valid)


def score_vals(truth, fc_lows, fvals):
    """lib.score with the field values at the analysed centres given (for re-scoring kept lows cheaply)"""
    rows = []
    for (la, lo, p), fv in zip(truth, fvals):
        if len(fc_lows):
            d = km(la, lo, fc_lows[:, 0], fc_lows[:, 1])
            j = int(d.argmin()); dist = float(d[j])
        else:
            dist = 1e9
        dp = fc_lows[j, 2] - p if dist <= 1000 else fv - p
        rows.append((min(dist, 1000.0), dp, dist <= 300, p))
    return np.array(rows, np.float64).reshape(-1, 4)
