"""Byte-range fetch of 10 m wind and MSLP from the AWS open-data mirrors.

A thin wrapper over the shared download package `nwp` (awips-tools/nwp, pinned in requirements.txt):
HTTP, retries, 503 handling, index parsing, URLs and GRIB decoding all live there. What stays here is
rk-specific: the build-window wait, decoding each message once (whole globe) and cutting both basins
from it, Pa -> hPa, and assembling members into {basin: {...}}.
Sources (public, no account): GFS / GDAS, GEFS, ECMWF IFS / AIFS / AIFS ENS (see nwp.sources).
"""
import datetime as dt
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import nwp
import numpy as np
from nwp import sources

from .basins import BASINS, crop

GFS, GEFS, EC = sources.GFS, sources.GEFS, sources.EC
GEFS_MEMBERS = sources.GEFS_MEMBERS
_CROP = {k: crop(k) for k in BASINS}

# the marine wind page builds at these UTC start times and runs for an hour; stay off the buckets then
BUILD_WINDOWS = ((2, 15), (8, 15), (14, 15), (20, 15))
_wait_lock = threading.Lock()


def wait_for_quiet():
    """If the UTC time is within a page build window, sleep until it ends (says so on stderr)."""
    if os.environ.get("RK_IGNORE_BUILD_WINDOWS") == "1":
        return
    with _wait_lock:
        while True:
            now = dt.datetime.now(dt.timezone.utc)
            m = now.hour * 60 + now.minute + now.second / 60
            end = next((h * 60 + mi + 60 for h, mi in BUILD_WINDOWS if h * 60 + mi <= m < h * 60 + mi + 60), None)
            if end is None:
                return
            wait = (end - m) * 60
            print("rk.fetch: inside a marine wind page build window; waiting %.0f min" % (wait / 60), file=sys.stderr)
            time.sleep(wait + 1)


def get(url, rng=None, tries=8):
    """nwp.get (None on 403/404, 503 SlowDown retried fast, other errors backed off), after the
    build-window wait."""
    wait_for_quiet()
    return nwp.get(url, rng, tries)


def _cut(v):
    """One decoded global grid -> {basin: 2-D float32 crop}."""
    return {k: v[iy, ix].copy() for k, (iy, ix) in _CROP.items()}


def decode(blob):
    """One GRIB2 message -> {basin: 2-D float32 crop}, north-up, lon 0..360 order."""
    return _cut(nwp.decode(blob))


def _ncep(url, want):
    """want {'UGRD:10 m above ground': 'u', ...} -> {name: {basin: arr}} or None.
    'msl' falls back to MSLET inside nwp."""
    out = nwp.ncep(url, want)
    return None if out is None else {n: _cut(v) for n, v in out.items()}


def _by_basin(out, names):
    """{name: {basin: arr}} -> {basin: {name: arr}}."""
    return {b: {n: out[n][b] for n in names} for b in BASINS}


UV = {"UGRD:10 m above ground": "u", "VGRD:10 m above ground": "v"}
UVP = dict(UV, **{"PRMSL:mean sea level": "msl"})
_EC_PARAMS = {"10u": "u", "10v": "v", "msl": "msl"}
_EC_SELECT = {("sfc", p, None): n for p, n in _EC_PARAMS.items()}


def gfs_url(d, fh, prefix="gfs"):
    build = sources.gdas if prefix == "gdas" else sources.gfs
    return build(d.strftime("%Y%m%d"), d.strftime("%H"), fh)


def _ec_member(job):
    base, typ, r = job
    blob = nwp.get(base + ".grib2", nwp.span(r))
    return typ, int(r.get("number", 0)), _EC_PARAMS[r["param"]], None if blob is None else _cut(nwp.decode(blob.content))


def det(model, cycle, step):
    """Deterministic run -> {basin: {'u','v','msl'}} (u, v m/s; msl hPa) or None if not posted.
    model: gfs, ifs or aifs. Step 0 of gfs and ifs is the analysis."""
    wait_for_quiet()
    if model == "gfs":
        out = _ncep(gfs_url(cycle, step), UVP)
        if out is None:
            return None
    elif model in ("ifs", "aifs"):
        raw = nwp.fields("ifs" if model == "ifs" else "aifs-single", cycle.strftime("%Y%m%d%H"), step,
                         _EC_SELECT)
        if raw is None or len(raw) != 3:
            return None
        out = {n: _cut(v) for n, v in raw.items()}
    else:
        raise ValueError("unknown deterministic model %r" % model)
    res = _by_basin(out, ("u", "v", "msl"))
    for b in res:
        res[b]["msl"] = res[b]["msl"] / 100.0  # Pa -> hPa
    return res


# Lower-level fields for the storm-core model. Key maps copied from the marine wind page
# (awips-tools marine_wind/pipeline/fetch.py: GFS_LOW, EC_LOW_SFC, EC_LOW_PL).
GFS_LOW = {"TMP:2 m above ground": "t2", "TMP:surface": "skt", "UGRD:925 mb": "u925", "VGRD:925 mb": "v925",
           "TMP:925 mb": "t925", "UGRD:850 mb": "u850", "VGRD:850 mb": "v850", "TMP:850 mb": "t850",
           "LAND:surface": "land", "ICEC:surface": "ice"}
EC_LOW_SFC = {"2t": "t2", "skt": "skt"}
EC_LOW_PL = {(p, lev): p + lev for p in ("u", "v", "t") for lev in ("925", "850")}
_EC_LOW = {("sfc", p, None): n for p, n in EC_LOW_SFC.items()}
_EC_LOW.update({("pl", p, lev): n for (p, lev), n in EC_LOW_PL.items()})
LOW_NAMES = ("t2", "skt", "u925", "v925", "t925", "u850", "v850", "t850")


def low(model, cycle, step):
    """Lower-level fields -> {basin: {'t2','skt','u925','v925','t925','u850','v850','t850'
    (+ 'land','ice' for gfs)}} or None if not posted or incomplete. Temperatures K, winds m/s,
    land 0-1 (GFS LAND), ice fraction 0-1 (GFS ICEC). model: gfs, ifs or aifs."""
    wait_for_quiet()
    if model == "gfs":
        out = _ncep(gfs_url(cycle, step), GFS_LOW)
        names = LOW_NAMES + ("land", "ice")
    elif model in ("ifs", "aifs"):
        raw = nwp.fields("ifs" if model == "ifs" else "aifs-single", cycle.strftime("%Y%m%d%H"), step, _EC_LOW)
        out = None if raw is None else {n: _cut(v) for n, v in raw.items()}
        names = LOW_NAMES
    else:
        raise ValueError("unknown deterministic model %r" % model)
    if out is None or any(n not in out for n in names):
        return None
    return _by_basin(out, names)


def members(ens, cycle, step, msl=True, workers=6, wind=True):
    """Ensemble members -> {basin: {'u': [n,y,x], 'v': [n,y,x], 'msl': [n,y,x]}} or None.
    ens: gefs (c00 + p01..p30), ens (IFS ENS, -ef), aifs-ens (-cf + -pf). Members missing a field are dropped;
    msl is left out of the result when msl=False, u and v when wind=False (MSLP only, a third of the bytes)."""
    wait_for_quiet()
    want = (("u", "v") if wind else ()) + (("msl",) if msl else ())
    if not want:
        raise ValueError("members: ask for wind, msl or both")
    mem = {}
    if ens == "gefs":
        keys = {k: n for k, n in UVP.items() if n in want}
        ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")

        def one(m):
            return m, _ncep(sources.gefs(ymd, hh, step, m), keys)

        with ThreadPoolExecutor(workers) as ex:
            for i, (m, o) in enumerate(ex.map(one, GEFS_MEMBERS)):
                if o is not None:
                    mem[i] = o
    elif ens in ("ens", "aifs-ens"):
        model, typs = ("ifs", ("ef",)) if ens == "ens" else ("aifs-ens", ("cf", "pf"))
        wanted = tuple(p for p, n in _EC_PARAMS.items() if n in want)
        ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        jobs = []
        for typ in typs:
            base = sources.ecmwf(model, "enfo", typ, ymd, hh, step)
            recs = nwp.ec_records(base)
            if recs is None:
                return None
            jobs += [(base, typ, r) for r in recs if r.get("levtype") == "sfc" and r["param"] in wanted]

        with ThreadPoolExecutor(workers) as ex:
            for typ, m, name, f in ex.map(_ec_member, jobs):
                if f is not None:
                    mem.setdefault((typ == "pf", m), {})[name] = f   # control and perturbed files number separately
    else:
        raise ValueError("unknown ensemble %r" % ens)
    keys_ok = sorted(k for k, d in mem.items() if all(n in d for n in want))
    if not keys_ok:
        return None
    res = {}
    for b in BASINS:
        res[b] = {n: np.stack([mem[k][n][b] for k in keys_ok]) for n in want}
        if msl:
            res[b]["msl"] = res[b]["msl"] / 100.0  # Pa -> hPa
    return res


PATTERN = {"HGT:500 mb": "z500", "PRMSL:mean sea level": "msl", "UGRD:250 mb": "u250", "VGRD:250 mb": "v250"}


def gfs_pattern(cycle, step):
    """GFS 500 hPa height (m), MSLP (Pa, MSLET fallback), 250 hPa u and v (m/s) on the whole 0.25 deg globe
    [721, 1440] (lat 90..-90) -> dict, or None if not posted. The Storm Twins inputs (rk.twins)."""
    wait_for_quiet()
    return nwp.ncep(gfs_url(cycle, step), PATTERN)


def gfs_mask(valid):
    """GFS f000 LAND and ICEC at the valid time -> {basin: {'land','ice'}} or None."""
    out = _ncep(gfs_url(valid, 0), {"LAND:surface": "land", "ICEC:surface": "ice"})
    return None if out is None else _by_basin(out, ("land", "ice"))


def gdas_background(valid):
    """The previous GDAS cycle's (valid - 6 h) f003..f009 10 m wind, for building ship and buoy winds
    -> {basin: {'u': [7,y,x], 'v': [7,y,x], 'land': [y,x]}} or None if any hour is missing."""
    cyc = valid - dt.timedelta(hours=6)
    U = {b: [] for b in BASINS}
    V = {b: [] for b in BASINS}
    land = {}
    for fh in range(3, 10):
        keys = dict(UV)
        if fh == 3:
            keys["LAND:surface"] = "land"
        r = _ncep(gfs_url(cyc, fh, prefix="gdas"), keys)
        if r is None:
            return None
        for b in BASINS:
            U[b].append(r["u"][b])
            V[b].append(r["v"][b])
            if "land" in r:
                land[b] = r["land"][b]
    return {b: {"u": np.stack(U[b]), "v": np.stack(V[b]), "land": land[b]} for b in BASINS}


# ---- GEFSv12 reforecast (2000-2019, 00 UTC, 5 members a day, 11 on Wednesdays; noaa-gefs-retrospective) ----

REFORECAST = "https://noaa-gefs-retrospective.s3.amazonaws.com/GEFSv12/reforecast"
REFORECAST_MEMBERS = ("c00", "p01", "p02", "p03", "p04")


def reforecast_url(day, member, var="pres_msl", days="1-10"):
    """The GRIB2 file holding every lead of one variable for one 00 UTC reforecast run and member.
    var is the file stem (pres_msl, ugrd_hgt, tmp_2m, ...); days '1-10' (0.25 deg) or '10-16'."""
    d = day.strftime("%Y%m%d") + "00"
    return "%s/%s/%s/%s/Days:%s/%s_%s_%s.grib2" % (REFORECAST, d[:4], d, member, days, var, d, member)


def reforecast_index(url):
    """{forecast hour: (start, end)} from the file's .idx (end None for the last record), or None.
    Each file holds one variable, so the lead is the key (the first record of a lead wins)."""
    r = get(url + ".idx")
    if r is None:
        return None
    rows = [ln.split(":") for ln in r.text.strip().splitlines()]
    out = {}
    for i, f in enumerate(rows):
        lead = f[5].split()[0]
        if not lead.isdigit():
            continue
        end = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else None
        out.setdefault(int(lead), (int(f[1]), end))
    return out


def gefs_reforecast(day, member, steps, var="pres_msl"):
    """One reforecast run and member -> {step: {basin: 2-D float32}} for the steps asked (MSLP in hPa,
    other fields in their GRIB units), or None when the file is not there. A missing step is left out."""
    url = reforecast_url(day, member, var)
    idx = reforecast_index(url)
    if idx is None:
        return None
    out = {}
    for s in steps:
        if s not in idx:
            continue
        blob = get(url, idx[s])
        if blob is None:
            continue
        v = _cut(nwp.decode(blob.content))
        out[s] = {b: a / 100.0 for b, a in v.items()} if var.startswith("pres_msl") else v
    return out
