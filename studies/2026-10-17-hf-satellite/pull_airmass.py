"""Fill the GOES air-mass boxes (truth kind airmass) for every pilot fix, per basin (GOES-East for the Atlantic,
GOES-West for the Pacific). Resumable: cached times are skipped. Then publish with tools/publish_store.py.

    python3 studies/2026-10-17-hf-satellite/pull_airmass.py [--workers 4] [--dry-run]
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
    jobs = sorted({(b, t.to_pydatetime()) for b, t in zip(d["basin"], d["valid"])})
    todo = [j for j in jobs if not store.truth_local("airmass", *j)]
    print("%d basin-times, %d to fetch (~%.1f GB at ~26 MB each)" % (len(jobs), len(todo), len(todo) * 0.026),
          flush=True)
    if a.dry_run:
        return
    t0, done, missing = time.time(), 0, []

    def one(j):
        return j, satellite.airmass_box(*j)

    with ThreadPoolExecutor(a.workers) as ex:
        for j, r in ex.map(one, todo):
            done += 1
            if r is None:
                missing.append("%s %s" % (j[0], j[1].strftime("%Y%m%d%H")))
            if done % 25 == 0:
                print("%d/%d  %.0f s" % (done, len(todo), time.time() - t0), flush=True)
    print("done %d, not available %d: %s" % (done, len(missing), missing))


if __name__ == "__main__":
    main()
