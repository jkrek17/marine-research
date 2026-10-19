"""Day 5-7 bomb watch: 24 h low tracking, the Bergeron rule and the 2 deg neighbourhood grid (preregistration.md).

One rule for members, models and analyses: lows are 13-cell MSLP minima below 1012 hPa away from the box edge,
deduplicated within 150 km; a low at t takes the nearest low of the same member at t-24 within 1,200 km; it is a
bomb when (p(t-24) - p(t)) x sin60 / sin(mean lat) >= 24 hPa.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import minimum_filter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-16-pressure-d5-7"))
from rk.score import km  # noqa: E402

BELOW, SIZE, PAD = 1012.0, 13, 6
SEP_KM, TRACK_KM, NBR_KM = 150.0, 1200.0, 500.0
BERGERON = 24.0
CELL = 2.0
BOXES = {"natl": (30.0, 67.0, 285.0, 359.75), "npac": (30.0, 67.0, 160.0, 245.0)}


def dec(a):
    """Stored int16 (hPa*10 - 10000) -> hPa float32."""
    return (a.astype(np.float32) + 10000.0) / 10.0


def find_lows(hpa, lats, lons):
    """Grid minima -> array (k, 3) of lat, lon, hPa (deduplicated, deepest kept)."""
    mn = minimum_filter(hpa, size=SIZE, mode="nearest")
    ys, xs = np.where((hpa == mn) & (hpa < BELOW))
    ok = (ys >= PAD) & (ys < hpa.shape[0] - PAD) & (xs >= PAD) & (xs < hpa.shape[1] - PAD)
    lows = np.array([(lats[y], lons[x], hpa[y, x]) for y, x in zip(ys[ok], xs[ok])], float).reshape(-1, 3)
    return dedupe(lows)


def dedupe(lows):
    lows = lows[np.argsort(lows[:, 2])]
    keep = []
    for i in range(len(lows)):
        if all(km(lows[i, 0], lows[i, 1], lows[j, 0], lows[j, 1]) > SEP_KM for j in keep):
            keep.append(i)
    return lows[keep]


def bombs(prev, now):
    """Lows (k, 3) at t-24 and t of one member -> array (m, 4): lat, lon, hPa at t and the Bergeron number
    of every low at t matched to a low at t-24 within 1,200 km (all matched lows, bombs or not)."""
    out = []
    if not len(prev):
        return np.zeros((0, 4))
    for la, lo, p in now:
        d = km(prev[:, 0], prev[:, 1], la, lo)
        j = int(np.argmin(d))
        if d[j] > TRACK_KM:
            continue
        mlat = 0.5 * (la + prev[j, 0])
        ndr = (prev[j, 2] - p) * np.sin(np.radians(60.0)) / np.sin(np.radians(mlat)) / BERGERON
        out.append((la, lo, p, ndr))
    return np.array(out, float).reshape(-1, 4)


def cells(basin):
    """2 deg cell centres of the box -> (lat, lon) 1-D arrays."""
    s, n, w, e = BOXES[basin]
    la = np.arange(s + CELL / 2, n, CELL)
    lo = np.arange(w + CELL / 2, e, CELL)
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    return LA.ravel(), LO.ravel()


def near(points, clat, clon, radius=NBR_KM):
    """Points (k, >=2) -> bool per cell: any point within radius of the cell centre."""
    hit = np.zeros(clat.shape, bool)
    for la, lo in points[:, :2]:
        hit |= km(clat, clon, la, lo) <= radius
    return hit


def member_field(member_bombs, clat, clon):
    """{member: bombs array} -> share of members with a bomb (Bergeron >= 1) ending within 500 km of each cell,
    plus the per-ensemble shares {ens: share} for equal-weight pooling."""
    return {m: near(b[b[:, 3] >= 1.0], clat, clon) for m, b in member_bombs.items()}
