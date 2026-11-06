"""Look-up tools for the agent (reads only the case folder's fields.npz; never the deck or its truth).
  python3 tools.py <case_dir> section LAT1 LON1 LAT2 LON2   # 850 theta-e, 10 m wind, MSLP every ~50 nm along a line
  python3 tools.py <case_dir> troughs                       # isobar kinks: lines of max cyclonic curvature near the low
  python3 tools.py <case_dir> gradmax LAT LON [RADIUS_NM]   # strongest 850 theta-e gradient near a point
Longitudes: degrees east (+) or west (-)."""
import sys
from pathlib import Path

import numpy as np


def load(d):
    z = np.load(Path(d) / "fields.npz")
    return {k: z[k] for k in z.files}


def interp(F, key, la, lo):
    lat, lon = F["lat"], F["lon"]
    lo = np.where(np.asarray(lo) < lon[0] - 1, np.asarray(lo) + 360, lo)
    i = (lat[0] - np.asarray(la)) / (lat[0] - lat[1])
    j = (np.asarray(lo) - lon[0]) / (lon[1] - lon[0])
    i0 = np.clip(np.floor(i).astype(int), 0, len(lat) - 2)
    j0 = np.clip(np.floor(j).astype(int), 0, len(lon) - 2)
    di, dj = np.clip(i - i0, 0, 1), np.clip(j - j0, 0, 1)
    a = F[key]
    return (a[i0, j0] * (1 - di) * (1 - dj) + a[i0 + 1, j0] * di * (1 - dj) + a[i0, j0 + 1] * (1 - di) * dj + a[i0 + 1, j0 + 1] * di * dj)


def nm(la1, lo1, la2, lo2):
    p1, p2, dl = np.radians(la1), np.radians(la2), np.radians(lo2 - lo1)
    return 6880.13 * np.arcsin(np.minimum(1, np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2)))


def ew(lo):
    lo = ((lo + 180) % 360) - 180
    return f"{abs(lo):.1f}{'W' if lo < 0 else 'E'}"


def section(F, la1, lo1, la2, lo2):
    L = nm(la1, lo1, la2, lo2)
    n = max(2, int(L / 50) + 1)
    la = np.linspace(la1, la2, n)
    dlo = ((lo2 - lo1 + 180) % 360) - 180
    lo = lo1 + np.linspace(0, dlo, n)
    te, u, v, p = (interp(F, k, la, lo) for k in ("te850", "u10", "v10", "msl"))
    print(f"Section {la1:.1f}N {ew(lo1)} -> {la2:.1f}N {ew(lo2)}, {L:.0f} nm")
    print(" dist_nm   lat     lon     te850_K  wind_from_deg  wind_kt  mslp")
    for k in range(n):
        spd = np.hypot(u[k], v[k]) * 1.94384
        dirn = (np.degrees(np.arctan2(-u[k], -v[k])) + 360) % 360
        print(f"{k * L / (n - 1):7.0f}  {la[k]:5.1f}  {ew(lo[k]):>7}  {te[k]:7.1f}  {dirn:11.0f}  {spd:8.0f}  {p[k]:6.1f}")


def gradmax(F, la, lo, r=200):
    lat, lon = F["lat"], F["lon"]
    th = F["te850"]
    gy, gx = np.gradient(th)
    LAT = np.broadcast_to(lat[:, None], th.shape)
    LON = np.broadcast_to(lon[None, :], th.shape)
    dy = 0.5 * 111.2
    g = np.hypot(gx / (dy * np.cos(np.radians(LAT))), gy / dy) * 100     # K per 100 km
    d = nm(la, lo % 360, LAT, LON)
    m = np.where(d <= r, g, -1)
    order = np.argsort(m.ravel())[::-1][:5]
    print(f"Strongest 850 theta-e gradients within {r:.0f} nm of {la:.1f}N {ew(lo)} (K per 100 km):")
    for o in order:
        if m.ravel()[o] < 0:
            break
        i, j = np.unravel_index(o, th.shape)
        print(f"  {lat[i]:.1f}N {ew(lon[j])}: {g[i, j]:.1f}  (theta-e {th[i, j]:.0f} K)")


def troughs(F):
    from scipy.ndimage import gaussian_filter
    p = gaussian_filter(np.nan_to_num(F["msl"], nan=np.nanmean(F["msl"])), 1.0)
    lap = np.gradient(np.gradient(p, axis=0), axis=0) + np.gradient(np.gradient(p, axis=1), axis=1)
    lat, lon = F["lat"], F["lon"]
    # trough axis cells: laplacian locally large and positive, pressure not at a closed minimum
    from scipy.ndimage import maximum_filter
    from scipy.ndimage import minimum_filter
    near_min = maximum_filter((p == minimum_filter(p, size=5)).astype(np.uint8), size=5) > 0   # skip the low centres themselves
    pk = (lap == maximum_filter(lap, size=5)) & (lap > np.nanpercentile(lap, 90)) & ~near_min
    ii, jj = np.where(pk)
    print("Cells of strongest cyclonic isobar curvature (troughs/kinks), strongest first:")
    for k in np.argsort(-lap[ii, jj])[:12]:
        print(f"  {lat[ii[k]]:.1f}N {ew(lon[jj[k]])}: curvature {lap[ii[k], jj[k]]:.2f} hPa/cell^2, mslp {F['msl'][ii[k], jj[k]]:.0f}")


if __name__ == "__main__":
    d, cmd, *a = sys.argv[1:]
    F = load(d)
    a = [float(x) for x in a]
    {"section": lambda: section(F, *a), "troughs": lambda: troughs(F), "gradmax": lambda: gradmax(F, *a)}[cmd]()
