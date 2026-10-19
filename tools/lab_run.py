#!/usr/bin/env python3
"""The wxmap.pro lab job: the latest run's lows with how rare they are and their Storm Twins, and the day 5-7
bomb watch, as JSON for the lab page (jkrek17/wxmap.pro lab/).

  python3 tools/lab_run.py lows [--cycle YYYYMMDDHH] --out DIR   -> DIR/lows.json  (after each 00/12 UTC GFS)
  python3 tools/lab_run.py bomb [--cycle YYYYMMDD12] --out DIR   -> DIR/bomb.json  (after each 12 UTC ENS)

lows: GFS f012-f072 every 12 h, both basins (rk.basins). Lows are the bomb rule's grid minima (rk.bomb.find_lows)
at or below LOW_MAX hPa over open water. Each gets
  rarity  rk.climo.rarity: share of ERA5 pipeline A cyclones (a proxy, 1979-2025) within 1,000 km in its
          month whose lowest pressure stayed above it (studies/2026-10-19-storm-rarity);
  twins   rk.twins: the 30 nearest ERA5 library fixes to its GFS storm-centred pattern and how many reached
          hurricane force in the next 24 h (ERA5 gust class, a proxy), with the five closest storms
          (studies/2026-10-19-storm-twins: Brier skill +0.088 vs climatology from GFS f024, Oct-Apr; reads low
          above 30%). Left out (null) from May to September, outside the library's and the test's months.
bomb: 12 UTC GEFS + ENS (+ AIFS ENS when posted), +96..+168 h MSLP: the share of all members with a bomb
(1 Bergeron, latitude-adjusted, rk.bomb) ending within 500 km of each 2 deg ocean cell at +120/+144/+168 h,
calibrated per lead with the study's fit (studies/2026-10-19-bomb-d5-7/results/calibration.json). Cells at 10%
or more are written with a level: 1 low (10-20%), 2 medium (20-35%), 3 high (35% and up). Only day 5 passed
the study's rule, so the page shows days 6-7 as levels, not numbers (Jason's lab decision, "capped").

Files are written atomically. Downloads wait out the marine wind page build windows (rk.fetch).
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rk import basins, bomb, calibrate, climo, fetch, twins  # noqa: E402

UTC = dt.timezone.utc
LOW_STEPS = (12, 24, 36, 48, 60, 72)
LOW_MAX = 1000.0
TWIN_MONTHS = (10, 11, 12, 1, 2, 3, 4)
BOMB_LEADS = (120, 144, 168)
ENS = ("gefs", "ens", "aifs-ens")
CALIBRATION = ROOT / "studies" / "2026-10-19-bomb-d5-7" / "results" / "calibration.json"
LEVELS = ((0.10, 1), (0.20, 2), (0.35, 3))      # calibrated chance -> 1 low, 2 medium, 3 high
NAMES = {1: "low", 2: "medium", 3: "high"}


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False))
    os.replace(tmp, path)


def r1(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 1)


# ---------------------------------------------------------------- lows: rarity and Storm Twins

def basin_lows(msl_pa):
    """Global 0.25 deg MSLP (Pa, lat 90..-90) -> [(basin, lat, lon, hPa)] at or below LOW_MAX, centred over open
    water (rk.bomb.ocean_mask: land and sea-ice minima are left out)."""
    out = []
    for b in basins.BASINS:
        iy, ix = basins.crop(b)
        lats, lons = basins.grid(b)
        sea = bomb.ocean_mask(b)
        for la, lo, p in bomb.find_lows((msl_pa[iy][:, ix] / 100.0).astype(np.float32), lats, lons):
            if p <= LOW_MAX and sea[int(np.argmin(np.abs(lats - la))), int(np.argmin(np.abs(lons - lo)))]:
                out.append((b, float(la), float(lo), float(p)))
    return out


def twin_card(lib, pcs):
    t = twins.twins(lib, pcs, k=30)
    closest = [{"time": str(lib["time"][j]), "basin": str(lib["basin"][j]), "lat": r1(lib["lat"][j]),
                "lon": r1(lib["lon"][j]), "hpa": r1(lib["msl"][j]), "cls": int(lib["gcls"][j])} for j in t["closest"]]
    return {"n": t["n"], "hf": int(t["counts"][3]), "counts": t["counts"], "closest": closest}


def lows_for(cycle, step, assets, ref, g=None):
    """One forecast step -> list of low dicts (empty when the step is not posted)."""
    g = fetch.gfs_pattern(cycle, step) if g is None else g
    if g is None:
        return None
    valid = cycle + dt.timedelta(hours=step)
    found = basin_lows(g["msl"])
    pcs = None
    if found and valid.month in TWIN_MONTHS:
        lib, clim, frozen = assets
        X = twins.gfs_patches(g, np.array([(la, lo) for _, la, lo, _ in found]), valid, clim)
        pcs = frozen.pcs(X)
    out = []
    for i, (b, la, lo, p) in enumerate(found):
        r = climo.rarity(la, lo, valid.month, p, ref=ref)
        out.append({"valid": iso(valid), "fhr": step, "basin": b, "lat": la, "lon": lo, "hpa": r1(p),
                    "rarity": {"pct": r1(r["pct"]), "n": r["n"], "months": r["months"], "deepest": r1(r["deepest"])},
                    "twins": twin_card(assets[0], pcs[i]) if pcs is not None else None})
    return out


def latest_gfs(now=None):
    """Newest 00/12 UTC GFS cycle whose last lows step is posted."""
    now = now or dt.datetime.now(UTC).replace(tzinfo=None)
    c = now.replace(minute=0, second=0, microsecond=0, hour=0 if now.hour < 12 else 12)
    for _ in range(6):
        if fetch.nwp.ncep_index(fetch.gfs_url(c, LOW_STEPS[-1])) is not None:
            return c
        c -= dt.timedelta(hours=12)
    return None


def run_lows(cycle, out):
    ref = climo.era5_peaks()
    if ref is None:
        raise SystemExit("lab_run: ERA5 cyclone peaks could not be read")
    assets = twins.assets()
    lows = []
    for s in LOW_STEPS:
        got = lows_for(cycle, s, assets, ref)
        if got is None:
            raise SystemExit("lab_run: GFS %s f%03d not posted" % (cycle.strftime("%Y%m%d%H"), s))
        lows += got
        print("f%03d: %d lows" % (s, len(got)), flush=True)
    write_json(out / "lows.json", {
        "kind": "lows", "model": "GFS", "cycle": cycle.strftime("%Y%m%d%H"), "made": iso(dt.datetime.now(UTC)),
        "hours": list(LOW_STEPS), "low_max_hpa": LOW_MAX, "twin_months": list(TWIN_MONTHS),
        "classes": list(twins.CLASSES), "lows": lows})
    print("wrote", out / "lows.json", len(lows), "lows")


# ---------------------------------------------------------------- bomb watch, day 5-7

def level(p):
    lv = 0
    for lo, v in LEVELS:
        if p >= lo:
            lv = v
    return lv


def member_lows(fields, basin):
    """members() result for one basin -> [lows (k, 3)] per member."""
    lats, lons = basins.grid(basin)
    return [bomb.find_lows(m.astype(np.float32), lats, lons) for m in fields[basin]["msl"]]


def bomb_shares(ens_lows, clat, clon, lead):
    """{ens: {step: [lows per member]}} -> pooled member share (0-1) per cell for bombs ending at `lead`, members."""
    hits = []
    for e, by in ens_lows.items():
        prev, now = by.get(lead - 24), by.get(lead)
        if prev is None or now is None:
            continue
        if len(prev) != len(now):      # a member missing at one step: members no longer line up
            print("%s +%d h: %d members at t-24, %d at t; left out" % (e, lead, len(prev), len(now)), flush=True)
            continue
        for p, n in zip(prev, now):
            b = bomb.bombs(p, n)
            hits.append(bomb.near(b[b[:, 3] >= 1.0], clat, clon))
    return (np.mean(hits, axis=0) if hits else None), len(hits)


def latest_ens(now=None):
    """Newest 12 UTC run with GEFS and ENS posted at +168 h."""
    now = now or dt.datetime.now(UTC).replace(tzinfo=None)
    c = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if c > now:
        c -= dt.timedelta(days=1)
    src = fetch.sources
    for _ in range(3):
        ymd = c.strftime("%Y%m%d")
        ok_g = fetch.nwp.ncep_index(src.gefs(ymd, "12", 168, "p30")) is not None
        ok_e = fetch.nwp.ec_records(src.ecmwf("ifs", "enfo", "ef", ymd, "12", 168)) is not None
        if ok_g and ok_e:
            return c
        c -= dt.timedelta(days=1)
    return None


def run_bomb(cycle, out):
    cal = json.loads(CALIBRATION.read_text())
    steps = sorted({L - 24 for L in BOMB_LEADS} | set(BOMB_LEADS))
    cells = {}
    for b in basins.BASINS:
        lats, lons = basins.grid(b)
        cells[b] = bomb.ocean_cells(b, lats, lons)
    lows = {b: {} for b in basins.BASINS}
    used = []
    for e in ENS:
        by = {}
        for s in steps:
            f = fetch.members(e, cycle, s, wind=False)
            if f is None:
                break
            by[s] = f
        if len(by) < len(steps):
            if e in ("gefs", "ens"):
                raise SystemExit("lab_run: %s %s +%d h not posted" % (e, cycle.strftime("%Y%m%d%H"), s))
            print("%s not complete; left out (optional, as in the study)" % e, flush=True)
            continue
        used.append(e)
        for b in basins.BASINS:
            lows[b][e] = {s: member_lows(f, b) for s, f in by.items()}
        print(e, "members", len(by[steps[0]][next(iter(basins.BASINS))]["msl"]), flush=True)
    leads = []
    for L in BOMB_LEADS:
        raw_k, cal_k = cal["knots"][str(L)]
        rows, members = [], 0
        for b in basins.BASINS:
            clat, clon = cells[b]
            p, members = bomb_shares(lows[b], clat, clon, L)
            if p is None:
                continue
            pc = calibrate.apply(p, raw_k, cal_k)
            for la, lo, q in zip(clat, clon, pc):
                lv = level(q)
                if lv:
                    rows.append([b, float(la), float(lo), round(float(100 * q)), lv])
        leads.append({"lead": L, "day": L // 24, "valid": iso(cycle + dt.timedelta(hours=L)), "members": members,
                      "numbers": L == 120, "cells": rows})
        print("+%d h: %d cells at 10%% or more" % (L, len(rows)), flush=True)
    write_json(out / "bomb.json", {
        "kind": "bomb", "cycle": cycle.strftime("%Y%m%d%H"), "made": iso(dt.datetime.now(UTC)), "ensembles": used,
        "cell_deg": bomb.CELL, "radius_km": bomb.NBR_KM,
        "levels": [{"level": v, "name": NAMES[v], "from_pct": round(100 * lo)} for lo, v in LEVELS],
        "fields": ["basin", "lat", "lon", "pct", "level"], "leads": leads})
    print("wrote", out / "bomb.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("lows", "bomb"))
    ap.add_argument("--cycle", help="YYYYMMDDHH (default: the newest posted)")
    ap.add_argument("--out", required=True, help="folder the page reads (lows.json, bomb.json)")
    a = ap.parse_args(argv)
    cycle = dt.datetime.strptime(a.cycle, "%Y%m%d%H") if a.cycle else (latest_gfs() if a.what == "lows" else latest_ens())
    if cycle is None:
        raise SystemExit("lab_run: no recent run posted")
    print("lab_run", a.what, cycle.strftime("%Y%m%d%H"), flush=True)
    (run_lows if a.what == "lows" else run_bomb)(cycle, Path(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
