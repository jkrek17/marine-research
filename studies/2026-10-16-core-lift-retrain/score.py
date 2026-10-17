#!/usr/bin/env python3
"""Score the core-lift products against ASCAT, from the grids predict.py wrote.

  python3 score.py --set store+basin [--root DIR] [--results DIR] [--workers 4] [--boot 1000]
  python3 score.py --summary-only [--results DIR]            (recompute the summary from the case CSVs)
  python3 score.py --final [--choice-dir DIR]                (held-out weeks, once; see below)
  python3 score.py --final-extra --steps ...                 (held-out cases --final could not score, same choice)

Products per case (forecast speed at the grid, kt; r10 = the live blend):
  blend                    r10
  live_lift                r10 + 5 where the LIVE model's P >= 0.35 (Core Lifted today)
  lift{L}@{t}              r10 + L where the new model's P >= t, L in 3, 5, 8, t in 0.20, 0.35, 0.50
  kP{k}                    r10 + k x P (new model), k in 5, 8, 10
  member@{x}               r10 + 5 where p48_nb >= x on the candidate cells (no model), x in 0.1, 0.2, 0.3
Truth: rk.truth.ascat_target(basin, valid): ASCAT real 10 m wind, intercalibrated, on the basin grid; `seen` =
cells an ASCAT cell landed in (all hours near the valid time).
Scores per basin, step and product, counted per case in case_scores.csv (counts, not ratios):
  (a) storm tiles: 5x5 deg tiles with >= 150 seen cells; observed event = any seen cell >= 48 kt, forecast event
      = any forecast cell >= 48 kt AMONG THE SEEN CELLS (rk.score.tile_hits). h48 / m48 / fa48 and nt48 tiles.
  (b) gale tiles, the same at 34 kt (h34, m34, fa34, nt34).
  (c) cell area: fc48 = seen cells with forecast >= 48, ob48 = seen cells with ASCAT >= 48 (ratio = fc48/ob48).
  (d) reliability of P (live, new, and p48_nb as a reference) in 10 bins against y (ASCAT 48+ within ~50 km,
      ascat_target.y) at candidate seen cells: case_reliability.csv (n, sum_y, sum_p per bin).
summary.csv: pooled POD, FAR, CSI (storm and gale), area ratio with whole-week 95% intervals, and for every
product the difference from live_lift (POD, FAR, CSI storm; CSI gale) with whole-week 95% intervals
(rk.compare.paired_counts: the same resampled weeks for both products). summary_reliability.csv: pooled
reliability per basin and model with whole-week intervals on the observed frequency.

Default: TUNE weeks, out-of-fold P (what predict.py wrote without --final). --final scores the HELD-OUT weeks
and is a one-time gate: it needs FINAL_CHOICE.json in the study folder, {"product": "lift5@0.35", "set":
"store+basin"}, written after the tune results are in; it scores only blend, live_lift and the chosen product
with the chosen set's final model, and refuses to run if the final result files already exist. (--choice-dir
exists so the tests can point at a scratch folder; it is not a way round the gate.)
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import common as C
from rk import cases, compare, score, truth
from rk.basins import grid

LIFT_KT, LIFT_P = 5.0, 0.35            # the live page (storm.py)
LIFTS, THRS, KS, MEMBER_X = (3, 5, 8), (0.20, 0.35, 0.50), (5, 8, 10), (0.1, 0.2, 0.3)
BINS = 10


def lift_name(L, t):
    return "lift%d@%.2f" % (L, t)


def product_names():
    return (["blend", "live_lift"] + [lift_name(L, t) for t in THRS for L in LIFTS]
            + ["kP%d" % k for k in KS] + ["member@%.1f" % x for x in MEMBER_X])


def products(r10, p48_nb, cand, P_live, P_new):
    """{name: forecast speed grid (kt)}; P grids are zero off the candidate cells."""
    Pl, Pn = np.asarray(P_live, np.float64), np.asarray(P_new, np.float64)
    r10 = np.asarray(r10, np.float32)
    out = {"blend": r10, "live_lift": np.where(Pl >= LIFT_P, r10 + LIFT_KT, r10)}
    for t in THRS:
        for L in LIFTS:
            out[lift_name(L, t)] = np.where(Pn >= t, r10 + L, r10)
    for k in KS:
        out["kP%d" % k] = r10 + k * Pn.astype(np.float32)
    for x in MEMBER_X:
        out["member@%.1f" % x] = np.where(cand & (np.asarray(p48_nb) >= x), r10 + LIFT_KT, r10)
    return out


def case_job(job):
    """-> (job, status, rows, rel_rows)."""
    basin, cycle, step, root, setname, names = job
    base_p = C.p_path(root, "base", basin, cycle, step)
    live_p = C.p_path(root, "live", basin, cycle, step)
    set_p = C.p_path(root, setname, basin, cycle, step)
    if not (base_p.exists() and live_p.exists() and set_p.exists()):
        return job, "missing_grids", [], []
    import datetime as dt
    t = truth.ascat_target(basin, cycle + dt.timedelta(hours=step))
    if t is None:
        return job, "missing_ascat", [], []
    b, pl, pn = np.load(base_p), np.load(live_p), np.load(set_p)
    lats, lons = grid(basin)
    seen, spd = t["seen"], t["spd"]
    prods = products(b["r10"], b["p48_nb"], b["cand"], pl["P"], pn["P"])
    key = {"basin": basin, "cycle": cases.tag(cycle), "step": step}
    ob48 = int(((spd >= 48) & seen).sum())
    rows = []
    for name in names:
        f = prods[name]
        r = dict(key, product=name)
        for thr, tag in ((48, "48"), (34, "34")):
            tl = score.tile_hits(f, spd, seen, lats, lons, thr)
            h, m, fa = score.tile_counts(tl)
            r.update({"nt" + tag: len(tl), "h" + tag: h, "m" + tag: m, "fa" + tag: fa})
        r["fc48"] = int(((f >= 48) & seen).sum())
        r["ob48"] = ob48
        rows.append(r)
    cs = b["cand"] & seen
    y = t["y"][cs].astype(float)
    rel = []
    for model, P in (("live", pl["P"]), (setname, pn["P"]), ("p48_nb", b["p48_nb"])):
        p = np.asarray(P, np.float64)[cs]
        bi = np.clip((p * BINS).astype(int), 0, BINS - 1)
        n = np.bincount(bi, minlength=BINS)
        sy = np.bincount(bi, weights=y, minlength=BINS)
        sp = np.bincount(bi, weights=p, minlength=BINS)
        for i in range(BINS):
            rel.append(dict(key, model=model, bin=i, n=int(n[i]), sum_y=float(sy[i]), sum_p=float(sp[i])))
    return job, "done", rows, rel


def _ratio(num, den):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


METRICS = {
    "pod": (lambda c: _ratio(c["h48"], c["h48"] + c["m48"])),
    "far": (lambda c: _ratio(c["fa48"], c["h48"] + c["fa48"])),
    "csi": (lambda c: _ratio(c["h48"], c["h48"] + c["m48"] + c["fa48"])),
    "gale_csi": (lambda c: _ratio(c["h34"], c["h34"] + c["m34"] + c["fa34"])),
}
COUNTS = ["nt48", "h48", "m48", "fa48", "nt34", "h34", "m34", "fa34", "fc48", "ob48"]


def _wk(g):
    iso = g.cycle.dt.isocalendar()
    return (iso.year.astype(int) * 100 + iso.week.astype(int)).to_numpy()


def summarize(case_df, rel_df, outdir, n_boot, baseline="live_lift", prefix=""):
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
                     "n_weeks": len(np.unique(_wk(gp))),
                     "tiles48": int(tot.h48 + tot.m48), "h48": int(tot.h48), "m48": int(tot.m48),
                     "fa48": int(tot.fa48), "tiles34": int(tot.h34 + tot.m34), "h34": int(tot.h34),
                     "m34": int(tot.m34), "fa34": int(tot.fa34), "fc48": int(tot.fc48), "ob48": int(tot.ob48)}
                for k, fn in METRICS.items():
                    r[k] = float(fn(c))
                r["area_ratio"] = float(_ratio(c["fc48"], c["ob48"]))
                _, dr = compare.boot_sums(_wk(gp), gp[["fc48", "ob48"]].to_numpy(float), n_boot=n_boot, seed=0)
                ar = _ratio(dr[:, 0], dr[:, 1])
                ar = ar[np.isfinite(ar)]
                r["area_lo"], r["area_hi"] = (np.percentile(ar, [2.5, 97.5]) if len(ar) else (np.nan, np.nan))
                if prod != baseline and (g["product"] == baseline).any():
                    for k, fn in METRICS.items():
                        p = compare.paired_counts(g, prod, baseline, fn, COUNTS, n_boot=n_boot, seed=0,
                                                  method_col="product", case_cols=["basin", "step"])
                        r["d_" + k], r["d_%s_lo" % k], r["d_%s_hi" % k] = (float(p["diff"][0]), float(p["lo"][0]),
                                                                           float(p["hi"][0]))
                rows.append(r)
    summ = pd.DataFrame(rows)
    summ.to_csv(Path(outdir) / (prefix + "summary.csv"), index=False, float_format="%.4f")
    # reliability
    rl = rel_df.copy()
    rl["cycle"] = pd.to_datetime(rl["cycle"].astype(str), format="%Y%m%d%H")
    rrows = []
    for (basin, model), g in rl.groupby(["basin", "model"]):
        for i in range(BINS):
            gb = g[g.bin == i]
            n, sy, sp = gb.n.sum(), gb.sum_y.sum(), gb.sum_p.sum()
            _, dr = compare.boot_sums(_wk(gb), gb[["n", "sum_y"]].to_numpy(float), n_boot=n_boot, seed=0)
            fr = _ratio(dr[:, 1], dr[:, 0])
            fr = fr[np.isfinite(fr)]
            lo, hi = np.percentile(fr, [2.5, 97.5]) if len(fr) else (np.nan, np.nan)
            mp_ = sp / n if n else np.nan
            fq = sy / n if n else np.nan
            mid = 0.2 <= i / BINS and (i + 1) / BINS <= 0.8
            rrows.append({"basin": basin, "model": model, "bin": i, "lo": i / BINS, "hi": (i + 1) / BINS,
                          "n": int(n), "mean_p": mp_, "freq": fq, "freq_lo": lo, "freq_hi": hi,
                          "mid_bin": mid, "within10": (abs(fq - mp_) <= 0.10) if (mid and n >= 30) else np.nan})
    rsum = pd.DataFrame(rrows)
    rsum.to_csv(Path(outdir) / (prefix + "summary_reliability.csv"), index=False, float_format="%.4f")
    return summ, rsum


def print_summary(summ, rsum):
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)
    s = summ[summ.step == "all"]
    cols = ["basin", "product", "tiles48", "pod", "far", "csi", "gale_csi", "area_ratio", "d_pod", "d_pod_lo",
            "d_pod_hi", "d_far", "d_far_lo", "d_far_hi", "d_csi", "d_csi_lo", "d_csi_hi"]
    print(s[[c for c in cols if c in s]].round(3).to_string(index=False))
    print("\nReliability (mid bins 20-80%):")
    r = rsum[rsum.mid_bin]
    print(r[["basin", "model", "lo", "hi", "n", "mean_p", "freq", "freq_lo", "freq_hi", "within10"]]
          .round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default=None, help="model set name (e.g. store+basin)")
    ap.add_argument("--root", default=None)
    ap.add_argument("--results", default=str(C.HERE / "results"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--final-extra", action="store_true",
                    help="after --final: score held-out cases the final run could not (no truth then), with the "
                         "same locked choice; writes final_extra_*")
    ap.add_argument("--choice-dir", default=str(C.HERE), help="folder holding FINAL_CHOICE.json (tests only)")
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--steps", default=",".join(map(str, cases.STEPS)))
    a = ap.parse_args()
    out = Path(a.results)
    if a.final_extra:
        a.final = True
    prefix = "final_extra_" if a.final_extra else ("final_" if a.final else "")
    root = Path(a.root) if a.root else C.default_root()
    names = product_names()
    if a.final:
        ch = Path(a.choice_dir) / "FINAL_CHOICE.json"
        if not ch.exists():
            sys.exit("refusing --final: %s does not exist. The held-out weeks are scored once, after the "
                     "product and model set are chosen from the tune results (write FINAL_CHOICE.json "
                     "with {\"product\": ..., \"set\": ...})." % ch)
        choice = json.load(open(ch))
        if choice.get("product") not in names or choice.get("set") not in C.SETS:
            sys.exit("FINAL_CHOICE.json: product must be one of %s and set one of %s" % (names, list(C.SETS)))
        if a.set and a.set != choice["set"]:
            sys.exit("--set %s differs from the chosen set %s" % (a.set, choice["set"]))
        a.set = choice["set"]
        names = ["blend", "live_lift"] + ([choice["product"]] if choice["product"] not in ("blend", "live_lift") else [])
        if a.final_extra:
            if not (out / "final_case_scores.csv").exists():
                sys.exit("--final-extra comes after --final")
            if (out / "final_extra_case_scores.csv").exists() and not a.summary_only:
                sys.exit("refusing --final-extra: %s exists" % (out / "final_extra_case_scores.csv"))
        elif (out / "final_case_scores.csv").exists() and not a.summary_only:
            sys.exit("refusing --final: %s exists; the held-out score is used once." % (out / "final_case_scores.csv"))
    out.mkdir(parents=True, exist_ok=True)
    if a.summary_only:
        cs = pd.read_csv(out / (prefix + "case_scores.csv"), dtype={"cycle": str})
        rs = pd.read_csv(out / (prefix + "case_reliability.csv"), dtype={"cycle": str})
        print_summary(*summarize(cs, rs, out, a.boot, prefix=prefix))
        return
    if not a.set:
        sys.exit("--set is required")
    want = "held_out" if a.final else "tune"
    steps = tuple(int(s) for s in a.steps.split(","))
    jobs = [(b, c, s, str(root), a.set, names) for b, c, s in C.all_cases(a.basins.split(","), steps)
            if cases.split(c) == want]
    if a.final_extra:      # only the cases the final run left unscored
        done = pd.read_csv(out / "final_case_scores.csv", dtype={"cycle": str})
        seen = set(zip(done["basin"], done["cycle"], done["step"].astype(int)))
        jobs = [j for j in jobs if (j[0], cases.tag(j[1]), j[2]) not in seen]
    print("scoring %d %s cases, set %s, %d products -> %s" % (len(jobs), want, a.set, len(names), out), flush=True)
    tally = {"done": 0, "missing_grids": 0, "missing_ascat": 0}
    rows, rel = [], []
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, (job, status, r, rr) in enumerate(pool.imap_unordered(case_job, jobs, chunksize=2), 1):
            tally[status] += 1
            rows += r
            rel += rr
            if i % 100 == 0 or i == len(jobs):
                print("[%d/%d] %.0fs %s" % (i, len(jobs), time.time() - t0, tally), flush=True)
    if not rows:
        sys.exit("no case could be scored: %s" % tally)
    cs = pd.DataFrame(rows).sort_values(["basin", "cycle", "step", "product"]).reset_index(drop=True)
    rs = pd.DataFrame(rel).sort_values(["basin", "cycle", "step", "model", "bin"]).reset_index(drop=True)
    cs.to_csv(out / (prefix + "case_scores.csv"), index=False)
    rs.to_csv(out / (prefix + "case_reliability.csv"), index=False)
    summ, rsum = summarize(cs, rs, out, a.boot, prefix=prefix)
    print_summary(summ, rsum)
    print("SUMMARY: %d %s cases scored, %s; wrote %s*.csv" % (tally["done"], want, tally, out / prefix), flush=True)


if __name__ == "__main__":
    main()
