"""Front drill: the pure pieces shared by find_cases.py and build_deck.py (no network, no files).

Lows are (hpa, lat, lon) tuples as rk.fronts returns them; fronts are {"type", "lat", "lon"} dicts
(lon 0-360). Distances in km unless the name says nm.
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import fronts as F  # noqa: E402

NM_KM = 1.852
KM_DEG = 111.19            # km per degree of latitude
ATTACH_KM = 300.0          # a front belongs to a low when one of its ends is this close
LINK_KM = 600.0            # the same low in the next or previous analysis
SECOND_LOW_KM = 500.0
NON_TROUGH = ("cold", "warm", "occluded", "stationary")
DRAWN = ("cold", "warm", "occluded")      # what the trainee draws (the stationary fronts and the low are given)

# WPC's coded bulletin clipped fronts at its slanted map edge until this analysis and covers the Atlantic to ~0W from it.
# First analysis with the full domain (searched by day, then by analysis): 2026-08-12 15Z has 28 fronts, easternmost
# point at 28-42N 260E (no ocean fronts); 18Z has 71 reaching 357E. Later odd-hour bulletins (03/09/15/21Z) can be partial.
COVERAGE_FULL_FROM = dt.datetime(2026, 8, 12, 18)
EDGE_TOL_DEG = 1.5         # a system front end this close to the old edge (or beyond) is counted as clipped


def km(lat1, lon1, lat2, lon2):
    return F.distance_nm(lat1, lon1, lat2, lon2) * NM_KM


def length_nm(lat, lon):
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if len(lat) < 2:
        return 0.0
    return float(np.sum(F.distance_nm(lat[:-1], lon[:-1], lat[1:], lon[1:])))


# ---------------------------------------------------------------- finder
def merged(analysis):
    """Merged fronts of an analysis (same-type ends within 30 nm joined)."""
    return F.merge_segments(analysis["fronts"])


def attached(fronts, lat, lon, max_km=ATTACH_KM):
    """Non-trough fronts with an end within max_km of the point -> list of fronts."""
    out = []
    for f in fronts:
        if f["type"] not in NON_TROUGH:
            continue
        ends = km(lat, lon, np.array([f["lat"][0], f["lat"][-1]]), np.array([f["lon"][0], f["lon"][-1]]))
        if float(np.min(ends)) <= max_km:
            out.append(f)
    return out


def type_set(fronts, lat, lon, max_km=ATTACH_KM):
    """Sorted tuple of the non-trough front types attached to the point."""
    return tuple(sorted({f["type"] for f in attached(fronts, lat, lon, max_km)}))


def nearest_low(lows, lat, lon, max_km=LINK_KM):
    """The analysed low (hpa, lat, lon) nearest to a point within max_km, or None."""
    best, bd = None, max_km
    for lw in lows:
        d = float(km(lat, lon, lw[1], lw[2]))
        if d <= bd:
            best, bd = lw, d
    return best


def has_second_low(lows, lat, lon, max_km=SECOND_LOW_KM):
    """True when another analysed low (not the one at the point itself) lies within max_km."""
    others = [lw for lw in lows if float(km(lat, lon, lw[1], lw[2])) > 1.0]
    return any(float(km(lat, lon, lw[1], lw[2])) <= max_km for lw in others)


def types_match(prev, nxt, current_types, lat, lon):
    """The low's non-trough type set is the same 6 h before and 6 h after. prev and nxt are
    (lows, merged fronts) of the neighbouring analyses or None; the low there is the nearest analysed low
    within LINK_KM. A missing analysis, no matching low, or a different set -> False."""
    for nb in (prev, nxt):
        if nb is None:
            return False
        lw = nearest_low(nb[0], lat, lon)
        if lw is None or type_set(nb[1], lw[1], lw[2]) != tuple(current_types):
            return False
    return True


def types_match_relaxed(prev, nxt, current_types, lat, lon):
    """Relaxed type check: every cold, warm or occluded type present now was also present (attached to the nearest
    analysed low within LINK_KM) 6 h before or 6 h after. A missing neighbour is skipped; with no neighbour that has
    the low, False."""
    need = set(current_types) & set(DRAWN)
    got, seen = set(), False
    for nb in (prev, nxt):
        if nb is None:
            continue
        lw = nearest_low(nb[0], lat, lon)
        if lw is None:
            continue
        seen = True
        got |= set(type_set(nb[1], lw[1], lw[2]))
    return seen and need <= got


def link_tracks(lows_by_time, max_km=LINK_KM):
    """Track ids for lows across consecutive analyses. lows_by_time: dict valid -> list of lows. Returns
    dict (valid, index) -> track id. A low links to the nearest unclaimed low of the previous time (6 h
    earlier) within max_km, closest pairs first; otherwise it starts a new track."""
    ids, nxt = {}, 0
    times = sorted(lows_by_time)
    for t in times:
        cur = lows_by_time[t]
        prev_t = t - dt.timedelta(hours=6)
        prev = lows_by_time.get(prev_t, [])
        pairs = sorted((float(km(c[1], c[2], p[1], p[2])), i, j)
                       for i, c in enumerate(cur) for j, p in enumerate(prev))
        used_c, used_p = set(), set()
        for d, i, j in pairs:
            if d > max_km:
                break
            if i in used_c or j in used_p:
                continue
            ids[(t, i)] = ids[(prev_t, j)]
            used_c.add(i)
            used_p.add(j)
        for i in range(len(cur)):
            if (t, i) not in ids:
                ids[(t, i)] = nxt
                nxt += 1
    return ids


# ---------------------------------------------------------------- deck truth
def clip_fronts(fronts, lat_n, lon_w, ny=51, nx=81, res=0.5, margin=1.0, min_nm=150.0, step_nm=25):
    """Curve each front through its coded points (rk.fronts.smooth, a point every step_nm) and clip to the box minus
    `margin` degrees. A front that leaves and re-enters
    becomes several pieces; pieces with under min_nm inside are dropped. Returns [{"type", "pts":
    [[lat, lon], ...]}] with lon 0-360."""
    s, n = lat_n - (ny - 1) * res + margin, lat_n - margin
    w_off, e_off = margin, (nx - 1) * res - margin
    out = []
    for f in fronts:
        la, lo = F.smooth(f["lat"], f["lon"], step_nm)
        rel = (lo - lon_w) % 360.0
        inside = (la >= s) & (la <= n) & (rel >= w_off) & (rel <= e_off)
        i = 0
        while i < len(la):
            if not inside[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(la) and inside[j + 1]:
                j += 1
            if length_nm(la[i:j + 1], lo[i:j + 1]) >= min_nm:
                out.append({"type": f["type"],
                            "pts": [[round(float(a), 3), round(float(b), 3)] for a, b in zip(la[i:j + 1], lo[i:j + 1])]})
            i = j + 1
    return out


SYS_SEED_KM = 300.0        # a non-trough front with an end this close to the case low belongs to its system
SYS_CHAIN_NM = 60.0        # ... and so does a front whose end is this close to a point of a system front
SYS_PAD_NM = 60.0          # the ring around the system: farthest system point from the low plus this
SYS_MAX_NM = 900.0
SYS_MIN_NM = 250.0         # a case needs this much non-trough system front after clipping


def mark_system(fronts, low_lat, low_lon):
    """Flag the clipped fronts ([{"type", "pts": [[lat, lon], ...]}], modified in place) that belong to the case
    low's system: "sys" true for a non-trough front with an end within SYS_SEED_KM of the low, then repeatedly for
    any front (a trough too) with an end within SYS_CHAIN_NM of a point of a non-trough system front (the cold front
    trailing from the triple point of an occlusion, a stationary continuation). Troughs are attached but never
    extend the system. Returns the ring radius in nm: the farthest system point from the low plus SYS_PAD_NM,
    capped at SYS_MAX_NM (0 when no front is in the system)."""
    P = [np.asarray(f["pts"], float) for f in fronts]
    sysf = [False] * len(fronts)
    for i, f in enumerate(fronts):
        if f["type"] in NON_TROUGH:
            p = P[i]
            ends = km(low_lat, low_lon, p[[0, -1], 0], p[[0, -1], 1])
            sysf[i] = bool(np.min(ends) <= SYS_SEED_KM)
    changed = True
    while changed:
        changed = False
        for i, f in enumerate(fronts):
            if sysf[i]:
                continue
            ends = P[i][[0, -1]]
            for j, g in enumerate(fronts):
                if not sysf[j] or g["type"] not in NON_TROUGH:
                    continue
                d = F.distance_nm(ends[:, 0][:, None], ends[:, 1][:, None], P[j][:, 0][None, :], P[j][:, 1][None, :])
                if float(np.min(d)) <= SYS_CHAIN_NM:
                    sysf[i] = True
                    changed = True
                    break
    r = 0.0
    for i, f in enumerate(fronts):
        f["sys"] = sysf[i]
        if sysf[i]:
            r = max(r, float(np.max(F.distance_nm(low_lat, low_lon, P[i][:, 0], P[i][:, 1]))))
    return min(SYS_MAX_NM, round(r + SYS_PAD_NM)) if r > 0 else 0


def sys_length_nm(fronts):
    """Total length (nm) of the non-trough fronts flagged "sys"."""
    return sum(length_nm([p[0] for p in f["pts"]], [p[1] for p in f["pts"]])
               for f in fronts if f.get("sys") and f["type"] in NON_TROUGH)


def lows_in_box(lows, lat_n, lon_w, ny=51, nx=81, res=0.5):
    """Analysed lows inside the box edges -> [{"lat", "lon", "hpa"}]."""
    out = []
    for hpa, la, lo in lows:
        rel = (lo - lon_w) % 360.0
        if lat_n - (ny - 1) * res <= la <= lat_n and 0 <= rel <= (nx - 1) * res:
            out.append({"lat": round(float(la), 2), "lon": round(float(lo), 2), "hpa": float(hpa)})
    return out


# ---------------------------------------------------------------- hints
def bilin(field, lat_n, lon_w, lat, lon, res=0.5):
    """Bilinear sample of a box field (row 0 north, column 0 west) at points; NaN outside or on NaN cells."""
    f = np.asarray(field, float)
    y = (lat_n - np.asarray(lat, float)) / res
    x = ((np.asarray(lon, float) - lon_w) % 360.0) / res
    ok = (y >= 0) & (y <= f.shape[0] - 1) & (x >= 0) & (x <= f.shape[1] - 1)
    y0 = np.clip(np.floor(y).astype(int), 0, f.shape[0] - 2)
    x0 = np.clip(np.floor(x).astype(int), 0, f.shape[1] - 2)
    fy, fx = np.clip(y - y0, 0, 1), np.clip(x - x0, 0, 1)
    v = (f[y0, x0] * (1 - fy) * (1 - fx) + f[y0, x0 + 1] * (1 - fy) * fx
         + f[y0 + 1, x0] * fy * (1 - fx) + f[y0 + 1, x0 + 1] * fy * fx)
    return np.where(ok, v, np.nan)


def tangents(lat, lon, half=2):
    """Unit tangent (east, north) of a polyline at each vertex over +-half vertices."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    n = len(lat)
    te, tn = np.zeros(n), np.zeros(n)
    for i in range(n):
        a, b = max(0, i - half), min(n - 1, i + half)
        de = (((lon[b] - lon[a] + 180) % 360) - 180) * np.cos(np.radians(lat[i]))
        dn = lat[b] - lat[a]
        m = np.hypot(de, dn)
        te[i], tn[i] = (de / m, dn / m) if m > 0 else (0.0, 0.0)
    return te, tn


def offset(lat, lon, east, north, dist_km):
    """Points dist_km along the unit vector (east, north) from (lat, lon)."""
    lat = np.asarray(lat, float)
    return (lat + north * dist_km / KM_DEG,
            (np.asarray(lon, float) + east * dist_km / (KM_DEG * np.cos(np.radians(lat)))) % 360.0)


def side_points(pts, dist_km):
    """pts [[lat, lon], ...] -> ((lat, lon) of the left side, (lat, lon) of the right side) of the line
    (left of the direction of travel), dist_km away."""
    p = np.asarray(pts, float)
    te, tn = tangents(p[:, 0], p[:, 1])
    left = offset(p[:, 0], p[:, 1], -tn, te, dist_km)
    right = offset(p[:, 0], p[:, 1], tn, -te, dist_km)
    return left, right


def wrap180(d):
    return (np.asarray(d, float) + 180.0) % 360.0 - 180.0


def wind_dir(u, v):
    """Meteorological direction (deg the wind blows from)."""
    return (np.degrees(np.arctan2(-np.asarray(u, float), -np.asarray(v, float)))) % 360.0


def thermal_contrast(fronts_pts, te, u, v, lat_n, lon_w, dist_km=150.0, res=0.5):
    """Across-front contrast for the fronts of one type (list of [[lat, lon], ...]): theta-e on the warm
    and cold sides (medians over the points; warm = the higher side overall) and the 10 m wind turn
    from the warm side to the cold side (deg, positive = veers, clockwise). Returns dict or None."""
    wl, cl, dv, ws = [], [], [], []
    for pts in fronts_pts:
        if len(pts) < 3:
            continue
        (la1, lo1), (la2, lo2) = side_points(pts, dist_km)
        a = bilin(te, lat_n, lon_w, la1, lo1, res)
        b = bilin(te, lat_n, lon_w, la2, lo2, res)
        ua, va = bilin(u, lat_n, lon_w, la1, lo1, res), bilin(v, lat_n, lon_w, la1, lo1, res)
        ub, vb = bilin(u, lat_n, lon_w, la2, lo2, res), bilin(v, lat_n, lon_w, la2, lo2, res)
        wl.append((a, b, wind_dir(ua, va), wind_dir(ub, vb), np.hypot(ua, va), np.hypot(ub, vb)))
    if not wl:
        return None
    a = np.concatenate([x[0] for x in wl])
    b = np.concatenate([x[1] for x in wl])
    d1 = np.concatenate([x[2] for x in wl])
    d2 = np.concatenate([x[3] for x in wl])
    s1 = np.concatenate([x[4] for x in wl])
    s2 = np.concatenate([x[5] for x in wl])
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return None
    left_warm = np.nanmedian(a[ok] - b[ok]) >= 0
    warm, cold = (a, b) if left_warm else (b, a)
    dw, dc = (d1, d2) if left_warm else (d2, d1)
    sw, sc = (s1, s2) if left_warm else (s2, s1)
    kk = ok & np.isfinite(dw) & np.isfinite(dc) & (sw >= 1.0) & (sc >= 1.0)
    turn = float(np.median(wrap180(dc[kk] - dw[kk]))) if kk.sum() >= 3 else None
    return {"te_warm": float(np.median(warm[ok])), "te_cold": float(np.median(cold[ok])),
            "dte": float(np.median(warm[ok] - cold[ok])), "turn": turn, "n": int(ok.sum())}


def ridge_contrast(fronts_pts, te700, lat_n, lon_w, side_km=250.0, near_km=75.0, res=0.5):
    """700 hPa theta-e on the line (best of the line and +-near_km across it) against the mean of the
    two sides side_km away, medians over the points -> {"ridge", "on", "around", "n"} or None."""
    on, around = [], []
    for pts in fronts_pts:
        if len(pts) < 3:
            continue
        p = np.asarray(pts, float)
        (l1, o1), (l2, o2) = side_points(pts, near_km)
        c = np.vstack([bilin(te700, lat_n, lon_w, p[:, 0], p[:, 1], res),
                       bilin(te700, lat_n, lon_w, l1, o1, res), bilin(te700, lat_n, lon_w, l2, o2, res)])
        (a1, b1), (a2, b2) = side_points(pts, side_km)
        s = 0.5 * (bilin(te700, lat_n, lon_w, a1, b1, res) + bilin(te700, lat_n, lon_w, a2, b2, res))
        with np.errstate(all="ignore"):
            on.append(np.nanmax(c, axis=0))
        around.append(s)
    if not on:
        return None
    on, around = np.concatenate(on), np.concatenate(around)
    ok = np.isfinite(on) & np.isfinite(around)
    if ok.sum() < 3:
        return None
    return {"on": float(np.median(on[ok])), "around": float(np.median(around[ok])),
            "ridge": float(np.median(on[ok] - around[ok])), "n": int(ok.sum())}


def isobar_angle(fronts_pts, msl, lat_n, lon_w, res=0.5, min_grad=0.05):
    """Mean angle (deg, 0 = along the isobars, 90 = across them) between the front and the local isobars
    of the MSLP field, over the points where the gradient is at least min_grad hPa per 100 km, with the
    mean gradient. None when too few points."""
    ang, gr = [], []
    for pts in fronts_pts:
        if len(pts) < 3:
            continue
        p = np.asarray(pts, float)
        te, tn = tangents(p[:, 0], p[:, 1])
        h = 100.0
        e1 = bilin(msl, lat_n, lon_w, *offset(p[:, 0], p[:, 1], 1.0, 0.0, h), res)
        e0 = bilin(msl, lat_n, lon_w, *offset(p[:, 0], p[:, 1], -1.0, 0.0, h), res)
        n1 = bilin(msl, lat_n, lon_w, *offset(p[:, 0], p[:, 1], 0.0, 1.0, h), res)
        n0 = bilin(msl, lat_n, lon_w, *offset(p[:, 0], p[:, 1], 0.0, -1.0, h), res)
        gx, gy = (e1 - e0) / 2.0, (n1 - n0) / 2.0      # hPa per 100 km
        g = np.hypot(gx, gy)
        with np.errstate(all="ignore"):
            along = np.abs(te * -gy + tn * gx) / g      # |tangent . isobar direction| (isobar dir = (-gy, gx)/|g|)
        k = np.isfinite(g) & (g >= min_grad) & np.isfinite(along)
        ang.append(np.degrees(np.arccos(np.clip(along[k], 0, 1))))
        gr.append(g[k])
    if not ang:
        return None
    ang, gr = np.concatenate(ang), np.concatenate(gr)
    if len(ang) < 3:
        return None
    return {"angle": float(np.mean(ang)), "grad": float(np.mean(gr)), "n": int(len(ang))}


def _turn_text(turn):
    if turn is None:
        return ""
    return " and the 10 m wind %s %d deg going from the warm side to the cold side" % (
        "veers" if turn >= 0 else "backs", round(abs(turn)))


def hint(typ, fronts_pts, fields, lat_n, lon_w):
    """One line for the reveal about this case's fronts of one type, numbers from the fields
    (fields: dict with msl, te850, te700, u10, v10 on the box grid), or None when they cannot be computed."""
    if typ in ("cold", "warm"):
        c = thermal_contrast(fronts_pts, fields["te850"], fields["u10"], fields["v10"], lat_n, lon_w)
        if c is None:
            return None
        if typ == "cold":
            return ("Cold front: 850 hPa theta-e falls %.0f K from the warm side to the cold side (%.0f to %.0f K, "
                    "150 km either side)%s." % (c["dte"], c["te_warm"], c["te_cold"], _turn_text(c["turn"])))
        return ("Warm front: 850 hPa theta-e is %.0f K higher on the warm side (%.0f against %.0f K, "
                "150 km either side)%s." % (c["dte"], c["te_warm"], c["te_cold"], _turn_text(c["turn"])))
    if typ == "occluded":
        r = ridge_contrast(fronts_pts, fields["te700"], lat_n, lon_w)
        if r is None:
            return None
        return ("Occluded front: 700 hPa theta-e along the front is %.0f K, %+.0f K against the air 250 km either "
                "side (%.0f K): the warm ridge wrapping into the low." % (r["on"], r["ridge"], r["around"]))
    if typ == "stationary":
        a = isobar_angle(fronts_pts, fields["msl"], lat_n, lon_w)
        if a is None:
            return None
        return ("Stationary front: the isobars run %.0f deg off the front on average (0 = along it; mean gradient "
                "%.1f hPa per 100 km)." % (a["angle"], a["grad"]))
    return None


# ---------------------------------------------------------------- old coverage edge
def old_edge():
    """(lat of band centres, edge longitude 0-360) of WPC's map edge before COVERAGE_FULL_FROM, from old_edge.csv
    (domain_edge.py: per 1-degree band, easternmost Atlantic point over all analyses 2024-11 to 2026-07, smoothed)."""
    import csv
    rows = list(csv.DictReader(open(Path(__file__).with_name("old_edge.csv"))))
    return (np.array([float(r["lat_band_south"]) + 0.5 for r in rows]), np.array([float(r["edge_lon"]) for r in rows]))


# WPC's coded bulletin stops at 180 and at 359.0 (checked over 13 Aug-5 Nov 2026: no coded point west of 180W or east of 1W).
BASIN_EDGE = {"npac": (180.0, None), "natl": (None, 359.0)}     # (west edge lon, east edge lon) of the coded analysis


def basin_edge_clipped(fronts, basin, tol=EDGE_TOL_DEG):
    """True when an end of a system non-trough front (already flagged "sys") lies within tol degrees of the edge of the
    coded domain: 180 in the North Pacific, 1W in the Atlantic (the analysis stops there, the front may go on)."""
    west, east = BASIN_EDGE[basin]
    for f in fronts:
        if not f.get("sys") or f["type"] not in NON_TROUGH:
            continue
        for p in (f["pts"][0], f["pts"][-1]):
            if west is not None and west <= p[1] <= west + tol:
                return True
            if east is not None and p[1] >= east - tol:
                return True
    return False


def edge_clipped(fronts, tol=EDGE_TOL_DEG):
    """True when an end of a system non-trough front (a deck record's "fronts", already flagged "sys") lies within tol
    degrees of longitude of the old coverage edge at its latitude, or east of it."""
    la, lo = old_edge()
    for f in fronts:
        if not f.get("sys") or f["type"] not in NON_TROUGH:
            continue
        for p in (f["pts"][0], f["pts"][-1]):
            if 250.0 <= p[1] <= 360.0 and p[1] >= np.interp(p[0], la, lo) - tol:
                return True
    return False
