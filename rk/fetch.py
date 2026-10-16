"""Byte-range fetch of 10 m wind and MSLP from the AWS open-data mirrors.

Each GRIB message is decoded once and cropped for both basins. Only the needed records are
downloaded (from the .idx / .index files). Sources (public, no account):
    GFS / GDAS  noaa-gfs-bdp-pds   gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF
    GEFS        noaa-gefs-pds      gefs.YYYYMMDD/HH/atmos/pgrb2sp25/geMMM.tHHz.pgrb2s.0p25.fFFF
    ECMWF       ecmwf-forecasts    YYYYMMDD/HHz/{ifs,aifs-single,aifs-ens}/0p25/{oper,enfo}/
"""
import datetime as dt
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import eccodes
import numpy as np
import requests

from .basins import BASINS, crop

GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GEFS = "https://noaa-gefs-pds.s3.amazonaws.com"
EC = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
GEFS_MEMBERS = ["c00"] + ["p%02d" % i for i in range(1, 31)]

_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64))
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
    """GET (optionally a byte range); None on 403/404. S3 answers 503 SlowDown when a freshly
    posted file gets many range requests, so 503 is retried quickly with jitter (up to 60 times);
    other errors back off exponentially."""
    wait_for_quiet()
    headers = {"Range": "bytes=%d-%s" % (rng[0], "" if rng[1] is None else rng[1])} if rng else None
    fails = slow = 0
    while fails < tries and slow < 60:
        try:
            r = _session.get(url, headers=headers, timeout=180)
            if r.status_code in (200, 206):
                return r
            if r.status_code in (403, 404):
                return None
            if r.status_code == 503:
                slow += 1
                time.sleep(0.5 + 1.5 * random.random())
                continue
        except requests.RequestException:
            pass
        fails += 1
        time.sleep(min(2 ** fails, 60) * (0.5 + random.random()))
    raise RuntimeError("failed: " + url)


def decode(blob):
    """One GRIB2 message -> {basin: 2-D float32 crop}, north-up, lon 0..360 order."""
    h = eccodes.codes_new_from_message(blob)
    try:
        ni, nj = eccodes.codes_get(h, "Ni"), eccodes.codes_get(h, "Nj")
        v = eccodes.codes_get_values(h).reshape(nj, ni).astype(np.float32)
        lat0 = eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees")
        lon0 = eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees")
    finally:
        eccodes.codes_release(h)
    if lat0 < 0:
        v = v[::-1]
    if lon0 > 100:  # ECMWF open data starts at -180 (stored as 180)
        v = np.roll(v, ni // 2, axis=1)
    return {k: v[iy, ix].copy() for k, (iy, ix) in _CROP.items()}


def _ncep_index(url):
    r = get(url + ".idx")
    if r is None:
        return None
    lines = [l.split(":") for l in r.text.splitlines() if l.strip()]
    idx = {}
    for i, f in enumerate(lines):
        end = int(lines[i + 1][1]) - 1 if i + 1 < len(lines) else None
        idx.setdefault(f[3] + ":" + f[4], (int(f[1]), end))
    return idx


def _ncep(url, want):
    """want {'UGRD:10 m above ground': 'u', ...} (alternatives joined by '|') -> {name: {basin: arr}} or None."""
    idx = _ncep_index(url)
    if idx is None:
        return None
    out = {}
    for key, name in want.items():
        k = next((a for a in key.split("|") if a in idx), None)
        if k is None:
            return None
        r = get(url, idx[k])
        if r is None:
            return None
        out[name] = decode(r.content)
    return out


def _by_basin(out, names):
    """{name: {basin: arr}} -> {basin: {name: arr}}."""
    return {b: {n: out[n][b] for n in names} for b in BASINS}


UV = {"UGRD:10 m above ground": "u", "VGRD:10 m above ground": "v"}
UVP = dict(UV, **{"PRMSL:mean sea level|MSLET:mean sea level": "msl"})


def gfs_url(d, fh, prefix="gfs"):
    ymd, hh = d.strftime("%Y%m%d"), d.strftime("%H")
    return "%s/%s.%s/%s/atmos/%s.t%sz.pgrb2.0p25.f%03d" % (GFS, prefix, ymd, hh, prefix, hh, fh)


def _ec_base(model, stream, typ, d, step):
    ymd, hh = d.strftime("%Y%m%d"), d.strftime("%H")
    return "%s/%s/%sz/%s/0p25/%s/%s%s0000-%dh-%s-%s" % (EC, ymd, hh, model, stream, ymd, hh, step, stream, typ)


def _ec_records(base):
    r = get(base + ".index")
    if r is None:
        return None
    return [json.loads(l) for l in r.text.splitlines() if l.strip().startswith("{")]


_EC_PARAMS = {"10u": "u", "10v": "v", "msl": "msl"}


def _ec_get(base, r):
    blob = get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1))
    return None if blob is None else decode(blob.content)


def det(model, cycle, step):
    """Deterministic run -> {basin: {'u','v','msl'}} (u, v m/s; msl hPa) or None if not posted.
    model: gfs, ifs or aifs. Step 0 of gfs and ifs is the analysis."""
    if model == "gfs":
        out = _ncep(gfs_url(cycle, step), UVP)
        if out is None:
            return None
    elif model in ("ifs", "aifs"):
        base = _ec_base("ifs" if model == "ifs" else "aifs-single", "oper", "fc", cycle, step)
        recs = _ec_records(base)
        if recs is None:
            return None
        out = {}
        for r in recs:
            if r.get("levtype") == "sfc" and r["param"] in _EC_PARAMS:
                f = _ec_get(base, r)
                if f is None:
                    return None
                out[_EC_PARAMS[r["param"]]] = f
        if len(out) != 3:
            return None
    else:
        raise ValueError("unknown deterministic model %r" % model)
    res = _by_basin(out, ("u", "v", "msl"))
    for b in res:
        res[b]["msl"] = res[b]["msl"] / 100.0  # Pa -> hPa
    return res


def members(ens, cycle, step, msl=True, workers=6):
    """Ensemble members -> {basin: {'u': [n,y,x], 'v': [n,y,x], 'msl': [n,y,x]}} or None.
    ens: gefs (c00 + p01..p30), ens (IFS ENS, -ef), aifs-ens (-cf + -pf). Members missing a field are dropped;
    msl is left out of the result when msl=False."""
    want = ("u", "v", "msl") if msl else ("u", "v")
    mem = {}
    if ens == "gefs":
        keys = dict(UVP if msl else UV)

        def one(m):
            url = "%s/gefs.%s/%s/atmos/pgrb2sp25/ge%s.t%sz.pgrb2s.0p25.f%03d" % (
                GEFS, cycle.strftime("%Y%m%d"), cycle.strftime("%H"), m, cycle.strftime("%H"), step)
            return m, _ncep(url, keys)

        with ThreadPoolExecutor(workers) as ex:
            for i, (m, o) in enumerate(ex.map(one, GEFS_MEMBERS)):
                if o is not None:
                    mem[i] = o
    elif ens in ("ens", "aifs-ens"):
        model, typs = ("ifs", ("ef",)) if ens == "ens" else ("aifs-ens", ("cf", "pf"))
        wanted = ("10u", "10v", "msl") if msl else ("10u", "10v")
        jobs = []
        for typ in typs:
            base = _ec_base(model, "enfo", typ, cycle, step)
            recs = _ec_records(base)
            if recs is None:
                return None
            jobs += [(base, typ, r) for r in recs if r.get("levtype") == "sfc" and r["param"] in wanted]

        def one(job):
            base, typ, r = job
            return typ, int(r.get("number", 0)), _EC_PARAMS[r["param"]], _ec_get(base, r)

        with ThreadPoolExecutor(workers) as ex:
            for typ, m, name, f in ex.map(one, jobs):
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
