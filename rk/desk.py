"""The marine desk's issued wind grids: NDFD oceanic 10 m wind speed (YCYZ98 days 1-3, YCYZ97 days 4-7),
averaged onto the basins' 0.25 deg grids. See rk/CONTRACT.md. Raw GRIB files are downloaded to a temporary
file, decoded and deleted; only the basin grids are cached."""
import datetime as dt
import os
import tempfile
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import KT, fetch
from .basins import BASINS, grid
from .cases import parse, tag
from .paths import data
from .store import _save

BUCKET = "https://noaa-ndfd-pds.s3.amazonaws.com/"
PRODUCTS = ("YCYZ98", "YCYZ97")
HOURS = (10, 22)
VALID_HOURS = (0, 6, 12, 18)
MISSING = 9998.0          # NDFD marks missing with 9999
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_MAPS = {}                # (product, Ni, Nj) -> {basin: int32 flat box index per NDFD cell, -1 outside}
_lock = threading.Lock()  # eccodes is not thread-safe; downloads still run in parallel


def cache_dir():
    """$RK_DESK, else DATA/desk."""
    e = os.environ.get("RK_DESK")
    if e:
        Path(e).mkdir(parents=True, exist_ok=True)
        return Path(e)
    return data("desk", "x").parent


def _path(basin, issue):
    return cache_dir() / basin / (tag(issue) + ".npz")


def issuances(day, product="YCYZ98"):
    """Snapshots of one product on one UTC date: [(datetime, key, size)] sorted by time."""
    prefix = "wmo/wspd/%s/%s_KWBN_" % (day.strftime("%Y/%m/%d"), product)
    r = fetch.get(BUCKET + "?list-type=2&prefix=" + prefix)
    if r is None:
        return []
    out = []
    for c in ET.fromstring(r.content).iter(_NS + "Contents"):
        key = c.find(_NS + "Key").text
        out.append((dt.datetime.strptime(key[-12:], "%Y%m%d%H%M"), key, int(c.find(_NS + "Size").text)))
    return sorted(out)


def pick(day, hour, product="YCYZ98"):
    """Key of the first snapshot at or after hour:00 on the day and before hour+3, or None."""
    t0 = dt.datetime(day.year, day.month, day.day, hour)
    for t, key, _ in issuances(day, product):
        if t0 <= t < t0 + dt.timedelta(hours=3):
            return key
    return None


# ---- NDFD cells -> 0.25 deg boxes ----

def box_index(lat, lon, basin):
    """Flat index (row-major, ny*nx) of the 0.25 deg box each cell centre falls in; -1 outside the box.
    Snapping is floor(x/0.25 + 0.5), so a cell at a box centre +-0.125 belongs to that box."""
    b = BASINS[basin]
    lats, lons = grid(basin)
    ny, nx = len(lats), len(lons)
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float) % 360
    row = np.floor((b["north"] - lat) / 0.25 + 0.5).astype(np.int64)
    col = np.floor(lon / 0.25 + 0.5).astype(np.int64) - int(round(b["west"] * 4))
    ok = (row >= 0) & (row < ny) & (col >= 0) & (col < nx)
    return np.where(ok, row * nx + col, -1).astype(np.int32)


def unscan(values, ni, alternative):
    """NDFD oceanic GRIB uses alternative row scanning (every second row runs east to west) and eccodes
    returns the values in file order while its latitudes/longitudes run west to east on every row, so the
    odd rows must be reversed to line up with them."""
    v = np.asarray(values)
    if not alternative:
        return v
    v = v.reshape(-1, ni).copy()
    v[1::2] = v[1::2, ::-1]
    _check_rows(v)
    return v.ravel()


def _check_rows(v):
    """Native 10 km grid: a field with rows lined up is about as smooth north-south as east-west
    (mirrored rows were ~25x rougher). Guards against a decoder that starts undoing the scan itself."""
    ok = v < MISSING
    dr = np.abs(np.diff(v, axis=0))[ok[1:] & ok[:-1]].mean()
    dc = np.abs(np.diff(v, axis=1))[ok[:, 1:] & ok[:, :-1]].mean()
    assert dr < 3 * dc + 0.05, "NDFD rows look mirrored (row %.2f vs column %.2f m/s)" % (dr, dc)


def area_mean(values, idx, n):
    """Mean of the valid cells in each box -> float32 [n] (NaN where a box has no valid cell).
    values: 1-D NDFD values (>= 9998 or non-finite is missing); idx from box_index."""
    v = np.asarray(values, float)
    sel = (idx >= 0) & np.isfinite(v) & (v < MISSING)
    s = np.bincount(idx[sel], weights=v[sel], minlength=n)
    c = np.bincount(idx[sel], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c > 0, s / c, np.nan).astype(np.float32)


def _mapping(product, h):
    """{basin: index} for the grid of this message handle; module cache, then npz under the cache dir."""
    import eccodes as ec
    ni, nj = ec.codes_get(h, "Ni"), ec.codes_get(h, "Nj")
    k = (product, ni, nj)
    if k in _MAPS:
        return _MAPS[k]
    p = cache_dir() / ("map_%s.npz" % product)
    if p.exists():
        with np.load(p) as z:
            if int(z["Ni"]) == ni and int(z["Nj"]) == nj:
                _MAPS[k] = {b: z[b] for b in BASINS}
                return _MAPS[k]
    lat = ec.codes_get_array(h, "latitudes")
    lon = ec.codes_get_array(h, "longitudes")
    assert len(lat) == ni * nj, "lat/lon length does not match Ni x Nj"
    m = {b: box_index(lat, lon, b) for b in BASINS}
    _save(str(p), Ni=np.array(ni), Nj=np.array(nj), **m)
    _MAPS[k] = m
    return m


def _decode(path, product):
    """GRIB file -> {basin: {valid datetime: kt array}}, ref datetime. Only 00/06/12/18 UTC valid times."""
    import eccodes as ec
    out = {b: {} for b in BASINS}
    ref = None
    with _lock, open(path, "rb") as f:
        while True:
            h = ec.codes_grib_new_from_file(f)
            if h is None:
                break
            try:
                vd, vt = ec.codes_get(h, "validityDate"), ec.codes_get(h, "validityTime")
                if vt % 100 != 0 or (vt // 100) not in VALID_HOURS:
                    continue
                m = _mapping(product, h)
                assert ec.codes_get(h, "Ni") * ec.codes_get(h, "Nj") == len(m["natl"]), "grid changed within a file"
                if ref is None:
                    d, t = ec.codes_get(h, "dataDate"), ec.codes_get(h, "dataTime")
                    ref = dt.datetime.strptime("%08d%04d" % (d, t), "%Y%m%d%H%M")
                v = unscan(ec.codes_get_values(h), ec.codes_get(h, "Ni"),
                           ec.codes_get(h, "alternativeRowScanning"))
                valid = dt.datetime.strptime("%08d%04d" % (vd, vt), "%Y%m%d%H%M")
                for b in BASINS:
                    ny, nx = len(grid(b)[0]), len(grid(b)[1])
                    out[b][valid] = (area_mean(v, m[b], ny * nx) * KT).reshape(ny, nx)
            finally:
                ec.codes_release(h)
    return out, ref


def _fetch_product(day, hour, product):
    """Download and decode one product's snapshot -> (decoded, ref) or None if not posted."""
    key = pick(day, hour, product)
    if key is None:
        return None
    r = fetch.get(BUCKET + key)
    if r is None:
        return None
    fd, tmp = tempfile.mkstemp(dir=cache_dir(), suffix=".grib2.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        del r
        return _decode(tmp, product)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read(issue):
    out = {}
    for b in BASINS:
        p = _path(b, issue)
        if not p.exists():
            return None
        with np.load(p) as z:
            out[b] = {"ref": parse(str(z["ref"])), "valid": [parse(str(s)) for s in z["valid"]],
                      "speed": z["speed"], "product": [str(s) for s in z["product"]],
                      "refs": [parse(str(s)) for s in z["refs"]]}
    return out


def load(issue_dt):
    """Desk wind grids for the 10Z or 22Z issuance -> {basin: {...}} or None (see CONTRACT)."""
    issue = dt.datetime(issue_dt.year, issue_dt.month, issue_dt.day, issue_dt.hour)
    if issue.hour not in HOURS:
        raise ValueError("desk full updates are at %s UTC, got %02dZ" % (HOURS, issue.hour))
    got = _read(issue)
    if got is not None:
        return got
    day = issue.replace(hour=0)
    parts = []
    for product in PRODUCTS:
        r = _fetch_product(day, issue.hour, product)
        if r is None and product == PRODUCTS[0]:
            return None
        parts.append((product, r))
    for b in BASINS:
        (cache_dir() / b).mkdir(exist_ok=True)
        merged = {}   # valid -> (product, ref, array); the first product wins
        for product, r in parts:
            if r is None:
                continue
            for valid, a in r[0][b].items():
                merged.setdefault(valid, (product, r[1], a))
        valid = sorted(merged)
        arrays = dict(speed=np.stack([merged[v][2] for v in valid]).astype(np.float16),
                      valid=np.array([tag(v) for v in valid]),
                      product=np.array([merged[v][0] for v in valid]),
                      refs=np.array([tag(merged[v][1]) for v in valid]),
                      ref=np.array(tag(parts[0][1][1])))
        _save(str(_path(b, issue)), **arrays)
    return _read(issue)


def fill(start, end, hours=HOURS, workers=3, log=None):
    """Load every issuance from start to end (dates, inclusive); cached ones are skipped.
    Returns counts {'ok','missing','failed','partial','cached'} plus 'failed_tags' and 'partial_tags'."""
    rep = {"ok": 0, "missing": 0, "failed": 0, "partial": 0, "cached": 0, "failed_tags": [], "partial_tags": []}
    jobs = []
    d = dt.datetime(start.year, start.month, start.day)
    while d <= dt.datetime(end.year, end.month, end.day):
        for h in hours:
            issue = d.replace(hour=h)
            if all(_path(b, issue).exists() for b in BASINS):
                rep["cached"] += 1
            else:
                jobs.append(issue)
        d += dt.timedelta(days=1)

    def run(issue):
        try:
            r = load(issue)
        except Exception as e:   # one bad file must not stop a long fill
            return issue, "failed", repr(e)
        if r is None:
            return issue, "missing", ""
        return issue, ("ok" if "YCYZ97" in r["natl"]["product"] else "partial"), ""

    with ThreadPoolExecutor(workers) as ex:
        for issue, what, msg in ex.map(run, jobs):
            if what == "partial":
                rep["partial"] += 1
                rep["partial_tags"].append(tag(issue))
                rep["ok"] += 1
            elif what == "failed":
                rep["failed"] += 1
                rep["failed_tags"].append(tag(issue))
            else:
                rep[what] += 1
            if log:
                log(issue, what, msg)
    return rep
