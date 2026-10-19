"""Pull the +96 h MSLP (GFS, IFS, AIFS and every GEFS / ENS / AIFS ENS member) for the 12Z runs the day 5-7
pressure study already holds at +120/+144/+168, so a low's deepening over the 24 h ending at +120 h can be
scored. Reuses that study's downloader (byte ranges, waits out the marine wind build windows) with tag 'fc96':
files CACHE/fc96_{noaa|ec}_YYYYMMDD.npz in the same local cache, then into the store as mslpd57_96_{src}
(`../2026-10-16-pressure-d5-7/store_io.py put`).

Run: python3 fetch96.py noaa|ec [FIRST LAST]   (default 20250301 20261008, winter first)
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026-10-16-pressure-d5-7"))
import download as D   # noqa: E402

if __name__ == "__main__":
    src = sys.argv[1]
    a, b = (sys.argv[2:4] + ["20250301", "20261008"][len(sys.argv[2:4]):])
    os.makedirs(D.CACHE, exist_ok=True)
    order = sorted(D.days(a, b), key=lambda d: (0 if d[4:6] in ("11", "12", "01", "02", "03") else 1, d))
    with ThreadPoolExecutor(16) as pool:
        def one(c):
            D.wait_clear()
            t = time.time()
            try:
                return c, D.cycle(c, pool, src, steps=(96,), det_steps=(96,), tag="fc96"), time.time() - t
            except Exception as ex:
                return c, repr(ex), time.time() - t
        par = int(os.environ.get("PAR", "3" if src == "ec" else "1"))
        with ThreadPoolExecutor(par) as outer:
            for c, r, s in outer.map(one, order):
                print("fc96", c, r, "%.0fs" % s, flush=True)
