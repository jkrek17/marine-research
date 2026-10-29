"""Truth for scoring: the analysis (where), ship and buoy winds, and ASCAT (how strong).

obs()    ship and buoy 10 m wind rebuilt from the GDAS first guess plus the O-B departure
ascat()  RSS ASCAT v2.1 cells near the valid time, equivalent-neutral or real 10 m wind
smap_day()  RSS SMAP v1.0 L3 daily winds (L-band radiometer), a second equivalent-neutral instrument
star_day(), star()  NOAA STAR OSCAT-3 and coastal ultra-high-resolution ASCAT passes (kinds oscat, uhr)
ascat_grid()  ascat() snapped to the basin grid (seen mask, max speed)
hf_archive(), hf_fixes()  OPC hurricane-force low fixes from the jkrek17/hf-low archive
era5()   any ERA5 single-level field at an hour, from the public ARCO zarr (a reanalysis: a proxy for the analysis,
         back to 1940), cut to both boxes and cached under CACHE/truth/era5/ (not in releases)
Everything here is cached as truth files (rk.store.truth_*): CACHE/truth first, then the legacy
DATA/truth, then the release truth-{kind}[-{basin}]-{YYYYMM} of marine-research-data. A new file is written
to CACHE/truth and marked unpublished; tools/publish_store.py sends it. A loader returns None when its source
is not posted. The hf-low archive is not in releases: hf_archive() reads it from the hf-low repo over HTTPS.
"""
import datetime as dt
import functools
import io
import json
import re
import threading
from pathlib import Path

import numpy as np

from . import KT, fetch
from .basins import BASINS, grid, inside, sample
from . import paths
from .store import (analysis, truth_cache_path, truth_locate, truth_save)  # noqa: F401  (analysis is re-exported)

HERE = Path(__file__).resolve().parent
BLACKLIST_FILE = HERE / "data" / "obs_blacklist_basins.txt"
FIXED_FILE = HERE / "data" / "fixed_stations.txt"
BUOY_BLOCKS = {"13", "21", "22", "31", "32", "41", "42", "44", "45", "46", "48", "61", "62", "63", "64"}
BUOY_Z, SHIP_TO_BUOY = 4.0, 0.88


# ---- ship and buoy winds ----

def _platform(sid, lat, lon):
    """Classify each station id as buoy, drifter, fixed (platform on a fixed site) or ship."""
    sid = np.asarray(sid)
    out = np.empty(len(sid), dtype="U8")
    for s in np.unique(sid):
        k = sid == s
        tol = 0.05 if s.isdigit() else 0.02
        moving = (np.ptp(lat[k]) > tol) or (np.ptp(lon[k]) > tol)
        if s.isdigit() and (len(s) == 7 or s[:2] in BUOY_BLOCKS):
            out[k] = "drifter" if moving else "buoy"
        elif s.isdigit():
            out[k] = "fixed"
        else:
            out[k] = "fixed" if (k.sum() >= 2 and not moving) else "ship"
    return out


def canon(sid):
    """Same station under its two spellings (7-digit ids with a 00 in the middle) -> one id."""
    sid = np.asarray(sid).astype("U12")
    return np.array([s[:2] + s[4:] if (len(s) == 7 and s.isdigit() and s[2:4] == "00") else s for s in sid],
                    dtype="U12")


def _id_set(path, comments=True):
    if not path.exists():
        return set()
    rows = [l.split()[0] for l in path.read_text().splitlines()
            if l.strip() and not (comments and l.lstrip().startswith("#"))]
    return set(rows)


def blacklist():
    """Stations with a persistent O-B bias or spread (rk/data/obs_blacklist_basins.txt)."""
    return _id_set(BLACKLIST_FILE)


def fixed_stations():
    """The 75 coastal stations that read 3-5 kt low (rk/data/fixed_stations.txt)."""
    return _id_set(FIXED_FILE)


def charnock_factor(spd, z_from, z_to=10.0, alpha=0.011, nu=1.5e-5, k=0.4, g=9.81):
    """Neutral log-profile ratio U(z_to)/U(z_from) with Charnock roughness; spd in m/s."""
    spd = np.maximum(np.asarray(spd, float), 0.5)
    us = spd * k / np.log(z_from / 1e-4)
    for _ in range(20):
        z0 = alpha * us ** 2 / g + 0.11 * nu / us
        us = spd * k / np.log(z_from / z0)
    return np.log(z_to / z0) / np.log(z_from / z0)


def _build_obs(valid):
    """Download the marine csv and the GDAS background for the valid time and cache both basins."""
    import pandas as pd
    ymd, hh = valid.strftime("%Y%m%d"), valid.strftime("%H")
    r = fetch.get("%s/gdas.%s/%s/atmos/wdqms/gdas.t%sz.marine.csv" % (fetch.GFS, ymd, hh, hh))
    if r is None:
        return False
    bg = fetch.gdas_background(valid)
    if bg is None:
        return False
    d0 = pd.read_csv(io.StringIO(r.text), comment="#", dtype={"Station_id": str})
    d0 = d0[d0.var_id.isin([41, 42])]
    for b in BASINS:
        d = d0[inside(b, d0.latitude.to_numpy(), d0.Longitude.to_numpy())]
        key = ["Station_id", "yyyymmdd", "HHMMSS", "latitude", "Longitude"]
        d = d.drop_duplicates(key + ["var_id"])
        u = d[d.var_id == 41].set_index(key)[["StatusFlag", "Bg_dep", "CodeType"]]
        v = d[d.var_id == 42].set_index(key)[["StatusFlag", "Bg_dep"]]
        m = u.join(v, how="inner", lsuffix="_u", rsuffix="_v").reset_index()
        t = pd.to_datetime(m.yyyymmdd.astype(str) + m.HHMMSS.astype(int).map("{:06d}".format), format="%Y%m%d%H%M%S")
        dth = ((t - pd.Timestamp(valid)).dt.total_seconds() / 3600.0).to_numpy()
        U, V, land = bg[b]["u"], bg[b]["v"], bg[b]["land"]
        lat, lo = m.latitude.to_numpy(float), m.Longitude.to_numpy(float) % 360
        # background f003..f009 of the previous cycle: obs time t (h from valid) is forecast hour t + 6, index t + 3
        fh = np.clip(dth + 3.0, 0, 6)
        i0 = np.clip(np.floor(fh).astype(int), 0, 5)
        w = fh - i0
        bu, bv = np.empty(len(m)), np.empty(len(m))
        for k in range(6):
            s = i0 == k
            if s.any():
                bu[s] = (1 - w[s]) * sample(U[k], b, lat[s], lo[s]) + w[s] * sample(U[k + 1], b, lat[s], lo[s])
                bv[s] = (1 - w[s]) * sample(V[k], b, lat[s], lo[s]) + w[s] * sample(V[k + 1], b, lat[s], lo[s])
        ou, ov = bu + m.Bg_dep_u.to_numpy(), bv + m.Bg_dep_v.to_numpy()
        st = np.maximum(m.StatusFlag_u.to_numpy(), m.StatusFlag_v.to_numpy()).astype(np.int16)
        sid = m.Station_id.astype(str).to_numpy().astype("U12")
        truth_save("obs", b, valid, lat=lat, lon=lo, u=ou, v=ov, dt_hours=dth, station_id=sid, status=st,
              platform=_platform(sid, lat, lo), land=sample(land, b, lat, lo),
              bg_speed_kt=np.hypot(bu, bv) * KT)
    return True


def obs_points(basin, valid):
    """All status-flagged marine points of the valid time's csv, with the rebuilt wind -> dict or None."""
    p = truth_locate("obs", basin, valid)
    if p is None:
        if not _build_obs(valid):
            return None
        p = truth_cache_path("obs", basin, valid)
    with np.load(p) as z:
        return {k: z[k] for k in z.files}


def obs(basin, valid, platforms=("buoy", "drifter"), adjust10m=True, max_dt=1.0):
    """Ship and buoy winds at the valid time, one record per station -> dict of 1-D arrays, or None if the
    marine csv or the GDAS background is not posted.

    Wind = GDAS first guess (previous cycle f003..f009, linear in time, bilinear in space) + O-B departure.
    Status 0 only, within max_dt hours, open water, blacklisted and fixed coastal stations removed; u, v
    are averaged within the window. adjust10m: ships scaled by 0.88 onto the buoy basis, then everything
    raised from 4 m to 10 m (neutral Charnock). Fields: lat, lon, u, v (m/s, unadjusted), speed_kt,
    speed_kt_raw, bg_speed_kt, station_id, platform. platforms: add "ship", "fixed" for ships + buoys."""
    o = obs_points(basin, valid)
    if o is None:
        return None
    cid = canon(o["station_id"])
    k = (o["status"] == 0) & (np.abs(o["dt_hours"]) <= max_dt + 1e-6) & (o["land"] <= 1e-6)
    k &= np.isin(o["platform"], platforms) & np.isfinite(o["u"]) & np.isfinite(o["v"])
    bad = list(blacklist() | fixed_stations())
    if bad:
        k &= ~np.isin(cid, bad) & ~np.isin(o["station_id"], bad)
    idx = np.where(k)[0]
    out = {f: [] for f in ("lat", "lon", "u", "v", "station_id", "platform", "bg_speed_kt")}
    for s in np.unique(cid[idx]):
        m = idx[cid[idx] == s]
        pref = min(o["station_id"][m], key=len)
        m = m[o["station_id"][m] == pref]
        for f in ("lat", "lon", "u", "v", "bg_speed_kt"):
            out[f].append(o[f][m].mean())
        out["station_id"].append(s)
        out["platform"].append(o["platform"][m[0]])
    out = {f: np.array(v) for f, v in out.items()}
    if not len(out["lat"]):
        out["speed_kt"] = np.zeros(0)
        out["speed_kt_raw"] = np.zeros(0)
        return out
    out["speed_kt"] = np.hypot(out["u"], out["v"]) * KT
    out["speed_kt_raw"] = out["speed_kt"].copy()
    if adjust10m:
        f = np.where(np.isin(out["platform"], ["ship", "fixed"]), SHIP_TO_BUOY, 1.0)
        f = f * charnock_factor(out["speed_kt"] / KT * f, BUOY_Z)
        out["speed_kt"] = out["speed_kt"] * f
    return out


# ---- stability: equivalent-neutral to real 10 m wind ----

def _psi(zeta, kind):
    """Stability function for momentum ("m") or heat ("h"): Businger-Dyer/Paulson when unstable,
    Beljaars-Holtslag when stable. zeta = z / L."""
    zeta = np.asarray(zeta, float)
    out = np.zeros_like(zeta)
    u = zeta < 0
    x = (1 - 16 * zeta[u]) ** 0.25
    if kind == "m":
        out[u] = 2 * np.log((1 + x) / 2) + np.log((1 + x * x) / 2) - 2 * np.arctan(x) + np.pi / 2
    else:
        out[u] = 2 * np.log((1 + x * x) / 2)
    s = ~u
    zs = np.minimum(zeta[s], 10)
    a, b, c, d = 1.0, 0.667, 5.0, 0.35
    if kind == "m":
        out[s] = -(a * zs + b * (zs - c / d) * np.exp(-d * zs) + b * c / d)
    else:
        out[s] = -((1 + 2 * a * zs / 3) ** 1.5 + b * (zs - c / d) * np.exp(-d * zs) + b * c / d - 1)
    return out


def enw_to_real(enw_kt, dT, T=285.0, k=0.4, g=9.81, alpha=0.011, nu=1.5e-5, zt=2.0):
    """Equivalent-neutral 10 m wind (kt) -> real 10 m wind (kt) for air minus sea temperature dT (K,
    air at 2 m). Lower in unstable air (dT < 0), higher in stable air."""
    U = np.maximum(np.asarray(enw_kt, float) / KT, 0.5)
    dT = np.asarray(dT, float)
    us = U * k / np.log(10 / 1e-4)
    for _ in range(20):
        z0 = alpha * us ** 2 / g + 0.11 * nu / us
        us = U * k / np.log(10 / z0)            # ENW defines u* through the neutral profile
    z0 = alpha * us ** 2 / g + 0.11 * nu / us
    Linv = np.zeros_like(U)
    for _ in range(30):
        ts = k * dT / (np.log(zt / 1e-4) - _psi(zt * Linv, "h"))
        Linv = np.clip(k * g * ts / (T * us ** 2), -5, 2)
    real = us / k * (np.log(10 / z0) - _psi(10 * Linv, "m"))
    return real * KT


def airsea(basin, valid):
    """GFS analysis 2 m air minus skin temperature (K, box grid) at the valid time -> array or None.
    Cached as truth kind "airsea" (both basins at once)."""
    p = truth_locate("airsea", basin, valid)
    if p is None:
        out = fetch._ncep(fetch.gfs_url(valid, 0), {"TMP:2 m above ground": "t2", "TMP:surface": "skt"})
        if out is None:
            return None
        for b in BASINS:
            truth_save("airsea", b, valid, t2=out["t2"][b], skt=out["skt"][b])
        p = truth_cache_path("airsea", basin, valid)
    with np.load(p) as z:
        return (z["t2"] - z["skt"]).astype(np.float32)


# ---- ASCAT ----

ASCAT_URL = "https://data.remss.com/ascat/metop{s}/bmaps_v02.1/y{y}/m{m}/ascat{s}_{d}_v02.1.gz"
_LAT = -89.875 + 0.25 * np.arange(720)
_LON = 0.125 + 0.25 * np.arange(1440)
_LAT_RANGE = (15.0, 70.0)
_SAT_ID = {"b": 2, "c": 3}
# Metop-B minus Metop-C equivalent-neutral speed gap (kt) by speed (kt), band means from 3.3 million same-cell
# B-C pairs within 60 min, winter 2025-26: +0.30 at 25-35 kt, +0.57 at 35-45, +0.84 at 45-55, +1.25 at 55+.
# Source: /mnt/project-files/chance-calibration/ascat_noise/results.md (2026-10-16). Flat beyond the last knot.
INTERCAL_SPEED = [0.0, 30.0, 40.0, 50.0, 60.0]
INTERCAL_GAP = [0.0, 0.30, 0.57, 0.84, 1.25]


def _intercal(spd, sat):
    """Meet halfway: half the B-C gap off Metop-B (sat 2), half onto Metop-C (sat 3); other ids unchanged.
    spd is equivalent-neutral kt, the gap is read at the raw speed."""
    spd = np.asarray(spd, np.float32)
    sat = np.asarray(sat)
    half = 0.5 * np.interp(spd, INTERCAL_SPEED, INTERCAL_GAP)
    sign = np.where(sat == _SAT_ID["b"], -1.0, np.where(sat == _SAT_ID["c"], 1.0, 0.0))
    return (spd + sign * half).astype(np.float32)


def _ascat_get(sat, ymd):
    """One satellite's daily bytemap -> uint8 [2 passes, 5 vars, 720, 1440] or None if not posted."""
    import gzip
    r = fetch.get(ASCAT_URL.format(s=sat, y=ymd[:4], m=ymd[4:6], d=ymd))
    if r is None:
        return None
    return np.frombuffer(gzip.decompress(r.content), np.uint8).reshape(2, 5, 720, 1440)


def _ascat_cells(a, sat_id):
    """Valid ocean cells of one satellite-day, latitudes 15-70N. Bytes: time = b*6 min UTC, speed = b*0.2 m/s,
    direction = b*1.5 deg (toward), rain (bit 0 scatterometer flag, bits 2-7 radiometer rain), sos = b*0.02."""
    rows = np.nonzero((_LAT >= _LAT_RANGE[0]) & (_LAT <= _LAT_RANGE[1]))[0]
    parts = []
    for p in range(2):
        t, w, d, rn, so = (a[p, i][rows] for i in range(5))
        iy, ix = np.nonzero((w <= 250) & (t <= 240))
        parts.append(dict(
            lat=_LAT[rows][iy].astype(np.float32), lon=_LON[ix].astype(np.float32),
            t_min=(t[iy, ix].astype(np.int16) * 6),
            spd_enw_kt=(w[iy, ix] * 0.2 * KT).astype(np.float32),
            dir_deg=((d[iy, ix] * 1.5 + 180.0) % 360).astype(np.float32),
            scat_rain=(rn[iy, ix] & 1).astype(np.uint8), rad_rain=(rn[iy, ix] >> 2).astype(np.uint8),
            sos=(so[iy, ix] * 0.02).astype(np.float32), sat=np.full(iy.size, sat_id, np.uint8)))
    return {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}


def ascat_day(day):
    """All valid ocean cells of a UTC day (both Metop satellites, 15-70N, all longitudes) -> dict or None.
    t_min is minutes after 00 UTC of that day. Cached as truth kind "ascat" (one file per day). A day with only one
    satellite posted is cached only once it is a week old (the other may still arrive)."""
    ymd = day.strftime("%Y%m%d")
    p = truth_locate("ascat", None, day)
    if p is not None:
        with np.load(p) as z:
            return {k: z[k] for k in z.files if k != "sats"}
    parts, sats = [], ""
    for s in ("b", "c"):
        a = _ascat_get(s, ymd)
        if a is not None:
            parts.append(_ascat_cells(a, _SAT_ID[s]))
            sats += s
    if not parts:
        return None
    c = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
    age = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.datetime.combine(day, dt.time())
    if len(sats) == 2 or age > dt.timedelta(days=7):
        truth_save("ascat", None, day, sats=np.array(sats), **c)
    return c


# ---- SMAP ----

SMAP_URL = "https://data.remss.com/smap/wind/L3/v01.0/daily/{kind}/{y}/RSS_smap_wind_daily_{y}_{m}_{d}{nrt}_v01.0.nc"
_SMAP_LAT = -89.875 + 0.25 * np.arange(720)
_NC_LOCK = threading.Lock()  # the netCDF/HDF5 library is not thread-safe
_SMAP_MAGIC = (b"\x89HDF\r\n\x1a\n", b"CDF\x01", b"CDF\x02")


def _smap_get(day, kind):
    """One RSS SMAP daily netCDF (kind "FINAL" or "NRT") as bytes, or None if not posted. RSS answers a
    missing file with an HTML page, so the bytes must start with the netCDF/HDF5 signature."""
    ymd = day.strftime("%Y %m %d").split()
    r = fetch.get(SMAP_URL.format(kind=kind, y=ymd[0], m=ymd[1], d=ymd[2], nrt="_NRT" if kind == "NRT" else ""))
    if r is None or not r.content.startswith(_SMAP_MAGIC):
        return None
    return r.content


def _smap_cells(blob):
    """Valid ocean cells of one SMAP daily file, latitudes 15-70N, both nodes. wind int16 x 0.01 m/s
    (equivalent-neutral 10 m), minute int16 of the UTC day, -9999 missing; node 0 ascending (~18 h local),
    1 descending (~06 h local). Layout [lat 720, lon 1440, node 2]-agnostic: axes are read by dimension name."""
    import netCDF4
    with _NC_LOCK, netCDF4.Dataset("smap.nc", memory=blob) as ds:
        out = {}
        for name in ("wind", "minute"):
            v = ds.variables[name]
            v.set_auto_maskandscale(False)
            a = np.asarray(v[:])
            out[name] = np.moveaxis(a, [v.dimensions.index(d) for d in ("lat", "lon", "node")], [0, 1, 2])
        lat = np.asarray(ds.variables["lat"][:], float)
        lon = np.asarray(ds.variables["lon"][:], float) % 360
    w, m = out["wind"], out["minute"]
    ok = (w != -9999) & (w >= 0) & (m != -9999) & (m >= 0)
    ok &= ((lat >= _LAT_RANGE[0]) & (lat <= _LAT_RANGE[1]))[:, None, None]
    iy, ix, node = np.nonzero(ok)
    return dict(lat=lat[iy].astype(np.float32), lon=lon[ix].astype(np.float32),
                t_min=m[iy, ix, node].astype(np.int16),
                spd_enw_kt=(w[iy, ix, node].astype(np.float32) * 0.01 * KT).astype(np.float32),
                node=node.astype(np.uint8))


def smap_day(day):
    """All valid ocean cells of a UTC day of RSS SMAP v1.0 L3 daily winds (15-70N, all longitudes, both
    nodes) -> dict or None if neither FINAL nor NRT is posted. Fields: lat, lon (0-360), t_min (minute of the
    UTC day), spd_enw_kt (equivalent-neutral 10 m wind, kt), node (0 ascending ~18 h local, 1 descending ~06 h
    local). FINAL is tried first, then NRT. Cached as truth kind "smap" with final = 1 for FINAL,
    0 for NRT (a cached NRT day is not re-fetched when FINAL appears; delete the file to refresh)."""
    ymd = day.strftime("%Y%m%d")
    p = truth_locate("smap", None, day)
    if p is not None:
        with np.load(p) as z:
            return {k: z[k] for k in z.files if k != "final"}
    blob, final = _smap_get(day, "FINAL"), 1
    if blob is None:
        blob, final = _smap_get(day, "NRT"), 0
    if blob is None:
        return None
    c = _smap_cells(blob)
    truth_save("smap", None, day, final=np.array(final, np.uint8), **c)
    return c


# ---- NOAA STAR passes (OSCAT-3, coastal UHR ASCAT) ----

STAR_URL = "https://manati.star.nesdis.noaa.gov"
STAR_LAYERS = {"oscat": ("oscat3_AS", "oscat3_DS"),
               "uhr": ("UHR_METOP-B_AS", "UHR_METOP-B_DS", "UHR_METOP-C_AS", "UHR_METOP-C_DS")}
_STAR_LIST = STAR_URL + "/product_src/info/oswtviewer/map_layers.php?date={ymd}&prefix={prefix}"
_STAR_SAT = {"oscat3": 0, "UHR_METOP-B": 1, "UHR_METOP-C": 2}   # sat code by prefix without the node suffix
_STAR_PASS_MIN = 100      # nominal pass length (one orbit), used for the last pass of a layer
_STAR_CACHE_DAYS = 2      # a day younger than this is still gaining passes and is not cached
_RE_DOY = re.compile(r"(\d{4})-(\d{3})T(\d{2})-(\d{2})-(\d{2})")
_RE_YMD = re.compile(r"_(\d{8})T(\d{6})_")


def _star_start(name):
    """Pass start (naive UTC datetime) from a STAR pass file name: '..._2026-301T02-32-14_lite5.json' (year,
    day of year, time; OSCAT-3) or '..._20261028T003525_73213_rev1of1_ec.json' (UHR ASCAT). ValueError if neither."""
    m = _RE_DOY.search(name)
    if m:
        y, doy, h, mi, sec = (int(g) for g in m.groups())
        return dt.datetime(y, 1, 1) + dt.timedelta(days=doy - 1, hours=h, minutes=mi, seconds=sec)
    m = _RE_YMD.search(name)
    if m:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    raise ValueError("no pass start time in %r" % name)


def star_passes(kind, day):
    """Passes NOAA STAR lists for a UTC day -> [(prefix, url, start datetime)] sorted by (prefix, start); empty when
    nothing is posted. The server keeps only about the last month."""
    out = []
    for prefix in STAR_LAYERS[kind]:
        r = fetch.get(_STAR_LIST.format(ymd=day.strftime("%Y%m%d"), prefix=prefix))
        if r is None:
            continue
        j = json.loads(r.content)
        for u in j.get("json_urls") or []:
            out.append((prefix, STAR_URL + u if u.startswith("/") else u, _star_start(u)))
    return sorted(out, key=lambda x: (x[0], x[2]))


def _star_grid(recs):
    """UHR ASCAT layout, leaflet-velocity grids [{header: {parameterNumber 2 (u) | 3 (v) | other (q), lo1, la1,
    dx, dy, nx, ny}, data: [row-major from la1 southward, None = no wind]}] -> point records like OSCAT's."""
    by = {}
    for r in recs:
        h = r["header"]
        by[{2: "u", 3: "v"}.get(h.get("parameterNumber"), "q")] = r
    h = by["u"]["header"]
    nx, ny = int(h["nx"]), int(h["ny"])
    def arr(k):
        if k not in by:
            return np.zeros(nx * ny, np.float32)
        return np.array([np.nan if x is None else x for x in by[k]["data"]], np.float32)
    u, v, q = arr("u"), arr("v"), arr("q")
    ok = np.isfinite(u) & np.isfinite(v)
    iy, ix = np.divmod(np.nonzero(ok)[0], nx)
    la = h["la1"] - iy * h["dy"]
    lo = h["lo1"] + ix * h["dx"]
    qq = np.nan_to_num(q[ok]).astype(int)
    return [dict(la=float(a), lo=float(b), u=float(c), v=float(d), q=int(e))
            for a, b, c, d, e in zip(la, lo, u[ok], v[ok], qq)]


def _star_points(recs):
    """Pass records -> arrays cropped to latitudes 15-70N, lon 0-360, speeds in knots. OSCAT-3 files are point
    records [{la, lo, u, v, q}]; UHR ASCAT files are regular grids (see _star_grid), converted first."""
    if recs and "header" in recs[0]:
        recs = _star_grid(recs)
    if not recs:
        z = np.zeros(0, np.float32)
        return dict(lat=z, lon=z, u_kt=z, v_kt=z, spd_kt=z, q=np.zeros(0, np.uint8))
    la = np.array([r["la"] for r in recs], np.float32)
    keep = np.nonzero((la >= _LAT_RANGE[0]) & (la <= _LAT_RANGE[1]))[0]
    recs = [recs[i] for i in keep]
    u = np.array([r["u"] for r in recs], np.float32)
    v = np.array([r["v"] for r in recs], np.float32)
    return dict(lat=la[keep], lon=(np.array([r["lo"] for r in recs], np.float32) % 360).astype(np.float32),
                u_kt=u, v_kt=v, spd_kt=np.hypot(u, v).astype(np.float32),
                q=np.array([r["q"] for r in recs], np.uint8))


def star_day(kind, day):
    """All points of the passes NOAA STAR lists under a UTC day, kind "oscat" (OSCAT-3, ~12.5 km) or "uhr" (coastal
    ultra-high-resolution ASCAT, Metop-B and -C) -> dict or None when no pass is posted. Latitudes 15-70N, raw
    points (land and ice not masked). Fields: lat, lon (float32, 0-360), u_kt, v_kt, spd_kt (float32; 10 m wind as
    served by NOAA STAR, equivalent-neutral not confirmed, knots), q (uint8, quality flag from the source, 1 =
    flagged, meaning undocumented, likely rain; kept), t_min (int16, pass START minute from 00 UTC of `day`, negative
    when the pass started the previous day), t_end_min (int16, start of the next pass of the same layer, or start +
    100 min for the last: a point's time is only bracketed, [t_min, t_end_min]), node (uint8, 0 ascending, 1
    descending), sat (uint8, 0 OSCAT-3, 1 Metop-B, 2 Metop-C), pass_id (int16, index into the sorted pass list).
    Cached as truth kind `kind` only when the day is at least 2 days old; the server keeps about a month."""
    p = truth_locate(kind, None, day)
    if p is not None:
        with np.load(p) as z:
            return {k: z[k] for k in z.files}
    passes = star_passes(kind, day)
    if not passes:
        return None
    midnight = dt.datetime.combine(day, dt.time())
    parts = []
    for i, (prefix, url, start) in enumerate(passes):
        r = fetch.get(url)
        if r is None:
            continue
        c = _star_points(json.loads(r.content))
        n = c["lat"].size
        nxt = [s for pf, _, s in passes if pf == prefix and s > start]
        t0 = int(round((start - midnight).total_seconds() / 60))
        t1 = int(round((min(nxt) - midnight).total_seconds() / 60)) if nxt else t0 + _STAR_PASS_MIN
        c.update(t_min=np.full(n, t0, np.int16), t_end_min=np.full(n, t1, np.int16),
                 node=np.full(n, 0 if prefix.endswith("_AS") else 1, np.uint8),
                 sat=np.full(n, _STAR_SAT[prefix[:-3]], np.uint8), pass_id=np.full(n, i, np.int16))
        parts.append(c)
    if not parts:
        return None
    c = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
    age = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - midnight
    if age >= dt.timedelta(days=_STAR_CACHE_DAYS):
        truth_save(kind, None, day, **c)
    return c


def star(kind, lat_range, lon_range, t0, t1):
    """star_day points inside the box (lat_range (lo, hi), lon_range (lo, hi) in 0-360, lo <= hi) whose pass bracket
    [t_min, t_end_min] overlaps [t0, t1] (naive UTC datetimes) -> dict (star_day fields plus `day_min`, minutes from
    t0 to 00 UTC of the file's day) or None when no day is posted. Points outside the window are dropped, not times
    refined: a point's time is only known to lie in its bracket."""
    d, last = (t0 - dt.timedelta(days=1, hours=2)).date(), (t1 + dt.timedelta(hours=2)).date()
    parts = []
    while d <= last:
        c = star_day(kind, d)
        if c is not None:
            base = (dt.datetime.combine(d, dt.time()) - t0).total_seconds() / 60.0
            win = (t1 - t0).total_seconds() / 60.0
            ok = ((c["lat"] >= lat_range[0]) & (c["lat"] <= lat_range[1])
                  & (c["lon"] >= lon_range[0]) & (c["lon"] <= lon_range[1])
                  & (base + c["t_min"] <= win) & (base + c["t_end_min"] >= 0))
            parts.append({k: v[ok] for k, v in c.items()} | {"day_min": np.full(int(ok.sum()), base, np.float32)})
        d += dt.timedelta(days=1)
    if not parts:
        return None
    return {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}


@functools.lru_cache(maxsize=64)
def water_mask(basin, valid):
    """Open, ice-free water at the valid time (bool, basin grid) -> array or None: the analysis mask when the
    analysis is stored or can be built, else the same definition (GFS f000 land < 0.01 and ice <= 0.15) from
    GFS alone. The mask never used IFS, but analysis() needs both models, and there is no IFS analysis at
    06/18 UTC, which left the Pacific's best ASCAT hours unscored before 2026-10-17."""
    an = analysis(basin, valid)
    if an is not None:
        return an["mask"]
    m = fetch.gfs_mask(valid)
    if m is None:
        return None
    return (m[basin]["land"] < 0.01) & (m[basin]["ice"] <= 0.15)



def mask_time(basin, valid):
    """The time whose analysis supplies the open-water mask for `valid`: valid itself when its analysis exists, else
    the 00/12 UTC analysis 6 h or less away (the earlier one first), else None."""
    cands = [valid]
    if valid.hour not in (0, 12):
        h = valid.hour % 12
        cands += [valid - dt.timedelta(hours=h), valid + dt.timedelta(hours=12 - h)]
    for c in cands:
        if abs((c - valid).total_seconds()) <= 6 * 3600 and analysis(basin, c) is not None:
            return c
    return None


def ascat(basin, valid, max_dt_min=90, real=True, intercal=True, rain_keep_kt=None, smap_dt_min=180,
          rain_speed="ascat"):
    """ASCAT cells within max_dt_min of the valid time, inside the basin box -> dict of 1-D arrays, or None
    when a needed day is not posted (RSS lags about 2 days) or the analysis is missing.

    Rain dropped (scatterometer flag, or radiometer rain >= 2); open water only (analysis mask sampled at
    the cell > 0.99). spd_enw_kt is the equivalent-neutral 10 m wind; spd_kt equals it when real=False, else
    the real 10 m wind using the analysis air minus sea temperature at the cell. Also lat, lon, dt_min
    (obs minus valid), dir_deg (from), sat (2 Metop-B, 3 Metop-C).

    intercal (default True): Metop-B reads higher than Metop-C by a gap that grows with speed (+0.30 kt at
    25-35 kt to +1.25 at 55+, INTERCAL_*); half the gap is subtracted from B and added to C on the
    equivalent-neutral speed before the real-wind conversion, so spd_enw_kt and spd_kt both carry it.
    spd_enw_raw_kt is the unadjusted equivalent-neutral speed. intercal=False gives the raw RSS values.

    rain_keep_kt (default None: every rain-flagged cell dropped): keep a rain-flagged cell whose raw
    equivalent-neutral speed is >= rain_keep_kt where SMAP agrees: the largest SMAP wind (smap_day,
    equivalent-neutral, not rain-masked) within one 0.25 deg cell of it, from passes within smap_dt_min of
    the valid time, is also >= rain_keep_kt. Returns None if a needed SMAP day is not posted. Field
    rain_kept (bool) marks the kept rain cells. Rain cells below the threshold stay dropped, so only use it
    to ask what the dropped strong cells change (adversarial audit 2026-10-17, holes 4 and 6).
    rain_speed "ascat" (default): only rain cells ASCAT itself reads at rain_keep_kt+ are candidates, and keep
    ASCAT's speed. "smap": any rain-flagged cell where SMAP reads rain_keep_kt+ is kept, with the larger of
    ASCAT and SMAP (equivalent-neutral; intercal and the real-wind step then apply as usual): the upper bound
    for cores ASCAT cannot read in rain.

    Open-water mask: water_mask(basin, valid), which builds it from GFS alone where there is no analysis (06/18
    UTC: the IFS analysis is not posted); failing that, the nearest 00/12 UTC analysis within 6 h (mask_time), which
    also supplies the GFS air-sea field when the valid time's is missing. At 00/12 UTC the behaviour is unchanged."""
    valid = dt.datetime.combine(valid, dt.time()) if type(valid) is dt.date else valid
    lo, hi = valid - dt.timedelta(minutes=max_dt_min), valid + dt.timedelta(minutes=max_dt_min)
    days = sorted({lo.date(), hi.date()})
    parts = []
    for day in days:
        c = ascat_day(day)
        if c is None:
            return None
        t0 = dt.datetime.combine(day, dt.time())
        c = dict(c)
        c["dt_min"] = (c.pop("t_min").astype(np.float32) + (t0 - valid).total_seconds() / 60.0)
        parts.append(c)
    c = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
    near = (np.abs(c["dt_min"]) <= max_dt_min) & inside(basin, c["lat"], c["lon"])
    rainy = (c["scat_rain"] != 0) | (c["rad_rain"] >= 2)
    kept = np.zeros(rainy.shape, bool)
    if rain_keep_kt is not None:
        if rain_speed not in ("ascat", "smap"):
            raise ValueError("rain_speed must be 'ascat' or 'smap'")
        cand = near & rainy
        if rain_speed == "ascat":
            cand &= c["spd_enw_kt"] >= rain_keep_kt
        if cand.any():
            sm = _smap_max(valid, smap_dt_min, c["lat"][cand], c["lon"][cand], rain_keep_kt)
            if sm is None:
                return None
            agree = np.isfinite(sm)
            idx = np.flatnonzero(cand)[agree]
            kept[idx] = True
            if rain_speed == "smap":
                c["spd_enw_kt"] = c["spd_enw_kt"].astype(np.float32, copy=True)
                c["spd_enw_kt"][idx] = np.maximum(c["spd_enw_kt"][idx], sm[agree])
    k = near & (~rainy | kept)
    c["rain_kept"] = kept
    c = {f: v[k] for f, v in c.items()}
    tm = valid
    mask = water_mask(basin, valid)
    if mask is None:
        tm = mask_time(basin, valid)
        if tm is None:
            return None
        mask = analysis(basin, tm)["mask"]
    ok = sample(mask.astype(float), basin, c["lat"], c["lon"]) > 0.99
    out = {f: v[ok] for f, v in c.items() if f not in ("scat_rain", "rad_rain", "sos")}
    out["spd_enw_raw_kt"] = out["spd_enw_kt"].copy()
    if intercal:
        out["spd_enw_kt"] = _intercal(out["spd_enw_kt"], out["sat"])
    out["spd_kt"] = out["spd_enw_kt"].copy()
    if real:
        a = airsea(basin, valid)
        if a is None and tm != valid:
            a = airsea(basin, tm)
        if a is None:
            return None
        dT = sample(a, basin, out["lat"], out["lon"])
        good = np.isfinite(dT)
        out = {f: v[good] for f, v in out.items()}
        out["spd_kt"] = enw_to_real(out["spd_enw_kt"], dT[good]).astype(np.float32)
    return out


def _smap_max(valid, dt_min, lat, lon, floor_kt=0.0):
    """Largest SMAP equivalent-neutral wind (kt) within one 0.25 deg cell of each (lat, lon), from SMAP cells
    within dt_min of valid; NaN where none (or none >= floor_kt). None when a needed SMAP day is not posted."""
    lo, hi = valid - dt.timedelta(minutes=dt_min), valid + dt.timedelta(minutes=dt_min)
    best = {}
    for day in sorted({lo.date(), hi.date()}):
        sm = smap_day(day)
        if sm is None:
            return None
        off = (dt.datetime.combine(day, dt.time()) - valid).total_seconds() / 60.0
        k = (np.abs(sm["t_min"].astype(np.float64) + off) <= dt_min) & (sm["spd_enw_kt"] >= floor_kt)
        for r, q, v in zip(np.floor(sm["lat"][k] / 0.25 + 0.5).astype(int),
                           np.floor((sm["lon"][k] % 360) / 0.25 + 0.5).astype(int) % 1440, sm["spd_enw_kt"][k]):
            if v > best.get((r, q), -1.0):
                best[(r, q)] = float(v)
    r0 = np.floor(np.asarray(lat, np.float64) / 0.25 + 0.5).astype(int)
    q0 = np.floor((np.asarray(lon, np.float64) % 360) / 0.25 + 0.5).astype(int)
    out = np.full(r0.shape, np.nan, np.float32)
    for n, (r, q) in enumerate(zip(r0, q0)):
        vals = [best[(r + dr, (q + dq) % 1440)] for dr in (-1, 0, 1) for dq in (-1, 0, 1)
                if (r + dr, (q + dq) % 1440) in best]
        if vals:
            out[n] = max(vals)
    return out

def ascat_target(basin, valid, thr=48.0, box=(5, 7), max_dt_min=90, rain_keep_kt=None, rain_speed="ascat",
                 smap_dt_min=180):
    """ASCAT storm-core target on the basin grid -> dict or None (None when ascat() is None: a day not posted).

    Uses ascat(real=True, intercal=True). Cells are snapped to the 0.25 deg grid with floor(x + 0.5) (the
    RSS centres sit 0.125 deg off the grid; see LESSONS); when several observations fall in one cell the
    highest counts. Returns
      seen    bool [y, x]  a (rain-free, open-water) ASCAT cell landed here
      spd     float [y, x] ASCAT real 10 m wind (kt) in the cell, NaN where unseen
      max_nb  float [y, x] maximum of spd over the box (rows, columns) centred on the cell, unseen cells
              ignored; NaN at unseen cells. box (5, 7) is about 50 km each way at 30-67 N, as the live
              model's target (wind-focus core/code/ascat_target.py: 5x7 maximum filter, -1 for unseen).
      y       bool [y, x]  seen & (max_nb >= thr); the training label. Only cells ASCAT saw count.
    No seen cell at all gives all-False / all-NaN grids (a valid case with nothing to score).
    rain_keep_kt, rain_speed, smap_dt_min: passed to ascat() (rain-flagged strong cells kept where SMAP agrees)."""
    from scipy import ndimage
    from .basins import grid
    a = ascat(basin, valid, max_dt_min=max_dt_min, real=True, intercal=True, rain_keep_kt=rain_keep_kt,
              rain_speed=rain_speed, smap_dt_min=smap_dt_min)
    if a is None:
        return None
    lats, lons = grid(basin)
    ny, nx = len(lats), len(lons)
    row = np.floor((lats[0] - np.asarray(a["lat"], np.float64)) / 0.25 + 0.5).astype(int)
    col = np.floor(((np.asarray(a["lon"], np.float64) % 360) - lons[0]) / 0.25 + 0.5).astype(int)
    ok = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
    spd = np.full((ny, nx), -1.0, np.float32)
    np.maximum.at(spd, (row[ok], col[ok]), np.asarray(a["spd_kt"], np.float32)[ok])
    seen = spd >= 0
    max_nb = ndimage.maximum_filter(spd, size=box)
    out_spd = np.where(seen, spd, np.nan).astype(np.float32)
    max_nb = np.where(seen, max_nb, np.nan).astype(np.float32)
    return {"seen": seen, "spd": out_spd, "max_nb": max_nb, "y": seen & (max_nb >= thr)}


# ---- ASCAT on the model grid: single cells and 3 x 3 boxes ----

def ascat_to_grid(basin, lat, lon, spd_kt):
    """Snap ASCAT cells to the basin's 0.25 deg model grid with floor(x + 0.5) (RSS centres sit 0.125 deg off
    the grid; np.rint empties every other row and column). Several cells in one grid cell (two satellites or
    passes inside the window) are averaged. Returns (grid, count): grid [ny, nx] in kt, NaN where there is
    no cell; count = number of cells averaged."""
    lats, lons = grid(basin)
    ny, nx = len(lats), len(lons)
    iy = np.floor((lats[0] - np.asarray(lat, float)) / 0.25 + 0.5).astype(int)
    ix = np.floor((np.asarray(lon, float) % 360 - lons[0]) / 0.25 + 0.5).astype(int)
    k = (iy >= 0) & (iy < ny) & (ix >= 0) & (ix < nx) & np.isfinite(spd_kt)
    s = np.zeros(ny * nx)
    c = np.zeros(ny * nx)
    flat = iy[k] * nx + ix[k]
    np.add.at(s, flat, np.asarray(spd_kt, float)[k])
    np.add.at(c, flat, 1.0)
    c = c.reshape(ny, nx)
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(c > 0, s.reshape(ny, nx) / c, np.nan)
    return g, c


def box_mean(grid_kt, min_valid=6, size=3):
    """Mean of the valid cells in the size x size box centred on every grid cell, NaN where fewer than
    min_valid of the size*size cells are valid (edges count missing cells as invalid). The centre cell need
    not itself be valid. Returns (mean, n_valid)."""
    g = np.asarray(grid_kt, float)
    ok = np.isfinite(g)
    r = size // 2
    ny, nx = g.shape
    pv = np.pad(np.where(ok, g, 0.0), r)
    po = np.pad(ok.astype(float), r)
    s = np.zeros((ny, nx))
    n = np.zeros((ny, nx))
    for dy in range(size):
        for dx in range(size):
            s += pv[dy:dy + ny, dx:dx + nx]
            n += po[dy:dy + ny, dx:dx + nx]
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(n >= min_valid, s / n, np.nan)
    return m, n


def ascat_box(basin, valid, intercal=True, max_dt_min=90, real=True, min_valid=6):
    """ASCAT truth on the basin's model grid at a valid time -> dict or None (as ascat()).
    cells: real 10 m wind, Metop-B/C offset met halfway by ascat(intercal=) snapped to the grid and averaged where cells
    coincide, NaN without a cell. box: mean of the valid cells in the 3 x 3 box, NaN where fewer than
    min_valid of 9 are valid. n_box: valid cells in the box. Events: box >= threshold (the main truth) or
    cells >= threshold (the single-cell version, for comparison)."""
    a = ascat(basin, valid, max_dt_min=max_dt_min, real=real, intercal=intercal)
    if a is None:
        return None
    spd = np.asarray(a["spd_kt"], float)
    cells, _ = ascat_to_grid(basin, a["lat"], a["lon"], spd)
    box, nb = box_mean(cells, min_valid=min_valid)
    return {"cells": cells.astype(np.float32), "box": box.astype(np.float32), "n_box": nb.astype(np.int8)}


def ascat_grid(basin, valid, **kw):
    """rk.truth.ascat cells (same keyword arguments) on the basin grid -> (seen, spd_kt) 2-D arrays, or
    (None, None) when ascat() returns None. seen is True where any cell landed; spd_kt holds the largest
    spd_kt there (0 elsewhere). RSS centres sit 0.125 deg off the 0.25 grid, so each snaps with
    floor(x + 0.5): np.rint's half-to-even rounding would send two rows to every even index and none
    to the odd ones, which breaks connected areas."""
    c = ascat(basin, valid, **kw)
    if c is None:
        return None, None
    lats, lons = grid(basin)
    seen = np.zeros((lats.size, lons.size), bool)
    spd = np.zeros(seen.shape, np.float32)
    iy = np.floor((lats[0] - c["lat"]) / 0.25 + 0.5).astype(int)
    ix = np.floor((np.asarray(c["lon"]) % 360 - lons[0]) / 0.25 + 0.5).astype(int)
    ok = (iy >= 0) & (iy < lats.size) & (ix >= 0) & (ix < lons.size)
    seen[iy[ok], ix[ok]] = True
    np.maximum.at(spd, (iy[ok], ix[ok]), np.asarray(c["spd_kt"], np.float32)[ok])
    return seen, spd


# ---- OPC hurricane-force lows (jkrek17/hf-low archive) ----

HF_LOWS_URL = "https://raw.githubusercontent.com/jkrek17/hf-low/main/data/hf_lows/HF_Data_-_{f}.csv"
HF_FILES = {"natl": "Atl", "npac": "Pac"}


def hf_archive(basin, refresh=False):
    """The hf-low archive for a basin -> DataFrame(event_id, valid (datetime), lat, lon (0-360), hpa, category).
    Categories as archived: HF (hurricane force), S (storm), DHF/DS (developing, not yet at that force).
    The spreadsheet behind it is the source; the CSV is not in the releases: it is read from the hf-low repo over
    HTTPS, cached under CACHE/truth/hf_lows/ (legacy DATA/truth/hf_lows as an offline fallback) and re-read from GitHub
    when refresh=True (the archive keeps growing). Returns None if it cannot be read. hpa is NaN where
    the archive has no pressure; rows whose date does not parse (archive typos) are dropped."""
    import pandas as pd
    name = "HF_Data_-_%s.csv" % HF_FILES[basin]
    p = paths.cache("truth", "hf_lows", name)
    legacy = paths.DATA / "truth" / "hf_lows" / name       # old shared folder, read only
    if refresh or not p.exists():
        r = fetch.get(HF_LOWS_URL.format(f=HF_FILES[basin]))
        if r is not None:
            p.write_bytes(r.content)
        elif legacy.exists() and not p.exists():
            p = legacy
        elif not p.exists():
            return None
    d = pd.read_csv(p, dtype=str)
    valid = pd.to_datetime(d["date"], format="%Y%m%d%H", errors="coerce")   # the archive has typo dates
    d, valid = d[valid.notna()], valid[valid.notna()]                        # (e.g. 2018232906): dropped
    return pd.DataFrame({
        "event_id": d["ID"].values, "valid": valid.values,
        "lat": d["Latitude"].astype(float).values, "lon": d["Longitude"].astype(float).values % 360,
        "hpa": pd.to_numeric(d["Pressure"], errors="coerce").values, "category": d["Category"].str.strip().values})


def hf_fixes(basin, valid, categories=("HF",), in_box=True):
    """Archive fixes at one valid time (exact hour) -> DataFrame (as hf_archive), inside the basin box by
    default. Fixes are 6-hourly (00/06/12/18 UTC)."""
    a = hf_archive(basin)
    if a is None:
        return None
    k = (a["valid"] == valid) & a["category"].isin(categories)
    if in_box:
        k &= inside(basin, a["lat"].values, a["lon"].values)
    return a[k].reset_index(drop=True)


# ---- ERA5 (ARCO zarr on Google Cloud, public) ----

ERA5_ZARR = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
_ERA5_T0 = dt.datetime(1900, 1, 1)


def era5(valid, var="mean_sea_level_pressure", cache=True):
    """ERA5 at one hour -> {basin: 2-D float32} on the boxes' 0.25 deg grid (same layout as the analysis;
    MSLP in hPa, other fields in ERA5 units), or None if the chunk is not there. ERA5 is a reanalysis: say
    "ERA5 (proxy)" wherever it stands in for the analysis. Cached as CACHE/truth/era5/VAR/YYYYMMDDHH.npz
    (about 0.4 MB an hour; cache=False for bulk pulls that keep only what they derive)."""
    import numcodecs
    p = paths.cache("truth", "era5", var, valid.strftime("%Y%m%d%H") + ".npz")
    if p.exists():
        with np.load(p) as z:
            return {b: z[b] for b in z.files}
    i = int((valid - _ERA5_T0).total_seconds() // 3600)
    r = fetch.get("%s/%s/%d.0.0" % (ERA5_ZARR, var, i))
    if r is None:
        return None
    a = np.frombuffer(numcodecs.Blosc().decode(r.content), dtype="<f4").reshape(721, 1440)
    out = {b: (v / 100.0 if var == "mean_sea_level_pressure" else v).astype(np.float32)
           for b, v in fetch._cut(a).items()}
    if cache:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, **out)
        tmp.replace(p)
    return out
