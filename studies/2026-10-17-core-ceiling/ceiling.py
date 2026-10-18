#!/usr/bin/env python3
"""How much core wind does ASCAT still see above Core Lifted at the archive's HF lows?

The ceiling on what a sharper wind (downscaling) could win near hurricane-force lows.

  AWIPS_TOOLS=<awips-tools checkout> python3 ceiling.py [--workers 4] [--categories HF S] [--limit N]

Cases: hf-low archive fixes (rk.truth.hf_archive) inside the basin box, valid 00/06/12/18 UTC,
Nov 2025 - Mar 2026 (the months the store holds full fields), forecast from the 00/12 UTC cycle that is 24-29, 48-53 or 72-77 h earlier (one step per
lead day: f024/f030, f048/f054, f072/f078). The store had no low-level files at f030/f054/f078 in
this winter; they are filled into LOW_ROOT (tools/fill_low.py --root) and read from there when the store has none.
Truth: ASCAT real 10 m wind, intercalibrated, rain dropped (rk.truth.ascat_grid), snapped to the basin grid.
A case is scored when ASCAT saw at least MIN_SEEN grid cells within RADIUS_KM of the fix.
Per case, the peak over the SEEN cells within the radius for ASCAT and for each product:
  gfs, ifs, aifs   deterministic 10 m speed (rk.store.load_det)
  blend            r10, the page's blend (rk.features.core)
  corelift         r10 + 5 kt where the live core model's P >= 0.35 (awips-tools storm.core_grid)
Also the 5th-highest seen cell (ascat_k5, {product}_k5): a peak not set by one noisy cell.
Momentum test (added 2026-10-18): each model's 925 and 850 mb speed ({m}_s925, {m}_s850): its peak over
the seen cells, and how many of ASCAT's >= 48 / >= 64 kt cells have >= 48 / >= 64 kt aloft in the same cell
(_ge64_cell) or within ~50 km (_ge64_nb). If the momentum is aloft, mixing it down can make a 64 kt core.
Also the peak over ALL cells in the radius (seen or not) for each product.
Writes cases.csv (one row per fix and lead); summary.py turns it into the tables.
Each store cycle is evicted from the local cache after use (published files only; nothing is written).
"""
import argparse
import datetime as dt
import importlib
import json
import multiprocessing as mp
import os
import shutil
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from scipy import ndimage  # noqa: E402

from rk import KT, basins, paths, score, store, truth  # noqa: E402
from rk import features  # noqa: E402

RADIUS_KM = 500.0
NB_MOM = 5            # momentum test neighbourhood: 5 x 5 cells, about 50 km
MIN_SEEN = 200
START, END = dt.datetime(2025, 11, 1), dt.datetime(2026, 4, 1)   # full store fields: Nov 2025 - Mar 2026
LEADS = (24, 48, 72)
PRODUCTS = ("gfs", "ifs", "aifs", "blend", "corelift")
OUT = HERE / "cases.csv"
# Low-level (core-model) files the store lacked, filled with tools/fill_low.py --root (2026-10-18):
# f030/f054/f078 for all three models, and IFS/AIFS f024/f048/f072 for 2025-12-16 to 2026-01-19.
LOW_ROOT = paths.cache("extra", "core-ceiling-low")

_LIVE = {}


def live():
    if not _LIVE:
        root = os.environ.get("AWIPS_TOOLS") or str(HERE.parents[2] / "awips-tools")
        pipe = Path(root) / "marine_wind" / "pipeline"
        sys.path.insert(0, str(pipe))
        _LIVE["storm"] = importlib.import_module("storm")
        _LIVE["model"] = json.load(open(pipe / "core_model.json"))
        assert tuple(_LIVE["model"]["features"]) == features.FEATURES, "live feature order changed"
    return _LIVE["storm"], _LIVE["model"]


def fixes(categories):
    rows = []
    for b in ("natl", "npac"):
        df = truth.hf_archive(b)
        df = df[df.category.isin(categories)]
        df = df[(df.valid >= START) & (df.valid < END) & (df.valid.dt.hour % 6 == 0)]
        df = df[basins.inside(b, df.lat.to_numpy(), df.lon.to_numpy())]
        for r in df.itertuples():
            rows.append((b, r.event_id, r.valid.to_pydatetime(), float(r.lat), float(r.lon), float(r.hpa),
                         r.category))
    return rows


def jobs(categories, limit=None):
    """Group fix x lead by (basin, cycle) so each cycle is loaded once and then evicted."""
    by = {}
    for b, ev, valid, lat, lon, hpa, cat in fixes(categories):
        for lead in LEADS:
            cyc = valid - dt.timedelta(hours=lead)
            cyc = cyc.replace(hour=cyc.hour - cyc.hour % 12)
            step = int((valid - cyc).total_seconds() // 3600)
            by.setdefault((b, cyc), []).append(dict(basin=b, event_id=ev, valid=valid, lat=lat, lon=lon,
                                                     hpa=hpa, category=cat, lead=lead, step=step))
    out = sorted(kv for kv in by.items() if kv[0][1] >= START)   # cycles before START have no full fields
    return out[:limit] if limit else out


def kth(x, k):
    """k-th largest value (the peak with the k-1 strongest cells dropped; robust to one noisy ASCAT cell)."""
    x = np.sort(np.asarray(x, float)[np.isfinite(x)])
    return float(x[-k]) if len(x) >= k else float("nan")


def circle(basin, lat, lon):
    la, lo = basins.grid(basin)
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    return score.km(LA, LO, lat, lon) <= RADIUS_KM


def evict(basin, cycle):
    d = paths.cache("fields", basin, cycle.strftime("%Y%m%d%H"))
    if d.exists() and not (d / ".dirty").exists():
        shutil.rmtree(d, ignore_errors=True)


def run_cycle(item):
    (basin, cycle), cases_ = item
    rows = []
    try:
        storm, model = live()
        for step in sorted({c["step"] for c in cases_}):
            f = features.core(basin, cycle, step)
            if f is None and LOW_ROOT.exists():
                f = features.core(basin, cycle, step, low_root=LOW_ROOT)   # 06/18 UTC steps filled for this study
            det = {m: store.load_det(basin, cycle, m, step) for m in ("gfs", "ifs", "aifs")}
            if f is None or any(v is None for v in det.values()):
                for c in cases_:
                    if c["step"] == step:
                        rows.append(dict(c, cycle=cycle, status="no_forecast"))
                continue
            P = storm.core_grid(f, f["ocean"], model)
            grids = {m: det[m]["speed"] for m in det}
            grids["blend"] = f["r10"]
            grids["corelift"] = np.where(P >= storm.LIFT_P, f["r10"] + storm.LIFT_KT, f["r10"])
            aloft = {}                                  # momentum test: 925 / 850 mb speed (kt) per model
            for m in ("gfs", "ifs", "aifs"):
                lw = store.load_low(basin, cycle, m, step)
                if lw is None and LOW_ROOT.exists():
                    lw = store.load_low(basin, cycle, m, step, root=LOW_ROOT)
                if lw is not None:
                    for lev in ("925", "850"):
                        sp = np.hypot(lw["u" + lev], lw["v" + lev]) * KT
                        aloft[m + "_s" + lev] = (sp, ndimage.maximum_filter(sp, size=NB_MOM, mode="nearest"))
            for c in (c for c in cases_ if c["step"] == step):
                seen, spd = truth.ascat_grid(basin, c["valid"])
                row = dict(c, cycle=cycle)
                if seen is None:
                    rows.append(dict(row, status="no_ascat"))
                    continue
                circ = circle(basin, c["lat"], c["lon"])
                sc = seen & circ
                row["n_seen"] = int(sc.sum())
                if row["n_seen"] < MIN_SEEN:
                    rows.append(dict(row, status="few_seen"))
                    continue
                row["status"] = "ok"
                row["ascat_peak"] = float(spd[sc].max())
                row["ascat_k5"] = kth(spd[sc], 5)
                row["ascat_n48"] = int((spd[sc] >= 48).sum())
                row["ascat_n64"] = int((spd[sc] >= 64).sum())
                row["p_max_seen"] = float(P[sc].max())
                for k, g in grids.items():
                    row[k + "_peak"] = float(np.nanmax(g[sc]))
                    row[k + "_k5"] = kth(g[sc], 5)
                    row[k + "_peak_all"] = float(np.nanmax(g[circ]))
                    row[k + "_n48"] = int((g[sc] >= 48).sum())
                    row[k + "_n64"] = int((g[sc] >= 64).sum())
                for thr in (48, 64):
                    ob = sc & (spd >= thr)
                    for k, (sp, spn) in aloft.items():
                        row["%s_peak" % k] = float(np.nanmax(sp[sc]))
                        # share of ASCAT >= thr cells where the model carries >= thr aloft (same cell / within ~50 km)
                        row["%s_ge%d_cell" % (k, thr)] = int((sp[ob] >= thr).sum())
                        row["%s_ge%d_nb" % (k, thr)] = int((spn[ob] >= thr).sum())
                rows.append(row)
    except Exception:
        traceback.print_exc()
        rows += [dict(c, cycle=cycle, status="error") for c in cases_ if not any(
            r["event_id"] == c["event_id"] and r["valid"] == c["valid"] and r["lead"] == c["lead"] for r in rows)]
    finally:
        evict(basin, cycle)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--categories", nargs="+", default=["HF", "S"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    todo = jobs(a.categories, a.limit)
    done, frames = set(), []
    if OUT.exists():
        old = pd.read_csv(OUT)
        done = {(b, c) for b, c in zip(old.basin, old.cycle)}
        frames.append(old)
    todo = [j for j in todo if (j[0][0], str(j[0][1])) not in done]
    print("cycles to do: %d" % len(todo), flush=True)
    ctx = mp.get_context("spawn")
    n = 0
    with ctx.Pool(a.workers) as pool:
        for rows in pool.imap_unordered(run_cycle, todo):
            if rows:
                frames.append(pd.DataFrame(rows))
            n += 1
            if n % 20 == 0 or n == len(todo):
                # rewrite the whole table: rows of different status carry different columns
                tmp = OUT.with_suffix(".tmp")
                pd.concat(frames, ignore_index=True).to_csv(tmp, index=False)
                os.replace(tmp, OUT)
                print("%d/%d cycles" % (n, len(todo)), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
