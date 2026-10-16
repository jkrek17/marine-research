#!/usr/bin/env python3
"""Fill the shared field cache (rk.store) and the analyses for a run of cycles.

  python3 tools/fill_store.py --start 20260101 --end 20260131 [--hours 0,12] [--basin both|natl|npac]
         [--every-days N] [--steps 24,48,...] [--workers 6] [--models noaa|ecmwf|gfs,ifs,...]
         [--no-analysis] [--dry-run]

Every cycle at --hours (default 0 and 12 UTC) is streamed once and BOTH basins are stored: the GRIB
messages are global and decoded once, so the second basin costs no extra streaming. The analyses (GFS and
IFS step 0 plus the mask) at every valid time are cached for both basins the same way. --basin only
chooses which basins are written (default both; there is rarely a reason to narrow it).
--models picks what is streamed: a comma list from gfs, ifs, aifs (deterministic) and gefs, ens, aifs-ens
(ensembles), default all six; the shorthands noaa (= gfs,gefs) and ecmwf (= ifs,aifs,ens,aifs-ens) expand in
place and can be mixed with names. --no-analysis skips the analyses (they need IFS, an ECMWF fetch), which
is what a NOAA-only fill wants. The dry-run estimate counts only the chosen models.
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
        rep = store.fill(c, steps=steps, models=det, ens=ens, workers=a.workers, basins=bs)
        done = new = miss = 0
        for b in () if a.no_analysis else bs:
            for s in steps:
                valid = c + dt.timedelta(hours=s)
                p = store._analysis_path(b, valid)
                had = p.exists()
                got = store.analysis(b, valid)
                done += got is not None and had
                new += got is not None and not had
                miss += got is None
        tail = "" if a.no_analysis else " | analyses new %d, cached %d, missing %d" % (new, done, miss)
        print("%s %s: fetched %d, existing %d, missing %d, ens skipped %d%s%s"
              % (rep["cycle"], ",".join(bs), len(rep["fetched"]), len(rep["existing"]), len(rep["missing"]),
                 len(rep["skipped_ens"]), (" (%s)" % ",".join(rep["skipped_ens"])) if rep["skipped_ens"] else "",
                 tail), flush=True)


if __name__ == "__main__":
    main()
