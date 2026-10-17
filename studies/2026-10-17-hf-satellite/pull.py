"""Fill the GridSat-B1 IR boxes (truth kind gridsat) for every pilot fix time. Resumable: cached times are
skipped; one read serves both basins. Then publish with tools/publish_store.py.

    python3 studies/2026-10-17-hf-satellite/pull.py [--workers 4] [--dry-run]
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from common import fixes
from rk import satellite, store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = fixes()
    times = sorted({t.to_pydatetime() for t in d["valid"]})
    todo = [t for t in times if not all(store.truth_local("gridsat", b, t) for b in ("natl", "npac"))]
    print("%d fixes, %d valid times, %d to fetch (~%.1f GB at ~10 MB each)"
          % (len(d), len(times), len(todo), len(todo) * 0.0105), flush=True)
    if a.dry_run:
        return
    t0, done, missing = time.time(), 0, []

    def one(t):
        return t, satellite.box("natl", t)

    with ThreadPoolExecutor(a.workers) as ex:
        for t, r in ex.map(one, todo):
            done += 1
            if r is None:
                missing.append(t)
            if done % 25 == 0:
                print("%d/%d  %.0f s" % (done, len(todo), time.time() - t0), flush=True)
    print("done %d, not posted %d: %s" % (done, len(missing), [m.strftime("%Y%m%d%H") for m in missing]))


if __name__ == "__main__":
    main()
