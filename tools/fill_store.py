#!/usr/bin/env python3
"""Fill the shared field cache (rk.store) and the analyses for a run of cycles.

  python3 tools/fill_store.py --start 20260101 --end 20260131 [--basin natl|npac|both]
         [--every-days N] [--steps 24,48,...] [--workers 6] [--dry-run]

Each basin uses its own cycle hour (npac 00 UTC, natl 12 UTC), so they are different cycles.
Prints one line per cycle. --dry-run lists the cycles and a rough estimate of GB streamed.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

from rk import cases  # noqa: E402

GB_ENS, GB_DET = 0.1, 0.003   # GB per model-step (ensemble / deterministic), from the 2026-01-15 index sizes: GEFS 0.08, ENS and AIFS ENS ~0.1, one deterministic run 0.002


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--basin", default="both", choices=("natl", "npac", "both"))
    ap.add_argument("--every-days", type=int, default=1)
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    start, end = dt.datetime.strptime(a.start, "%Y%m%d"), dt.datetime.strptime(a.end, "%Y%m%d")
    steps = tuple(int(s) for s in a.steps.split(","))
    names = ("natl", "npac") if a.basin == "both" else (a.basin,)

    plan = {}   # cycle -> basins that use it
    for b in names:
        for c in cases.cycles(b, start, end, a.every_days):
            plan.setdefault(c, []).append(b)
    order = sorted(plan)

    from rk import store
    n_ens, n_det = len(store.ENS), len(store.DET)
    per_cycle = len(steps) * (n_ens * GB_ENS + n_det * GB_DET) + 2 * GB_DET * len(steps)   # + analyses
    if a.dry_run:
        for c in order:
            print("%s  %s" % (cases.tag(c), ",".join(plan[c])))
        print("%d cycles, steps %s; rough estimate %.1f GB streamed (about %.2f GB per ensemble model-step, "
              "%.3f per deterministic; ignores files already cached)"
              % (len(order), steps, per_cycle * len(order), GB_ENS, GB_DET))
        return

    for c in order:
        bs = tuple(plan[c])
        rep = store.fill(c, steps=steps, workers=a.workers, basins=bs)
        done = new = miss = 0
        for b in bs:
            for s in steps:
                valid = c + dt.timedelta(hours=s)
                p = store._analysis_path(b, valid)
                had = p.exists()
                got = store.analysis(b, valid)
                done += got is not None and had
                new += got is not None and not had
                miss += got is None
        print("%s %s: fetched %d, existing %d, missing %d, ens skipped %d%s | analyses new %d, cached %d, missing %d"
              % (rep["cycle"], ",".join(bs), len(rep["fetched"]), len(rep["existing"]), len(rep["missing"]),
                 len(rep["skipped_ens"]), (" (%s)" % ",".join(rep["skipped_ens"])) if rep["skipped_ens"] else "",
                 new, done, miss), flush=True)


if __name__ == "__main__":
    main()
