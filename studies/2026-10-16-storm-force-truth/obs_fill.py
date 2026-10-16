"""Build the GDAS marine obs cache (truth/obs) for winter 2025-26: Atlantic 12 UTC and Pacific 00 UTC cycles.
Run: nohup python3 obs_fill.py > /dev/null 2>&1 &   Log: rk.paths.data("logs", "storm_truth_obs.log")."""
import datetime as dt
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import basins, fetch, paths, truth  # noqa: E402

START, END, WORKERS = dt.date(2025, 11, 1), dt.date(2026, 3, 31), 4
LOG = paths.data("logs", "storm_truth_obs.log")


def say(msg):
    with open(LOG, "a") as f:
        f.write("%s %s\n" % (dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), msg))


def one(job):
    b, v = job
    t = time.time()
    try:
        o = truth.obs(b, v, platforms=("buoy", "drifter", "ship", "fixed"), max_dt=0.5)
    except Exception as e:
        say("%s %s ERROR %r" % (b, v, e))
        return 0
    say("%s %s %s %.1fs" % (b, v, "missing" if o is None else "%d obs" % len(o["lat"]), time.time() - t))
    return 1


def main():
    fetch.wait_for_quiet()
    days = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    jobs = [(b, dt.datetime.combine(d, dt.time(basins.BASINS[b]["hour"]))) for d in days for b in basins.BASINS]
    say("start %d cycles, %d workers" % (len(jobs), WORKERS))
    with ThreadPoolExecutor(WORKERS) as ex:
        n = sum(ex.map(one, jobs))
    say("done %d/%d" % (n, len(jobs)))


if __name__ == "__main__":
    main()
