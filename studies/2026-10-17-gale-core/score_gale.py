#!/usr/bin/env python3
"""Score the gale-core products against ASCAT 34 kt, from the grids predict.py wrote (--thr 34 --cand gale).

  python3 score_gale.py --set live28+basin --root DIR --results DIR [--curves FILE] [--workers 2] [--boot 1000]
  python3 score_gale.py --summary-only --results DIR          (recompute summary and selection from case_scores.csv)
  python3 score_gale.py --final [--choice-dir DIR]             (held-out weeks, once; see below)

Products per case (forecast speed on the basin grid, kt; r10 = the live blend):
  baseline        Core Lifted today: r10 + 5 where the live storm-core chance P >= 0.35
  galecore@t      max(baseline, 34) where the gale-core chance >= t, t in 0.3 .. 0.7 (model '<set>@34', zero off
                  the gale candidate cells: ocean & (r10 >= 24 | a model >= 30))
  ref@t           max(baseline, 34) where the CALIBRATED member gale chance >= t on ocean cells: the pooled
                  GEFS+ENS share p34 (cell), remapped by the Chance calibration thread's winter / ASCAT curves
                  (rk.calib) - the no-model reference
  refnb@t         the same with the neighbourhood-maximum share p34_nb (information only; not in the win line)
Truth: rk.truth.ascat_target(basin, valid, thr=34): ASCAT real 10 m wind, intercalibrated; `seen` = cells ASCAT
landed in. Counts per case and product (case_scores.csv; counts, not ratios):
  ob34    seen cells with ASCAT >= 34            caught  of those, cells where the forecast is >= 34
  fc34    seen cells with forecast >= 34         (area ratio = fc34 / ob34)
  nt34, h34, m34, fa34   gale tiles (5x5 deg, >= 150 seen cells; rk.score.tile_hits at 34 kt)
  split   rk.cases.split of the cycle date
summary.csv: per basin and step (and "all" = pooled over leads) and product: gale-cell catch = caught / ob34,
area ratio, gale-tile POD / FAR / CSI with whole-week 95% intervals (catch, area, CSI), and for every product the
difference from the baseline (catch, area, CSI; rk.compare.paired_counts, the same resampled weeks).
selection.csv / tune_summary.md: the design's win line applied mechanically to the TUNE weeks, step "all":
a threshold t QUALIFIES when, in both basins, galecore@t has forecast 34+ area / ASCAT 34+ area <= 1.3 and
gale-tile CSI not below the baseline's (point values); the chosen t is the qualifying one with the highest
catch gain (smaller of the two basins' gains; ties by the mean), and line 1 is met only if the catch gain's
interval is above zero in both basins. galecore@t is then compared with ref@t on catch (paired, same weeks).

Default: TUNE weeks, out-of-fold P (what predict.py wrote without --final). --final scores the HELD-OUT weeks and
is a one-time gate: it needs FINAL_CHOICE.json in the study folder ({"t": 0.5, "set": "live28+basin"}, written
after the tune results are in), scores only the baseline, galecore@t and ref@t of the chosen t with the final
model, and refuses to run if FINAL_CHOICE.json is missing, if the final result files exist, or if the marker
FINAL_RUN.json is already in the study folder. (--choice-dir exists so the tests can point at a scratch
folder; it is not a way round the gate.)
"""
import argparse
import datetime as dt
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
from rk import calib, cases, compare, score, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

THR = 34
LIFT_KT, LIFT_P = 5.0, 0.35
TS = (0.3, 0.4, 0.5, 0.6, 0.7)
AREA_CAP = 1.3
BASELINE = "baseline"
COUNTS = ["ob34", "caught", "fc34", "nt34", "h34", "m34", "fa34"]


def _ratio(num, den):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


METRICS = {
    "catch": lambda c: _ratio(c["caught"], c["ob34"]),
    "area": lambda c: _ratio(c["fc34"], c["ob34"]),
    "gale_csi": lambda c: _ratio(c["h34"], c["h34"] + c["m34"] + c["fa34"]),
    "gale_pod": lambda c: _ratio(c["h34"], c["h34"] + c["m34"]),
    "gale_far": lambda c: _ratio(c["fa34"], c["h34"] + c["fa34"]),
}


def gname(t):
    return "galecore@%.1f" % t


def rname(t):
    return "ref@%.1f" % t


def rnbname(t):
    return "refnb@%.1f" % t


def product_names(ts=TS):
    return [BASELINE] + [gname(t) for t in ts] + [rname(t) for t in ts] + [rnbname(t) for t in ts]


def products(r10, p_live, p_gale, p34_cal, p34nb_cal, ocean, ts=TS):
    """{name: forecast speed grid (kt)}. P grids are zero off their candidate cells; the reference chances are
    calibrated member shares (0..1), used on ocean cells only."""
    r10 = np.asarray(r10, np.float32)
    base = np.where(np.asarray(p_live, np.float64) >= LIFT_P, r10 + LIFT_KT, r10).astype(np.float32)
    lift = np.maximum(base, np.float32(THR))
    pg = np.asarray(p_gale, np.float64)
    out = {BASELINE: base}
    for t in ts:
        out[gname(t)] = np.where(pg >= t, lift, base)
    for t in ts:
        out[rname(t)] = np.where(ocean & (np.asarray(p34_cal, np.float64) >= t), lift, base)
    for t in ts:
        out[rnbname(t)] = np.where(ocean & (np.asarray(p34nb_cal, np.float64) >= t), lift, base)
    return out


def case_counts(f, spd, seen, lats, lons):
    """Count dict of one forecast grid against ASCAT speeds at seen cells."""
    f = np.nan_to_num(np.asarray(f, float), nan=-1.0)
    ob = seen & (np.nan_to_num(spd, nan=-1.0) >= THR)
    fc = seen & (f >= THR)
    tl = score.tile_hits(f, spd, seen, lats, lons, THR)
    h, m, fa = score.tile_counts(tl)
    return {"ob34": int(ob.sum()), "caught": int((ob & fc).sum()), "fc34": int(fc.sum()), "nt34": len(tl),
            "h34": h, "m34": m, "fa34": fa}


def case_job(job):
    """-> (job, status, rows)."""
    basin, cycle, step, root, setname, names, ts, curves_path = job
    base_p = C.p_path(root, "base", basin, cycle, step)
    live_p = C.p_path(root, "live", basin, cycle, step)
    set_p = C.p_path(root, setname, basin, cycle, step)
    if not (base_p.exists() and live_p.exists() and set_p.exists()):
        return job, "missing_grids", []
    t = truth.ascat_target(basin, cycle + dt.timedelta(hours=step), thr=float(THR))
    if t is None:
        return job, "missing_ascat", []
    b, pl, pg = np.load(base_p), np.load(live_p), np.load(set_p)
    for k in ("p34", "p34_nb", "ocean"):
        if k not in b:
            raise RuntimeError("%s lacks %r: rerun predict.py into a fresh root" % (base_p, k))
    curves = calib.load_curves(curves_path)
    cal = calib.p34_remap(b["p34"], basin, step, curves)
    calnb = calib.p34_remap(b["p34_nb"], basin, step, curves)
    prods = products(b["r10"], pl["P"], pg["P"], cal, calnb, b["ocean"], ts)
    lats, lons = grid(basin)
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step, "split": cases.split(cycle)}
    return job, "done", [dict(key, product=n, **case_counts(prods[n], t["spd"], t["seen"], lats, lons))
                         for n in names]


def _wk(g):
    iso = g.cycle.dt.isocalendar()
    return (iso.year.astype(int) * 100 + iso.week.astype(int)).to_numpy()


def _interval(gp, fn, n_boot):
    """Whole-week interval of a pooled ratio fn(counts)."""
    _, dr = compare.boot_sums(_wk(gp), gp[COUNTS].to_numpy(float), n_boot=n_boot, seed=0)
    v = fn({c: dr[:, i] for i, c in enumerate(COUNTS)})
    v = v[np.isfinite(v)]
    return tuple(np.percentile(v, [2.5, 97.5])) if len(v) else (np.nan, np.nan)


def summarize(case_df, outdir, n_boot, baseline=BASELINE, prefix=""):
    df = case_df.copy()
    df["cycle"] = pd.to_datetime(df["cycle"].astype(str), format="%Y%m%d%H")
    rows = []
    for basin in sorted(df.basin.unique()):
        db = df[df.basin == basin]
        for stp in ["all"] + sorted(db.step.unique().tolist()):
            g = db if stp == "all" else db[db.step == stp]
            for prod in g["product"].unique():
                gp = g[g["product"] == prod]
                tot = gp[COUNTS].sum()
                c = {k: np.array(float(v)) for k, v in tot.items()}
                r = {"basin": basin, "step": stp, "product": prod, "n_cases": len(gp),
                     "n_weeks": len(np.unique(_wk(gp)))}
                r.update({k: int(v) for k, v in tot.items()})
                for k, fn in METRICS.items():
                    r[k] = float(fn(c))
                for k in ("catch", "area", "gale_csi"):
                    r[k + "_lo"], r[k + "_hi"] = _interval(gp, METRICS[k], n_boot)
                if prod != baseline and (g["product"] == baseline).any():
                    for k, fn in METRICS.items():
                        p = compare.paired_counts(g, prod, baseline, fn, COUNTS, n_boot=n_boot, seed=0,
                                                  method_col="product", case_cols=["basin", "step"])
                        r["d_" + k], r["d_%s_lo" % k], r["d_%s_hi" % k] = (float(p["diff"][0]), float(p["lo"][0]),
                                                                           float(p["hi"][0]))
                rows.append(r)
    summ = pd.DataFrame(rows)
    summ.to_csv(Path(outdir) / (prefix + "summary.csv"), index=False, float_format="%.4f")
    return summ


def _vs_ref(case_df, t, basin, n_boot):
    """galecore@t minus ref@t, pooled over leads in one basin: dict metric -> (diff, lo, hi)."""
    df = case_df.copy()
    df["cycle"] = pd.to_datetime(df["cycle"].astype(str), format="%Y%m%d%H")
    g = df[df.basin == basin]
    out = {}
    for k in ("catch", "area", "gale_csi"):
        p = compare.paired_counts(g, gname(t), rname(t), METRICS[k], COUNTS, n_boot=n_boot, seed=0,
                                  method_col="product", case_cols=["basin", "step"])
        out[k] = (float(p["diff"][0]), float(p["lo"][0]), float(p["hi"][0]))
    return out


def select(summ, case_df, ts=TS, n_boot=1000, basins=C.BASIN_LIST):
    """The win line on the summary (step "all"): -> (table DataFrame, chosen t or None). One row per t and basin."""
    s = summ[summ.step.astype(str) == "all"]
    rows = []
    for t in ts:
        for b in basins:
            g = s[(s.basin == b) & (s["product"] == gname(t))]
            if g.empty:
                continue
            g = g.iloc[0]
            vr = _vs_ref(case_df, t, b, n_boot)
            rows.append({"t": t, "basin": b, "catch": g.catch, "d_catch": g.d_catch, "d_catch_lo": g.d_catch_lo,
                         "d_catch_hi": g.d_catch_hi, "area": g.area, "area_ok": bool(g.area <= AREA_CAP),
                         "d_gale_csi": g.d_gale_csi, "d_gale_csi_lo": g.d_gale_csi_lo,
                         "d_gale_csi_hi": g.d_gale_csi_hi, "csi_ok": bool(g.d_gale_csi >= 0),
                         "line1": bool(g.d_catch_lo > 0),
                         "vs_ref_catch": vr["catch"][0], "vs_ref_catch_lo": vr["catch"][1],
                         "vs_ref_catch_hi": vr["catch"][2], "vs_ref_area": vr["area"][0],
                         "vs_ref_csi": vr["gale_csi"][0]})
    tab = pd.DataFrame(rows)
    chosen = None
    if len(tab):
        best = None
        for t, g in tab.groupby("t"):
            if len(g) < len(basins) or not (g.area_ok.all() and g.csi_ok.all()):
                continue
            key = (g.d_catch.min(), g.d_catch.mean())
            if best is None or key > best[0]:
                best = (key, t)
        chosen = None if best is None else float(best[1])
    if len(tab):
        tab["qualifies"] = tab.groupby("t")[["area_ok", "csi_ok"]].transform("all").all(axis=1)
        tab["chosen"] = tab.t == chosen if chosen is not None else False
    return tab, chosen


def verdict_lines(tab, chosen, label):
    if chosen is None:
        return ["%s: NO t qualifies (area <= %.1f and gale-tile CSI not lower, in both basins)." % (label, AREA_CAP)]
    g = tab[tab.t == chosen]
    line1 = bool(g.line1.all())
    beats = bool((g.vs_ref_catch_lo > 0).all())
    return ["%s: t = %.1f would be chosen (highest catch gain among t meeting area <= %.1f and gale-tile CSI not "
            "lower, both basins)." % (label, chosen, AREA_CAP),
            "  win line point 1 (catch gain, interval above zero in both basins): %s" % ("MET" if line1 else "NOT MET"),
            "  galecore@%.1f vs ref@%.1f on catch, interval above zero in both basins: %s%s" % (
                chosen, chosen, "YES" if beats else "NO",
                "" if beats else (" (point differences %s)" % ", ".join(
                    "%s %+.3f [%+.3f, %+.3f]" % (r.basin, r.vs_ref_catch, r.vs_ref_catch_lo, r.vs_ref_catch_hi)
                    for r in g.itertuples())))]


def _f(x, d=3):
    return "%.*f" % (d, x) if np.isfinite(x) else "-"


def write_md(summ, tab, chosen, path, label, extra=""):
    s = summ[summ.step.astype(str) == "all"]
    L = ["# Gale cores: %s results (%s weeks)" % (label.lower(), label), "",
         "Gale-cell catch = ASCAT 34+ seen cells the forecast also has at 34+; area = forecast 34+ seen cells / "
         "ASCAT 34+ seen cells; gale-tile CSI = 5x5 deg tiles at 34 kt. Pooled over +24..+120 h; brackets are "
         "whole-week 95% intervals; the d columns are differences from the baseline (Core Lifted today).", ""]
    for b in sorted(s.basin.unique()):
        L += ["## %s" % b, "", "| product | catch | d catch | area | d area | gale CSI | d CSI | gale FAR |",
              "|---|---|---|---|---|---|---|---|"]
        for r in s[s.basin == b].itertuples():
            dc = "" if np.isnan(getattr(r, "d_catch", np.nan)) else "%+.3f [%+.3f, %+.3f]" % (
                r.d_catch, r.d_catch_lo, r.d_catch_hi)
            da = "" if np.isnan(getattr(r, "d_area", np.nan)) else "%+.2f [%+.2f, %+.2f]" % (
                r.d_area, r.d_area_lo, r.d_area_hi)
            dq = "" if np.isnan(getattr(r, "d_gale_csi", np.nan)) else "%+.3f [%+.3f, %+.3f]" % (
                r.d_gale_csi, r.d_gale_csi_lo, r.d_gale_csi_hi)
            L.append("| %s | %s [%s, %s] | %s | %s [%s, %s] | %s | %s [%s, %s] | %s | %s |" % (
                r.product, _f(r.catch), _f(r.catch_lo), _f(r.catch_hi), dc, _f(r.area, 2), _f(r.area_lo, 2),
                _f(r.area_hi, 2), da, _f(r.gale_csi), _f(r.gale_csi_lo), _f(r.gale_csi_hi), dq, _f(r.gale_far)))
        L.append("")
    L += ["## Win line applied mechanically (%s weeks)" % label, ""]
    L += ["| t | basin | d catch [interval] | area | d gale CSI | line 1 | galecore - ref catch [interval] |",
          "|---|---|---|---|---|---|---|"]
    for r in tab.itertuples():
        L.append("| %.1f%s | %s | %+.3f [%+.3f, %+.3f] | %.2f | %+.3f | %s | %+.3f [%+.3f, %+.3f] |" % (
            r.t, " *" if r.chosen else "", r.basin, r.d_catch, r.d_catch_lo, r.d_catch_hi, r.area, r.d_gale_csi,
            "yes" if r.line1 else "no", r.vs_ref_catch, r.vs_ref_catch_lo, r.vs_ref_catch_hi))
    L += ["", "\\* chosen t", ""]
    L += verdict_lines(tab, chosen, label)
    if extra:
        L += ["", extra]
    Path(path).write_text("\n".join(L) + "\n")


def print_summary(summ, tab, chosen, label):
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)
    s = summ[summ.step.astype(str) == "all"]
    cols = ["basin", "product", "ob34", "catch", "catch_lo", "catch_hi", "area", "area_lo", "area_hi", "gale_csi",
            "d_catch", "d_catch_lo", "d_catch_hi", "d_area", "d_gale_csi", "d_gale_csi_lo", "d_gale_csi_hi"]
    print("\n[%s weeks] pooled over leads" % label)
    print(s[[c for c in cols if c in s]].round(3).to_string(index=False))
    if len(tab):
        print("\nWin line, per t and basin:")
        print(tab.round(3).to_string(index=False))
    print()
    for line in verdict_lines(tab, chosen, label):
        print(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default="live28+basin", help="feature set (the model is '<set>@34')")
    ap.add_argument("--root", default=None)
    ap.add_argument("--results", default=str(HERE / "results"))
    ap.add_argument("--curves", default=str(HERE / "p34_curves.json"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--choice-dir", default=str(HERE), help="folder holding FINAL_CHOICE.json (tests only)")
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    a = ap.parse_args()
    out = Path(a.results)
    prefix = "final_" if a.final else ""
    label = "HELD-OUT" if a.final else "TUNE"
    root = Path(a.root) if a.root else C.default_root()
    ts, setbase = TS, a.set
    if a.final and a.summary_only:
        sys.exit("--summary-only is for the tune results; the held-out score is written once with --final")
    if a.final:
        ch = Path(a.choice_dir) / "FINAL_CHOICE.json"
        marker = Path(a.choice_dir) / "FINAL_RUN.json"
        if not ch.exists():
            sys.exit("refusing --final: %s does not exist. The held-out weeks are scored once, after t and the "
                     "model set are chosen from the tune results (write FINAL_CHOICE.json with "
                     "{\"t\": ..., \"set\": ...})." % ch)
        if marker.exists() or (out / "final_case_scores.csv").exists():
            sys.exit("refusing --final: the held-out score has been run already (%s); it is used once." % (
                marker if marker.exists() else out / "final_case_scores.csv"))
        choice = json.load(open(ch))
        if choice.get("set") not in C.SETS or not any(abs(choice.get("t", -1) - t) < 1e-9 for t in TS):
            sys.exit("FINAL_CHOICE.json: t must be one of %s and set one of %s" % (list(TS), list(C.SETS)))
        if a.set != choice["set"] and a.set != "live28+basin":
            sys.exit("--set %s differs from the chosen set %s" % (a.set, choice["set"]))
        setbase, ts = choice["set"], (float(choice["t"]),)
    out.mkdir(parents=True, exist_ok=True)
    if a.summary_only:
        cs = pd.read_csv(out / (prefix + "case_scores.csv"), dtype={"cycle": str})
        summ = summarize(cs, out, a.boot, prefix=prefix)
        tab, chosen = select(summ, cs, ts, a.boot)
        tab.to_csv(out / (prefix + "selection.csv"), index=False, float_format="%.4f")
        write_md(summ, tab, chosen, out / "tune_summary.md", label)
        print_summary(summ, tab, chosen, label)
        return
    names = product_names(ts)
    if a.final:
        names = [BASELINE, gname(ts[0]), rname(ts[0])]
    setname = C.target_name(setbase, THR)
    want = "held_out" if a.final else "tune"
    steps = tuple(int(s) for s in a.steps.split(","))
    jobs = [(b, c, s, str(root), setname, names, ts, a.curves) for b, c, s in C.all_cases(a.basins.split(","), steps)
            if cases.split(c) == want]
    print("scoring %d %s cases, model %s, %d products -> %s" % (len(jobs), want, setname, len(names), out), flush=True)
    tally = {"done": 0, "missing_grids": 0, "missing_ascat": 0}
    rows = []
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, status, r) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=2), 1):
            tally[status] += 1
            rows += r
            if i % 100 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    if not rows:
        sys.exit("no case could be scored: %s" % tally)
    cs = pd.DataFrame(rows).sort_values(["basin", "cycle", "step", "product"]).reset_index(drop=True)
    cs.to_csv(out / (prefix + "case_scores.csv"), index=False)
    summ = summarize(cs, out, a.boot, prefix=prefix)
    if a.final:
        marker.write_text(json.dumps({"scored": dt.datetime.now(dt.timezone.utc).isoformat(), "choice": choice}))
        print(summ[summ.step.astype(str) == "all"].round(3).to_string(index=False))
        print("SUMMARY: %d held-out cases scored, %s; wrote %s*.csv" % (tally["done"], tally, out / prefix), flush=True)
        return
    tab, chosen = select(summ, cs, ts, a.boot)
    tab.to_csv(out / "selection.csv", index=False, float_format="%.4f")
    write_md(summ, tab, chosen, out / "tune_summary.md", label,
             extra="Cases scored: %d (%s)." % (tally["done"], tally))
    print_summary(summ, tab, chosen, label)
    print("SUMMARY: %d %s cases scored, %s; wrote %s*.csv" % (tally["done"], want, tally, out / prefix), flush=True)


if __name__ == "__main__":
    main()
