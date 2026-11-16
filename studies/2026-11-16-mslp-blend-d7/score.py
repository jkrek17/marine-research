"""Scores for one MSLP map against one analysis (design.md Part A scores).

    case(fc, an, mask, basin, an_prev=None) -> (field_row, lows, false_n, n_fc)

field_row  rmse, bias (cos-lat weighted, open water), rmse_ls (both fields Gaussian-smoothed, sigma 300 km,
           then differenced; same weights and mask), sharp (mean |grad p| forecast / analysis over open water
           within 1000 km of analysed lows < 1000 hPa; NaN with none)
lows       one row per analysed low < 1000 hPa (3 deg inside the box), house form rk.score.low_case:
           lat, lon, an_hpa, pos_km (nearest forecast low < 1010 within 1000 km, a miss costs 1000), depth_err_hpa
           (forecast minus analysed; a miss uses the forecast field at the analysed centre), hit (<= 300 km);
           plus pos_h (one-to-one Hungarian match, 1000 km cap and cost for an unmatched low), fc_lat, fc_lon,
           fc_hpa of the nearest forecast low, and along_km / cross_km (forecast minus analysed in the frame of
           the analysed low's track, direction from the nearest analysed low (< 1010) 24 h earlier within
           1000 km; along positive ahead, cross positive to the right; NaN for a miss, no earlier low, or a
           track under 50 km; always NaN at +24 h because the cycle-time analysis is not extracted).
false_n    forecast lows < 1000 with no analysed low < 1005 within 500 km
n_fc       forecast lows < 1000

case_full(...) also returns `fdeep`: forecast lows < 980 hPa with the analysed value they are compared with
(nearest analysed low < 1005 within 500 km, else the analysis at the forecast centre) so strong-low depth is
judged in both directions.

For speed the runner scores one forecast against three truths: prep_fc() and prep_truth() hold what does not
change, and case_full() takes them through `fcp` and `tp`. tests/test_mslp_blend_score.py checks the cached
path against rk.score.low_case.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from rk import score as rks, basins

CAP_KM = 1000.0
SIGMA_KM = 300.0
KM_DEG = 111.195
_GRID = {}


def _grid(basin):
    if basin not in _GRID:
        lats, lons = basins.grid(basin)
        la2, lo2 = np.meshgrid(lats, lons, indexing="ij")
        _GRID[basin] = (lats, lons, la2, lo2)
    return _GRID[basin]


def _smooth(f, basin):
    lats = _grid(basin)[0]
    sy = SIGMA_KM / (0.25 * KM_DEG)
    sx = sy / np.cos(np.radians(float(np.mean(lats))))
    return ndimage.gaussian_filter(np.asarray(f, np.float64), (sy, sx), mode="nearest")


def _gradmag(f, basin):
    """|grad p| in hPa per 100 km."""
    lats, _, la2, _ = _grid(basin)
    dy = 0.25 * KM_DEG
    gy, gx = np.gradient(np.asarray(f, np.float64), dy, axis=0), np.gradient(np.asarray(f, np.float64), 1.0, axis=1)
    gx = gx / (dy * np.cos(np.radians(la2)))
    return 100.0 * np.hypot(gy, gx)


def prep_fc(fc, basin):
    fc = np.asarray(fc, np.float32)
    return {"f": fc, "lows": rks.find_lows(fc, basin, 1010.0), "ls": _smooth(fc, basin), "grad": _gradmag(fc, basin)}


def prep_truth(an, mask, basin, an_prev=None):
    an = np.asarray(an, np.float32)
    lows = rks.find_lows(an, basin, 1000.0, inset_deg=3.0)
    t = {"f": an, "mask": np.asarray(mask).astype(bool), "lows": lows,
         "lows_all": rks.find_lows(an, basin, 1005.0), "ls": _smooth(an, basin), "grad": _gradmag(an, basin),
         "prev": None if an_prev is None else rks.find_lows(np.asarray(an_prev, np.float32), basin, 1010.0)}
    _, _, la2, lo2 = _grid(basin)
    reg = np.zeros(an.shape, bool)
    for r in lows.itertuples():
        reg |= rks.km(la2, lo2, r.lat, r.lon) <= 1000.0
    t["region"] = reg & t["mask"]
    return t


def _hungarian(truth, fc):
    """One-to-one position error per analysed low; unmatched or beyond the cap costs the cap."""
    n = len(truth)
    out = np.full(n, CAP_KM)
    if n == 0 or len(fc) == 0:
        return out
    c = np.minimum(rks.km(truth.lat.to_numpy()[:, None], truth.lon.to_numpy()[:, None],
                          fc.lat.to_numpy()[None, :], fc.lon.to_numpy()[None, :]), CAP_KM)
    r, k = linear_sum_assignment(c)
    out[r] = c[r, k]
    return out


def _en(lat0, lon0, lat1, lon1):
    """east, north displacement in km from point 0 to point 1 (tangent plane at the mid latitude)."""
    dl = (lon1 - lon0 + 180) % 360 - 180
    return dl * KM_DEG * np.cos(np.radians((lat0 + lat1) / 2)), (lat1 - lat0) * KM_DEG


def _along_cross(m, prev):
    n = len(m)
    al, cr = np.full(n, np.nan), np.full(n, np.nan)
    if prev is None or len(prev) == 0:
        return al, cr
    for i, r in enumerate(m.itertuples()):
        if not r.matched or not np.isfinite(r.fc_lat):
            continue
        d = rks.km(r.lat, r.lon, prev.lat.to_numpy(), prev.lon.to_numpy())
        j = int(d.argmin())
        if d[j] > 1000.0:
            continue
        te, tn = _en(prev.lat.iloc[j], prev.lon.iloc[j], r.lat, r.lon)
        norm = float(np.hypot(te, tn))
        if norm < 50.0:
            continue
        te, tn = te / norm, tn / norm
        ee, en = _en(r.lat, r.lon, r.fc_lat, r.fc_lon)
        al[i] = ee * te + en * tn
        cr[i] = ee * tn - en * te          # right of the direction of travel is positive
    return al, cr


def case_full(fc, an, mask, basin, an_prev=None, fcp=None, tp=None):
    lats, _, la2, lo2 = _grid(basin)
    fcp = fcp or prep_fc(fc, basin)
    tp = tp or prep_truth(an, mask, basin, an_prev)
    f, a, mk = fcp["f"], tp["f"], tp["mask"]
    e = rks.field_error(f, a, lats, mk)
    els = rks.field_error(fcp["ls"], tp["ls"], lats, mk)
    reg = tp["region"]
    sharp = float(fcp["grad"][reg].mean() / tp["grad"][reg].mean()) if reg.any() and tp["grad"][reg].mean() > 0 else np.nan
    row = {"rmse": e["rmse"], "bias": e["bias"], "rmse_ls": els["rmse"], "sharp": sharp}

    truth, fl = tp["lows"], fcp["lows"]
    m = rks.match_lows(truth, fl, CAP_KM, miss_penalty_km=CAP_KM, miss_depth="field", fc_msl=f, basin=basin)
    lows = pd.DataFrame({"lat": m.lat.to_numpy(), "lon": m.lon.to_numpy(), "an_hpa": m.hpa.to_numpy(),
                         "pos_km": m.pos_err_km.to_numpy(), "depth_err_hpa": m.depth_err_hpa.to_numpy(),
                         "hit": (m.matched & (m.pos_err_km <= 300.0)).to_numpy()})
    lows["pos_h"] = _hungarian(truth, fl)
    lows["fc_lat"] = np.where(m.matched, m.fc_lat, np.nan)
    lows["fc_lon"] = np.where(m.matched, m.fc_lon, np.nan)
    lows["fc_hpa"] = np.where(m.matched, m.fc_hpa, np.nan)
    lows["along_km"], lows["cross_km"] = _along_cross(m, tp["prev"])
    deep = fl[fl.hpa < 1000.0]
    false_n = int(rks.false_lows(tp["lows_all"], deep, 500.0))

    sd = fl[fl.hpa < 980.0]
    rows = []
    ta = tp["lows_all"]
    for r in sd.itertuples():
        if len(ta):
            d = rks.km(r.lat, r.lon, ta.lat.to_numpy(), ta.lon.to_numpy())
            j = int(d.argmin())
            an_h = float(ta.hpa.iloc[j]) if d[j] <= 500.0 else float(basins.sample(a, basin, r.lat, r.lon))
        else:
            an_h = float(basins.sample(a, basin, r.lat, r.lon))
        rows.append((r.lat, r.lon, r.hpa, an_h, r.hpa - an_h))
    fdeep = pd.DataFrame(rows, columns=["lat", "lon", "fc_hpa", "an_hpa", "err_hpa"])
    return {"field": row, "lows": lows, "false_n": false_n, "n_fc": int(len(deep)), "fdeep": fdeep}


def case(fc, an, mask, basin, an_prev=None):
    r = case_full(fc, an, mask, basin, an_prev)
    return r["field"], r["lows"], r["false_n"], r["n_fc"]
