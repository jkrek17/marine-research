"""Byte-range fetch from the AWS open-data mirrors, cropped to both basins at once.

Domains (0.25 deg, north-first rows, west-first columns):
  natl  30-67N, 75W-0.25W    (the box the recipe was tuned on)
  npac  30-67N, 160E-115W    (OPC Pacific high seas and offshore waters)
Each GRIB message is decoded once and cut for both domains.
"""
import os, json, time
import numpy as np, requests, eccodes

GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GEFS = "https://noaa-gefs-pds.s3.amazonaws.com"
EC = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
_S = requests.Session()
_S.mount("https://", requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64))

DOMS = {"natl": (67.0, 30.0, 285.0, 359.75), "npac": (67.0, 30.0, 160.0, 245.0)}
CROP = {}
for k, (n, s, w, e) in DOMS.items():
    iy = slice(int((90 - n) * 4), int((90 - s) * 4) + 1)
    ix = slice(int(w * 4), int(e * 4) + 1)
    CROP[k] = (iy, ix)
LATS = {k: np.linspace(DOMS[k][0], DOMS[k][1], CROP[k][0].stop - CROP[k][0].start) for k in DOMS}
LONS = {k: np.arange(CROP[k][1].start, CROP[k][1].stop) * 0.25 for k in DOMS}   # 0..360
LONS180 = {k: np.where(v > 180, v - 360, v) for k, v in LONS.items()}


def get(url, rng=None, tries=40):
    for i in range(tries):
        try:
            h = {"Range": "bytes=%d-%s" % (rng[0], "" if rng[1] is None else rng[1])} if rng else None
            r = _S.get(url, headers=h, timeout=120)
            if r.status_code in (200, 206):
                return r
            if r.status_code in (403, 404):
                return None
            if r.status_code == 503:          # S3 SlowDown: retry quickly with jitter
                time.sleep(0.3 + 1.5 * np.random.rand())
                continue
        except requests.RequestException:
            pass
        time.sleep(min(2 ** i, 30) * (0.5 + np.random.rand()))
    raise RuntimeError("fetch failed " + url)


def decode(blob):
    """GRIB2 message -> {dom: 2-D float32 crop}."""
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
    if lon0 > 100:          # ECMWF open data starts at 180W
        v = np.roll(v, ni // 2, axis=1)
    return {k: v[iy, ix].copy() for k, (iy, ix) in CROP.items()}


def ncep_index(url):
    r = get(url + ".idx")
    if r is None:
        return None
    lines = [l.split(":") for l in r.text.splitlines() if l.strip()]
    out = {}
    for i, f in enumerate(lines):
        end = int(lines[i + 1][1]) - 1 if i + 1 < len(lines) else None
        out.setdefault(f[3] + ":" + f[4], (int(f[1]), end))
    return out


def ncep(url, keys):
    """keys {'UGRD:10 m above ground': 'u', ...} -> {name: {dom: arr}} or None."""
    idx = ncep_index(url)
    if idx is None:
        return None
    out = {}
    for k, name in keys.items():
        alts = k.split("|")
        kk = next((a for a in alts if a in idx), None)
        if kk is None:
            continue
        a, b = idx[kk]
        r = get(url, (a, b))
        if r is None:
            return None
        out[name] = decode(r.content)
    return out


def gfs_url(ymd, hh, fh):
    return "%s/gfs.%s/%s/atmos/gfs.t%sz.pgrb2.0p25.f%03d" % (GFS, ymd, hh, hh, fh)


def gefs_url(ymd, hh, fh, mem):
    pre = "geavg" if mem == "avg" else "ge" + mem
    return "%s/gefs.%s/%s/atmos/pgrb2sp25/%s.t%sz.pgrb2s.0p25.f%03d" % (GEFS, ymd, hh, pre, hh, fh)


def ec_index(model, stream, typ, ymd, hh, step):
    base = "%s/%s/%sz/%s/0p25/%s/%s%s0000-%dh-%s-%s" % (EC, ymd, hh, model, stream, ymd, hh, step, stream, typ)
    r = get(base + ".index")
    if r is None:
        return None, None
    return base, [json.loads(l) for l in r.text.splitlines() if l.strip().startswith("{")]


def ec_fields(model, stream, typ, ymd, hh, step, params):
    """params {'10u':'u',...} sfc only -> list of (member, name, {dom: arr})."""
    base, recs = ec_index(model, stream, typ, ymd, hh, step)
    if recs is None:
        return None
    out = []
    for r in recs:
        if r.get("levtype") == "sfc" and r["param"] in params:
            blob = get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1))
            if blob is None:
                return None
            out.append((int(r.get("number", 0)), params[r["param"]], decode(blob.content)))
    return out
