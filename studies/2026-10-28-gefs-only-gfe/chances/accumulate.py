"""GEFS-only chance counts vs the ASCAT 3x3 box, at 0.25 deg and at 0.5 deg (rk.features.half_deg on the share grids).

    python3 accumulate.py [--workers 3]

Same cases and lead groups as studies/2026-10-16-chance-calibration/run_first_look.py (winter 2025-26, 1 Nov to
31 Mar; Atlantic 00 and 12 UTC, Pacific 00 UTC; steps +24..+120; lead groups le48/72/ge96) and the same truth
(rk.truth.ascat_box). The Pacific also gets the 06/18 UTC valid times from the 00/12 UTC cycles at +30..+126 h
(kind "0618", grouped with run_first_look.GROUP_0618). Reused from that script: START/END, retry, GROUP_0618,
STEPS_0618, HOURS; the open-water check for 06/18 UTC copies its rule.

The 0.5 deg shares are not multiples of 1/31, so counts are kept per share quantised to 1e-4: array [2, 10001]
(cells, events) per key "basin|kind|res|thr|group|split". Resumable: a finished (basin, kind, cycle) is skipped.
Output (not committed): rk.paths.data("extra", "gefs-only-gfe", "chances")."""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parents[1] / "2026-10-16-chance-calibration"))
from rk import calibrate as C, cases, features, paths, store, truth  # noqa: E402
import run_first_look as R  # noqa: E402

OUT = paths.data("extra", "gefs-only-gfe", "chances", "x").parent
THRS = R.THRS
NQ = 10001


def group_of(kind, step):
    return R.GROUP_0618[step] if kind == "0618" else C.lead_group(step)


def tasks():
    out = []
    for basin in R.BASINS:
        for h in R.HOURS[basin]:
            out += [(basin, "main", c) for c in cases.cycles(basin, R.START, R.END, hour=h)]
    for h in (0, 12):                                   # Pacific valid 06 / 18 UTC (cycle 00 / 12 UTC)
        out += [("npac", "0618", c) for c in cases.cycles("npac", R.START, R.END, hour=h)]
    return out


def work_group(group):
    """Run one cycle's tasks together (main and 0618 share the cycle's zip), then drop the cycle's field cache
    if this call created it (the disk is shared; the store re-downloads on demand)."""
    import shutil
    basin, c = group[0][0], group[0][2]
    d = store._cache_dir(basin, c)
    existed = d.exists()
    out = [work(t) for t in group]
    if not existed:
        shutil.rmtree(d, ignore_errors=True)
    return out


def work(task):
    basin, kind, c = task
    steps = R.STEPS_0618 if kind == "0618" else cases.STEPS
    counts, rows, log = {}, [], []
    if R.retry(store.load_ens, basin, c, "gefs", steps[0], what="idx") is None:
        return task, counts, rows, ["no GEFS %s %s" % (basin, c)]
    split = cases.split(c)
    for step in steps:
        e = R.retry(store.load_ens, basin, c, "gefs", step, what="ens")
        if e is None:
            continue
        valid = c + dt.timedelta(hours=step)
        if kind == "0618":
            near = [valid - dt.timedelta(hours=valid.hour % 12), valid + dt.timedelta(hours=12 - valid.hour % 12)]
            ok = any(store.truth_locate("analysis", basin, x) is not None for x in near)
        else:
            ok = store.truth_locate("analysis", basin, valid) is not None
        ag = R.retry(truth.ascat_box, basin, valid, what="truth") if ok else None
        if ag is None:
            log.append("no truth %s %s" % (basin, valid))
            continue
        box = ag["box"]
        m = np.isfinite(box)
        if not m.any():
            continue
        g = group_of(kind, step)
        for thr in THRS:
            p = e["p%d" % thr]
            ev = box[m] >= thr
            for res, grid in (("025", p), ("050", features.half_deg(p))):
                q = np.clip(np.rint(grid[m] * 1e4), 0, 1e4).astype(int)
                arr = counts.setdefault("|".join((basin, kind, res, str(thr), g, split)), np.zeros((2, NQ)))
                arr[0] += np.bincount(q, minlength=NQ)
                arr[1] += np.bincount(q[ev], minlength=NQ)
            rows.append((basin, kind, thr, g, step, c.strftime("%Y%m%d%H"), split, int(m.sum()), int(ev.sum())))
    return task, counts, rows, log


def save(counts, rows, done):
    tmp = OUT / "counts.tmp.npz"
    np.savez_compressed(tmp, **counts)
    os.replace(tmp, OUT / "counts.npz")
    tmp = OUT / "cycle_rows.csv.tmp"
    pd.DataFrame(rows, columns="basin kind thr group step cycle split n events".split()).to_csv(tmp, index=False)
    os.replace(tmp, OUT / "cycle_rows.csv")
    json.dump(sorted(done), open(OUT / "done.json", "w"))


def main(workers):
    OUT.mkdir(parents=True, exist_ok=True)
    counts, rows, done = {}, [], set()
    if (OUT / "done.json").exists():
        with np.load(OUT / "counts.npz") as z:
            counts = {k: z[k] for k in z.files}
        rows = [tuple(r) for r in pd.read_csv(OUT / "cycle_rows.csv", dtype={"cycle": str}).itertuples(index=False, name=None)]
        done = set(json.load(open(OUT / "done.json")))
    todo = [t for t in tasks() if "%s|%s|%s" % (t[0], t[1], t[2].strftime("%Y%m%d%H")) not in done]
    groups = {}
    for t in todo:
        groups.setdefault((t[0], t[2]), []).append(t)
    groups = list(groups.values())
    print("tasks", len(todo), "in", len(groups), "cycle groups; already", len(done), flush=True)
    logs = []
    with mp.Pool(workers) as pool:
        for i, res in enumerate(pool.imap_unordered(work_group, groups)):
            for t, cn, rw, lg in res:
                for k, v in cn.items():
                    counts[k] = counts.get(k, 0) + v
                rows += rw
                logs += lg
                done.add("%s|%s|%s" % (t[0], t[1], t[2].strftime("%Y%m%d%H")))
            if i % 10 == 9:
                save(counts, rows, done)
                print("checkpoint", i + 1, "/", len(groups), flush=True)
    save(counts, rows, done)
    (OUT / "accumulate.log").write_text("\n".join(logs) + "\n")
    print("done; notes:", len(logs), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    main(ap.parse_args().workers)
