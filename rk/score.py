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


# ---- low centres (cyclone objects), ported from the day 5-7 lows study's lib.py ----

_LOW_COLS = ["lat", "lon", "hpa"]
_R_EARTH = 6371.0


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Longitudes in any convention (0-360 or -180..180); arrays broadcast."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians((np.asarray(lon2, float) - np.asarray(lon1, float) + 180) % 360 - 180)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _empty_lows():
    return pd.DataFrame({c: np.array([], float) for c in _LOW_COLS})


def _as_lows(x):
    if x is None:
        return _empty_lows()
    if isinstance(x, pd.DataFrame):
        return x[_LOW_COLS].reset_index(drop=True)
    a = np.asarray(x, float).reshape(-1, 3)
    return pd.DataFrame(a, columns=_LOW_COLS)


def find_lows(msl, basin, below=1000.0, size=13, inset_deg=0.0, sep_km=150.0):
    """Local MSLP minima (hPa) on the basin grid, below `below`, as DataFrame[lat, lon, hpa].

    A cell is a low when it equals the minimum of its size x size window (13 cells = 3.25 deg at
    0.25 deg; the day 5-7 lows study's default) and is under `below` (that study used 1000 hPa).
    Minima within 2 cells of the grid edge are dropped; `inset_deg` also drops lows closer than
    that to the box edge (the study used 3.0 for analysed lows, 0.0 for forecast lows). Minima
    closer than `sep_km` (study default 150) are deduplicated keeping the deepest, because
    flat-bottomed lows give twin minima. Longitudes are 0-360. Sorted deepest first.
    """
    from scipy.ndimage import minimum_filter
    from rk.basins import BASINS, grid
    f = np.asarray(msl, float)
    lats, lons = grid(basin)
    if f.shape != (len(lats), len(lons)):
        raise ValueError("msl shape %s does not match the %s grid %s" % (f.shape, basin, (len(lats), len(lons))))
    filled = np.where(np.isfinite(f), f, np.inf)
    mn = minimum_filter(filled, size=size, mode="nearest")
    ys, xs = np.where((filled == mn) & (filled < below))
    edge = 2
    ok = (ys >= edge) & (ys < f.shape[0] - edge) & (xs >= edge) & (xs < f.shape[1] - edge)
    ys, xs = ys[ok], xs[ok]
    out = pd.DataFrame({"lat": lats[ys], "lon": lons[xs], "hpa": f[ys, xs]})
    if inset_deg and len(out):
        b = BASINS[basin]
        keep = ((out.lat <= b["north"] - inset_deg) & (out.lat >= b["south"] + inset_deg)
                & (out.lon >= b["west"] + inset_deg) & (out.lon <= b["east"] - inset_deg))
        out = out[keep]
    out = out.sort_values("hpa", kind="stable").reset_index(drop=True)
    keep = []
    for i in range(len(out)):
        if all(km(out.lat[i], out.lon[i], out.lat[j], out.lon[j]) > sep_km for j in keep):
            keep.append(i)
    return out.iloc[keep].reset_index(drop=True)


def match_lows(truth_lows, fc_lows, radius_km=300.0, miss_penalty_km=None, miss_depth="nan",
               fc_msl=None, basin=None):
    """Match each truth low to the nearest forecast low within radius_km (study default 300 km).

    One row per truth low: lat, lon, hpa (truth), matched, pos_err_km (distance to the nearest
    forecast low, NaN if none within the radius), depth_err_hpa (forecast minus truth; negative =
    forecast too deep; NaN if unmatched), fc_lat, fc_lon, fc_hpa (NaN if unmatched). A forecast
    low may match more than one truth low.

    Miss convention (defaults keep the NaN behaviour above):
      miss_penalty_km: if set (the day 5-7 study used 1000), an unmatched truth low gets this
        position error. The point: a method that drops hard lows must not look better on position
        by skipping them; a miss has to cost something. Matched rows keep their true distance.
      miss_depth: "nan" leaves the depth error of a miss NaN; "field" fills it with the forecast
        field value at the analysed centre minus the truth depth (needs fc_msl, the forecast MSLP
        on the basin grid, and basin; bilinear, exact at grid points). A forecast with no low
        there is then charged for the pressure it actually has.
    Note the study also let a low 300-1000 km away supply the depth error of a miss; here a miss
    is always charged the field value at the centre.
    """
    if miss_depth not in ("nan", "field"):
        raise ValueError("miss_depth must be 'nan' or 'field', not %r" % (miss_depth,))
    if miss_depth == "field" and (fc_msl is None or basin is None):
        raise ValueError("miss_depth='field' needs fc_msl and basin")
    t, fc = _as_lows(truth_lows), _as_lows(fc_lows)
    rows = []
    for la, lo, p in t[_LOW_COLS].itertuples(index=False):
        d = km(la, lo, fc.lat.to_numpy(), fc.lon.to_numpy()) if len(fc) else np.array([])
        j = int(d.argmin()) if len(d) else -1
        if j >= 0 and d[j] <= radius_km:
            rows.append((la, lo, p, True, float(d[j]), float(fc.hpa[j] - p), fc.lat[j], fc.lon[j], fc.hpa[j]))
        else:
            pos = np.nan if miss_penalty_km is None else float(miss_penalty_km)
            dep = np.nan
            if miss_depth == "field":
                from rk.basins import sample
                dep = float(sample(fc_msl, basin, la, lo)) - p
            rows.append((la, lo, p, False, pos, dep, np.nan, np.nan, np.nan))
    cols = ["lat", "lon", "hpa", "matched", "pos_err_km", "depth_err_hpa", "fc_lat", "fc_lon", "fc_hpa"]
    df = pd.DataFrame(rows, columns=cols)
    df["matched"] = df["matched"].astype(bool)
    return df


def false_lows(truth_lows_all, fc_lows, radius_km=300.0):
    """Number of forecast lows with no truth low (any depth in the table given) within radius_km.

    Pass truth lows found with a looser threshold than the forecast lows (the day 5-7 study judged
    forecast lows < 1000 hPa against analysed lows < 1005 hPa, with a 500 km radius; this function
    defaults to the 300 km hit radius, so say which you used).
    """
    t, fc = _as_lows(truth_lows_all), _as_lows(fc_lows)
    n = 0
    for la, lo, _ in fc[_LOW_COLS].itertuples(index=False):
        if not len(t) or km(la, lo, t.lat.to_numpy(), t.lon.to_numpy()).min() > radius_km:
            n += 1
    return n


def low_scores(truth_msl, fc_msl, basin, below=1000.0, radius_km=300.0, fc_below=None,
               false_radius_km=None, false_truth_below=None, miss_penalty_km=None, miss_depth="nan"):
    """Score forecast lows against analysed lows in one call. Every threshold is a parameter.

    below: truth-low threshold, hPa (study 1000). Truth lows: find_lows(truth_msl, basin, below,
      inset_deg=3.0), the study's analysed lows.
    fc_below: threshold for the forecast lows used for MATCHING (default = below; study 1010, so a
      shallow forecast low near a deep analysed one still counts as the match).
    radius_km: hit radius (study 300).
    false_radius_km: radius for false lows (default = radius_km; study 500).
    false_truth_below: threshold of the truth lows a forecast low is judged against for being
      false (default below + 5; study 1005).
    False lows are the forecast lows (found at fc_below) that are deeper than `below` and have no
    truth low under false_truth_below within false_radius_km (study: forecast < 1000, truth < 1005).
    miss_penalty_km, miss_depth: passed to match_lows (study: 1000 and "field"). When the penalty
      is set, pos_err_km_median covers ALL truth lows with misses charged the penalty; otherwise
      hits only. depth_err_hpa_mean covers hits plus, with miss_depth="field", the misses.

    The study's preregistered call:
      low_scores(an, fc, basin, below=1000, fc_below=1010, radius_km=300, false_radius_km=500,
                 false_truth_below=1005, miss_penalty_km=1000, miss_depth="field")
    Returns dict(hits, misses, false, pos_err_km_median, depth_err_hpa_mean, n_truth); the error
    entries are NaN when nothing contributes. Depth error is forecast minus truth (negative =
    forecast too deep).
    """
    fc_below = below if fc_below is None else fc_below
    false_radius_km = radius_km if false_radius_km is None else false_radius_km
    false_truth_below = below + 5.0 if false_truth_below is None else false_truth_below
    truth = find_lows(truth_msl, basin, below, inset_deg=3.0)
    fc = find_lows(fc_msl, basin, fc_below)
    truth_all = find_lows(truth_msl, basin, false_truth_below)
    m = match_lows(truth, fc, radius_km, miss_penalty_km=miss_penalty_km, miss_depth=miss_depth,
                   fc_msl=fc_msl, basin=basin)
    hits = int(m.matched.sum())
    pos, dep = m.pos_err_km.dropna(), m.depth_err_hpa.dropna()
    return {"hits": hits, "misses": int(len(m) - hits),
            "false": false_lows(truth_all, fc[fc.hpa < below], false_radius_km),
            "pos_err_km_median": float(pos.median()) if len(pos) else float("nan"),
            "depth_err_hpa_mean": float(dep.mean()) if len(dep) else float("nan"),
            "n_truth": int(len(truth))}
