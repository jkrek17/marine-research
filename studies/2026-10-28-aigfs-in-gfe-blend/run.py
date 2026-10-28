#!/usr/bin/env python3
"""AI-GFS as the AI member of the GFE blend: per-case counts (design.md).

  python3 run.py [--split held_out|tune|all] [--basins natl,npac] [--start 2025-11-01] [--end 2026-03-31]
                 [--workers 2] [--max-cycles N] [--out DIR]

Products per case (basin, cycle, step), each a kt grid on the basin grid:
  blends (rk.features.det_blend, the page's deterministic recipe, no members, no core lift)
    A   gfs + ifs + aifs, AIFS weight x 0.5      G1  gfs + ifs + aigfs, all weight 1
    Gh  gfs + ifs + aigfs, AI-GFS weight x 0.5   N   gfs + ifs
  singles: gfs, ifs, aifs, aigfs 10 m speed (rk.store.load_det).
A case is scored only when ALL four blends and all four singles exist (so every comparison is on identical
cases); otherwise it is skipped as `missing_inputs` and not cached, so a rerun picks it up once the data land.
Truth: rk.truth.ascat_target (real 10 m wind, intercal, passes within 90 min); a day not posted is `missing_ascat`.

Cases: winter 2025-26 (1 Nov - 31 Mar). natl: 12 UTC cycles, steps 24..120 every 24 h. npac: 00 and 12 UTC
cycles, steps 24..120 AND 30..126 every 24 h (valid 00/12 and 06/18 UTC). --split picks tune or held-out weeks
by rk.cases.split(cycle) (default held_out; nothing is fitted, tune is a second look).

Per (case, product) one row of counts, written to OUT/case_counts.csv (columns `variant` = product name,
`product` = blend | single, `valid_hr`, `split`):
  h34 m34 fa34 nt34, h48 m48 fa48 nt48   5x5 deg tile hits / misses / false alarms / tiles (rk.score.tile_hits,
                                         >= 150 seen cells; forecast event among the SEEN cells)
  fc34 ob34 fc48 ob48                    seen cells with forecast >= thr / ASCAT >= thr (area ratio = fc/ob)
  b_n b_sum_err b_sum_abs                buoy pairs where forecast or buoy >= 34 kt: n, sum(fc - obs), sum|err|
  g_n g_sum                              seen cells with ASCAT >= 34 (and finite forecast): n, sum(fc - ASCAT)
  gc_n gc_sum / gw_n gw_sum              the same split into cold air / not cold air
Cold air = (t2 - skt) < -3 K from GFS low-level fields of the same run (rk.store.load_low(basin, cycle, "gfs",
step)), i.e. rk.features' `dT = t2 - skt` (2 m air minus skin temperature; negative = air colder than the sea,
the unstable side; the same dT sign convention rk.truth.enw_to_real uses). The "stability study" named in the
design card is not in this repository, so this is the definition in rk, the only one found by grep of
LESSONS.md, studies/ and rk/; threshold -3 K (cold outbreaks), chosen before any full run because 0 K put ~90% of gale cells in "cold". load_low exists only for steps 24..120 of the
00/12 UTC steps; where it is None (the +30..+126 steps) the four split counts are NaN and the case is still
scored. Pooled split bias must therefore be read as "cases that have low-level fields".
Finished cases are cached in OUT/cache/<basin>/<cycle>_f<step>.json and skipped on a rerun.
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import cases, features, paths, score, store, truth  # noqa: E402
from rk.basins import grid, inside  # noqa: E402

BLENDS = {
    "A": dict(models=("gfs", "ifs", "aifs"), weights={"aifs": 0.5}),
    "G1": dict(models=("gfs", "ifs", "aigfs"), weights=None),
    "Gh": dict(models=("gfs", "ifs", "aigfs"), weights={"aigfs": 0.5}),
    "N": dict(models=("gfs", "ifs"), weights=None),
}
SINGLES = ("gfs", "ifs", "aifs", "aigfs")
THRS = (34, 48)
WINDOW = (dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31))
STEPS_00_12 = (24, 48, 72, 96, 120)
STEPS_06_18 = (30, 54, 78, 102, 126)
COLD_K = -3.0         # cold air: t2 - skt < COLD_K (air 3 K or more colder than the sea: cold outbreaks; 0 K put ~90% of gale cells in "cold")
COUNTS = ["nt34", "h34", "m34", "fa34", "nt48", "h48", "m48", "fa48", "fc34", "ob34", "fc48", "ob48",
          "b_n", "b_sum_err", "b_sum_abs"]
BIAS_COUNTS = ["g_n", "g_sum", "gc_n", "gc_sum", "gw_n", "gw_sum"]


def case_list(basins, start, end, split, max_cycles=None):
    """[(basin, cycle, step)]: natl 12 UTC cycles; npac 00 and 12 UTC cycles with both step sets."""
    out = []
    for b in basins:
        hours = (12,) if b == "natl" else (0, 12)
        steps = STEPS_00_12 if b == "natl" else STEPS_00_12 + STEPS_06_18
        cyc = sorted(c for h in hours for c in cases.cycles(b, start, end, hour=h)
                     if split == "all" or cases.split(c) == split)
        if max_cycles:
            cyc = cyc[:max_cycles]
        out += [(b, c, s) for c in cyc for s in steps]
    return out


def cache_path(out, basin, cycle, step):
    return Path(out) / "cache" / basin / ("%s_f%03d.json" % (cases.tag(cycle), step))


def buoy_table(basin, valid):
    """Buoy observations inside the basin, or None when the table is not there."""
    o = truth.obs(basin, valid, platforms=("buoy",))
    if o is None or len(o["lat"]) == 0:
        return o, False
    keep = inside(basin, o["lat"], o["lon"])
    return {k: np.asarray(v)[keep] for k, v in o.items()}, True


def buoy_counts(basin, o, fc):
    """(n, sum_err, sum_abs_err) of buoy pairs where forecast or buoy >= 34 kt."""
    if o is None or len(o["lat"]) == 0:
        return 0, 0.0, 0.0
    p = score.points(fc, basin, o)
    p = p[np.isfinite(p.fc_kt) & np.isfinite(p.obs_kt)]
    p = p[(p.fc_kt >= 34) | (p.obs_kt >= 34)]
    return int(len(p)), float(p.err.sum()), float(p.abs_err.sum())


def case_job(job):
    """-> (job, status, rows). status: done, existing, missing_inputs, missing_ascat."""
    basin, cycle, step, out = job
    cp = cache_path(out, basin, cycle, step)
    if cp.exists():
        return job, "existing", json.load(open(cp))
    valid = cycle + dt.timedelta(hours=step)
    prods = {}
    for v, spec in BLENDS.items():
        b = features.det_blend(basin, cycle, step, models=spec["models"], weights=spec["weights"])
        if b is None:
            return job, "missing_inputs", []
        prods[v] = ("blend", b["r10"])
    for m in SINGLES:
        d = store.load_det(basin, cycle, m, step)
        if d is None:
            return job, "missing_inputs", []
        prods[m] = ("single", np.asarray(d["speed"], np.float32))
    t = truth.ascat_target(basin, valid)
    if t is None:
        return job, "missing_ascat", []
    low = store.load_low(basin, cycle, "gfs", step)
    cold = None if low is None else (low["t2"] - low["skt"]) < COLD_K
    lats, lons = grid(basin)
    seen, spd = t["seen"], t["spd"]
    gale = seen & np.isfinite(spd) & (spd >= 34)
    o, _ = buoy_table(basin, valid)
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "valid_hr": valid.hour,
           "split": cases.split(cycle)}
    rows = []
    for v, (kind, f) in prods.items():
        r = dict(key, variant=v, product=kind)
        for thr in THRS:
            h, m, fl = score.tile_counts(tl := score.tile_hits(f, spd, seen, lats, lons, thr))
            r.update({"nt%d" % thr: len(tl), "h%d" % thr: h, "m%d" % thr: m, "fa%d" % thr: fl,
                      "fc%d" % thr: int(((f >= thr) & seen).sum()),
                      "ob%d" % thr: int(((spd >= thr) & seen).sum())})
        n, se, sa = buoy_counts(basin, o, f)
        r.update(b_n=n, b_sum_err=se, b_sum_abs=sa)
        g = gale & np.isfinite(f)
        err = np.where(g, f - spd, 0.0)
        r.update(g_n=int(g.sum()), g_sum=float(err.sum()))
        if cold is None:
            r.update(gc_n=np.nan, gc_sum=np.nan, gw_n=np.nan, gw_sum=np.nan)
        else:
            r.update(gc_n=int((g & cold).sum()), gc_sum=float(err[cold].sum()),
                     gw_n=int((g & ~cold).sum()), gw_sum=float(err[~cold].sum()))
        rows.append(r)
    cp.parent.mkdir(parents=True, exist_ok=True)
    tmp = cp.with_suffix(".tmp")
    json.dump(rows, open(tmp, "w"))
    os.replace(tmp, cp)
    return job, "done", rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="folder for case_counts.csv and the cache "
                    "(default RK_DATA/extra/aigfs-in-gfe-blend)")
    ap.add_argument("--split", default="held_out", choices=["held_out", "tune", "all"])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--start", default="2025-11-01")
    ap.add_argument("--end", default="2026-03-31")
    ap.add_argument("--max-cycles", type=int, default=None, help="first N cycles per basin (small run)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else paths.data("extra", "aigfs-in-gfe-blend")
    out.mkdir(parents=True, exist_ok=True)
    start, end = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    allc = case_list(a.basins.split(","), start, end, a.split, a.max_cycles)
    jobs = [(b, c, s, str(out)) for b, c, s in allc]
    print("cases: %d (%s) -> %s" % (len(jobs), a.split, out), flush=True)
    tally = {"done": 0, "existing": 0, "missing_inputs": 0, "missing_ascat": 0}
    rows, t0 = [], time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, status, r) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=2), 1):
            tally[status] += 1
            rows += r
            if i % 50 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    if rows:
        df = pd.DataFrame(rows).sort_values(["basin", "cycle", "step", "product", "variant"])
        df.to_csv(out / "case_counts.csv", index=False)
        print("wrote %s (%d rows, %d cases)" % (out / "case_counts.csv", len(df), len(df) // 8))
    print("SUMMARY: cases %d %s" % (len(jobs), tally), flush=True)


if __name__ == "__main__":
    main()
