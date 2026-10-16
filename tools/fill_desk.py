#!/usr/bin/env python3
"""Fill the desk wind cache (rk.desk) for a range of dates.

  python3 tools/fill_desk.py --start 2026-01-01 --end 2026-01-31 [--workers 3] [--hours 10,22]

Loads the 10Z and 22Z full-update issuances (YCYZ98 days 1-3 and YCYZ97 days 4-7), averages them onto both
basins' 0.25 deg grids and caches the result under $RK_DESK (default DATA/desk). Raw GRIB files are deleted.
Resumable: issuances already cached are skipped, so rerun the same command after an interruption.
"""
import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

from rk import desk  # noqa: E402
from rk.cases import tag  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--hours", default="10,22", help="issuance hours UTC (default 10,22)")
    a = ap.parse_args()
    start, end = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    hours = tuple(int(h) for h in a.hours.split(","))
    t0 = time.time()
    n = [0]

    def log(issue, what, msg):
        n[0] += 1
        print("%s %s %s (%d done, %.0f s)" % (tag(issue), what, msg, n[0], time.time() - t0), flush=True)

    rep = desk.fill(start, end, hours=hours, workers=a.workers, log=log)
    print("done: ok %d (partial %d), missing %d, failed %d, already cached %d, %.0f s"
          % (rep["ok"], rep["partial"], rep["missing"], rep["failed"], rep["cached"], time.time() - t0), flush=True)
    if rep["failed_tags"]:
        print("failed: " + " ".join(rep["failed_tags"]), flush=True)
    sys.exit(1 if rep["failed"] else 0)


if __name__ == "__main__":
    main()
