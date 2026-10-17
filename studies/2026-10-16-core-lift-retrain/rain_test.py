#!/usr/bin/env python3
"""Adversarial audit 2026-10-17, holes 4(c) and 6: ASCAT drops rain-flagged cells. Do the dropped strong cells,
where SMAP agrees, change how Core Lifted and the gale-core lift score?

  python3 rain_test.py CL_ROOT GALE_ROOT OUT_DIR [--workers 3] [--steps 24,...]

Reads the grids predict.py wrote (base: blend r10 and candidates; live: live core likelihood; <gale set>: the
gale-core chance), all cases with grids (tune weeks out of fold and held-out). Truth three ways through
rk.truth.ascat_target: "dropped" (as every score so far), "strict" (rain-flagged cells kept where ASCAT itself
reads the threshold and SMAP within 3 h agrees) and "upper" (any rain-flagged cell kept where SMAP within 5 h
reads the threshold, at the larger of ASCAT and SMAP). Products: Core Lifted (+5 kt at live likelihood 35%)
and galecore@0.6 (Core Lifted raised to 34 kt where the gale-core chance >= 0.6). Counts per case: ASCAT cells
at 48+ / 34+ and how many the product has at that speed, split into cells the rain flag kept and cells it
dropped, and storm/gale tile hits, misses and false alarms under each truth. Writes rain_cases.csv and
rain_summary.csv (pooled per basin)."""
import argparse
import datetime as dt
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
from rk import cases, score, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

GALE_SET = "live28+basin@34"
TRUTHS = {"dropped": {}, "strict": {"rain_speed": "ascat"}, "upper": {"rain_speed": "smap"}}
SMAP_DT = {"strict": 180, "upper": 300}


def target(basin, valid, thr, how):
    if how == "dropped":
        return truth.ascat_target(basin, valid, thr=thr)
    return truth.ascat_target(basin, valid, thr=thr, rain_keep_kt=float(thr), rain_speed=TRUTHS[how]["rain_speed"],
                              smap_dt_min=SMAP_DT[how])


def case_job(job):
    basin, cycle, step, cl_root, gale_root = job
    bp, lp = C.p_path(cl_root, "base", basin, cycle, step), C.p_path(cl_root, "live", basin, cycle, step)
    gp = C.p_path(gale_root, GALE_SET, basin, cycle, step)
    if not (bp.exists() and lp.exists() and gp.exists()):
        return job, "missing_grids", []
    b, pl, pg = np.load(bp), np.load(lp), np.load(gp)
    r10 = np.asarray(b["r10"], np.float32)
    corelift = np.where(np.asarray(pl["P"]) >= 0.35, r10 + 5, r10).astype(np.float32)
    galecore = np.where(np.asarray(pg["P"]) >= 0.6, np.maximum(corelift, 34), corelift).astype(np.float32)
    prods = {"corelift": corelift, "galecore@0.6": galecore}
    valid = cycle + dt.timedelta(hours=step)
    lats, lons = grid(basin)
    rows = []
    for thr in (48, 34):
        base = target(basin, valid, thr, "dropped")
        if base is None:
            return job, "missing_ascat", []
        for how in TRUTHS:
            t = base if how == "dropped" else target(basin, valid, thr, how)
            if t is None:
                return job, "missing_smap", []
            seen, spd = t["seen"], t["spd"]
            ob = seen & (np.nan_to_num(spd, nan=-1) >= thr)
            ob_base = ob & base["seen"] & (np.nan_to_num(base["spd"], nan=-1) >= thr)
            added = ob & ~ob_base
            for name, f in prods.items():
                tl = score.tile_hits(f, spd, seen, lats, lons, thr)
                h, m, fa = score.tile_counts(tl)
                rows.append({"basin": basin, "cycle": cases.tag(cycle), "step": step, "split": cases.split(cycle),
                             "thr": thr, "truth": how, "product": name, "ob": int(ob.sum()),
                             "caught": int((ob & (f >= thr)).sum()), "added": int(added.sum()),
                             "added_caught": int((added & (f >= thr)).sum()), "fc": int((seen & (f >= thr)).sum()),
                             "h": h, "m": m, "fa": fa})
    return job, "done", rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cl_root")
    ap.add_argument("gale_root")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--steps", default="24,30,48,54,72,78,96,102,120,126")
    a = ap.parse_args()
    steps = tuple(int(s) for s in a.steps.split(","))
    jobs = [(b, c, s, a.cl_root, a.gale_root) for b, c, s in C.all_cases(["natl", "npac"], steps)]
    tally, rows = {}, []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, st, r) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=4), 1):
            tally[st] = tally.get(st, 0) + 1
            rows += r
            if i % 200 == 0 or i == len(jobs):
                print("[%d/%d] %s" % (i, len(jobs), tally), flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = pd.DataFrame(rows)
    d.to_csv(out / "rain_cases.csv", index=False)
    g = d.groupby(["basin", "thr", "product", "truth"])[["ob", "caught", "added", "added_caught", "fc", "h", "m", "fa"]].sum()
    g["catch"] = g.caught / g.ob
    g["catch_added"] = g.added_caught / g.added.where(g.added > 0)
    g["area"] = g.fc / g.ob
    g["pod"] = g.h / (g.h + g.m)
    g["far"] = g.fa / (g.h + g.fa)
    g["csi"] = g.h / (g.h + g.m + g.fa)
    g = g.reset_index()
    g.to_csv(out / "rain_summary.csv", index=False, float_format="%.4f")
    print(g[["basin", "thr", "product", "truth", "ob", "added", "catch", "catch_added", "area", "pod", "far", "csi"]]
          .round(3).to_string(index=False))
    print("SUMMARY: %s" % tally)


if __name__ == "__main__":
    main()
