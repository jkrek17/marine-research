#!/usr/bin/env python3
"""Follow-up (Jason 16:48-16:50Z: "what solution draws the right amount of area and magnitude" / "how would we fix
it"): Best Wind draws 1.26 / 1.30x ASCAT's gale water (whole winter), because of the gale-core floor (raise to 34 kt
where the gale-core chance Pg >= 60%); without it the blend draws 0.85 / 0.81x. Variants of the floor on Best Wind:
  G_off          no floor
  G_p<p>         floor where Pg >= p% (60 = live, 70, 80, 90)
  G_m<m>         live floor only where the stronger of GFS/ECMWF >= m kt (28, 30, 32)
  G_r<p>         partial: raise toward 34 by clip((Pg - p) / (1 - p), 0, 1) of the gap, p = 0.6, 0.7
Rule (set before scoring, tune weeks): gale cell area (grid >= 34 over ASCAT >= 34, seen cells) closest to 1.0
averaged over both basins, subject to all-water and decision-cell MAE not above live Best Wind in either basin;
storm/HF are untouched by construction (the floor only acts below 34). Held-out scored once.
  python3 gale_floor.py --split tune|held_out   -> RK_DATA/extra/most-likely-wind/gale_<split>.csv.gz
  python3 gale_floor.py --report                -> gale_tune.csv, gale_heldout.csv, GALE.json
"""
import argparse
import gzip
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import score_cells as SC  # noqa: E402
from rk import score  # noqa: E402

VARS = ["G_off"] + ["G_p%d" % p for p in (60, 70, 80, 90)] + ["G_m%d" % m for m in (28, 30, 32)] + \
       ["G_r%d" % p for p in (60, 70)]


def variant(v, pre, d):
    Pg = d["Pg"]
    if v == "G_off":
        return pre
    kind, x = v[2], int(v[3:])
    if kind == "p":
        return np.where(Pg >= x / 100.0, np.maximum(pre, 34.0), pre)
    if kind == "m":
        strong = np.nan_to_num(np.fmax(d["gfs"], d["ifs"]), nan=-1)
        return np.where((Pg >= 0.6) & (strong >= x), np.maximum(pre, 34.0), pre)
    p = x / 100.0
    f = np.clip((Pg - p) / (1 - p), 0, 1)
    return np.where(pre < 34.0, pre + f * (34.0 - pre), pre)


def job(args):
    basin, cyc, step, path = args
    d = SC.load(path, basin)
    if d is None:
        return []
    seen = d["seen"] & d["ocean"] & np.isfinite(d["spd"])
    ob = np.where(seen, d["spd"], np.nan)
    blend = d["base05"] + d["boost"]
    strong = np.nan_to_num(np.fmax(d["gfs"], d["ifs"]), nan=-1.0)
    add = sum(SC.ramp(strong, kt, st) for kt, st in SC.RAMPS)
    add = add + np.where(d["p48nb"] >= SC.HF_P, SC.ramp(strong, *SC.HF), 0.0)
    pre = np.where(d["lift_on"], blend + add, blend)
    prods = {v: variant(v, pre, d).astype(np.float32) for v in VARS}
    hi = np.max(np.stack(list(prods.values())), 0)
    dec = seen & ((hi >= 30) | (np.nan_to_num(ob, nan=-1) >= 30))
    tiles = SC.F.Tiles(basin, seen)
    o34 = seen & (np.nan_to_num(ob, nan=-1) >= 34)
    rows = []
    for v, fc in prods.items():
        a = score.band_error(fc, ob, mask=seen, edges=())
        c = score.band_error(fc, ob, mask=dec, edges=())
        g = score.band_error(fc, ob, mask=seen, edges=(30.0, 34.0), by="fc")
        f = seen & (fc >= 34)
        nt, h, m, fa = tiles.counts(fc, ob, 34)
        rows.append(dict(basin=basin, cycle=cyc.isoformat(), step=step, week="%d-%02d" % cyc.isocalendar()[:2],
                         product=v, n_all=int(a["n"][0]), abs_all=a["sum_abs"][0], n_dec=int(c["n"][0]),
                         abs_dec=c["sum_abs"][0], n_g=int(g["n"][2]), err_g=g["sum_err"][2], abs_g=g["sum_abs"][2],
                         fc34=int(f.sum()), ob34=int(o34.sum()), cau34=int((f & o34).sum()), h34=h, m34=m, fa34=fa))
    return rows


def run(split):
    jobs = SC.cases_for("natl", split) + SC.cases_for("npac", split)
    with mp.get_context("spawn").Pool(4) as pool:
        rows = [r for rr in pool.imap_unordered(job, jobs, chunksize=8) for r in rr]
    with gzip.open(SC.OUT / ("gale_%s.csv.gz" % split), "wt") as fh:
        pd.DataFrame(rows).to_csv(fh, index=False)


def table(split):
    d = pd.read_csv(SC.OUT / ("gale_%s.csv.gz" % split))
    s = d.groupby(["basin", "product"]).sum(numeric_only=True)
    out = pd.DataFrame({"mae_all": s.abs_all / s.n_all, "mae_dec": s.abs_dec / s.n_dec,
                        "gale_area": s.fc34 / s.ob34, "gale_cell_catch": s.cau34 / s.ob34,
                        "gale_tile_catch": s.h34 / (s.h34 + s.m34), "false_gale_tiles": s.fa34,
                        "bias_grid34plus": s.err_g / s.n_g, "mae_grid34plus": s.abs_g / s.n_g})
    return out.reset_index()


def report():
    t = table("tune")
    t.round(3).to_csv(HERE / "gale_tune.csv", index=False)
    w = t.pivot_table(index="product", columns="basin", values=["mae_all", "mae_dec", "gale_area"])
    ref = w.loc["G_p60"]
    ok = w[(w["mae_all"] <= ref["mae_all"] + 1e-9).all(axis=1) & (w["mae_dec"] <= ref["mae_dec"] + 1e-9).all(axis=1)]
    dist = (ok["gale_area"] - 1).abs().mean(axis=1).sort_values()
    pick = dist.index[0]
    json.dump({"rule": __doc__.split("Rule")[1].split("Held-out")[0].strip(), "passing": list(dist.index),
               "pick": pick}, open(HERE / "GALE.json", "w"), indent=1)
    print("pick", pick)
    print(t.round(3).to_string())
    if (SC.OUT / "gale_held_out.csv.gz").exists():
        h = table("held_out")
        h.round(3).to_csv(HERE / "gale_heldout.csv", index=False)
        print(h.round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("tune", "held_out"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.split:
        run(a.split)
    if a.report:
        report()
