#!/usr/bin/env python3
"""Fill the field store (rk.store) and the analyses for a run of cycles. Fields are written to the local
cache (RK_CACHE) and marked unpublished; tools/publish_store.py sends them to the releases. Cycles already
in the cache, the old RK_DATA/fields or a release are not fetched again.

  python3 tools/fill_store.py --start 20260101 --end 20260131 [--hours 0,12] [--basin both|natl|npac]
         [--every-days N] [--steps 24,48,...] [--workers 6] [--models noaa|ecmwf|gfs,ifs,...]
         [--no-analysis] [--complete] [--min-age-hours H] [--dry-run]

Every cycle at --hours (default 0 and 12 UTC) is streamed once and BOTH basins are stored: the GRIB
messages are global and decoded once, so the second basin costs no extra streaming. The analyses (GFS and
IFS step 0 plus the mask) at every valid time are cached for both basins the same way. --basin only
chooses which basins are written (default both; there is rarely a reason to narrow it).
--models picks what is streamed: a comma list from gfs, ifs, aifs (deterministic) and gefs, ens, aifs-ens
(ensembles), default all six; the shorthands noaa (= gfs,gefs) and ecmwf (= ifs,aifs,ens,aifs-ens) expand in
place and can be mixed with names. --no-analysis skips the analyses (they need IFS, an ECMWF fetch), which
is what a NOAA-only fill wants. The dry-run estimate counts only the chosen models.
--complete stores an ensemble step only when every member came back (gefs 31, ens 51, aifs-ens 51), so a
step that is still being posted is not stored short and then treated as existing; an incomplete step is
reported as "ens skipped" and the next run retries it. --min-age-hours H skips cycles younger than H hours
(the scheduled job uses 8: the ensembles are complete about 8 h after the cycle). Analyses are only built for
valid times that have already passed. Nothing marks a cycle "complete": a cycle holds whichever files have been
stored, and a later run adds the rest, merged into the published zip by tools/publish_store.py.
Prints one line per cycle. --dry-run lists the cycles and estimates GB streamed (per cycle, independent
of the number of basins) and GB kept on disk (about 4 MB per basin-step for all six models, measured).
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

from rk import cases  # noqa: E402

MB_STEP = 4   # MB kept per basin-step for all six models (measured)
GB_DET = 0.003   # GB per deterministic model-step
GB_STEP = {"gefs": 0.08, "ens": 0.1, "aifs-ens": 0.1}   # GB per ensemble model-step, from the 2026-01-15 index sizes
SHORTHAND = {"noaa": ("gfs", "gefs"), "ecmwf": ("ifs", "aifs", "ens", "aifs-ens")}


def parse_models(text, allowed):
    """Expand a --models string (names and the shorthands noaa/ecmwf) to a de-duplicated tuple of names."""
    out = []
    for tok in (t.strip().lower() for t in text.split(",") if t.strip()):
        for m in SHORTHAND.get(tok, (tok,)):
            if m not in allowed:
                raise SystemExit("unknown model %r; choose from %s or noaa, ecmwf" % (m, ",".join(allowed)))
            if m not in out:
                out.append(m)
    if not out:
        raise SystemExit("--models is empty")
    return tuple(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--hours", default="0,12", help="cycle hours UTC, comma separated (default 0,12)")
    ap.add_argument("--basin", default="both", choices=("natl", "npac", "both"),
                    help="which basins to write (default both; streaming cost does not change)")
    ap.add_argument("--every-days", type=int, default=1)
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--models", default="gfs,ifs,aifs,gefs,ens,aifs-ens",
                    help="comma list from gfs,ifs,aifs,gefs,ens,aifs-ens, or noaa (gfs,gefs) / ecmwf "
                         "(ifs,aifs,ens,aifs-ens); default all six")
    ap.add_argument("--no-analysis", action="store_true",
                    help="skip caching the analyses (they need IFS, an ECMWF fetch)")
    ap.add_argument("--complete", action="store_true",
                    help="store an ensemble step only when all its members came back (see above)")
    ap.add_argument("--min-age-hours", type=float, default=0.0,
                    help="skip cycles younger than this many hours (default 0)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    start, end = dt.datetime.strptime(a.start, "%Y%m%d"), dt.datetime.strptime(a.end, "%Y%m%d")
    steps = tuple(int(s) for s in a.steps.split(","))
    names = ("natl", "npac") if a.basin == "both" else (a.basin,)
    hours = sorted({int(h) for h in a.hours.split(",")})

    order = []   # every cycle at the requested hours, each stored for all of `names`
    day = start
    while day <= end:
        order += [day + dt.timedelta(hours=h) for h in hours]
        day += dt.timedelta(days=a.every_days)

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    young = [c for c in order if now - c < dt.timedelta(hours=a.min_age_hours)]
    order = [c for c in order if c not in young]
    if young:
        print("skipping %d cycle(s) younger than %g h: %s" % (len(young), a.min_age_hours,
                                                               ",".join(cases.tag(c) for c in young)), flush=True)

    from rk import store
    chosen = parse_models(a.models, store.DET + store.ENS)
    det = tuple(m for m in store.DET if m in chosen)
    ens = tuple(m for m in store.ENS if m in chosen)
    per_step = sum(GB_STEP[m] for m in ens) + GB_DET * len(det)
    per_cycle = len(steps) * (per_step + (0 if a.no_analysis else 2 * GB_DET))   # + analyses (GFS and IFS step 0)
    disk = len(order) * len(steps) * len(names) * MB_STEP / 1000
    if a.dry_run:
        for c in order:
            print("%s  %s" % (cases.tag(c), ",".join(names)))
        print("%d cycles (hours %s), basins %s, steps %s, models %s%s; rough estimate %.1f GB streamed (ensemble "
              "model-step GB %s, %.3f per deterministic; per cycle, whatever the basins; ignores files "
              "already cached) and about %.1f GB kept on disk (%d MB per basin-step for all six models)"
              % (len(order), ",".join(map(str, hours)), ",".join(names), steps, ",".join(chosen),
                 ", no analyses" if a.no_analysis else "", per_cycle * len(order),
                 "/".join("%s %.2f" % (m, GB_STEP[m]) for m in ens) or "none", GB_DET,
                 disk * len(chosen) / 6, MB_STEP))
        return

    for c in order:
        bs = tuple(names)
        rep = store.fill(c, steps=steps, models=det, ens=ens, workers=a.workers, basins=bs, complete=a.complete)
        done = new = miss = 0
        for b in () if a.no_analysis else bs:
            for s in steps:
                valid = c + dt.timedelta(hours=s)
                if valid > now:                      # not yet happened: no analysis to take
                    miss += 1
                    continue
                if store.truth_exists("analysis", b, valid):   # cache, old shared folder or release
                    done += 1
                    continue
                got = store.analysis(b, valid)
                new += got is not None
                miss += got is None
        tail = "" if a.no_analysis else " | analyses new %d, cached %d, missing %d" % (new, done, miss)
        print("%s %s: fetched %d, existing %d, missing %d, ens skipped %d%s%s"
              % (rep["cycle"], ",".join(bs), len(rep["fetched"]), len(rep["existing"]), len(rep["missing"]),
                 len(rep["skipped_ens"]), (" (%s)" % ",".join(rep["skipped_ens"])) if rep["skipped_ens"] else "",
                 tail), flush=True)


if __name__ == "__main__":
    main()
