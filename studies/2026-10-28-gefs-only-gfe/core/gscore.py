#!/usr/bin/env python3
"""Tune choices and the one held-out score of the GEFS-only core lift (design card section 2).

  python3 gscore.py tune  [--workers 3]       thresholds on TUNE weeks -> results/tune_*.csv, FINAL_CHOICE.json
  python3 gscore.py final [--workers 3]       held-out weeks, once -> results/final_*.csv, FINAL_RUN.json
  python3 gscore.py verdict                   verdict.md from the final counts (win line applied mechanically)

Products on the base wind N (grids from gpredict.py; kt):
  N          rk.features.det_blend(models=("gfs","ifs"))
  lift       storm lift: N + 5 where the storm-core chance Ps >= t
  galecore   lift, then max(wind, 34) where the gale-core chance Pg >= t34
  live       live Core Lifted on the page blend (all ensembles; reference, does not decide)
  nomodel    N + 5 where the GEFS 48 kt share (neighbourhood max) >= x on the candidate cells (reference)
each for the 0.25 deg GEFS inputs (variant q) and the 0.5 deg inputs (variant h; decides).
Tune choices (pooled over both basins, 00/12 UTC valid, +24..+120):
  t  : the t (0.01 steps) whose storm area (seen cells with forecast >= 48 / ASCAT 48+ cells) is closest to live
       Core Lifted's on the same tune cells; x: the same rule for the nomodel reference;
  t34: as the gale-core study chose its t (score_gale.select): among 0.3..0.7 those where, in both basins, the
       gale-core product has gale area <= 1.3 and gale-tile CSI not below `lift`'s; the one with the highest
       gale-cell catch gain (the smaller of the basins' gains, ties by the mean).
Counts per case and product (tile hits at 34 / 48 on 5x5 deg tiles with >= 150 seen cells, forecast event among
the seen cells; seen cells with forecast / ASCAT at 34 and 48; ASCAT 34+ cells caught): rk.score.tile_hits,
score_gale.case_counts. Paired whole-week intervals: rk.compare.paired_counts.
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import gcommon as G
import common as C
import score_gale as SG
from rk import cases, compare, score, truth
from rk.basins import grid

TS_SWEEP = np.round(np.arange(0.05, 0.9501, 0.01), 2)
T34S = SG.TS
LIFT_KT = 5.0
STEPS_B = (30, 54, 78, 102, 126)
COUNTS = SG.COUNTS + ["nt48", "h48", "m48", "fa48", "fc48", "ob48"]
VARIANTS = ("q", "h")
RES = G.HERE / "results"


def _ratio(num, den):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


METRICS = dict(SG.METRICS)
METRICS.update({
    "pod48": lambda c: _ratio(c["h48"], c["h48"] + c["m48"]),
    "far48": lambda c: _ratio(c["fa48"], c["h48"] + c["fa48"]),
    "csi48": lambda c: _ratio(c["h48"], c["h48"] + c["m48"] + c["fa48"]),
    "area48": lambda c: _ratio(c["fc48"], c["ob48"]),
})


def load_grids(basin, cycle, step):
    p = G.grid_path(basin, cycle, step)
    if not p.exists():
        return None
    with np.load(p) as z:
        return {k: z[k] for k in z.files}


def lift_wind(n32, P, t):
    return np.where(np.asarray(P, np.float32) >= t, n32 + np.float32(LIFT_KT), n32).astype(np.float32)


def gale_wind(lift, Pg, t34):
    return np.where(np.asarray(Pg, np.float32) >= t34, np.maximum(lift, np.float32(34.0)), lift).astype(np.float32)


def case_counts(f, spd, seen, lats, lons):
    """Count dict of one forecast grid against ASCAT speeds at seen cells."""
    f = np.nan_to_num(np.asarray(f, np.float32), nan=-1.0)
    r = SG.case_counts(f, spd, seen, lats, lons)
    h, m, fa = score.tile_counts(tl := score.tile_hits(f, spd, seen, lats, lons, 48))
    r.update(nt48=len(tl), h48=h, m48=m, fa48=fa, fc48=int(((f >= 48) & seen).sum()),
             ob48=int(((np.nan_to_num(spd, nan=-1.0) >= 48) & seen).sum()))
    return r


def _truth(basin, cycle, step):
    return truth.ascat_target(basin, cycle + dt.timedelta(hours=step))


# ---- tune ----

def sweep_job(j):
    """Per-case storm-area sweeps: seen-cell counts at 48+ for lift@t (t in TS_SWEEP) and nomodel@x, per variant."""
    G.install()
    basin, cycle, step = j
    g = load_grids(basin, cycle, step)
    if g is None:
        return j, "missing_grids", None
    t = _truth(basin, cycle, step)
    if t is None:
        return j, "missing_ascat", None
    seen, spd = t["seen"], t["spd"]
    n32 = g["N"].astype(np.float32)
    row = {"basin": basin, "cycle": cases.tag(cycle), "step": step,
           "ob48": int(((np.nan_to_num(spd, nan=-1.0) >= 48) & seen).sum()),
           "fc48_N": int(((n32 >= 48) & seen).sum()),
           "fc48_live": int(((g["live"].astype(np.float32) >= 48) & seen).sum())}
    edge = (n32 < 48) & ((n32 + np.float32(LIFT_KT)) >= 48) & seen
    for v in VARIANTS:
        ps = g["Ps_" + v].astype(np.float32)[edge]
        row["lift_" + v] = (ps[:, None] >= TS_SWEEP[None, :]).sum(0)
        xs = g["p48nb_" + v].astype(np.float32)[edge & g["cand_" + v]]
        row["nm_" + v] = (xs[:, None] >= TS_SWEEP[None, :]).sum(0)
    return j, "done", row


def gale_job(j):
    """Per-case counts for N, lift@t, galecore@t34 (t34 in T34S) of both variants at the chosen t."""
    G.install()
    basin, cycle, step, choice = j
    g = load_grids(basin, cycle, step)
    if g is None:
        return j[:3], "missing_grids", []
    t = _truth(basin, cycle, step)
    if t is None:
        return j[:3], "missing_ascat", []
    seen, spd = t["seen"], t["spd"]
    lats, lons = grid(basin)
    n32 = g["N"].astype(np.float32)
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "split": cases.split(cycle)}
    rows = []
    for v in VARIANTS:
        lift = lift_wind(n32, g["Ps_" + v], choice[v]["t"])
        prods = {"N": n32, "lift": lift}
        for t34 in T34S:
            prods["galecore@%.1f" % t34] = gale_wind(lift, g["Pg_" + v], t34)
        for name, f in prods.items():
            rows.append(dict(key, variant=v, product=name, **case_counts(f, spd, seen, lats, lons)))
    return j[:3], "done", rows


def tune_cases():
    out = []
    for b in ("natl", "npac"):
        cyc = sorted(cases.cycles(b, *C.WINDOW, hour=0) + cases.cycles(b, *C.WINDOW, hour=12))
        out += [(b, c, s) for c in cyc if not cases.held_out(c) for s in C.STEPS]
    return out


def _run(fn, jobs, workers, label):
    tally, res = {}, []
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers) as pool:
        for i, out in enumerate(pool.imap_unordered(fn, jobs, chunksize=4), 1):
            tally[out[1]] = tally.get(out[1], 0) + 1
            res.append(out)
            if i % 200 == 0 or i == len(jobs):
                print("[%s %d/%d] %.0fs %s" % (label, i, len(jobs), time.time() - t0, tally), flush=True)
    return res, tally


def choose_sweep(rows):
    """Pooled (both basins) t and x per variant from the per-case sweeps -> (choice dict, audit DataFrame)."""
    df = pd.DataFrame(rows)
    audit, choice = [], {}
    for v in VARIANTS:
        ob = df["ob48"].sum()
        live = df["fc48_live"].sum() / ob
        lift = np.sum(np.stack(df["lift_" + v].to_numpy()), 0) / ob
        nm = np.sum(np.stack(df["nm_" + v].to_numpy()), 0) / ob
        base = df["fc48_N"].sum() / ob
        # forecast area = N's own cells + lifted cells: the sweep counts only the cells newly lifted to 48+
        lift, nm = lift + base, nm + base
        it = int(np.argmin(np.abs(lift - live) + 1e-9 * np.arange(len(lift))[::-1]))
        ix = int(np.argmin(np.abs(nm - live) + 1e-9 * np.arange(len(nm))[::-1]))
        choice[v] = {"t": float(TS_SWEEP[it]), "x": float(TS_SWEEP[ix]), "live_ratio": float(live),
                     "lift_ratio": float(lift[it]), "nm_ratio": float(nm[ix]), "N_ratio": float(base),
                     "n_cases": int(len(df))}
        for b in ("natl", "npac"):
            d = df[df.basin == b]
            obb = d["ob48"].sum()
            lb = np.sum(np.stack(d["lift_" + v].to_numpy()), 0)[it]
            nb = np.sum(np.stack(d["nm_" + v].to_numpy()), 0)[ix]
            audit.append({"variant": v, "basin": b, "n_cases": len(d), "ob48": int(obb),
                          "area_N": d["fc48_N"].sum() / obb, "area_live": d["fc48_live"].sum() / obb,
                          "area_lift": (d["fc48_N"].sum() + lb) / obb, "area_nomodel": (d["fc48_N"].sum() + nb) / obb,
                          "t": choice[v]["t"], "x": choice[v]["x"]})
    return choice, pd.DataFrame(audit)


def week_ids(df):
    c = df["cycle"]
    c = c if pd.api.types.is_datetime64_any_dtype(c) else pd.to_datetime(c.astype(str), format="%Y%m%d%H")
    iso = c.dt.isocalendar()
    return (iso.year.astype(int) * 100 + iso.week.astype(int)).to_numpy()


def summarize(cdf, baselines, n_boot, extra_pairs=()):
    """Per variant, basin, product: pooled metrics with whole-week intervals on the area / catch ratios, and the
    paired difference from each baseline named in `baselines` (dict product -> baseline product)."""
    d = cdf.copy()
    d["cycle"] = pd.to_datetime(d["cycle"].astype(str), format="%Y%m%d%H")
    rows = []
    for v in sorted(d.variant.unique()):
        for b in sorted(d.basin.unique()):
            g = d[(d.variant == v) & (d.basin == b)]
            for prod in g["product"].unique():
                gp = g[g["product"] == prod]
                tot = gp[COUNTS].sum()
                c = {k: np.array(float(x)) for k, x in tot.items()}
                r = {"variant": v, "basin": b, "product": prod, "n_cases": len(gp), "n_weeks": len(np.unique(week_ids(gp)))}
                r.update({k: int(x) for k, x in tot.items()})
                for k, fn in METRICS.items():
                    r[k] = float(fn(c))
                _, dr = compare.boot_sums(week_ids(gp), gp[COUNTS].to_numpy(float), n_boot=n_boot, seed=0)
                for k in ("area48", "area", "catch", "pod48", "gale_csi"):
                    z = METRICS[k]({cc: dr[:, i] for i, cc in enumerate(COUNTS)})
                    z = z[np.isfinite(z)]
                    r[k + "_lo"], r[k + "_hi"] = tuple(np.percentile(z, [2.5, 97.5])) if len(z) else (np.nan, np.nan)
                rows.append(r)
            for prod, base in list(baselines.items()) + list(extra_pairs):
                if not ((g["product"] == prod).any() and (g["product"] == base).any()):
                    continue
                for k, fn in METRICS.items():
                    p = compare.paired_counts(g, prod, base, fn, COUNTS, n_boot=n_boot, seed=0,
                                              method_col="product", case_cols=["basin", "step"])
                    for r in rows:
                        if r["variant"] == v and r["basin"] == b and r["product"] == prod:
                            r["d_%s_vs_%s" % (k, base)] = float(p["diff"][0])
                            r["d_%s_vs_%s_lo" % (k, base)] = float(p["lo"][0])
                            r["d_%s_vs_%s_hi" % (k, base)] = float(p["hi"][0])
    return pd.DataFrame(rows)


def select_t34(cdf, n_boot):
    """The gale-core study's rule on the tune counts (per variant): -> (table, {variant: t34 or None})."""
    d = cdf.copy()
    d["cycle"] = pd.to_datetime(d["cycle"].astype(str), format="%Y%m%d%H")
    rows, chosen = [], {}
    for v in VARIANTS:
        tab = []
        for t34 in T34S:
            name = "galecore@%.1f" % t34
            for b in ("natl", "npac"):
                g = d[(d.variant == v) & (d.basin == b)]
                tot = g[g["product"] == name][COUNTS].sum()
                c = {k: np.array(float(x)) for k, x in tot.items()}
                out = {"variant": v, "t34": t34, "basin": b, "area": float(METRICS["area"](c)),
                       "catch": float(METRICS["catch"](c))}
                for k in ("catch", "gale_csi"):
                    p = compare.paired_counts(g, name, "lift", METRICS[k], COUNTS, n_boot=n_boot, seed=0,
                                              method_col="product", case_cols=["basin", "step"])
                    out["d_" + k], out["d_%s_lo" % k], out["d_%s_hi" % k] = (float(p["diff"][0]), float(p["lo"][0]), float(p["hi"][0]))
                out["area_ok"] = out["area"] <= SG.AREA_CAP
                out["csi_ok"] = out["d_gale_csi"] >= 0
                tab.append(out)
        tab = pd.DataFrame(tab)
        best = None
        for t34, g in tab.groupby("t34"):
            if len(g) < 2 or not (g.area_ok.all() and g.csi_ok.all()):
                continue
            key = (g.d_catch.min(), g.d_catch.mean())
            if best is None or key > best[0]:
                best = (key, t34)
        chosen[v] = None if best is None else float(best[1])
        tab["chosen"] = tab.t34 == chosen[v] if chosen[v] is not None else False
        rows.append(tab)
    return pd.concat(rows, ignore_index=True), chosen


def cmd_tune(a):
    RES.mkdir(parents=True, exist_ok=True)
    jobs = tune_cases()
    res, tally = _run(sweep_job, jobs, a.workers, "sweep")
    rows = [r for _, st, r in res if st == "done"]
    if not rows:
        sys.exit("no tune case could be scored: %s" % tally)
    choice, audit = choose_sweep(rows)
    audit.to_csv(RES / "tune_storm_area.csv", index=False, float_format="%.4f")
    print(audit.round(3).to_string(index=False), flush=True)
    print("storm t / x:", json.dumps(choice), flush=True)
    jobs2 = [(b, c, s, choice) for b, c, s in jobs]
    res2, tally2 = _run(gale_job, jobs2, a.workers, "gale")
    rows2 = [r for _, st, rr in res2 if st == "done" for r in rr]
    cdf = pd.DataFrame(rows2).sort_values(["variant", "basin", "cycle", "step", "product"]).reset_index(drop=True)
    G.root().mkdir(parents=True, exist_ok=True)
    cdf.to_csv(G.root() / "tune_case_counts.csv", index=False)
    tab, chosen = select_t34(cdf, a.boot)
    tab.to_csv(RES / "tune_gale_selection.csv", index=False, float_format="%.4f")
    print(tab.round(3).to_string(index=False), flush=True)
    summ = summarize(cdf, {"lift": "N"}, a.boot, extra_pairs=[("galecore@%.1f" % t, "lift") for t in T34S])
    summ.to_csv(RES / "tune_summary.csv", index=False, float_format="%.4f")
    final = {v: {"t": choice[v]["t"], "x": choice[v]["x"], "t34": chosen[v]} for v in VARIANTS}
    final["decides"] = "h"
    final["note"] = ("tune choices: t and x pooled over both basins so the storm 48+ area / ASCAT equals live Core Lifted's "
                     "on the same tune cells; t34 by the gale-core study's rule (score_gale.select); "
                     "tune cases %d (sweep %s, gale %s)" % (len(jobs), tally, tally2))
    json.dump(final, open(G.HERE / "FINAL_CHOICE.json", "w"), indent=1)
    print("wrote FINAL_CHOICE.json:", json.dumps(final), flush=True)


# ---- held-out, once ----

def final_job(j):
    G.install()
    basin, cycle, step, choice = j
    g = load_grids(basin, cycle, step)
    if g is None:
        return j[:3], "missing_grids", []
    t = _truth(basin, cycle, step)
    if t is None:
        return j[:3], "missing_ascat", []
    seen, spd = t["seen"], t["spd"]
    lats, lons = grid(basin)
    n32 = g["N"].astype(np.float32)
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "valid_hr": (cycle + dt.timedelta(hours=step)).hour,
           "split": cases.split(cycle)}
    rows = []
    live = g["live"].astype(np.float32)
    for v in VARIANTS:
        ch = choice[v]
        lift = lift_wind(n32, g["Ps_" + v], ch["t"])
        prods = {"N": n32, "live": live, "lift": lift,
                 "nomodel": np.where(g["cand_" + v] & (g["p48nb_" + v].astype(np.float32) >= ch["x"]),
                                     n32 + np.float32(LIFT_KT), n32).astype(np.float32)}
        if ch["t34"] is not None:
            prods["galecore"] = gale_wind(lift, g["Pg_" + v], ch["t34"])
        for name, f in prods.items():
            rows.append(dict(key, variant=v, product=name, **case_counts(f, spd, seen, lats, lons)))
    return j[:3], "done", rows


def final_cases():
    out = []
    for b in ("natl", "npac"):
        cyc = sorted(cases.cycles(b, *C.WINDOW, hour=0) + cases.cycles(b, *C.WINDOW, hour=12))
        steps = C.STEPS + (STEPS_B if b == "npac" else ())
        out += [(b, c, s) for c in cyc if cases.held_out(c) for s in steps]
    return out


def cmd_final(a):
    ch = G.HERE / "FINAL_CHOICE.json"
    marker = G.HERE / "FINAL_RUN.json"
    if not ch.exists():
        sys.exit("refusing final: FINAL_CHOICE.json does not exist (written by `gscore.py tune`).")
    if marker.exists() or (RES / "final_case_counts.csv").exists():
        sys.exit("refusing final: the held-out score has been run already; it is used once.")
    choice = json.load(open(ch))
    jobs = [(b, c, s, choice) for b, c, s in final_cases()]
    res, tally = _run(final_job, jobs, a.workers, "final")
    missing = [(j[0], cases.tag(j[1]), j[2], st) for j, st, _ in res if st != "done"]
    rows = [r for _, st, rr in res if st == "done" for r in rr]
    if not rows:
        sys.exit("no held-out case could be scored: %s" % tally)
    cdf = pd.DataFrame(rows).sort_values(["variant", "basin", "cycle", "step", "product"]).reset_index(drop=True)
    RES.mkdir(parents=True, exist_ok=True)
    cdf.to_csv(RES / "final_case_counts.csv", index=False)
    pd.DataFrame(missing, columns=["basin", "cycle", "step", "status"]).to_csv(RES / "final_missing.csv", index=False)
    marker.write_text(json.dumps({"scored": dt.datetime.now(dt.timezone.utc).isoformat(), "choice": choice,
                                  "tally": tally}))
    print("SUMMARY: held-out %s; wrote %s" % (tally, RES / "final_case_counts.csv"), flush=True)
    cmd_verdict(a)


# ---- verdict ----

def f3(x, d=3):
    return "%.*f" % (d, x) if x is not None and np.isfinite(x) else "-"


def fd(r, k, base, d=3, pts=False):
    v, lo, hi = (r.get("d_%s_vs_%s%s" % (k, base, s), np.nan) for s in ("", "_lo", "_hi"))
    return "%+.*f [%+.*f, %+.*f]" % (d, v, d, lo, d, hi) if np.isfinite(v) else "-"


def cmd_verdict(a):
    choice = json.load(open(G.HERE / "FINAL_CHOICE.json"))
    cdf = pd.read_csv(RES / "final_case_counts.csv", dtype={"cycle": str})
    summ = summarize(cdf, {"lift": "N", "live": "N", "nomodel": "N", "galecore": "lift"}, a.boot,
                     extra_pairs=[("galecore", "N"), ("lift", "live")])
    summ.to_csv(RES / "final_summary.csv", index=False, float_format="%.4f")
    # secondary: 00/12 UTC valid only (what the tune weeks cover)
    s2 = summarize(cdf[cdf.valid_hr.isin([0, 12])], {"lift": "N", "galecore": "lift"}, a.boot)
    s2.to_csv(RES / "final_summary_0012only.csv", index=False, float_format="%.4f")
    ncase = cdf[cdf["product"] == "N"].groupby(["variant", "basin"]).size()
    L = ["# GEFS only: core lift on the deterministic GFE blend, verdict", "",
         "Held-out weeks, scored once. Base wind N = GFS + IFS deterministic blend (rk.features.det_blend). Storm lift = N + 5 kt where the "
         "GEFS-only storm-core chance >= t; gale-core = lift, then at least 34 kt where the gale-core chance >= t34. Truth ASCAT real 10 m "
         "wind (intercal); tiles 5x5 deg with >= 150 seen cells; area = forecast cells / ASCAT cells at seen cells. Pooled over all scored "
         "leads (Atlantic +24..+120 at 00/12 UTC valid; Pacific also +30..+126 at 06/18 UTC); brackets are whole-week 95% intervals. "
         "0.25 = GEFS inputs as stored; 0.5 = GEFS inputs subsampled to the 0.5 deg points and interpolated back (the 0.5 result decides).", ""]
    L += ["Choices made on tune weeks: " + "; ".join(
        "%s: t = %.2f, x = %.2f, t34 = %s" % ({"q": "0.25", "h": "0.5"}[v], choice[v]["t"], choice[v]["x"],
                                              "none qualified" if choice[v]["t34"] is None else "%.1f" % choice[v]["t34"])
        for v in VARIANTS), ""]
    L += ["Cases scored (basin, variant: cases): " + ", ".join("%s %s: %d" % (b, v, n) for (v, b), n in ncase.items()), ""]
    wl = {}
    for v in VARIANTS:
        label = {"q": "0.25 deg", "h": "0.5 deg"}[v]
        L += ["## %s GEFS inputs" % label, ""]
        L += ["| basin | product | storm catch | d catch vs N | storm FAR | storm area | gale CSI | d gale CSI vs N | gale cells caught | gale area |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for b in ("natl", "npac"):
            for prod, nm in (("N", "N (GFS+IFS blend)"), ("lift", "N + 5 at storm-core"), ("galecore", "+ gale-core to 34"),
                             ("live", "live Core Lifted (ref)"), ("nomodel", "no-model lift (ref)")):
                g = summ[(summ.variant == v) & (summ.basin == b) & (summ["product"] == prod)]
                if g.empty:
                    continue
                r = g.iloc[0].to_dict()
                L.append("| %s | %s | %s | %s | %s | %s [%s, %s] | %s | %s | %s | %s |" % (
                    b, nm, f3(r["pod48"]), fd(r, "pod48", "N"), f3(r["far48"]), f3(r["area48"], 2), f3(r["area48_lo"], 2),
                    f3(r["area48_hi"], 2), f3(r["gale_csi"]), fd(r, "gale_csi", "N"), f3(r["catch"]), f3(r["area"], 2)))
        L.append("")
        checks = []
        for b in ("natl", "npac"):
            r = summ[(summ.variant == v) & (summ.basin == b) & (summ["product"] == "lift")].iloc[0].to_dict()
            c1 = r["d_pod48_vs_N"] >= 0.05 and r["d_pod48_vs_N_lo"] > 0
            c2 = r["area48"] <= 1.5
            c3 = r["d_gale_csi_vs_N"] >= -0.01
            checks += [(b, "1 storm catch up >= 5 pts, interval above 0", "%s" % fd(r, "pod48", "N"), c1),
                       (b, "2 storm area <= 1.5", f3(r["area48"], 2), c2),
                       (b, "3 gale CSI not lower than N by > 0.01", fd(r, "gale_csi", "N"), c3)]
        gchecks = []
        for b in ("natl", "npac"):
            g = summ[(summ.variant == v) & (summ.basin == b) & (summ["product"] == "galecore")]
            if g.empty:
                gchecks += [(b, "gale-core exists", "no t34 qualified on tune", False)]
                continue
            r = g.iloc[0].to_dict()
            gchecks += [(b, "G1 gale cells caught up vs lift, interval above 0", fd(r, "catch", "lift"),
                         r["d_catch_vs_lift_lo"] > 0),
                        (b, "G2 gale area <= 1.3", f3(r["area"], 2), r["area"] <= 1.3)]
        wl[v] = (all(c[3] for c in checks), all(c[3] for c in gchecks), checks, gchecks)
        L += ["Win line, storm lift against N (%s):" % label, "", "| basin | rule | value | pass |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (b, rule, val, "yes" if ok else "NO") for b, rule, val, ok in checks]
        L += ["", "Gale-core piece (%s):" % label, "", "| basin | rule | value | pass |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (b, rule, val, "yes" if ok else "NO") for b, rule, val, ok in gchecks]
        L.append("")
    sp, gp, _, _ = wl["h"]
    L = L[:2] + ["**Verdict (0.5 deg decides): storm lift %s; gale-core piece %s.** At 0.25 deg: storm lift %s, gale-core %s." % (
        "PASSES" if sp else "FAILS", "PASSES" if gp else "FAILS", "passes" if wl["q"][0] else "fails",
        "passes" if wl["q"][1] else "fails"), ""] + L[2:]
    L += ["## Notes", "",
          "- Low-level features use the GFS fields only (low_models = gfs): IFS low-level files are missing for 5% of Atlantic and 17% of Pacific "
          "tune cycles (and 20% of Pacific held-out 00 UTC runs at 00/12 UTC valid), and one definition had to serve every case. "
          "A GFS-only mean is not the live feature.",
          "- The training tables sample every second row and column, which are exactly the 0.5 deg points, so the 0.5 deg model is trained on "
          "uninterpolated values (only the neighbourhood-max features differ from 0.25); scoring uses the interpolated grids at every cell.",
          "- 0.5 deg inputs: the stored GEFS shares, mean and SD are subsampled and interpolated back before the features (r10, boost, m90, "
          "the neighbourhood maxima) are built, so every GEFS-derived feature is 0.5 deg.",
          "- Tune cases with all references: 1944 of 2320 (live Core Lifted needs the AIFS and IFS low files, missing for 260; 116 more lack "
          "the lag runs of the GFS+IFS blend). t = 0.67 and x = 0.25 are pooled over both basins; the tune area ratio match is in tune_storm_area.csv.",
          "- Gale-core and lift are scored on the same cases as N. 00/12 UTC valid only: final_summary_0012only.csv.", ""]
    Path(G.HERE / "verdict.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:4]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["tune", "final", "verdict"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    {"tune": cmd_tune, "final": cmd_final, "verdict": cmd_verdict}[a.cmd](a)


if __name__ == "__main__":
    main()
