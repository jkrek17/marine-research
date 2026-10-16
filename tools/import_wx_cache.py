#!/usr/bin/env python3
"""Convert another study's analysis cache into the rk.store analysis layout, so it is not downloaded again.

  python3 tools/import_wx_cache.py SRC [--dry-run] [--units ms|kt|auto] [--msl-units hpa|pa|auto]

SRC layout: SRC/truth/<natl|npac>/<YYYYMMDDHH>.npz with gfs_u gfs_v gfs_msl gfs_land gfs_ice ifs_u ifs_v
ifs_msl (float16). The grids must be exactly rk.basins' (natl 149x300, npac 149x341); a file with another
shape is refused and counted. u/v must be m/s and msl hPa: units are checked on the first file of each
basin (max speed, mean msl) and a kt or Pa cache is converted, unless forced with --units/--msl-units.
Files are written with rk.store.analysis_arrays (the same code store.analysis uses) to
CACHE/truth/analysis/<basin>/<tag>.npz (marked unpublished; tools/publish_store.py sends it); existing
targets (cache or old shared folder) are skipped. SRC is only read.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

import numpy as np  # noqa: E402

from rk import KT, basins, cases, store  # noqa: E402

KEYS = ("gfs_u", "gfs_v", "gfs_msl", "gfs_land", "gfs_ice", "ifs_u", "ifs_v", "ifs_msl")


def detect_units(z):
    """-> (wind factor to m/s, msl factor to hPa) from one file. A global-ocean 10 m wind max is well under
    60 m/s (117 kt), and a hurricane-force low in kt would read above 60; MSLP is ~1000 hPa or ~100000 Pa."""
    vmax = max(float(np.nanmax(np.hypot(z[m + "_u"].astype(np.float32), z[m + "_v"].astype(np.float32))))
               for m in ("gfs", "ifs"))
    pmean = float(np.nanmean(z["gfs_msl"].astype(np.float32)))
    wf = 1.0 if vmax < 60 else 1 / KT
    pf = 1.0 if pmean < 2000 else 0.01
    return wf, pf, vmax, pmean


def convert(z, wf, pf):
    def det(m):
        return {"u": z[m + "_u"].astype(np.float32) * wf, "v": z[m + "_v"].astype(np.float32) * wf,
                "msl": z[m + "_msl"].astype(np.float32) * pf}
    return store.analysis_arrays(det("gfs"), det("ifs"), z["gfs_land"].astype(np.float32),
                                 z["gfs_ice"].astype(np.float32))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--units", choices=("auto", "ms", "kt"), default="auto")
    ap.add_argument("--msl-units", choices=("auto", "hpa", "pa"), default="auto")
    a = ap.parse_args()
    src = Path(a.src)
    if not (src / "truth").is_dir():
        sys.exit("no %s/truth directory" % src)
    tot = {"new": 0, "existing": 0, "refused": 0, "bad": 0}
    for b in basins.BASINS:
        files = sorted((src / "truth" / b).glob("??????????.npz"))
        shape = tuple(len(x) for x in basins.grid(b))
        n = dict.fromkeys(tot, 0)
        wf = pf = None
        for f in files:
            try:
                valid = cases.parse(f.stem)
            except ValueError:
                n["bad"] += 1
                continue
            if store.truth_local("analysis", b, valid) is not None:
                n["existing"] += 1
                continue
            if a.dry_run:
                n["new"] += 1
                continue
            try:
                with np.load(f) as z:
                    if any(k not in z.files for k in KEYS):
                        n["bad"] += 1
                        continue
                    if any(z[k].shape != shape for k in KEYS):
                        n["refused"] += 1
                        print("refused %s: shape %s, expected %s" % (f, z["gfs_u"].shape, shape), file=sys.stderr)
                        continue
                    if wf is None:
                        w, p, vmax, pmean = detect_units(z)
                        wf = {"auto": w, "ms": 1.0, "kt": 1 / KT}[a.units]
                        pf = {"auto": p, "hpa": 1.0, "pa": 0.01}[a.msl_units]
                        print("%s: max speed %.1f (assumed %s), mean msl %.1f (assumed %s)"
                              % (b, vmax, "m/s" if wf == 1 else "kt, converting", pmean,
                                 "hPa" if pf == 1 else "Pa, converting"))
                    arrays = convert(z, wf, pf)
            except Exception as e:   # unreadable or truncated file: count it, keep going
                n["bad"] += 1
                print("bad %s: %s" % (f, e), file=sys.stderr)
                continue
            store.truth_save("analysis", b, valid, **arrays)
            n["new"] += 1
        print("%s: %d files, %s%s" % (b, len(files), ", ".join("%s %d" % kv for kv in n.items()),
                                      " (dry run: 'new' would be written)" if a.dry_run else ""))
        for k in tot:
            tot[k] += n[k]
    print("total: " + ", ".join("%s %d" % kv for kv in tot.items()))


if __name__ == "__main__":
    main()
