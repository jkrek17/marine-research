#!/usr/bin/env python3
"""Fill the lower-level field cache (rk.store.save_low) for a run of cycles.

  python3 tools/fill_low.py --start 20251201 --end 20251231 [--models gfs,ifs,aifs] [--steps 24,48,72,96,120]
         [--hours 0,12] [--root DIR] [--workers 4] [--every-days N]

One fetch per cycle, model and step serves both basins. Files already present are skipped, so a rerun
only fills the gaps. --root stores under DIR/fields/... instead of writing through rk.store.put (then publish with
tools/publish_store.py). Waits out the marine wind build windows (rk.fetch.wait_for_quiet).
Prints one line per cycle.
"""
import argparse
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

from rk import cases, fetch, store  # noqa: E402
from rk.basins import BASINS  # noqa: E402

MODELS = ("gfs", "ifs", "aifs")


def fill_cycle(cycle, models, steps, root, workers):
    rep = {"fetched": 0, "existing": 0, "missing": 0}
    jobs = []
    for m in models:
        for s in steps:
            if not cases.available(m, cycle):
                rep["missing"] += 1
            elif all((store.low_path(b, cycle, m, s, root).exists() if root else store.load_low(b, cycle, m, s) is not None)
                     for b in BASINS):
                rep["existing"] += 1
            else:
                jobs.append((m, s))

    def run(job):
        m, s = job
        fetch.wait_for_quiet()
        res = fetch.low(m, cycle, s)
        if res is None:
            return "missing"
        for b in BASINS:
            store.save_low(b, cycle, m, s, res[b], root)
        return "fetched"

    with ThreadPoolExecutor(workers) as ex:
        for what in ex.map(run, jobs):
            rep[what] += 1
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--hours", default="0,12")
    ap.add_argument("--every-days", type=int, default=1)
    ap.add_argument("--root", default=None, help="store under ROOT/fields instead of RK_DATA")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    models = tuple(m.strip() for m in a.models.split(",") if m.strip())
    bad = [m for m in models if m not in MODELS]
    if bad:
        raise SystemExit("unknown model(s) %s; choose from %s" % (",".join(bad), ",".join(MODELS)))
    steps = tuple(int(s) for s in a.steps.split(","))
    hours = sorted({int(h) for h in a.hours.split(",")})
    day, end = dt.datetime.strptime(a.start, "%Y%m%d"), dt.datetime.strptime(a.end, "%Y%m%d")
    while day <= end:
        for h in hours:
            c = day + dt.timedelta(hours=h)
            r = fill_cycle(c, models, steps, a.root, a.workers)
            print("%s natl,npac: fetched %d, existing %d, missing %d"
                  % (cases.tag(c), r["fetched"], r["existing"], r["missing"]), flush=True)
        day += dt.timedelta(days=a.every_days)


if __name__ == "__main__":
    main()
