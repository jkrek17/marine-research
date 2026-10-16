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


def brier_skill(p, y, w=None):
    """Weighted Brier skill score against the constant base rate of the same sample:
    1 - BS / (base (1 - base)), BS = sum w (p - y)^2 / sum w. NaN when the base rate is 0 or 1."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    w = np.ones_like(p) if w is None else np.asarray(w, float)
    sw = w.sum()
    if sw == 0:
        return float("nan")
    base = (w * y).sum() / sw
    ref = base * (1 - base)
    return float("nan") if ref == 0 else float(1 - (w * (p - y) ** 2).sum() / sw / ref)


def auc_from_hist(pos, neg):
    """ROC area from weighted histograms of the positives and negatives over probability bins ordered
    low to high (last axis; leading axes allowed, e.g. bootstrap draws). Ties within a bin count half."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    before = np.cumsum(neg, -1) - neg
    num = (pos * (before + 0.5 * neg)).sum(-1)
    den = pos.sum(-1) * neg.sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def auc(p, y, w=None):
    """Weighted ROC area (probability that a random positive outranks a random negative, ties half).
    NaN when one class is missing. Exact: groups equal values of p."""
    p, y = np.asarray(p, float), np.asarray(y, float) > 0.5
    w = np.ones_like(p) if w is None else np.asarray(w, float)
    up, inv = np.unique(p, return_inverse=True)
    pos = np.bincount(inv, weights=w * y, minlength=len(up))
    neg = np.bincount(inv, weights=w * ~y, minlength=len(up))
    return float(auc_from_hist(pos, neg))


def reliability(p, y, w=None, bins=10):
    """Reliability table: `bins` equal probability bins on [0, 1] (the last includes 1).
    Columns bin, lo, hi, n (cells), w (weight), mean_p, freq (observed relative frequency), weighted."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    w = np.ones_like(p) if w is None else np.asarray(w, float)
    b = np.clip((p * bins).astype(int), 0, bins - 1)
    rows = []
    for i in range(bins):
        s = b == i
        sw = w[s].sum()
        rows.append({"bin": i, "lo": i / bins, "hi": (i + 1) / bins, "n": int(s.sum()), "w": float(sw),
                     "mean_p": float((w[s] * p[s]).sum() / sw) if sw else np.nan,
                     "freq": float((w[s] * y[s]).sum() / sw) if sw else np.nan})
    return pd.DataFrame(rows)


def tile_hits(fc, ob, seen, lat, lon, thr, size_deg=5, min_seen=150):
    """Tile-by-tile event hits on a grid, at the cells the observation saw.

    fc, ob: forecast and observed speed on the same grid (kt); seen: bool grid, True where the
    observation exists (ob is ignored elsewhere, may be NaN); lat, lon: 1-D grid vectors (rows, columns)
    or 2-D grids (longitudes any convention, taken modulo 360). Tiles are size_deg boxes; a tile is kept
    when it has at least min_seen seen cells. In a kept tile the observed event is "any seen cell >= thr"
    and the forecast event is "any forecast cell >= thr among the SEEN cells" (a forecast storm outside the
    swath is not judged). NaN forecast cells never count.
    One row per tile: tile, lat0, lon0, n_seen, ob_event, fc_event (bool). Use `tile_counts` for totals.
    """
    fc = np.asarray(fc, float)
    ob = np.asarray(ob, float)
    seen = np.asarray(seen, bool)
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if lat.ndim == 1:
        lat, lon = np.meshgrid(lat, lon, indexing="ij")
    cols = ["tile", "lat0", "lon0", "n_seen", "ob_event", "fc_event"]
    iy = np.floor(lat / size_deg).astype(int)
    ix = np.floor((lon % 360) / size_deg).astype(int)
    key = (iy + 100) * 1000 + ix
    k = key[seen]
    if k.size == 0:
        return pd.DataFrame(columns=cols)
    o_ev = np.nan_to_num(ob[seen], nan=-1) >= thr
    f_ev = np.nan_to_num(fc[seen], nan=-1) >= thr
    uk, inv = np.unique(k, return_inverse=True)
    n = np.bincount(inv)
    o = np.bincount(inv, weights=o_ev) > 0
    f = np.bincount(inv, weights=f_ev) > 0
    keep = n >= min_seen
    uk, n, o, f = uk[keep], n[keep], o[keep], f[keep]
    y0, x0 = (uk // 1000 - 100) * size_deg, (uk % 1000) * size_deg
    return pd.DataFrame({"tile": ["%d_%d" % (a, b) for a, b in zip(y0, x0)], "lat0": y0, "lon0": x0,
                         "n_seen": n, "ob_event": o, "fc_event": f}, columns=cols)


def tile_counts(tiles):
    """(hits, misses, false_alarms) from a tile_hits table (or the sum over several)."""
    o, f = tiles["ob_event"].to_numpy(bool), tiles["fc_event"].to_numpy(bool)
    return int((o & f).sum()), int((o & ~f).sum()), int((~o & f).sum())


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


def low_case(truth_msl, fc_msl, basin, below=1000.0, fc_below=1010.0, radius_km=1000.0, hit_km=300.0,
             false_radius_km=500.0, false_truth_below=1005.0, miss_penalty_km=1000.0):
    """One case scored in the day 5-7 study's headline form (its `lib.score` and `lib.false_lows`).

    Per analysed low (find_lows(truth_msl, below, inset_deg=3.0)): position error to the nearest forecast low
    (found at fc_below) within radius_km, a miss charged miss_penalty_km; depth error forecast minus analysed
    from that nearest low, or, for a miss, the forecast field at the analysed centre minus the analysed value;
    hit = nearest forecast low within hit_km. This differs from low_scores in one way: the match radius is
    1000 km, so a low 300-1000 km away still supplies its position and depth error (the preregistered rule),
    and `hit` is the separate 300 km test.
    Returns (rows, false, n_fc): rows is a DataFrame [lat, lon, an_hpa, pos_km, depth_err_hpa, hit]; false is
    the number of forecast lows below `below` with no analysed low under false_truth_below within
    false_radius_km; n_fc is the number of forecast lows below `below`.
    """
    truth = find_lows(truth_msl, basin, below, inset_deg=3.0)
    truth_all = find_lows(truth_msl, basin, false_truth_below)
    fc = find_lows(fc_msl, basin, fc_below)
    m = match_lows(truth, fc, radius_km, miss_penalty_km=miss_penalty_km, miss_depth="field",
                   fc_msl=fc_msl, basin=basin)
    rows = pd.DataFrame({"lat": m.lat, "lon": m.lon, "an_hpa": m.hpa, "pos_km": m.pos_err_km,
                         "depth_err_hpa": m.depth_err_hpa, "hit": m.matched & (m.pos_err_km <= hit_km)})
    deep = fc[fc.hpa < below]
    return rows, false_lows(truth_all, deep, false_radius_km), int(len(deep))


# ---- warnings: areas of wind at or above a level, scored as events ----

def _label(m):
    from scipy import ndimage
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    sizes = ndimage.sum(m, lab, range(1, n + 1)) if n else np.array([])
    return lab, sizes


def warning_events(warned, truth_kt, seen, thr, mask=None, slack=4, min_cells=2, min_area_cells=3,
                   judge_frac=0.3, judge_min=10):
    """Score one warned area (boolean grid) at one level against observed wind (e.g. ASCAT on the grid).

    events   8-connected areas of observed >= thr (seen cells only, >= min_cells cells) inside mask
    hits     events with a warned cell within `slack` cells (4 cells ~ 60 nm at 0.25 deg)
    areas    8-connected warned areas (>= min_area_cells cells); `judged` = those the observations saw
             (>= judge_min seen cells and >= judge_frac of the area); `false` = judged areas with no
             observed >= thr within `slack` cells
    cells    warned cells that were seen; `bad_cells` = those with no observed >= thr within `slack`
    Returns dict(events, hits, areas, judged, false, cells, bad_cells, warned_cells)."""
    from scipy import ndimage
    warned = np.asarray(warned, bool)
    seen = np.asarray(seen, bool)
    if mask is not None:
        warned = warned & mask
        seen = seen & mask
    obs = seen & (np.nan_to_num(np.asarray(truth_kt, float)) >= thr)
    k = np.ones((2 * slack + 1, 2 * slack + 1), bool)
    near_obs = ndimage.binary_dilation(obs, k) if obs.any() else obs
    near_warn = ndimage.binary_dilation(warned, k) if warned.any() else warned
    elab, esz = _label(obs)
    ev = [i + 1 for i in range(len(esz)) if esz[i] >= min_cells]
    hit_lab = set(np.unique(elab[near_warn & obs]))
    hits = sum(1 for i in ev if i in hit_lab)
    wlab, wsz = _label(warned)
    areas = [i + 1 for i in range(len(wsz)) if wsz[i] >= min_area_cells]
    judged = false = 0
    if areas:
        nseen = ndimage.sum(seen, wlab, areas)
        nnear = ndimage.sum(near_obs, wlab, areas)
        for j, i in enumerate(areas):
            if nseen[j] >= judge_min and nseen[j] >= judge_frac * wsz[i - 1]:
                judged += 1
                false += int(nnear[j] == 0)
    ws = warned & seen
    return dict(events=len(ev), hits=hits, areas=len(areas), judged=judged, false=false,
                cells=int(ws.sum()), bad_cells=int((ws & ~near_obs).sum()), warned_cells=int(warned.sum()))


def warning_points(warned, basin, lat, lon, radius_km, mask=None, min_area_cells=3):
    """Score one warned area against point events (e.g. archive hurricane-force low centres).

    hits     points with a warned cell within radius_km
    false    warned areas (>= min_area_cells) with no point within radius_km of any of their cells
    bad_cells  warned cells farther than radius_km from every point
    Returns dict(events, hits, areas, judged, false, cells, bad_cells, warned_cells) like warning_events
    (judged = areas: a point truth judges every area)."""
    from .basins import grid
    warned = np.asarray(warned, bool)
    if mask is not None:
        warned = warned & mask
    lats, lons = grid(basin)
    la2, lo2 = np.meshgrid(lats, lons, indexing="ij")
    lat, lon = np.atleast_1d(np.asarray(lat, float)), np.atleast_1d(np.asarray(lon, float))
    near = [km(la2, lo2, a, o) <= radius_km for a, o in zip(lat, lon)]
    near_any = np.any(near, 0) if near else np.zeros(warned.shape, bool)
    hits = sum(int((n & warned).any()) for n in near)
    wlab, wsz = _label(warned)
    areas = [i + 1 for i in range(len(wsz)) if wsz[i] >= min_area_cells]
    false = sum(int(not (near_any & (wlab == i)).any()) for i in areas)
    return dict(events=len(near), hits=hits, areas=len(areas), judged=len(areas), false=false,
                cells=int(warned.sum()), bad_cells=int((warned & ~near_any).sum()), warned_cells=int(warned.sum()))
