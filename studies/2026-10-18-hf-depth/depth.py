#!/usr/bin/env python3
"""Depth and pressure drop of each model's low at the core-ceiling cases (design.md).

  python3 depth.py [--workers 6] [--limit N]     -> lows.csv (one row per case x model)
  python3 depth.py --summary                     -> summary.md

lows.csv: case keys, archive hpa, the wind gaps from core-ceiling cases.csv, and per model: fc_hpa (its low
nearest the fix within 300 km, or when none the lowest MSLP within 150 km of the fix), pos_km, matched, drop (500 km ring minus
centre), and the analysis' an_hpa, an_drop at 00/12 UTC valid times.
"""
import argparse
import datetime as dt
import multiprocessing as mp
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-17-core-ceiling"))
import ceiling as C  # noqa: E402  (evict)
from rk import compare, score, store, truth  # noqa: E402

MODELS = ("gfs", "ifs", "aifs")
MATCH_KM = 300.0
BELOW = 1020.0
OUT = HERE / "lows.csv"


def low_at(msl, basin, lat, lon):
    """(hpa, pos_km, matched, drop, low lat, low lon) of the field's low nearest the fix."""
    lows = score.find_lows(msl, basin, below=BELOW)
    m = score.match_lows(pd.DataFrame({"lat": [lat], "lon": [lon], "hpa": [np.nan]}), lows, MATCH_KM,
                         miss_depth="field", fc_msl=msl, basin=basin).iloc[0]
    la, lo = (m.fc_lat, m.fc_lon) if m.matched else (lat, lon)
    drop, centre, _ = score.pressure_drop(msl, basin, la, lo)
    hpa = m.fc_hpa if m.matched else centre
    return float(hpa), float(m.pos_err_km), bool(m.matched), float(drop)


def run_cycle(item):
    (basin, cycle), cases_ = item
    rows = []
    try:
        for step in sorted({c["step"] for c in cases_}):
            det = {m: store.load_det(basin, cycle, m, step) for m in MODELS}
            for c in (c for c in cases_ if c["step"] == step):
                r = dict(c, cycle=cycle)
                for m in MODELS:
                    if det[m] is None:
                        continue
                    h, pk, ok, dr = low_at(det[m]["msl"], basin, c["lat"], c["lon"])
                    r.update({m + "_hpa": h, m + "_pos_km": pk, m + "_matched": ok, m + "_drop": dr})
                if c["valid"].hour % 12 == 0:
                    an = truth.analysis(basin, c["valid"])
                    if an is not None:
                        h, pk, ok, dr = low_at(an["msl"], basin, c["lat"], c["lon"])
                        r.update(an_hpa=h, an_pos_km=pk, an_matched=ok, an_drop=dr)
                rows.append(r)
    except Exception:
        traceback.print_exc()
    finally:
        C.evict(basin, cycle)
    return rows


def cases():
    d = pd.read_csv(HERE.parent / "2026-10-17-core-ceiling" / "cases.csv", parse_dates=["valid", "cycle"])
    d = d[(d.status == "ok") & (d.category == "HF")].drop_duplicates(["basin", "event_id", "valid", "lead"])
    by = {}
    for r in d.itertuples():
        c = dict(basin=r.basin, event_id=r.event_id, valid=r.valid.to_pydatetime(), lat=r.lat, lon=r.lon,
                 hpa=r.hpa, lead=r.lead, step=r.step)
        by.setdefault((r.basin, r.cycle.to_pydatetime()), []).append(c)
    return sorted(by.items()), d


def extract(workers, limit):
    todo, _ = cases()
    todo = todo[:limit] if limit else todo
    print("cycles: %d" % len(todo), flush=True)
    rows = []
    with mp.get_context("spawn").Pool(workers) as pool:
        for n, r in enumerate(pool.imap_unordered(run_cycle, todo), 1):
            rows += r
            if n % 40 == 0 or n == len(todo):
                print("%d/%d" % (n, len(todo)), flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False, float_format="%.2f")


def fit(h, x, y, n_boot=2000):
    """gap = a + b x, least squares; (a, a_lo, a_hi, b, b_lo, b_hi) with whole-week intervals."""
    X, Y = h[x].to_numpy(float), h[y].to_numpy(float)
    st = np.column_stack([np.ones_like(X), X, Y, X * X, X * Y])
    tot, dr = compare.boot_sums(h.week.to_numpy(), st, n_boot=n_boot, seed=0)

    def ab(s):
        n, sx, sy, sxx, sxy = (s[..., i] for i in range(5))
        b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        return (sy - b * sx) / n, b
    a, b = ab(tot)
    A, B = ab(dr)
    return a, *np.percentile(A, [2.5, 97.5]), b, *np.percentile(B, [2.5, 97.5])


def summary():
    lows = pd.read_csv(OUT, parse_dates=["valid"])
    _, cc = cases()
    cc = cc[["basin", "event_id", "valid", "lead"] + ["ascat_peak"] + ["%s_peak" % m for m in MODELS]
            + ["%s_peak_all" % m for m in MODELS]]
    d = lows.merge(cc, on=["basin", "event_id", "valid", "lead"])
    iso = d.valid.dt.isocalendar()
    d["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    out = ["# Too shallow or too smooth? Results", "",
           "Cases: %d (fix x lead), %d fixes, %d storms, %d weeks, %d Atlantic." % (
               len(d), d.drop_duplicates(["basin", "event_id", "valid"]).shape[0],
               d.groupby(["basin", "event_id"]).ngroups, d.week.nunique(), (d.basin == "natl").sum()), ""]
    out += ["## Depth and wind gap by model and lead", "",
            "Depth error = model low minus archive (hPa, + = too shallow); drop ratio = model / analysis pressure drop "
            "(500 km ring minus centre, 00/12 UTC only); gap = ASCAT peak minus model peak over the same seen cells (kt).",
            "", "| Model | Lead | n | Matched | Depth err mean | median | vs analysis | Drop ratio | Gap seen | Gap all cells |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        d[m + "_derr"] = d[m + "_hpa"] - d.hpa
        d[m + "_derr_an"] = d[m + "_hpa"] - d.an_hpa
        d[m + "_dratio"] = d[m + "_drop"] / d.an_drop
        d[m + "_gap"] = d.ascat_peak - d[m + "_peak"]
        d[m + "_gap_all"] = d.ascat_peak - d[m + "_peak_all"]
        for lead in (24, 48, 72, "all"):
            h = d if lead == "all" else d[d.lead == lead]
            h = h[h[m + "_hpa"].notna()]
            out.append("| %s | %s | %d | %.0f%% | %+.1f | %+.1f | %+.1f | %.2f | %.1f | %.1f |" % (
                m, lead, len(h), 100 * h[m + "_matched"].mean(), h[m + "_derr"].mean(), h[m + "_derr"].median(),
                h[m + "_derr_an"].mean(), h[m + "_dratio"].median(), h[m + "_gap"].mean(), h[m + "_gap_all"].mean()))
    an = d.drop_duplicates(["basin", "event_id", "valid"])
    an = an[an.an_hpa.notna() & an.hpa.notna()]
    out += ["", "Analysis low minus archive: mean %+.1f hPa, median %+.1f (%d fixes at 00/12 UTC)." % (
        (an.an_hpa - an.hpa).mean(), (an.an_hpa - an.hpa).median(), len(an)), ""]
    out += ["## Decision fit: gap = a + b x depth error (pooled leads; whole-week 95%)", "",
            "| Model | Predictor | n | a (gap at zero error, kt) | b (kt per unit) | Mean gap | Gap where error within 3 hPa (n) |",
            "|---|---|---|---|---|---|---|"]
    for m in MODELS:
        for x, lab in ((m + "_derr", "depth vs archive"), (m + "_derr_an", "depth vs analysis")):
            h = d[d[x].notna() & d[m + "_gap"].notna()]
            a, alo, ahi, b, blo, bhi = fit(h, x, m + "_gap")
            near = h[h[x].abs() <= 3]
            out.append("| %s | %s | %d | %.1f [%.1f, %.1f] | %+.2f [%+.2f, %+.2f] | %.1f | %.1f (%d) |" % (
                m, lab, len(h), a, alo, ahi, b, blo, bhi, h[m + "_gap"].mean(), near[m + "_gap"].mean(), len(near)))
        h = d[d[m + "_dratio"].notna() & d[m + "_gap"].notna()].copy()
        h["x"] = h[m + "_dratio"] - 1
        a, alo, ahi, b, blo, bhi = fit(h, "x", m + "_gap")
        out.append("| %s | drop ratio - 1 | %d | %.1f [%.1f, %.1f] | %+.1f [%+.1f, %+.1f] | %.1f | |" % (
            m, len(h), a, alo, ahi, b, blo, bhi, h[m + "_gap"].mean()))
    (HERE / "summary.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    summary() if a.summary else extract(a.workers, a.limit)
