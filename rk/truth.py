"""Truth for scoring: the analysis (where), ship and buoy winds, and ASCAT (how strong).

obs()    ship and buoy 10 m wind rebuilt from the GDAS first guess plus the O-B departure
ascat()  RSS ASCAT v2.1 cells near the valid time, equivalent-neutral or real 10 m wind
smap_day()  RSS SMAP v1.0 L3 daily winds (L-band radiometer), a second equivalent-neutral instrument
ascat_grid()  ascat() snapped to the basin grid (seen mask, max speed)
hf_archive(), hf_fixes()  OPC hurricane-force low fixes from the jkrek17/hf-low archive
Everything here is cached under DATA/truth. A loader returns None when its source is not posted.
"""
import datetime as dt
import io
import threading
from pathlib import Path

import numpy as np

from . import KT, fetch
from .basins import BASINS, grid, inside, sample
from .cases import tag
from .paths import data
from .store import _save, analysis  # noqa: F401  (analysis is re-exported)

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


def _obs_path(basin, valid):
    return data("truth", "obs", basin, tag(valid) + ".npz")


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
        _save(_obs_path(b, valid), lat=lat, lon=lo, u=ou, v=ov, dt_hours=dth, station_id=sid, status=st,
              platform=_platform(sid, lat, lo), land=sample(land, b, lat, lo),
              bg_speed_kt=np.hypot(bu, bv) * KT)
    return True


def obs_points(basin, valid):
    """All status-flagged marine points of the valid time's csv, with the rebuilt wind -> dict or None."""
    p = _obs_path(basin, valid)
    if not p.exists() and not _build_obs(valid):
        return None
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
    Cached under truth/airsea/{basin}/{YYYYMMDDHH}.npz (both basins at once)."""
    p = data("truth", "airsea", basin, tag(valid) + ".npz")
    if not p.exists():
        out = fetch._ncep(fetch.gfs_url(valid, 0), {"TMP:2 m above ground": "t2", "TMP:surface": "skt"})
        if out is None:
            return None
        for b in BASINS:
            _save(data("truth", "airsea", b, tag(valid) + ".npz"), t2=out["t2"][b], skt=out["skt"][b])
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
    t_min is minutes after 00 UTC of that day. Cached under truth/ascat/{YYYYMMDD}.npz. A day with only one
    satellite posted is cached only once it is a week old (the other may still arrive)."""
    ymd = day.strftime("%Y%m%d")
    p = data("truth", "ascat", ymd + ".npz")
    if p.exists():
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
        _save(p, sats=np.array(sats), **c)
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
    local). FINAL is tried first, then NRT. Cached under truth/smap/{YYYYMMDD}.npz with final = 1 for FINAL,
    0 for NRT (a cached NRT day is not re-fetched when FINAL appears; delete the file to refresh)."""
    ymd = day.strftime("%Y%m%d")
    p = data("truth", "smap", ymd + ".npz")
    if p.exists():
        with np.load(p) as z:
            return {k: z[k] for k in z.files if k != "final"}
    blob, final = _smap_get(day, "FINAL"), 1
    if blob is None:
        blob, final = _smap_get(day, "NRT"), 0
    if blob is None:
        return None
    c = _smap_cells(blob)
    _save(p, final=np.array(final, np.uint8), **c)
    return c


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


def ascat(basin, valid, max_dt_min=90, real=True, intercal=True):
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

    Fallback: where the analysis (open-water mask) or the GFS air-sea field is missing at the valid time itself
    (06/18 UTC: the IFS analysis is not posted), the nearest 00/12 UTC analysis within 6 h supplies both, the earlier
    one preferred (mask_time). At 00/12 UTC the behaviour is unchanged."""
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
    k = np.abs(c["dt_min"]) <= max_dt_min
    k &= (c["scat_rain"] == 0) & (c["rad_rain"] < 2) & inside(basin, c["lat"], c["lon"])
    c = {f: v[k] for f, v in c.items()}
    tm = mask_time(basin, valid)
    if tm is None:
        return None
    an = analysis(basin, tm)
    ok = sample(an["mask"].astype(float), basin, c["lat"], c["lon"]) > 0.99
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
    The spreadsheet behind it is the source; the CSV is cached under truth/hf_lows/ and re-read from GitHub
    when refresh=True (the archive keeps growing). Returns None if it cannot be read. hpa is NaN where
    the archive has no pressure; rows whose date does not parse (archive typos) are dropped."""
    import pandas as pd
    p = data("truth", "hf_lows", "HF_Data_-_%s.csv" % HF_FILES[basin])
    if refresh or not p.exists():
        r = fetch.get(HF_LOWS_URL.format(f=HF_FILES[basin]))
        if r is None:
            return None
        p.write_bytes(r.content)
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
