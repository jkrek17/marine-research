#!/usr/bin/env python3
"""GFE follow-up (Jason 17:45Z "score the GFE method"): Make_BestWind scored like the page grids, same cells.

  python3 gfe_score.py --split tune|held_out [--workers 4]   -> err_gfe_<split>, tiles_gfe_<split>, hist_gfe_<split>
  python3 summarize.py --split <split> --tag _gfe --refs gfe_best,det

Products (kt), cases that have the page inputs (build_cases.py) and the GFE sidecar (gfe_cases.py):
  det            the GFE blend (rk.features.det_blend GFS+ECMWF, lags 12/24; Make_BestWind step 1-3)
  gfe_best       Make_BestWind default: det + 0->6 kt over 38-42 and 0->4 more over 48-52 of max(GFS, ECMWF), ocean
  gfe_best_hf    + HF core option: 0->6 more over 52-56 where GFS 925 x stability (0.70/0.79/0.83) >= 55 kt
  gfe_own        trigger "Blend's own wind": ramps 36-40 / 44-48 of det itself
  gfe_x0.5 gfe_s+2   ramps half size / 2 kt later
  gfe_floor80    gfe_best + 34 kt where the page gale-core chance >= 80% (what the page now does; GFE has no
                 members, so reference only)
  blend best     the page blend and page Best Wind (80% gale floor), same cells, for reference
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402

import score_cells as SC  # noqa: E402
from rk import features, paths  # noqa: E402

M1, M2, OWN1, OWN2, HFR, HFG = (38.0, 42.0), (48.0, 52.0), (36.0, 40.0), (44.0, 48.0), (52.0, 56.0), 55.0


def r(x, kt, lo, hi):
    return kt * np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def gfe(det, trig, oc, scale=1.0, shift=0.0, own=False):
    a, b = (OWN1, OWN2) if own else (M1, M2)
    add = r(trig, 6 * scale, a[0] + shift, a[1] + shift) + r(trig, 4 * scale, b[0] + shift, b[1] + shift)
    return np.where(oc, det + add, det)


def products(d):
    det, oc = d["det"], d["ocean"]
    strong = np.nan_to_num(np.fmax(d["gfs"], d["ifs"]), nan=-1.0)
    p = {"det": det, "gfe_best": gfe(det, strong, oc)}
    hf = r(strong, 6.0, *HFR)
    if "s925" in d:
        ceil = features.hf_ceiling(det, d["s925"], d["sa"])[1]
        hf = np.where(np.nan_to_num(ceil, nan=-1) >= HFG, hf, 0.0)
    else:
        hf = 0.0 * hf
    p["gfe_best_hf"] = np.where(oc, p["gfe_best"] + hf, p["gfe_best"])
    p["gfe_own"] = gfe(det, np.nan_to_num(det, nan=-1.0), oc, own=True)
    p["gfe_x0.5"] = gfe(det, strong, oc, scale=0.5)
    p["gfe_s+2"] = gfe(det, strong, oc, shift=2.0)
    p["gfe_floor80"] = np.where(d["Pg"] >= 0.8, np.maximum(p["gfe_best"], 34.0), p["gfe_best"])
    blend = d["base05"] + d["boost"]
    p["blend"] = blend
    pb = SC.best(blend, d)               # live floor (60%)
    pre = SC.best(blend, dict(d, Pg=np.zeros_like(d["Pg"])))
    p["best"] = np.where(d["Pg"] >= 0.8, np.maximum(pre, 34.0), pre)
    del pb
    return p


_load = SC.load


def load(path, basin):
    d = _load(path, basin)
    if d is None:
        return None
    sp = paths.cache("extra", "most-likely-wind-gfe", basin) / path.name
    if not sp.exists():
        return None
    z = np.load(sp)
    for k in z.files:
        d[k] = z[k].astype(np.float32)
    return d


def job(args):
    SC.products = products
    SC.load = load
    return SC.job(args)


if __name__ == "__main__":
    SC.TAG = "_gfe"
    SC.JOB = job
    SC.main()
