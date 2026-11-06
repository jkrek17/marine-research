#!/usr/bin/env python3
"""Cases for the GFE wind tool study (design.md): the strong-core-lift cases, unchanged, plus a sidecar per case.

  python3 build.py [--workers 3] [--basins natl,npac] [--heldout-only | --tune-only] [--block 8]

Runs studies/2026-11-06-strong-core-lift/build.py's block loop (imported, not copied; its npz go to
rk.paths.cache("extra", "strong-core-lift", basin)) and, while each cycle's store files are on disk, writes
rk.paths.cache("extra", "gfe-wind-tool", basin)/<tag>_f<step>.npz with, where available:
  aigfs      float16  AI-GFS 10 m speed (kt), current run
  det_ah     float16  rk.features.det_blend(gfs, ifs, aigfs at half weight), lags 12/24 (absent if any run is)
  p34nb_h p48c_h p64nb_h  float16  GEFS 34 / 64 kt member share at 0.5 deg, neighbourhood max (rk.features.NB),
                      and the 48 kt share at 0.5 deg without the neighbourhood (cell value, as an AWIPS
                      probability grid would read)
Resumable: an existing sidecar is skipped; the base case is skipped by the strong-core-lift code.
"""
import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
SCL = HERE.parent / "2026-11-06-strong-core-lift"
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(SCL))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import build as B  # noqa: E402  (strong-core-lift build.py)
from rk import cases, features, paths, store  # noqa: E402

_base_case_job = B.case_job


def side_path(basin, cycle, step):
    return paths.cache("extra", "gfe-wind-tool", basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def sidecar(basin, cycle, step):
    sp = side_path(basin, cycle, step)
    if sp.exists() or not B.out_path(basin, cycle, step).exists():
        return
    out = {}
    a = store.load_det(basin, cycle, "aigfs", step)
    if a is not None:
        out["aigfs"] = a["speed"].astype(np.float16)
        d = features.det_blend(basin, cycle, step, models=("gfs", "ifs", "aigfs"), weights={"aigfs": 0.5},
                               lags=B.LAGS)
        if d is not None:
            out["det_ah"] = d["r10"].astype(np.float16)
    g = store.load_ens(basin, cycle, "gefs", step)
    if g is not None:
        nb = lambda x: ndimage.maximum_filter(x, size=features.NB, mode="nearest")  # noqa: E731
        out["p34nb_h"] = nb(features.half_deg(g["p34"])).astype(np.float16)
        out["p64nb_h"] = nb(features.half_deg(g["p64"])).astype(np.float16)
        out["p48c_h"] = features.half_deg(g["p48"]).astype(np.float16)
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_name(sp.stem + ".tmp.npz")
    np.savez_compressed(tmp, **out)
    os.replace(tmp, sp)


def case_job(job):
    r = _base_case_job(job)
    if r[1] in ("done", "existing"):
        sidecar(*job)
    return r


B.case_job = case_job   # module-level, so spawned workers (which import this file as __mp_main__) patch too

if __name__ == "__main__":
    B.main()
