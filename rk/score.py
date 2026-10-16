"""Scores for wind grids. Forecast and truth are on the same grid; wind in kt.

Every function returns NaN (never an error) when its denominator is zero.
An optional boolean `mask` limits the cells counted (True = use the cell).
Cells that are NaN in either field are never counted.
"""
import numpy as np
import pandas as pd


def _prep(fc, ob, mask=None):
    fc = np.asarray(fc, float)
    ob = np.asarray(ob, float)
    ok = np.isfinite(fc) & np.isfinite(ob)
    if mask is not None:
        ok &= np.asarray(mask, bool)
    return fc, ob, ok


def contingency(fc, ob, thr, mask=None):
    """(hits, false_alarms, misses) for wind >= thr."""
    fc, ob, ok = _prep(fc, ob, mask)
    f, o = fc >= thr, ob >= thr
    return (int(np.sum(f & o & ok)), int(np.sum(f & ~o & ok)), int(np.sum(~f & o & ok)))


def _div(a, b):
    return float("nan") if b == 0 else a / b


def csi(fc, ob, thr, mask=None):
    """Critical success index: hits / (hits + false alarms + misses)."""
    h, f, m = contingency(fc, ob, thr, mask)
    return _div(h, h + f + m)


def pod(fc, ob, thr, mask=None):
    """Probability of detection: hits / (hits + misses)."""
    h, f, m = contingency(fc, ob, thr, mask)
    return _div(h, h + m)


def far(fc, ob, thr, mask=None):
    """False alarm ratio: false alarms / (hits + false alarms)."""
    h, f, m = contingency(fc, ob, thr, mask)
    return _div(f, h + f)


def area_ratio(fc, ob, thr, mask=None):
    """Forecast area / observed area at the threshold (1 = right size)."""
    h, f, m = contingency(fc, ob, thr, mask)
    return _div(h + f, h + m)


def fss(fc, ob, thr, n=5, mask=None):
    """Fractions skill score with an n x n neighbourhood (n=5 is about 140 km at 0.25 deg).

    Masked or NaN cells count as no event and are left out of the final mean.
    """
    from scipy import ndimage
    fc, ob, ok = _prep(fc, ob, mask)
    pf = ndimage.uniform_filter(((fc >= thr) & ok).astype(float), n, mode="constant")
    po = ndimage.uniform_filter(((ob >= thr) & ok).astype(float), n, mode="constant")
    if not ok.any():
        return float("nan")
    pf, po = pf[ok], po[ok]
    den = np.mean(pf ** 2) + np.mean(po ** 2)
    return float("nan") if den == 0 else float(1 - np.mean((pf - po) ** 2) / den)


def error(fc, ob, min_kt=25, mask=None):
    """Bias, MAE and RMSE (forecast minus truth) over cells where either is >= min_kt."""
    fc, ob, ok = _prep(fc, ob, mask)
    sel = ok & ((fc >= min_kt) | (ob >= min_kt))
    n = int(sel.sum())
    if n == 0:
        return {"bias": np.nan, "mae": np.nan, "rmse": np.nan, "n": 0}
    d = fc[sel] - ob[sel]
    return {"bias": float(d.mean()), "mae": float(np.abs(d).mean()),
            "rmse": float(np.sqrt((d ** 2).mean())), "n": n}


def tile_peaks(fc_at_obs, ob, lat, lon, size_deg=5, min_n=150, min_peak=34):
    """Compare peak winds tile by tile (size_deg boxes) at observation points.

    fc_at_obs: forecast sampled at the observation points; ob: observed speed there.
    Keeps tiles with at least min_n points where either peak is >= min_peak.
    One row per tile: n, lat0, lon0, obs_max, obs_p98, fc_max, fc_p98, err_max, err_p98
    (errors are forecast minus observed).
    """
    cols = ["tile", "lat0", "lon0", "n", "obs_max", "obs_p98", "fc_max", "fc_p98", "err_max", "err_p98"]
    fc = np.asarray(fc_at_obs, float)
    ob = np.asarray(ob, float)
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float) % 360
    ok = np.isfinite(fc) & np.isfinite(ob) & np.isfinite(lat) & np.isfinite(lon)
    if not ok.any():
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame({"fc": fc[ok], "ob": ob[ok]})
    df["iy"] = np.floor(lat[ok] / size_deg).astype(int)
    df["ix"] = np.floor(lon[ok] / size_deg).astype(int)
    rows = []
    for (iy, ix), g in df.groupby(["iy", "ix"]):
        if len(g) < min_n:
            continue
        r = {"tile": f"{iy * size_deg}_{ix * size_deg}", "lat0": iy * size_deg, "lon0": ix * size_deg,
             "n": len(g), "obs_max": g.ob.max(), "obs_p98": np.percentile(g.ob, 98),
             "fc_max": g.fc.max(), "fc_p98": np.percentile(g.fc, 98)}
        if max(r["obs_max"], r["fc_max"]) < min_peak:
            continue
        r["err_max"] = r["fc_max"] - r["obs_max"]
        r["err_p98"] = r["fc_p98"] - r["obs_p98"]
        rows.append(r)
    return pd.DataFrame(rows, columns=cols)


def points(fc, basin, obs):
    """Sample a forecast grid (kt, basin crop) at observation points.

    obs: dict or DataFrame with lat, lon and speed_kt (or spd_kt).
    Returns a DataFrame: lat, lon, obs_kt, fc_kt, err (forecast minus obs), abs_err.
    """
    from rk.basins import sample  # written elsewhere; imported late
    o = pd.DataFrame(dict(obs)) if not isinstance(obs, pd.DataFrame) else obs
    col = "speed_kt" if "speed_kt" in o else "spd_kt"
    lat = o["lat"].to_numpy(float)
    lon = o["lon"].to_numpy(float)
    fcv = np.asarray(sample(fc, basin, lat, lon), float)
    out = pd.DataFrame({"lat": lat, "lon": lon % 360, "obs_kt": o[col].to_numpy(float), "fc_kt": fcv})
    out["err"] = out.fc_kt - out.obs_kt
    out["abs_err"] = out.err.abs()
    return out
