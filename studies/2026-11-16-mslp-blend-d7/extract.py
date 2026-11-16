"""Reduce the rk.store winter 2025-26 fields to one compact MSLP-only npz per basin-cycle.

Output: rk.paths.cache("extra", "mslp-blend-d7", basin, "YYYYMMDDHH.npz") (float32 hPa; truths at valid
times; mask uint8). After each cycle, the unpacked store cycle dir is cleaned except mslpd57_*.npz and any
file marked dirty (unpublished). Sequential, resumable, stops if free disk < 8 GB.
Usage: python3 extract.py [--limit N] [--cycles YYYYMMDDHH ...]
"""
import os, shutil, sys, time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import numpy as np
from rk import paths, store

BASINS = ("natl", "npac")
LEADS = tuple(range(24, 169, 24))
DET = ("gfs", "ifs", "aifs", "aigfs")
ENS = ("gefs", "ens", "aifs-ens")
MIN_FREE = 8e9
OUT = paths.cache("extra", "mslp-blend-d7", "_root").parent
LOG = OUT / "extract.log"


def cycles():
    t, end = datetime(2025, 11, 1), datetime(2026, 3, 31, 12)
    while t <= end:
        yield t
        t += timedelta(hours=12)


def free():
    return shutil.disk_usage(paths.CACHE).free


def clean(basin, cyc):
    d = paths.CACHE / "fields" / basin / f"{cyc:%Y%m%d%H}"
    if not d.is_dir():
        return 0
    dirty = {p.name for p in (d / ".dirty").glob("*")} if (d / ".dirty").is_dir() else set()
    n = 0
    for p in d.glob("*.npz"):
        if p.name.startswith("mslpd57_") or p.name in dirty:
            continue
        p.unlink()
        n += 1
    return n


def one(basin, cyc):
    arrs, miss = {}, []
    for L in LEADS:
        for m in DET:
            r = store.load_det(basin, cyc, m, L)
            if r is None:
                miss.append(f"{m}_f{L:03d}")
            else:
                arrs[f"{m}_f{L:03d}"] = r["msl"].astype(np.float32)
        for e in ENS:
            r = store.load_ens(basin, cyc, e, L) if L <= 120 else None
            if r is None:
                if L <= 120:
                    miss.append(f"{e}_f{L:03d}")
            else:
                arrs[f"{e}_mean_f{L:03d}"] = r["msl_mean"].astype(np.float32)
                arrs[f"{e}_std_f{L:03d}"] = r["msl_std"].astype(np.float32)
        try:
            a = store.analysis(basin, cyc + timedelta(hours=L))
        except Exception as ex:
            a = None
            print("analysis error", basin, cyc, L, repr(ex), file=sys.stderr)
        if a is None:
            miss.append(f"an_v{L:03d}")
        else:
            arrs[f"an_gfs_v{L:03d}"] = a["gfs"]["msl"].astype(np.float32)
            arrs[f"an_ifs_v{L:03d}"] = a["ifs"]["msl"].astype(np.float32)
            arrs[f"mask_v{L:03d}"] = np.asarray(a["mask"]).astype(np.uint8)
    return arrs, miss


def main():
    args = sys.argv[1:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    only = set(args[args.index("--cycles") + 1:]) if "--cycles" in args else None
    cl = [c for c in cycles() if only is None or f"{c:%Y%m%d%H}" in only]
    if limit:
        cl = cl[:limit]
    t0 = time.time()
    with open(LOG, "a") as log:
        for cyc in cl:
            for basin in BASINS:
                out = OUT / basin / f"{cyc:%Y%m%d%H}.npz"
                if out.exists():
                    continue
                if free() < MIN_FREE:
                    log.write(f"STOP low disk {free()/1e9:.1f} GB at {basin} {cyc:%Y%m%d%H}\n"); log.flush()
                    sys.exit(2)
                try:
                    arrs, miss = one(basin, cyc)
                    nd = sum(k.startswith(DET) and "_f" in k and "_mean" not in k for k in arrs)
                    if any(k.startswith(("gfs_f", "ifs_f", "aifs_f", "aigfs_f", "gefs_", "ens_", "aifs-ens_")) for k in arrs):
                        out.parent.mkdir(parents=True, exist_ok=True)
                        tmp = out.with_suffix(".tmp.npz")
                        np.savez_compressed(tmp, **arrs)
                        os.replace(tmp, out)
                        status = "ok"
                    else:
                        status = "NOFIELDS"
                    ncl = clean(basin, cyc)
                    log.write(f"{time.strftime('%H:%M:%S')} {basin} {cyc:%Y%m%d%H} {status} keys={len(arrs)} "
                              f"missing={len(miss)} cleaned={ncl} free={free()/1e9:.1f}GB "
                              f"miss_list={','.join(miss)}\n")
                except Exception as ex:
                    log.write(f"{basin} {cyc:%Y%m%d%H} ERROR {ex!r}\n")
                log.flush()
    print("done", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
