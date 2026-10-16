"""Hindcast cache for the warning experiment: winter 2025-26 (1 Nov - 31 Mar), 00Z and 12Z cycles,
steps 24 and 48, both basins (bfetch boxes: natl 30-67N 75W-0, npac 30-67N 160E-115W).

$WX_CACHE (default research-data/extra/warning-experiment)/cases/<dom>/<YYYYMMDDHH>_<step>.npz
  s10_gfs s10_ifs s10_aifs (kt) msl_gfs msl_ifs msl_aifs (hPa)      float16
  u925 v925 (kt, 3-model mean) t925 t2 skt (K, 3-model mean)          float16
  mem   uint8 member 10 m speed in 0.5 kt, rows GEFS (nsrc[0]) then ENS (nsrc[1]) then AIFS ENS (nsrc[2])
$WX_CACHE/truth/<dom>/<YYYYMMDDHH>.npz  GFS and IFS hour-0 analyses: gfs_u gfs_v gfs_msl gfs_land gfs_ice ifs_u ifs_v ifs_msl

usage: python3 build.py [test] ; env NJOBS (processes, default 3), NTHREADS (per process, default 12),
       ONLY=truth (analyses only), REV=1 (newest first). Pauses through the marine wind data build windows.
Cache defaults to the research kit extras folder (research-data/extra/warning-experiment) so other threads can reuse it.
"""
import os, sys, datetime as dt, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.environ.get("PROJECT_FILES", "/mnt/project-files"), "wind-focus", "basins", "code"))
os.environ.setdefault("NTHREADS", "12")
import numpy as np
import bfetch as F
from concurrent.futures import ThreadPoolExecutor

ROOT = os.environ.get("WX_CACHE", "/mnt/project-files/research-data/extra/warning-experiment")
KT = 1.943844
STEPS = [24, 48]
HOURS = ["12", "00"]
_P = None


def pool():
    global _P
    if _P is None:
        _P = ThreadPoolExecutor(int(os.environ["NTHREADS"]))
    return _P


GK = {"UGRD:10 m above ground": "u10", "VGRD:10 m above ground": "v10", "PRMSL:mean sea level|MSLET:mean sea level": "msl",
      "TMP:2 m above ground": "t2", "TMP:surface": "skt",
      "UGRD:925 mb": "u925", "VGRD:925 mb": "v925", "TMP:925 mb": "t925"}
ESFC = {"10u": "u10", "10v": "v10", "msl": "msl", "2t": "t2", "skt": "skt"}
EPL = {("u", "925"): "u925", ("v", "925"): "v925", ("t", "925"): "t925"}


def cycles():
    d, out = dt.date(2025, 11, 1), []
    while d <= dt.date(2026, 3, 31):
        out.append(d.strftime("%Y%m%d")); d += dt.timedelta(days=1)
    return out


def path(kind, dom, name):
    p = os.path.join(ROOT, kind, dom); os.makedirs(p, exist_ok=True)
    return os.path.join(p, name + ".npz")


def ec_get(model, ymd, hh, step, sfc, pl):
    base, recs = F.ec_index(model, "oper", "fc", ymd, hh, step)
    if recs is None:
        return None
    want = []
    for r in recs:
        if r.get("levtype") == "sfc" and r["param"] in sfc:
            want.append((r, sfc[r["param"]]))
        elif r.get("levtype") == "pl" and (r["param"], str(r.get("levelist"))) in pl:
            want.append((r, pl[(r["param"], str(r.get("levelist")))]))
    def g(x):
        r, n = x
        b = F.get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1), tries=12)
        return n, None if b is None else F.decode(b.content)
    out = dict(pool().map(g, want)) if want else {}
    return None if not out or any(v is None for v in out.values()) else out


def ec_members(model, ymd, hh, step):
    out = {}
    types = ["ef"] if model == "ifs" else ["cf", "pf"]
    for typ in types:
        base, recs = F.ec_index(model, "enfo", typ, ymd, hh, step)
        if recs is None:
            if model == "ifs" and typ == "ef":
                types += ["cf", "pf"]
                continue
            return None
        rr = [r for r in recs if r.get("levtype") == "sfc" and r["param"] in ("10u", "10v")]
        def g(r):
            b = F.get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1), tries=12)
            return r, None if b is None else F.decode(b.content)
        for r, a in pool().map(g, rr):
            if a is None:
                return None
            out.setdefault(int(r.get("number", 0)), {})["u" if r["param"] == "10u" else "v"] = a
    return out


def gefs_member(ymd, hh, step, m):
    return F.ncep(F.gefs_url(ymd, hh, step, m), {"UGRD:10 m above ground": "u", "VGRD:10 m above ground": "v"})


def build_case(ymd, hh, step):
    name = "%s%s_%03d" % (ymd, hh, step)
    if all(os.path.exists(path("cases", d, name)) for d in F.DOMS):
        return "have"
    P = pool()
    fut = {"gfs": P.submit(F.ncep, F.gfs_url(ymd, hh, step), GK),
           "ifs": P.submit(ec_get, "ifs", ymd, hh, step, ESFC, EPL),
           "aifs": P.submit(ec_get, "aifs-single", ymd, hh, step, ESFC, EPL)}
    gf = [P.submit(gefs_member, ymd, hh, step, m) for m in ["c00"] + ["p%02d" % i for i in range(1, 31)]]
    ens = ec_members("ifs", ymd, hh, step)
    aens = ec_members("aifs-ens", ymd, hh, step) or {}
    det = {k: f.result() for k, f in fut.items()}
    if any(v is None for v in det.values()):
        return "missing det %s" % [k for k, v in det.items() if v is None]
    gefs = [g for g in (f.result() for f in gf) if g is not None]
    if ens is None or len(gefs) < 20:
        return "missing ens (gefs %d, ens %s)" % (len(gefs), ens is not None)
    h16 = lambda a: np.asarray(a, np.float32).astype(np.float16)
    spd = lambda u, v: np.hypot(u, v) * KT
    for dom in F.DOMS:
        o = {}
        for m in ("gfs", "ifs", "aifs"):
            d = det[m]
            o["s10_" + m] = h16(spd(d["u10"][dom], d["v10"][dom]))
            o["msl_" + m] = h16(d["msl"][dom] / 100.0)
        for n, sc in (("u925", KT), ("v925", KT), ("t925", 1), ("t2", 1), ("skt", 1)):
            arr = [det[m][n][dom] for m in ("gfs", "ifs", "aifs") if n in det[m]]
            if arr:
                o[n] = h16(np.mean(arr, 0) * sc)
        rows = [spd(g["u"][dom], g["v"][dom]) for g in gefs]
        rows += [spd(ens[k]["u"][dom], ens[k]["v"][dom]) for k in sorted(ens)]
        rows += [spd(aens[k]["u"][dom], aens[k]["v"][dom]) for k in sorted(aens)]
        o["mem"] = np.clip(np.rint(np.array(rows) * 2), 0, 255).astype(np.uint8)
        o["nsrc"] = np.array([len(gefs), len(ens), len(aens)])
        np.savez_compressed(path("cases", dom, name), **o)
    return "ok gefs %d ens %d aens %d" % (len(gefs), len(ens), len(aens))


def build_truth(valid):
    if all(os.path.exists(path("truth", d, valid)) for d in F.DOMS):
        return "have"
    ymd, hh = valid[:8], valid[8:]
    g = F.ncep(F.gfs_url(ymd, hh, 0), {"UGRD:10 m above ground": "u", "VGRD:10 m above ground": "v",
                                        "PRMSL:mean sea level|MSLET:mean sea level": "msl",
                                        "LAND:surface": "land", "ICEC:surface": "ice"})
    e = ec_get("ifs", ymd, hh, 0, {"10u": "u", "10v": "v", "msl": "msl"}, {})
    if g is None or e is None:
        return "missing truth"
    for dom in F.DOMS:
        out = {"gfs_" + n: a[dom] for n, a in g.items()}
        out.update({"ifs_" + n: a[dom] for n, a in e.items()})
        np.savez_compressed(path("truth", dom, valid), **out)
    return "ok"


def wait_out_build():
    """Sleep through the marine wind data build (jobs ~02:30/08:30/14:30/20:30 UTC) so downloads don't collide."""
    import time
    while True:
        n = dt.datetime.utcnow()
        m = (n.hour % 6) * 60 + n.minute          # minutes since 00/06/12/18 UTC
        if not (125 <= m < 225):                  # 02:05-03:45 UTC and the same each 6 h
            return
        time.sleep(300)


def run(j):
    wait_out_build()
    t0 = dt.datetime.now()
    try:
        r = build_truth(j[1]) if j[0] == "t" else build_case(*j[1:])
    except Exception as ex:
        r = "ERR %s" % ex
        traceback.print_exc()
    return "%s %s (%.0fs)" % (j[1:], r, (dt.datetime.now() - t0).total_seconds())


if __name__ == "__main__":
    from multiprocessing import Pool
    cyc = cycles()
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        cyc = cyc[60:61]
    jobs = [("c", c, h, s) for c in cyc for h in HOURS for s in STEPS]
    valids = sorted({(dt.datetime.strptime(c + h, "%Y%m%d%H") + dt.timedelta(hours=s)).strftime("%Y%m%d%H")
                     for c in cyc for h in HOURS for s in STEPS})
    jobs += [("t", v) for v in valids]
    if os.environ.get("ONLY") == "truth":
        jobs = [j for j in jobs if j[0] == "t"]
    if os.environ.get("REV"):
        jobs = jobs[::-1]
    print(len(cyc), "days", len(jobs), "jobs", flush=True)
    with Pool(int(os.environ.get("NJOBS", "3"))) as p:
        for r in p.imap_unordered(run, jobs):
            print(r, flush=True)
    print("done", flush=True)
