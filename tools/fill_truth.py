#!/usr/bin/env python3
"""Fill the truth files (rk.store.truth_*) for a run of days through the kit's own loaders: analyses and
air-sea temperature difference (rk.store.analysis, rk.truth.airsea), ship and buoy winds (rk.truth.obs_points),
ASCAT days (rk.truth.ascat_day) and SMAP days (rk.truth.smap_day). New files go to the local cache (RK_CACHE),
marked unpublished; tools/publish_store.py sends them. A file already in the cache, the old RK_DATA/truth or
a release is not built again.

  python3 tools/fill_truth.py [--back-from 16 --back-to 3] [--start YYYYMMDD --end YYYYMMDD]
         [--hours 0,12] [--kinds analysis,airsea,obs,ascat,smap] [--dry-run]

Default window: from 16 to 3 days before today (UTC). ASCAT and SMAP lag the day by about 2 days, so a day
less than 3 days old is not tried; a day whose ASCAT has only one satellite and is under a week old is not
stored (rk.truth.ascat_day) and is tried again next run. Analyses, air-sea and obs are taken at --hours
(default 0 and 12 UTC, the basins' ASCAT hours). Prints one line per kind; exits 2 when a kind found
nothing at all (cached, published or new) but had days to do, which means its source was unreachable.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

KINDS = ("analysis", "airsea", "obs", "ascat", "smap")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--back-from", type=int, default=16, help="oldest day, days before today (default 16)")
    ap.add_argument("--back-to", type=int, default=3, help="newest day, days before today (default 3)")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--hours", default="0,12")
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    today = dt.datetime.now(dt.timezone.utc).date()
    if a.start or a.end:
        start = dt.datetime.strptime(a.start or a.end, "%Y%m%d").date()
        end = dt.datetime.strptime(a.end or a.start, "%Y%m%d").date()
    else:
        start, end = today - dt.timedelta(days=a.back_from), today - dt.timedelta(days=a.back_to)
    kinds = [k for k in a.kinds.split(",") if k]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise SystemExit("unknown kind %s; choose from %s" % (bad, ",".join(KINDS)))
    hours = sorted({int(h) for h in a.hours.split(",")})
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]

    from rk import store, truth
    from rk.basins import BASINS

    def day_job(kind, day):
        """Stems (valid times or the day) and the call that builds one of them."""
        if kind in ("ascat", "smap"):
            return [(None, day)], {"ascat": truth.ascat_day, "smap": truth.smap_day}[kind]
        valids = [dt.datetime.combine(day, dt.time(h)) for h in hours]
        build = {"analysis": lambda v: store.analysis("natl", v), "airsea": lambda v: truth.airsea("natl", v),
                 "obs": lambda v: truth.obs_points("natl", v)}[kind]   # each builds both basins at once
        return [(b, v) for v in valids for b in BASINS], build

    rc = 0
    for kind in kinds:
        have = new = miss = 0
        done = set()
        for day in days:
            items, build = day_job(kind, day)
            for b, t in items:
                if store.truth_exists(kind, b, t):
                    have += 1
                    continue
                if a.dry_run:
                    new += 1
                    continue
                if (kind, t) in done:         # the other basin was built with this one
                    continue
                try:
                    ok = build(t) is not None
                except Exception as e:        # one bad day must not stop the rest
                    print("%s %s: %s: %s" % (kind, t, type(e).__name__, e), file=sys.stderr)
                    ok = False
                done.add((kind, t))
                for bb in ([b] if b else [None]) if kind in ("ascat", "smap") else list(BASINS):
                    if store.truth_exists(kind, bb, t):
                        new += 1
                    else:
                        miss += 1
        print("%s: %d days %s, already published or cached %d, %s %d, not available %d"
              % (kind, len(days), "%s to %s" % (days[0], days[-1]) if days else "-", have,
                 "would build" if a.dry_run else "new", new, miss), flush=True)
        if not a.dry_run and have + new == 0 and miss:
            print("fill_truth: %s found nothing: its source looks unreachable" % kind, file=sys.stderr)
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
