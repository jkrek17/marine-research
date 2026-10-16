"""Desk added value: score the desk's issued wind grids against their alternatives.

For each issuance I (10Z with the 00Z model cycle c, 22Z with the 12Z cycle), basin and valid time V
(00/06/12/18Z the desk grid has), every method is scored on the same water: the cells inside the OPC High Seas Forecast area (rk.basins.opc_mask) where the desk and the
previous shift's grid (I-12h) are both present and the analysis mask is open ice-free water.

Methods (kt, basin 0.25 grid): desk; prev12 and prev24 (desk grids of I-12h and I-24h at V); auto24 =
prev24 + (M_c(V) - M_{c-24}(V)), M the mean of the deterministic models present for both cycles (the 12 h version,
auto12, waits for 12-h-offset steps in the store); gfs, ifs, aifs; mean3; blend (page recipe, no member-support
weighting) = mean3 + min(k * spd_std, 5 kt), k = 0.15 at lead 24 else 0.25, spd_std the mean over the ensembles
present among gefs, ens, aifs-ens. A model that is missing is skipped, so a rerun after the ECMWF half of the
store fills adds those columns with no code change.

Outputs (RK data folder extra/desk-value/): scores.csv.gz, edits.csv.gz, built from per-issuance parts in parts/.
Resumable: an issuance whose part files exist is skipped.  Usage: score.py START END [--workers N] [--rebuild]
(dates YYYY-MM-DD, inclusive; only issuances whose desk grids are already cached are scored).
"""
import argparse
import datetime as dt
import gzip
import math
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import basins, cases, classes, desk, paths, score, store, truth  # noqa: E402

OUT = paths.data("extra", "desk-value", "x").parent
PARTS = OUT / "parts"
BASINS = ("natl", "npac")
DET = ("gfs", "ifs", "aifs")
ENS = ("gefs", "ens", "aifs-ens")
THR = (34, 48, 64)
CLASS_NAMES = ("all",) + tuple(classes.NAMES)
MIN_ASCAT = 500


def tag(t):
    return cases.tag(t)


def cached(issue):
    return all(desk._path(b, issue).exists() for b in BASINS)


@lru_cache(maxsize=64)
def _desk(issue):
    if not cached(issue):
        return None
    d = desk.load(issue)
    return d


@lru_cache(maxsize=512)
def _det(basin, c, model, step):
    r = store.load_det(basin, c, model, step)
    return None if r is None else r["speed"]


@lru_cache(maxsize=256)
def _ens_std(basin, c, ens, step):
    r = store.load_ens(basin, c, ens, step)
    return None if r is None else r["spd_std"].astype(np.float32)


def desk_at(issue, basin, valid):
    d = _desk(issue)
    if d is None or d.get(basin) is None:
        return None
    v = d[basin]["valid"]
    if valid not in v:
        return None
    return d[basin]["speed"][v.index(valid)].astype(np.float32)


def snap_ascat(basin, valid):
    """ASCAT cells snapped to the basin grid, floor(x/0.25 + 0.5); mean where several land in one box.
    Returns (spd with NaN where unseen) or None."""
    a = truth.ascat(basin, valid)
    if a is None or len(a["spd_kt"]) == 0:
        return None
    b = basins.BASINS[basin]
    lats, lons = basins.grid(basin)
    ny, nx = len(lats), len(lons)
    lon = np.mod(a["lon"], 360.0)
    iy = np.floor((b["north"] - a["lat"]) / 0.25 + 0.5).astype(int)
    ix = np.floor((lon - b["west"]) / 0.25 + 0.5).astype(int)
    ok = (iy >= 0) & (iy < ny) & (ix >= 0) & (ix < nx) & np.isfinite(a["spd_kt"])
    flat = iy[ok] * nx + ix[ok]
    s = np.bincount(flat, weights=a["spd_kt"][ok], minlength=ny * nx)
    n = np.bincount(flat, minlength=ny * nx)
    out = np.full(ny * nx, np.nan, np.float32)
    out[n > 0] = (s[n > 0] / n[n > 0]).astype(np.float32)
    return out.reshape(ny, nx)


def model_fields(basin, c, lead):
    """{method: kt grid} for the models present for cycle c at step lead (lead in hours)."""
    out = {}
    for m in DET:
        g = _det(basin, c, m, lead)
        if g is not None:
            out[m] = g
    if all(m in out for m in DET):
        out["mean3"] = np.mean([out[m] for m in DET], axis=0)
        sd = [s for s in (_ens_std(basin, c, e, lead) for e in ENS) if s is not None]
        if sd:
            k = 0.15 if lead == 24 else 0.25
            out["blend"] = out["mean3"] + np.minimum(k * np.mean(sd, axis=0), 5.0)
    return out


def auto24_field(basin, c, lead, prev24):
    """prev24 + (M_c(V) - M_{c-24}(V)); M over the deterministic models present for both cycles.
    (auto12 would use the cycle 12 h earlier; the store has no 12-h-offset steps yet.)"""
    if prev24 is None or lead + 24 not in cases.STEPS:
        return None
    c0 = c - dt.timedelta(hours=24)
    pairs = []
    for m in DET:
        a, b = _det(basin, c, m, lead), _det(basin, c0, m, lead + 24)
        if a is not None and b is not None:
            pairs.append((a, b))
    if not pairs:
        return None
    return prev24 + (np.mean([p[0] for p in pairs], axis=0) - np.mean([p[1] for p in pairs], axis=0))


def stats(fc, ob):
    """Counts on 1-D arrays: n, error at cells where either >= 25 kt, contingency at 34/48/64."""
    e = score.error(fc, ob, 25)
    r = dict(n=int(len(fc)), n25=e["n"],
             sum_abs=e["mae"] * e["n"] if e["n"] else 0.0, sum_err=e["bias"] * e["n"] if e["n"] else 0.0)
    for t in THR:
        h, fa, mi = score.contingency(fc, ob, t)
        r.update({f"hits{t}": h, f"fa{t}": fa, f"miss{t}": mi, f"fc_cells{t}": h + fa, f"ob_cells{t}": h + mi})
    return r


def score_issue(issue):
    """-> (scores rows, edits rows) for one issuance."""
    srows, erows = [], []
    wk = issue.isocalendar()
    base = dict(issue=issue.strftime("%Y-%m-%d %H:%M"), iso_week=f"{wk[0]}-W{wk[1]:02d}",
                held_out=bool(cases.held_out(issue)))
    c = dt.datetime(issue.year, issue.month, issue.day, 0 if issue.hour == 10 else 12)
    prev12, prev24 = issue - dt.timedelta(hours=12), issue - dt.timedelta(hours=24)
    for basin in BASINS:
        d = _desk(issue)
        if d is None or d.get(basin) is None:
            continue
        for V in d[basin]["valid"]:
            lead = int((V - c).total_seconds() // 3600)
            if lead <= 0:
                continue
            dk = desk_at(issue, basin, V)
            p12 = desk_at(prev12, basin, V) if cached(prev12) else None
            if dk is None or p12 is None:
                continue
            an = truth.analysis(basin, V)
            if an is None:
                continue
            p24 = desk_at(prev24, basin, V) if cached(prev24) else None
            grids = {"desk": dk, "prev12": p12}
            if p24 is not None:
                grids["prev24"] = p24
            grids.update(model_fields(basin, c, lead))
            a24 = auto24_field(basin, c, lead, p24)
            if a24 is not None:
                grids["auto24"] = a24
            cls_grid = None
            if all(m in grids for m in DET):
                cls_grid = classes.classes(np.stack([grids[m] for m in DET]))
            asc = snap_ascat(basin, V)
            common = (np.isfinite(dk) & np.isfinite(p12) & np.asarray(an["mask"], bool)
                      & basins.opc_mask(basin))  # the OPC High Seas Forecast area only
            key = dict(base, basin=basin, valid=V.strftime("%Y-%m-%d %H:%M"), lead=lead)
            ob_anl = an["mean_speed"].astype(np.float32)
            for cname in CLASS_NAMES:
                if cname == "all":
                    sel = common
                elif cls_grid is None:
                    continue
                else:
                    sel = common & (cls_grid == classes.NAMES.index(cname))
                if not sel.any():
                    continue
                meths = {m: g for m, g in grids.items() if np.isfinite(g[sel]).all()}
                if "desk" not in meths:
                    continue
                truths = [("anl", sel & np.isfinite(ob_anl), ob_anl)]
                asc_sel = None
                if asc is not None:
                    asc_sel = sel & np.isfinite(asc)
                    # the 500-cell rule is on the whole basin's matched cells, not the class's
                    if int((common & np.isfinite(asc)).sum()) >= MIN_ASCAT and asc_sel.any():
                        truths.append(("ascat", asc_sel, asc))
                for tname, tsel, ob in truths:
                    mm = {m: g for m, g in meths.items() if np.isfinite(g[tsel]).all()}
                    for m, g in mm.items():
                        srows.append(dict(key, **{"method": m, "class": cname, "truth": tname},
                                          **stats(g[tsel], ob[tsel])))
                # edits (desk vs previous grid), and at ASCAT cells whether they moved toward the observation
                diff = dk[sel] - p12[sel]
                er = dict(key, **{"class": cname}, cells=int(sel.sum()),
                          edited=int((np.abs(diff) > 2).sum()), sum_abs_edit=float(np.abs(diff).sum()),
                          raised=int((diff > 2).sum()), lowered=int((diff < -2).sum()),
                          n_ascat=0, edited_ascat=0, toward=0, away=0, toward_ed=0, away_ed=0,
                          n_ascat_a=0, toward_a=0, away_a=0)
                if asc_sel is not None and asc_sel.any() and int((common & np.isfinite(asc)).sum()) >= MIN_ASCAT:
                    ob_a = asc[asc_sel]
                    dd, pp = np.abs(dk[asc_sel] - ob_a), np.abs(p12[asc_sel] - ob_a)
                    ed = np.abs(dk[asc_sel] - p12[asc_sel]) > 2
                    tw, aw = dd < pp - 0.5, dd > pp + 0.5
                    er.update(n_ascat=int(len(ob_a)), edited_ascat=int(ed.sum()), toward=int(tw.sum()),
                              away=int(aw.sum()), toward_ed=int((tw & ed).sum()), away_ed=int((aw & ed).sum()))
                    if "auto24" in meths:
                        da = np.abs(a24[asc_sel] - ob_a)
                        er.update(n_ascat_a=int(len(ob_a)), toward_a=int((dd < da - 0.5).sum()),
                                  away_a=int((dd > da + 0.5).sum()))
                erows.append(er)
    return srows, erows


def part_paths(issue):
    t = tag(issue)
    return PARTS / f"{t}_scores.csv.gz", PARTS / f"{t}_edits.csv.gz"


def run_one(issue):
    t0 = time.time()
    sp, ep = part_paths(issue)
    for attempt in range(4):  # a dropped connection while a missing analysis is fetched should not end the run
        try:
            s, e = score_issue(issue)
            break
        except Exception as ex:  # noqa: BLE001
            print(f"{tag(issue)} attempt {attempt + 1} failed: {ex!r}", flush=True)
            if attempt == 3:
                return tag(issue), -1, -1, False, time.time() - t0
            time.sleep(10 * (attempt + 1))
    ecm = any(r["method"] in ("ifs", "aifs") for r in s)
    # (returned above without writing parts when all attempts failed, so a rerun retries it)
    for p, rows in ((sp, s), (ep, e)):
        tmp = p.with_name(p.name + ".tmp")
        pd.DataFrame(rows).to_csv(tmp, index=False, compression="gzip")
        os.replace(tmp, p)
    return tag(issue), len(s), len(e), ecm, time.time() - t0


def combine():
    for kind in ("scores", "edits"):
        fs = sorted(PARTS.glob(f"*_{kind}.csv.gz"))
        dfs = []
        for f in fs:
            try:
                dfs.append(pd.read_csv(f))
            except pd.errors.EmptyDataError:  # an issuance with no scorable rows
                pass
        df = pd.concat(dfs, ignore_index=True)
        tmp = OUT / f"{kind}.csv.gz.tmp"
        df.to_csv(tmp, index=False, compression="gzip")
        os.replace(tmp, OUT / f"{kind}.csv.gz")
        print(f"{kind}.csv.gz: {len(df)} rows from {len(fs)} issuances", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--rebuild", action="store_true", help="rescore issuances that already have parts")
    a = ap.parse_args()
    PARTS.mkdir(parents=True, exist_ok=True)
    d0, d1 = (dt.datetime.strptime(x, "%Y-%m-%d") for x in (a.start, a.end))
    issues = []
    d = d0
    while d <= d1:
        for h in desk.HOURS:
            i = d.replace(hour=h)
            if cached(i):
                issues.append(i)
        d += dt.timedelta(days=1)
    todo = [i for i in issues if a.rebuild or not all(p.exists() for p in part_paths(i))]
    print(f"{len(issues)} cached issuances in range, {len(todo)} to score", flush=True)
    t0 = time.time()
    if a.workers > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(a.workers) as pool:
            it = pool.imap_unordered(run_one, todo)
            for k, r in enumerate(it, 1):
                print(f"[{k}/{len(todo)}] {r[0]} scores={r[1]} edits={r[2]} ecmwf={r[3]} {r[4]:.0f}s", flush=True)
    else:
        for k, i in enumerate(todo, 1):
            r = run_one(i)
            print(f"[{k}/{len(todo)}] {r[0]} scores={r[1]} edits={r[2]} ecmwf={r[3]} {r[4]:.0f}s", flush=True)
    combine()
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
