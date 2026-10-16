"""Fill the SMAP and ASCAT daily caches for winter 2025-26 (1 Nov 2025 - 31 Mar 2026), 4 downloads at a time.
Run: nohup python3 fill.py > /dev/null 2>&1 &   Log: rk.paths.data("logs", "storm_truth_fill.log").
No model or ECMWF downloads; only data.remss.com."""
import datetime as dt
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rk import fetch, paths, truth  # noqa: E402

START, END, WORKERS = dt.date(2025, 11, 1), dt.date(2026, 3, 31), 4
LOG = paths.data("logs", "storm_truth_fill.log")


def say(msg):
    with open(LOG, "a") as f:
        f.write("%s %s\n" % (dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), msg))


def one(job):
    kind, day = job
    fn = truth.smap_day if kind == "smap" else truth.ascat_day
    p = paths.data("truth", kind, day.strftime("%Y%m%d") + ".npz")
    had = p.exists()
    try:
        c = fn(day)
    except Exception as e:  # keep going; the day is reported missing
        say("%s %s ERROR %r" % (kind, day, e))
        return kind, day, "error", 0
    if c is None:
        say("%s %s not posted" % (kind, day))
        return kind, day, "missing", 0
    size = p.stat().st_size if p.exists() else 0
    say("%s %s %s %d cells %.2f MB" % (kind, day, "cached" if had else "filled", len(c["lat"]), size / 1e6))
    return kind, day, "cached" if had else "filled", 0 if had else size


def main():
    fetch.wait_for_quiet()
    days = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    jobs = [(k, d) for d in days for k in ("smap", "ascat")]
    say("start %d jobs, %d workers" % (len(jobs), WORKERS))
    res = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for r in ex.map(one, jobs):
            res.append(r)
    for k in ("smap", "ascat"):
        rs = [r for r in res if r[0] == k]
        miss = [str(r[1]) for r in rs if r[2] in ("missing", "error")]
        say("SUMMARY %s: %d days, filled %d, already cached %d, missing %d %s, written %.1f MB" % (
            k, len(rs), sum(r[2] == "filled" for r in rs), sum(r[2] == "cached" for r in rs), len(miss), miss,
            sum(r[3] for r in rs) / 1e6))
    say("done")


if __name__ == "__main__":
    main()
