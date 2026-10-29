"""Cell table for the day 5-7 HF checks (design.md): one row per (basin, 12 UTC cycle, lead, ocean cell) with the
archive HF storms near the cell, plus for every member the lowest low within 500 km.

Event (T1): an archive HF fix within NBR_KM of the cell within +-WINDOW_H of the valid time. The storms behind it are
kept (`storms`, ';'-joined event ids) so the scorer can apply the ASCAT confirmation of confirm.py (T2).
Members: the stored member lows (mslpd57_*, the day 5-7 pressure study) at the valid time. For each cell and member
slot (GEFS 31, ENS 51, AIFS ENS 51 = 133) the lowest low within NBR_KM, coded uint8 hPa - 900 (0-253),
NO_LOW = 255 when the member has no low there, ABSENT = 254 when the member is not stored for the run.

Writes CACHE/extra/hf-d5-7-checks/cells.parquet and members.npy (row-aligned; the member array is ~100 MB, so it
stays in the local cache, not in RK_DATA). Each run's store files are dropped from the cache once read (a whole
period of cycles would fill the session disk, LESSONS).
Run: python3 build.py [FIRST LAST]   (cycle dates, default 20250301 20260531)
"""
import datetime as dt
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-16-pressure-d5-7"))
import store_io  # noqa: E402
from rk import basins, bomb, cases, paths, score, store, truth  # noqa: E402

LEADS = (120, 144, 168)
NBR_KM = 500.0
WINDOW_H = 12
ENS = (("gefs", "noaa", 31), ("ens", "ec", 51), ("aifsens", "ec", 51))
SLOTS = sum(n for _, _, n in ENS)
NO_LOW, ABSENT = 255, 254
OUT = paths.cache("extra", "hf-d5-7-checks", "cells.parquet")


def code(hpa):
    """hPa -> uint8 hPa - 900, clipped to 0-253."""
    return np.clip(np.round(np.asarray(hpa, float) - 900), 0, 253).astype(np.uint8)


def member_slots(fc, basin, step, clat, clon):
    """[cells, SLOTS] uint8 lowest member low within NBR_KM, or None when GEFS or ENS is missing."""
    out = np.full((clat.size, SLOTS), ABSENT, np.uint8)
    j = 0
    have = set()
    for ens, src, n in ENS:
        z = fc.get(src)
        key = "low_%s_%s_%d" % (ens, basin, step)
        if z and key in z:
            have.add(ens)
            a = z[key]
            out[:, j:j + n] = NO_LOW
            for m in range(n):
                lows = bomb.dedupe(a[a[:, 0] == m][:, 1:].astype(float))
                if len(lows) == 0:
                    continue
                d = score.km(clat[:, None], clon[:, None], lows[None, :, 0], lows[None, :, 1])
                p = np.where(d <= NBR_KM, lows[None, :, 2], np.inf).min(1)
                ok = np.isfinite(p)
                out[ok, j + m] = code(p[ok])
        j += n
    return out if {"gefs", "ens"} <= have else None


def near_storms(fixes, clat, clon):
    """';'-joined archive event ids of HF fixes within NBR_KM of each cell ('' for none)."""
    ids = [set() for _ in clat]
    for r in fixes.itertuples():
        for i in np.flatnonzero(score.km(clat, clon, r.lat, r.lon) <= NBR_KM):
            ids[i].add(str(r.event_id))
    return [";".join(sorted(s)) for s in ids]


def drop_cache(cycle):
    """Remove a run's unzipped store files from the cache unless something there is unpublished."""
    for b in basins.BASINS:
        d = paths.CACHE / "fields" / b / cycle
        if d.exists() and not (d / ".dirty").exists():
            shutil.rmtree(d, ignore_errors=True)


def one(ymd, cl, hf):
    c0 = dt.datetime.strptime(ymd, "%Y%m%d").replace(hour=12)
    fc = {s: store_io.get("fc", s, ymd) for s in ("noaa", "ec")}
    drop_cache(ymd + "12")
    if not fc["noaa"] or not fc["ec"]:
        return None
    rows, mems = [], []
    for basin, (clat, clon) in cl.items():
        a = hf[basin]
        for L in LEADS:
            v = c0 + dt.timedelta(hours=L)
            m = member_slots(fc, basin, L, clat, clon)
            if m is None:
                continue
            f = a[(a.valid >= v - dt.timedelta(hours=WINDOW_H)) & (a.valid <= v + dt.timedelta(hours=WINDOW_H))]
            df = pd.DataFrame({"cell": np.arange(clat.size), "lat": clat, "lon": clon,
                               "storms": near_storms(f, clat, clon)})
            df["basin"], df["cycle"], df["lead"], df["valid"] = basin, c0, L, v
            rows.append(df)
            mems.append(m)
    if not rows:
        return None
    return pd.concat(rows, ignore_index=True), np.concatenate(mems)


def main():
    a, b = (sys.argv[1:3] + ["20250301", "20260531"][len(sys.argv[1:3]):])
    cl = {bs: bomb.ocean_cells(bs, *basins.grid(bs)) for bs in basins.BASINS}
    hf = {}
    for bs in basins.BASINS:
        h = truth.hf_archive(bs)
        h = h[(h.category == "HF") & basins.inside(bs, h.lat.values, h.lon.values)]
        hf[bs] = h.reset_index(drop=True)          # valid stays datetime64: Series.dt.to_pydatetime() can misalign
    days = pd.date_range(a, b).strftime("%Y%m%d").tolist()
    parts, mems = [], []
    with ProcessPoolExecutor(6) as ex:
        for d, r in zip(days, ex.map(one, days, [cl] * len(days), [hf] * len(days))):
            if r is not None:
                parts.append(r[0])
                mems.append(r[1])
            print(d, "ok" if r is not None else "skip", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t["split"] = [cases.split(c) for c in t.cycle]
    t["valid_held"] = [cases.held_out(v) for v in t.valid]
    t["event"] = t.storms != ""
    t.to_parquet(OUT, index=False)
    np.save(OUT.with_name("members.npy"), np.concatenate(mems))
    g = t.groupby(["basin", "lead"])
    print(g.size().rename("cells").to_frame().join(g.event.mean().rename("event_rate")))
    print("cycles", t.cycle.nunique(), "held-out cycles", t[t.split == "held_out"].cycle.nunique(), "->", OUT)


if __name__ == "__main__":
    main()
