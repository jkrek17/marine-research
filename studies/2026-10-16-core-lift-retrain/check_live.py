#!/usr/bin/env python3
"""Fidelity check of rk.features.core against the live page's storm.core_features.

  python3 check_live.py 2026101012 [--steps 24,72,120] [--awips PATH_TO_awips-tools] [--low-root DIR]

For one cycle (YYYYMMDDHH) and each basin and step:
  live  : full GEFS + ENS members (rk.fetch.members), GFS/IFS/AIFS 10 m (rk.fetch.det), AIFS ENS members,
          lower-level fields (rk.fetch.low); the blend and features exactly as marine_wind/pipeline/build.py
          step_values / core_layers do (support_base over members, boost, storm.core_features).
  store : rk.features.core on the store's statistics (the store must hold this cycle; rk.store.fill and
          tools/fill_low.py fill it; --low-root as for the study).
Reports, at the live candidate cells in both: per-feature correlation and mean difference (store - live),
and the core probability from core_model.json with storm.core_predict for both, with the mean and 95th
percentile of |difference| and the correlation. m90 and support-weighted r10 are expected to differ a
little (normal-member approximation, see rk/features.py); everything else should match to float16 noise.
This pulls full members (~80 per step): run it deliberately, not during the marine wind build windows.
The awips-tools checkout is found from --awips, $AWIPS_TOOLS, or a sibling directory of this repo.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from rk import KT, cases, features, fetch  # noqa: E402
from rk.basins import grid  # noqa: E402


def find_awips(arg):
    for p in (arg, os.environ.get("AWIPS_TOOLS"), Path(__file__).resolve().parents[3] / "awips-tools"):
        if p and (Path(p) / "marine_wind" / "pipeline" / "storm.py").exists():
            return Path(p) / "marine_wind" / "pipeline"
    sys.exit("awips-tools checkout not found: pass --awips or set AWIPS_TOOLS")


def live_support_base(speeds, members, h=5.0):
    """build.py support_base (SUPPORT_KT = 5.0)."""
    w = np.array([np.exp(-0.5 * ((members - s[None]) / h) ** 2).mean(0) for s in speeds]) + 1e-6
    return (w * speeds).sum(0) / w.sum(0)


def live_features(storm, basin, cycle, step, low_root):
    """storm.core_features from full members, as build.step_values / core_layers do. None if inputs missing."""
    dets = {m: fetch.det(m, cycle, step) for m in features.MODELS}
    lows = {m: fetch.low(m, cycle, step) for m in features.MODELS}
    g, e = fetch.members("gefs", cycle, step, msl=False), fetch.members("ens", cycle, step, msl=False)
    a = fetch.members("aifs-ens", cycle, step, msl=False)
    if any(d is None for d in dets.values()) or any(x is None for x in lows.values()) or g is None or e is None:
        return None
    r = lambda d: np.hypot(d["u"], d["v"]) * KT
    members = np.concatenate([r(g[basin]), r(e[basin])])
    speeds = np.array([np.hypot(dets[m][basin]["u"], dets[m][basin]["v"]) * KT for m in features.MODELS])
    mean = live_support_base(speeds, members)
    sigma = members.std(0)
    boost = np.minimum(features.k_for(step) * sigma, features.CAP_KT)
    lx = [lows[m][basin] for m in features.MODELS]
    low = {k: np.mean([x[k] for x in lx], 0) for k in ("t2", "skt", "t925", "t850")}
    for k in ("u925", "v925", "u850", "v850"):
        low[k] = np.mean([x[k] for x in lx], 0) * KT
    ocean = (lx[0]["land"] < 0.5) & ~(lx[0]["ice"] >= 0.5)
    asp = None if a is None else r(a[basin])
    lats, _ = grid(basin)
    f = storm.core_features(lats, mean + boost, boost, speeds, members, asp, low)
    f["ocean"] = ocean
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cycle", help="YYYYMMDDHH")
    ap.add_argument("--steps", default="24,72,120")
    ap.add_argument("--awips", default=None)
    ap.add_argument("--low-root", default=None)
    ap.add_argument("--basins", default="natl,npac")
    a = ap.parse_args()
    cycle = cases.parse(a.cycle)
    pipe = find_awips(a.awips)
    sys.path.insert(0, str(pipe))
    os.environ.setdefault("MARINE_DOMAIN", "natl")
    import storm  # noqa: E402  (awips-tools marine_wind/pipeline/storm.py)
    model = storm.load_model(str(pipe / "core_model.json"))
    assert tuple(model["features"]) == features.FEATURES, "feature list differs from core_model.json"
    for basin in a.basins.split(","):
        for step in (int(s) for s in a.steps.split(",")):
            tag = "%s %s +%d" % (basin, a.cycle, step)
            mine = features.core(basin, cycle, step, low_root=a.low_root)
            live = live_features(storm, basin, cycle, step, a.low_root)
            if mine is None or live is None:
                print("%s: skipped (store features %s, live inputs %s)"
                      % (tag, "ok" if mine is not None else "missing", "ok" if live is not None else "missing"))
                continue
            cand = mine["cand"] & (live["ocean"] & ((live["r10"] >= 28) | (live["mod_max"] >= 34)))
            print("%s: candidate cells in both %d (store %d, live %d)" % (
                tag, cand.sum(), mine["cand"].sum(), (live["ocean"] & ((live["r10"] >= 28) | (live["mod_max"] >= 34))).sum()))
            print("  %-16s %8s %10s" % ("feature", "corr", "mean diff"))
            for k in features.FEATURES:
                x, y = mine[k][cand].astype(float), live[k][cand].astype(float)
                ok = np.isfinite(x) & np.isfinite(y)
                if ok.sum() < 3:
                    print("  %-16s %8s %10s" % (k, "n/a", "n/a"))
                    continue
                c = np.corrcoef(x[ok], y[ok])[0, 1] if x[ok].std() > 0 and y[ok].std() > 0 else float("nan")
                print("  %-16s %8.4f %10.4f" % (k, c, (x[ok] - y[ok]).mean()))
            X1 = np.column_stack([mine[f][cand].astype(np.float64) for f in model["features"]])
            X2 = np.column_stack([np.asarray(live[f], np.float64)[cand] for f in model["features"]])
            p1, p2 = storm.core_predict(X1, model), storm.core_predict(X2, model)
            d = np.abs(p1 - p2)
            print("  core probability: corr %.4f, mean diff %+.4f, mean |diff| %.4f, p95 |diff| %.4f, "
                  "mean store %.3f live %.3f, share >= 0.35: store %.3f live %.3f" % (
                      np.corrcoef(p1, p2)[0, 1], (p1 - p2).mean(), d.mean(), np.percentile(d, 95),
                      p1.mean(), p2.mean(), (p1 >= 0.35).mean(), (p2 >= 0.35).mean()))


if __name__ == "__main__":
    main()
