"""Storm Twins: the storm-centred 500 nm pattern of a low and its closest past ERA5 storms.

Ported from jkrek17/hf-low research/era5/storm_patch_analogs (the recipe that was tested there, unchanged):
a 13 x 13 north-up patch, 154.33 km spacing (edge 926 km = 500 nm), bilinear from 1.5 degree fields; channels
500 hPa height, MSLP, 250 hPa u and v as anomalies from the WeatherBench2 1990-2019 ERA5 climatology; 0.25 degree
input is coarsened with that pipeline's conservative 7-point rule; the frozen 15-component PCA fitted on ERA5
2014-15..2020-21 (gfs/results/frozen_pca_full.npz). Twins are the k nearest library fixes in that space.
The library (32,288 ERA5 pipeline A fixes, Oct-Apr 2014-15..2021-22) is a proxy: its outcomes are ERA5's gust class.
"""
import numpy as np
from scipy import ndimage

NP, DKM = 13, 154.3333
RE = 6371.0
MASK_LAT = 85.0
CH = ("a_z500", "a_msl", "a_u250", "a_v250", "z500", "msl")
CLASSES = ("below gale", "gale", "storm", "hurricane force")
_a = (np.arange(NP) - NP // 2) * DKM
PX, PY = np.meshgrid(_a, _a, indexing="xy")
PR = np.hypot(PX, PY)
PBANG = np.degrees(np.arctan2(-PY, PX))
_W7 = np.array([0.5, 1, 1, 1, 1, 1, 0.5]) / 6.0


def destination(lat, lon, brg, dkm):
    p, l, b, d = np.radians(lat), np.radians(lon), np.radians(brg), dkm / RE
    p2 = np.arcsin(np.sin(p) * np.cos(d) + np.cos(p) * np.sin(d) * np.cos(b))
    l2 = l + np.arctan2(np.sin(b) * np.sin(d) * np.cos(p), np.cos(d) - np.sin(p) * np.sin(p2))
    return np.degrees(p2), np.degrees(l2) % 360


def sample(field, lat, lon):
    """Bilinear sample of field[121, 240] (lat -90..90, lon 0..358.5) at points; NaN where |lat| > 85."""
    row = (lat + 90) / 1.5
    col = (lon % 360) / 1.5
    f = np.concatenate([field, field[:, :1]], 1)
    out = ndimage.map_coordinates(f, [row, col], order=1, mode="nearest")
    return np.where(np.abs(lat) > MASK_LAT, np.nan, out)


def coarsen(a):
    """0.25 degree [721, 1440] (lat 90..-90) -> 1.5 degree [121, 240] (lat -90..90)."""
    a = a.astype(np.float64)
    nan = np.isnan(a)
    w = (~nan).astype(np.float64)
    a = np.where(nan, 0.0, a)

    def smooth(x):
        xl = np.concatenate([x[:, -3:], x, x[:, :3]], axis=1)
        y = sum(_W7[k] * xl[:, k:k + 1440] for k in range(7))[:, ::6]
        yl = np.concatenate([y[3:0:-1], y, y[-2:-5:-1]], axis=0)
        return sum(_W7[k] * yl[k:k + 721] for k in range(7))[::6]
    num, den = smooth(a), smooth(w)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0.5 * smooth(np.ones_like(w)), num / den, np.nan)
    return out[::-1]


def anomalies(z500_m, msl_hpa, u250, v250, clim, valid):
    """1.5 degree fields at a 00 or 12 UTC valid time -> {channel: field} (CH), anomalies against clim
    (npz with doy, hour, z500, msl, u250, v250 as [hour, doy, 121, 240])."""
    h = list(clim["hour"]).index(valid.hour)
    doy = valid.timetuple().tm_yday
    c = {k: clim[k][h, doy - 1].astype(np.float64) for k in ("z500", "msl", "u250", "v250")}
    return {"a_z500": z500_m - c["z500"], "a_msl": msl_hpa - c["msl"], "a_u250": u250 - c["u250"],
            "a_v250": v250 - c["v250"], "z500": z500_m, "msl": msl_hpa}


def patch(fields, lat, lon):
    """{channel: 1.5 degree field} -> patch [6, 13, 13] float16 centred on (lat, lon), north-up."""
    la, lo = destination(lat, lon, 90.0 + PBANG, PR)
    return np.stack([sample(fields[c], la, lo) for c in CH]).astype(np.float16)


def gfs_patches(g, lows, valid, clim):
    """rk.fetch.gfs_pattern fields at a 00/12 UTC valid time and lows (k, >=2: lat, lon) -> patches [k, 6, 13, 13]."""
    a = anomalies(coarsen(g["z500"]), coarsen(g["msl"]) / 100.0, coarsen(g["u250"]), coarsen(g["v250"]), clim, valid)
    return np.stack([patch(a, la, lo) for la, lo in np.asarray(lows)[:, :2]]) if len(lows) else np.zeros((0, 6, NP, NP), np.float16)


def assets():
    """The lab job's inputs from rk.store.lab_asset -> (library dict, climatology dict, Frozen)."""
    from . import store
    p = {n: store.lab_asset(n) for n in ("twins_library", "twins_clim0012", "twins_pca")}
    missing = [n for n, v in p.items() if v is None]
    if missing:
        raise FileNotFoundError("lab assets not found: %s (release lab-assets)" % ", ".join(missing))
    return dict(np.load(p["twins_library"])), dict(np.load(p["twins_clim0012"])), Frozen(p["twins_pca"])


class Frozen:
    """The frozen ERA5 scaler, mask and PCA (hf-low gfs/results/frozen_pca_full.npz)."""

    def __init__(self, path):
        z = np.load(path)
        self.sd, self.mask, self.mu, self.comp, self.pm = z["sd"], z["mask"], z["mu"], z["comp"], z["pm"]

    def pcs(self, X):
        """Patches [n, 6, 13, 13] -> [n, 15] pattern components."""
        Z = np.nan_to_num(np.asarray(X)[:, :4].astype(np.float32) / self.sd[:, :4], nan=0.0)
        Z = Z[:, :, self.mask].reshape(len(Z), -1)
        return (Z - self.mu - self.pm) @ self.comp.T


def twins(lib, pcs, k=30, exclude_season=None, show=5):
    """One low's 15 components -> {"n": k, "counts": twins per gust class (CLASSES order), "hf_share",
    "closest": indices into lib of the `show` closest twins from different storms}.
    lib: dict of arrays with pcs [N, 15], track, season, gcls. exclude_season drops same-season twins (hindcasts)."""
    ok = np.ones(len(lib["pcs"]), bool) if exclude_season is None else lib["season"] != exclude_season
    idx = np.flatnonzero(ok)
    d = np.sqrt(((lib["pcs"][idx] - pcs[None, :]) ** 2).sum(1))
    order = idx[np.argsort(d)]
    near = order[:k]
    counts = np.bincount(lib["gcls"][near], minlength=4)
    closest, seen = [], set()
    for j in order:
        if lib["track"][j] in seen:
            continue
        seen.add(lib["track"][j])
        closest.append(int(j))
        if len(closest) == show:
            break
    return {"n": k, "counts": counts.tolist(), "hf_share": float(counts[3] / k), "closest": closest}
