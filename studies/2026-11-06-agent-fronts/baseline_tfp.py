"""Rule-based baseline: thermal front parameter fronts (rk.frontfind) on the deck's 850 hPa theta-e, scored by the drill.

Tuned by grid search on the tune cases only (never the 50 test cases); then the chosen settings are scored once on the test cases.
  python3 baseline_tfp.py tune [--n 160]     -> tfp_tune.csv, tfp_params.json
  python3 baseline_tfp.py test               -> tfp_test.csv (and tfp_test_drawn.json)
"""
import argparse
import csv
import itertools
import json
import random

import numpy as np

import common
import deck
from rk import diag, frontfind

HERE = common.HERE


def draw_case(case, man, P):
    F = deck.fields(case, man)
    fr = frontfind.find_fronts(F["te850"], F["u10"], F["v10"], F["lat"], F["lon"], sigma=P["sigma"], grad_min=P["grad_min"],
                               min_len_nm=P["min_len_nm"], shift_cells=P["shift_cells"], stat_ms=P["stat_ms"])
    lap700 = None
    low = case["low"]
    out = []
    for f in fr:
        if f["type"] == "stationary":           # given to the trainee, never scored
            continue
        d = np.array([deck._nm(a, b, low["lat"], low["lon"]) for a, b in zip(f["lat"], f["lon"])])
        if d.min() > P["keep_nm"]:               # not this system
            continue
        typ = f["type"]
        if P["occ_nm"] and d.min() <= P["occ_nm"]:
            if lap700 is None:
                t7 = diag.smooth(F["te700"], 2.0)
                lap700 = (diag.ddx(diag.ddx(t7, F["lat"], F["lon"]), F["lat"], F["lon"]) + diag.ddy(diag.ddy(t7, F["lat"]), F["lat"])) * 1e10
                I = frontfind._interp(lap700, F["lat"], F["lon"])
            if np.nanmean(I(f["lat"], f["lon"])) < -P["occ_lap"]:   # on the 700 hPa warm tongue near the low
                typ = "occluded"
        out.append({"type": typ, "pts": common.taps(f["lat"], f["lon"])})
    return out


GRID = {"sigma": [1.0, 2.0], "grad_min": [3.0, 4.5, 6.0], "min_len_nm": [250, 400], "shift_cells": [0, 1.0],
        "stat_ms": [1.0], "keep_nm": [500, 900], "occ_nm": [0, 500], "occ_lap": [0.5]}
# round 2: round 1 (tfp_tune_round1.csv) peaked at its edge (grad_min 3, sigma 1, shift 1, keep 500, no occlusion)
GRID2 = {"sigma": [0.5, 1.0], "grad_min": [2.0, 2.5, 3.0], "min_len_nm": [150, 250], "shift_cells": [1.0, 1.5],
         "stat_ms": [1.0], "keep_nm": [500], "occ_nm": [0], "occ_lap": [0.5]}


def run(ids, P, man):
    by = {c["id"]: c for c in man["cases"]}
    drawn = {i: draw_case(by[i], man, P) for i in ids}
    return drawn, common.score(drawn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["tune", "test"])
    ap.add_argument("--n", type=int, default=160)
    ap.add_argument("--round", type=int, default=1)
    a = ap.parse_args()
    man = deck.manifest()
    if a.mode == "tune":
        ids = sorted(random.Random(deck.SEED).sample(deck.tune_ids(), a.n))
        rows = []
        G = GRID2 if a.round == 2 else GRID
        keys = list(G)
        for vals in itertools.product(*G.values()):
            P = dict(zip(keys, vals))
            _, sc = run(ids, P, man)
            m = float(np.mean([sc[i]["pct"] for i in ids]))
            rows.append({**P, "mean_pct": round(m, 2)})
            print(P, round(m, 1), flush=True)
        rows.sort(key=lambda r: -r["mean_pct"])
        with open(HERE / "tfp_tune.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        best = {k: rows[0][k] for k in keys}
        (HERE / "tfp_params.json").write_text(json.dumps({"params": best, "tune_cases": len(ids), "tune_mean_pct": rows[0]["mean_pct"]}, indent=1))
        print("best", rows[0])
    else:
        P = json.loads((HERE / "tfp_params.json").read_text())["params"]
        ids = deck.test_ids()
        drawn, sc = run(ids, P, man)
        (HERE / "tfp_test_drawn.json").write_text(json.dumps(drawn))
        with open(HERE / "tfp_test.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "basin", "pct", "n_truth", "n_matched", "n_type_right", "extras"])
            for i in ids:
                r = sc[i]
                w.writerow([i, by_basin(man, i), round(r["pct"], 1), len(r["rows"]), sum(x["matched"] for x in r["rows"]),
                            sum(x["matched"] and x["drawnType"] == x["type"] for x in r["rows"]), r["extras"]])
        print("TFP test mean", round(float(np.mean([sc[i]["pct"] for i in ids])), 1))


def by_basin(man, i):
    return next(c["basin"] for c in man["cases"] if c["id"] == i)


if __name__ == "__main__":
    main()
