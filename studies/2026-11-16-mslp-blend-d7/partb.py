"""Part B (design.md): the probability layer around the member-vote lows, day 5-7, 12 UTC, both basins.

Build stage (this file): for every 12 UTC cycle Mar 2025 - Oct 2026 and basin, run the day 5-7 member vote
(studies/2026-10-16-pressure-d5-7 method.py, imported; locked settings from its results/final.json) at +120/+144/+168
and keep, per vote low, what the probability products need: position, depth, support, the voters' own depths and
weights, the alternative-scenario clusters, and the analysed lows (GFS analysis, IFS analysis, their mean).

    python3 partb.py --build [--limit N] [--cycles YYYYMMDDHH ...] [--part i/n] [--start YYYYMMDD --end YYYYMMDD]
    python3 partb.py --status

Output: rk.paths.cache("extra","mslp-blend-d7","partb","cases",basin,"YYYYMMDDHH.pkl"), one per basin-cycle
(the resume unit). The scoring and calibration are in partb_analyze.py (pure helpers below, tested in
tests/test_mslp_blend_partb.py).

Disk: every rk.store.load unpacks the cycle's zip into the cache; after each basin-cycle (and each analysis
cycle) the unpacked files are cleaned with extract.clean (keeps mslpd57_* and unpublished files). Stops if free
disk < MIN_FREE.
"""
import argparse
import json
import os
import pickle
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
D57 = REPO / "studies" / "2026-10-16-pressure-d5-7"
for p in (str(REPO), str(HERE), str(D57)):
    if p not in sys.path:
        sys.path.insert(0, p)
import numpy as np
from rk import paths, store, score as rks

BASINS = ("natl", "npac")
LEADS = (120, 144, 168)
VOTE_W = {"gefs": 1, "ens": 1, "aifsens": 1, "gfs": 0.3, "ifs": 0.3, "aifs": 0.3}
VOTE_R = 450.0
START, END = datetime(2025, 3, 1, 12), datetime(2026, 10, 31, 12)
MIN_FREE = 6e9
ROOT = paths.cache("extra", "mslp-blend-d7", "partb", "_root").parent
CASES = ROOT / "cases"
# alternative scenario rule (design.md)
ALT_KM, ALT_HPA, ALT_SHARE, ALT_MAX, ALT_REACH = 300.0, 8.0, 0.20, 2, 1000.0


# ---------------------------------------------------------------- pure helpers (tested)

def wmedian(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    o = np.argsort(x)
    cw = np.cumsum(w[o]) / w.sum()
    return float(x[o][min(np.searchsorted(cw, 0.5), len(x) - 1)])


def alternatives(main, V, km=rks.km, reach=ALT_REACH, dkm=ALT_KM, dhpa=ALT_HPA, min_share=ALT_SHARE,
                 max_alt=ALT_MAX, others=()):
    """Alternative scenarios to the vote low `main` (lat, lon, hpa = the 50% depth).
    V: list of (weight, lows (k, 3 [lat, lon, hpa])), weights summing to 1 over all voters.
    Each voter gives its low nearest the main low within `reach` km (below 1008 hPa). It agrees with the main
    low when that low is within `dkm` km and `dhpa` hPa of it; the others are grouped greedily (a group = the
    dissenters within dkm km and dhpa hPa of its seed, the seed being the dissenter with the most dissenting weight
    around it), at most `max_alt` groups. A group is returned when its weight share of ALL voters >= `min_share`
    and its centre (weighted mean position, weighted median depth) is more than dkm km or dhpa hPa from the main
    low, and not within dkm km of another map low (`others`: list of (lat, lon)).
    Returns a list of dicts lat, lon, hpa, share, n, kind ('pos' > dkm km away, else 'depth'), dist_km."""
    la0, lo0, p0 = main
    cand = []
    for w, L in V:
        L = np.asarray(L, float).reshape(-1, 3)
        L = L[L[:, 2] < 1008.0]
        if not len(L):
            continue
        d = km(la0, lo0, L[:, 0], L[:, 1])
        j = int(d.argmin())
        if d[j] <= reach:
            cand.append((w, L[j, 0], L[j, 1], L[j, 2], d[j]))
    if not cand:
        return []
    C = np.array(cand)
    dis = ~((C[:, 4] <= dkm) & (np.abs(C[:, 3] - p0) <= dhpa))
    P = C[dis]
    out = []
    for _ in range(max_alt):
        if not len(P):
            break
        D = km(P[:, 1][:, None], P[:, 2][:, None], P[:, 1][None, :], P[:, 2][None, :])
        H = np.abs(P[:, 3][:, None] - P[:, 3][None, :])
        near = (D <= dkm) & (H <= dhpa)
        s = int((near * P[:, 0][None, :]).sum(1).argmax())
        sel = near[s]
        w = P[sel, 0]
        share = float(w.sum())
        lat = float((w * P[sel, 1]).sum() / w.sum())
        dl = (P[sel, 2] - P[s, 2] + 180) % 360 - 180
        lon = float((P[s, 2] + (w * dl).sum() / w.sum()) % 360)
        hpa = wmedian(P[sel, 3], w)
        dist = float(km(la0, lo0, lat, lon))
        ok = share >= min_share and (dist > dkm or abs(hpa - p0) > dhpa)
        if ok and any(km(lat, lon, a, b) <= dkm for a, b in others):
            ok = False
        if ok:
            out.append(dict(lat=lat, lon=lon, hpa=hpa, share=share, n=int(sel.sum()),
                            kind="pos" if dist > dkm else "depth", dist_km=dist))
        P = P[~sel]
    return out


# ---------------------------------------------------------------- build (reads the store)

def cycles(start=START, end=END):
    t = start
    while t <= end:
        yield t
        t += timedelta(days=1)


def free():
    return shutil.disk_usage(paths.CACHE).free


def _load_pair(basin, cyc, names):
    out = {}
    tag = f"{cyc:%Y%m%d%H}"
    for name in names:
        try:
            z = store.load(basin, tag, name)
        except Exception as ex:
            print("load failed", basin, tag, name, repr(ex), file=sys.stderr)
            z = None
        if z:
            out.update(z)
    return out or None


def _clean(basin, cyc):
    try:
        import extract
        extract.clean(basin, cyc)
    except Exception as ex:
        print("clean failed", basin, cyc, repr(ex), file=sys.stderr)


_AN = {}


def analysis(basin, valid):
    """(gfs, ifs) analyses at the 12 UTC valid time, hPa on the 0.25 deg basin grid, or None."""
    k = (basin, valid)
    if k not in _AN:
        a = _load_pair(basin, valid, ("mslpd57_an_noaa", "mslpd57_an_ec"))
        _clean(basin, valid)
        r = None
        if a and f"an_gfs_{basin}" in a and f"an_ifs_{basin}" in a:
            r = (a[f"an_gfs_{basin}"].astype(np.float32) / 10 + 1000, a[f"an_ifs_{basin}"].astype(np.float32) / 10 + 1000)
        if len(_AN) > 20:
            _AN.pop(next(iter(_AN)))
        _AN[k] = r
    return _AN[k]


def voter_depths(L, mem, V):
    """Weights and own central pressures of the voters behind one vote low (members: (voter, lat, lon))."""
    w, p = [], []
    for v, la, lo in mem:
        Lv = V[v][1]
        w.append(V[v][0])
        p.append(Lv[np.argmin(np.abs(Lv[:, 0] - la) + np.abs(Lv[:, 1] - lo)), 2])
    return np.array(w), np.array(p)


def build_case(basin, cyc, vm, T):
    mem = _load_pair(basin, cyc, ("mslpd57_noaa", "mslpd57_ec"))
    _clean(basin, cyc)
    if mem is None:
        return None
    from lib import find_lows
    out = {"basin": basin, "cycle": cyc, "leads": {}}
    for lead in LEADS:
        c = {"det": {}, "mem": {}, "mlows": {}, "lag": {}}
        ok = True
        for m in ("gfs", "ifs", "aifs"):
            k = "det_%s_%s_%d" % (m, basin, lead)
            if k not in mem:
                ok = False
                break
            c["det"][m] = mem[k].astype(np.float32) / 10.0 + 1000.0
        for en in ("gefs", "ens", "aifsens"):
            k = "mem_%s_%s_%d" % (en, basin, lead)
            if k in mem:
                c["mem"][en] = mem[k]
                c["mlows"][en] = mem["low_%s_%s_%d" % (en, basin, lead)]
        if not ok or "gefs" not in c["mem"] or "ens" not in c["mem"]:
            continue
        V = vm.voters(c, basin, VOTE_W, use_lag=False)
        mm = []
        lows = vm.consensus(V, R=VOTE_R, T=T[lead], q=0.5, members=mm)
        valid = cyc + timedelta(hours=lead)
        an = analysis(basin, valid)
        truth = None
        if an is not None:
            g, i = an
            truth = {"gfs": find_lows(g, basin, 1000.0, inset_deg=3.0), "ifs": find_lows(i, basin, 1000.0, inset_deg=3.0),
                     "mean": find_lows(((g + i) / 2).astype(np.float32), basin, 1000.0, inset_deg=3.0)}
        vd, alts = [], []
        for k in range(len(lows)):
            vd.append(voter_depths(lows[k], mm[k], V))
            others = [(lows[j, 0], lows[j, 1]) for j in range(len(lows)) if j != k]
            alts.append(alternatives((lows[k, 0], lows[k, 1], lows[k, 2]), V, others=others))
        out["leads"][lead] = dict(lows=lows, vd=vd, alts=alts, truth=truth, n_voters=len(V))
    return out


def case_path(basin, cyc):
    return CASES / basin / f"{cyc:%Y%m%d%H}.pkl"


def build(args):
    import method as vm
    with open(D57 / "results" / "final.json") as f:
        T = {int(k): v for k, v in json.load(f)["T"].items()}
    cl = list(cycles(datetime.strptime(args.start, "%Y%m%d").replace(hour=12), datetime.strptime(args.end, "%Y%m%d").replace(hour=12)))
    if args.cycles:
        cl = [datetime.strptime(c, "%Y%m%d%H") for c in args.cycles]
    if args.limit:
        cl = cl[:args.limit]
    idx, n = (int(x) for x in args.part.split("/"))
    cl = cl[idx::n]
    t0 = time.time()
    done = 0
    for cyc in cl:
        for basin in BASINS:
            out = case_path(basin, cyc)
            if out.exists():
                continue
            if free() < MIN_FREE:
                print("STOP low disk", free() / 1e9, "GB at", basin, cyc)
                sys.exit(2)
            try:
                r = build_case(basin, cyc, vm, T)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                print("ERROR", basin, cyc, repr(ex))
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump(r, f)
            os.replace(tmp, out)
            done += 1
        if done and done % 10 == 0:
            print(f"{cyc:%Y%m%d} done={done} free={free()/1e9:.1f}GB {time.time()-t0:.0f}s", flush=True)
    print("finished", done, f"{time.time()-t0:.0f}s free={free()/1e9:.1f}GB")


def status():
    for b in BASINS:
        fs = sorted((CASES / b).glob("*.pkl")) if (CASES / b).exists() else []
        print(b, len(fs), fs[0].stem if fs else "", fs[-1].stem if fs else "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cycles", nargs="*")
    ap.add_argument("--part", default="0/1")
    ap.add_argument("--start", default=START.strftime("%Y%m%d"))
    ap.add_argument("--end", default=END.strftime("%Y%m%d"))
    a = ap.parse_args()
    if a.status:
        status()
    elif a.build:
        build(a)
    else:
        ap.print_help()
