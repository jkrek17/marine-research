"""Pull day 5-7 MSLP for the pressure study: GFS, IFS, AIFS deterministic, GEFS (31), ENS (51), AIFS ENS (51)
at +120/+144/+168 h from 12Z runs, plus the GFS and IFS 12Z analyses, cropped to both basins (bfetch.DOMS).

Per cycle and source one file:
  det_{model}_{dom}_{step}   int16 0.25 deg  (hPa*10 - 10000), models gfs/ifs/aifs, steps 120,144,168,192
  mem_{ens}_{dom}_{step}     int16 0.5 deg   (n, ny, nx), ens gefs/ens/aifsens
  low_{ens}_{dom}_{step}     float32 (k, 4)  member, lat, lon, hPa: each member's local minima at 0.25 deg
Analyses CACHE/an_YYYYMMDD.npz: an_{gfs|ifs}_{dom} int16 0.25 deg.

Pauses during the marine wind data builds (02:30/08:30/14:30/20:30 UTC +-45 min).
Run: python3 download.py noaa|ec [FIRST LAST]   (cycle dates, default 20250301 20261008)
Files are fc_{src}_YYYYMMDD.npz and an_{src}_YYYYMMDD.npz, so the NOAA and ECMWF pulls run separately.
"""
import os, sys, time, datetime as dt, traceback
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.ndimage import minimum_filter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bfetch as B

from lib import CACHE   # one place for the store path (env PCACHE overrides)
STEPS = (120, 144, 168)
DET_STEPS = (120, 144, 168, 192)
HH = "12"
PAD = 6  # rows/cols from the edge ignored for minima


def enc(a):
    return np.clip(np.round(a / 10.0 - 10000), -32000, 32000).astype(np.int16)   # Pa -> hPa*10 - 10000


def member_lows(m, f, dom):
    lat, lon = B.LATS[dom], B.LONS[dom]
    hpa = f / 100.0
    mn = minimum_filter(hpa, size=13, mode="nearest")
    ys, xs = np.where((hpa == mn) & (hpa < 1012))
    ok = (ys >= PAD) & (ys < hpa.shape[0] - PAD) & (xs >= PAD) & (xs < hpa.shape[1] - PAD)
    return [(m, lat[y], lon[x], hpa[y, x]) for y, x in zip(ys[ok], xs[ok])]


def busy_window():
    now = dt.datetime.utcnow()
    mins = now.hour * 60 + now.minute
    return any(abs(mins - c) <= 45 or abs(mins - c - 1440) <= 45 for c in (150, 510, 870, 1230))


def wait_clear():
    while busy_window():
        time.sleep(120)


def gfs_det(ymd, step):
    r = B.ncep(B.gfs_url(ymd, HH, step), {"PRMSL:mean sea level|MSLET:mean sea level": "msl"})
    return None if not r or "msl" not in r else r["msl"]


def ec_det(model, ymd, step):
    r = B.ec_fields(model, "oper", "fc", ymd, HH, step, {"msl": "msl"})
    return None if not r else r[0][2]


def gefs_mem(ymd, step, mem):
    r = B.ncep(B.gefs_url(ymd, HH, step, mem), {"PRMSL:mean sea level|MSLET:mean sea level": "msl"})
    return None if not r or "msl" not in r else r["msl"]


def ec_ens(model, ymd, step):
    """All members' msl, fetching runs of adjacent records in one range request each."""
    out = []
    for typ in (("ef",) if model == "ifs" else ("cf", "pf")):
        base, recs = B.ec_index(model, "enfo", typ, ymd, HH, step)
        if recs is None:
            continue
        m = sorted([r for r in recs if r.get("param") == "msl" and r.get("levtype") == "sfc"], key=lambda r: r["_offset"])
        blocks = []
        for r in m:
            if blocks and r["_offset"] - blocks[-1][-1]["_offset"] - blocks[-1][-1]["_length"] < 200000:
                blocks[-1].append(r)
            else:
                blocks.append([r])
        for blk in blocks:
            a = blk[0]["_offset"]
            z = blk[-1]["_offset"] + blk[-1]["_length"] - 1
            data = B.get(base + ".grib2", (a, z))
            if data is None:
                continue
            c = data.content
            for r in blk:
                o = r["_offset"] - a
                out.append((int(r.get("number", 0)), B.decode(c[o:o + r["_length"]])))
    return out


def cycle(ymd, pool, src):
    """src 'noaa' (GFS + GEFS) or 'ec' (IFS, AIFS, ENS, AIFS ENS) -> CACHE/fc_{src}_YYYYMMDD.npz"""
    path = os.path.join(CACHE, "fc_%s_%s.npz" % (src, ymd))
    alt = os.environ.get("HAVE_DIR")      # also skip runs already stored here (when writing to a local overflow dir)
    if os.path.exists(path) or (alt and os.path.exists(os.path.join(alt, os.path.basename(path)))):
        return "have"
    out = {}
    jobs = {}
    for s in DET_STEPS:
        if src == "noaa":
            jobs[("gfs", s)] = pool.submit(gfs_det, ymd, s)
        else:
            jobs[("ifs", s)] = pool.submit(ec_det, "ifs", ymd, s)
            jobs[("aifs", s)] = pool.submit(ec_det, "aifs-single", ymd, s)
    for s in STEPS:
        if src == "noaa":
            for i in range(31):
                mem = "c00" if i == 0 else "p%02d" % i
                jobs[("gefs", s, i)] = pool.submit(gefs_mem, ymd, s, mem)
        else:
            jobs[("ens", s)] = pool.submit(ec_ens, "ifs", ymd, s)
            jobs[("aifsens", s)] = pool.submit(ec_ens, "aifs-ens", ymd, s)
    res = {}
    for k, f in jobs.items():
        try:
            res[k] = f.result()
        except Exception as ex:
            print("  miss", ymd, k, ex, flush=True)
            res[k] = None
    for (m, s) in [k for k in res if len(k) == 2 and k[0] in ("gfs", "ifs", "aifs")]:
        f = res[(m, s)]
        if f is not None:
            for d in B.DOMS:
                out["det_%s_%s_%d" % (m, d, s)] = enc(f[d])
    for s in STEPS:
        if src == "noaa":
            sets = {"gefs": [(i, res[("gefs", s, i)]) for i in range(31) if res[("gefs", s, i)] is not None]}
        else:
            sets = {"ens": res[("ens", s)], "aifsens": res[("aifsens", s)]}
        for e, lst in sets.items():
            if not lst:
                continue
            lst = sorted(lst, key=lambda t: t[0])
            for d in B.DOMS:
                out["mem_%s_%s_%d" % (e, d, s)] = np.stack([enc(f[d][::2, ::2]) for _, f in lst])
                lows = [lo for m, f in lst for lo in member_lows(m, f[d], d)]
                out["low_%s_%s_%d" % (e, d, s)] = np.array(lows, np.float32).reshape(-1, 4)
    np.savez_compressed(path + ".tmp.npz", **out)
    os.replace(path + ".tmp.npz", path)
    return "%d arrays" % len(out)


def analysis(ymd, src):
    path = os.path.join(CACHE, "an_%s_%s.npz" % (src, ymd))
    if os.path.exists(path):
        return "have"
    out = {}
    name = "gfs" if src == "noaa" else "ifs"
    f = gfs_det(ymd, 0) if src == "noaa" else ec_det("ifs", ymd, 0)
    if True:
        if f is not None:
            for d in B.DOMS:
                out["an_%s_%s" % (name, d)] = enc(f[d])
    np.savez_compressed(path + ".tmp.npz", **out)
    os.replace(path + ".tmp.npz", path)
    return "%d arrays" % len(out)


def days(a, b):
    d, e = dt.datetime.strptime(a, "%Y%m%d"), dt.datetime.strptime(b, "%Y%m%d")
    while d <= e:
        yield d.strftime("%Y%m%d")
        d += dt.timedelta(days=1)


if __name__ == "__main__":
    src = sys.argv[1]
    a, b = (sys.argv[2:4] + ["20250301", "20261008"][len(sys.argv[2:4]):])
    os.makedirs(CACHE, exist_ok=True)
    order = list(days(a, b))
    # winter first so a partial pull is already useful
    order.sort(key=lambda d: (0 if d[4:6] in ("11", "12", "01", "02", "03") else 1, d))
    last = (dt.datetime.strptime(b, "%Y%m%d") + dt.timedelta(days=7)).strftime("%Y%m%d")
    with ThreadPoolExecutor(16) as pool:
        def an(v):
            try:
                return v, analysis(v, src)
            except Exception as ex:
                return v, repr(ex)
        for v, r in pool.map(an, list(days(a, last))):
            print("an", v, r, flush=True)
        def one(c):
            wait_clear()
            t = time.time()
            try:
                return c, cycle(c, pool, src), time.time() - t
            except Exception as ex:
                return c, repr(ex), time.time() - t
        par = int(os.environ.get("PAR", "3" if src == "ec" else "1"))
        with ThreadPoolExecutor(par) as outer:
            for c, r, s in outer.map(one, order):
                print("fc", c, r, "%.0fs" % s, flush=True)
