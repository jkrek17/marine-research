#!/usr/bin/env python3
"""Train and cross-validate the core-lift model on the TUNE weeks only.

  python3 train.py TABLE_DIR [--thr 48] [--curves FILE] [--sets live28,live28+basin,store,store+basin] [--root DIR] [--results DIR]
                   [--workers 1] [--boot 1000]

TABLE_DIR holds the parquet files of build_table.py. Only rows with split == "tune" are read for fitting and
scoring; held-out weeks are never touched here. Feature sets: live28 (the 28 live features), live28+basin,
store (no lower-level features), store+basin. Model: HistGradientBoostingClassifier with the live settings
(common.HGB_PARAMS), sample weights w. Folds: tune ISO weeks, fold = tune-week index mod 5 (common.fold_of).

--thr (default 48) must match the table's target (the table records it). For a non-48 target the models and
OOF files are named '<set>@<thr>' (common.target_name) and the reference predictions are the raw member
shares instead of the live storm model: p34 (the cell share), p34_nb (its neighbourhood maximum) and, with
--curves (rk.calib JSON; default: p34_curves.json in the gale study folder), p34_cal = the calibrated cell
p34 (winter, ASCAT truth, by basin and lead group). The dBSS / dAUC columns are then against p34_cal
(named dbss_vs_p34_cal ...).

Outputs (ROOT defaults to the shared store under extra/core-lift-retrain):
  ROOT/models/<set>/fold{k}.joblib, final.joblib (fit on all tune rows), meta.json
  ROOT/oof/<set>.parquet            out-of-fold probability for every tune row
  RESULTS/cv_metrics.csv            per basin (and both): weighted Brier skill vs base rate and ROC area on the
                                    out-of-fold rows, with 95% intervals from resampling whole ISO weeks, for
                                    each set, for the LIVE model on the same rows (storm.core_predict) and for
                                    p48_nb used directly as a probability. The live model was trained on
                                    Atlantic winter 2025-26, so its Atlantic numbers are partly in-sample.
AUC intervals use 1000 probability bins (point values are exact); dBSS / dAUC are the set minus live on the same
resampled weeks. Use the spawn context when parallel (fork + OpenMP deadlocks after sklearn fits).
"""
import argparse
import json
import warnings
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np
import pandas as pd

import common as C
from rk import compare, features, score

_TABLE = {}


def tune_table(table_dir):
    if table_dir not in _TABLE:
        d = C.load_table(table_dir)
        d = d[d["split"] == "tune"].reset_index(drop=True)
        _TABLE[table_dir] = C.add_fold(d)
    return _TABLE[table_dir]


def fit_job(job):
    """job = (table_dir, set, fold|"final", root) -> (set, fold, oof_index, oof_p)."""
    table_dir, name, k, root = job
    import joblib
    d = tune_table(table_dir)
    cols = C.SETS[C.split_target(name)[0]]
    tr = np.ones(len(d), bool) if k == "final" else (d["fold"].to_numpy() != k)
    m = C.make_model().fit(d.loc[tr, cols].to_numpy(np.float64), d.loc[tr, "y"].to_numpy(),
                           sample_weight=d.loc[tr, "w"].to_numpy(np.float64))
    out = C.models_dir(root, name)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(m, out / ("final.joblib" if k == "final" else "fold%d.joblib" % k))
    if k == "final":
        return name, k, None, None
    te = np.nonzero(~tr)[0]
    return name, k, te, m.predict_proba(d.loc[tr == False, cols].to_numpy(np.float64))[:, 1]  # noqa: E712


NB = 1000


def _hists(p, y, w, wk_idx, nwk, edges):
    b = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    nb = len(edges) - 1
    pos = np.bincount(wk_idx * nb + b, weights=w * y, minlength=nwk * nb).reshape(nwk, nb)
    neg = np.bincount(wk_idx * nb + b, weights=w * (1 - y), minlength=nwk * nb).reshape(nwk, nb)
    return pos, neg


def metrics(sub, preds, n_boot, ref="live"):
    """sub: rows (one basin or both) with y, w, cycle; preds: {name: p}. -> list of dict rows."""
    y, w = sub["y"].to_numpy(float), sub["w"].to_numpy(float)
    wk = C.week_id(sub["cycle"])
    uw, wk_idx = np.unique(wk, return_inverse=True)
    nwk = len(uw)
    base = (w * y).sum() / w.sum()
    out, draws = [], {}
    for name, p in preds.items():
        p = np.asarray(p, float)
        edges = np.unique(np.quantile(p, np.linspace(0, 1, NB + 1)))
        if len(edges) < 2:
            edges = np.array([p.min() - 1e-9, p.max() + 1e-9])
        edges[-1] += 1e-9
        pos, neg = _hists(p, y, w, wk_idx, nwk, edges)
        se = np.bincount(wk_idx, weights=w * (p - y) ** 2, minlength=nwk)
        sw = np.bincount(wk_idx, weights=w, minlength=nwk)
        swy = np.bincount(wk_idx, weights=w * y, minlength=nwk)
        stats = np.hstack([np.c_[sw, swy, se], pos, neg])          # per-week additive statistics
        _, dr = compare.boot_sums(np.arange(nwk), stats, n_boot=n_boot, seed=0)

        def bss_auc(s):
            b0 = s[..., 1] / s[..., 0]
            with np.errstate(invalid="ignore", divide="ignore"):
                bss = 1 - (s[..., 2] / s[..., 0]) / (b0 * (1 - b0))
            return bss, score.auc_from_hist(s[..., 3:3 + pos.shape[1]], s[..., 3 + pos.shape[1]:])
        bd, ad = bss_auc(dr)
        draws[name] = (bd, ad)
        lo_b, hi_b = np.nanpercentile(bd, [2.5, 97.5])
        lo_a, hi_a = np.nanpercentile(ad, [2.5, 97.5])
        out.append({"model": name, "n_rows": len(sub), "n_pos": int(y.sum()), "n_weeks": nwk,
                    "base_rate": base, "bss": score.brier_skill(p, y, w), "bss_lo": lo_b, "bss_hi": hi_b,
                    "auc": score.auc(p, y, w), "auc_lo": lo_a, "auc_hi": hi_a})
    if ref in draws:
        refrow = next(x for x in out if x["model"] == ref)
        for r in out:
            if r["model"] == ref:
                continue
            db, da = draws[r["model"]][0] - draws[ref][0], draws[r["model"]][1] - draws[ref][1]
            r["dbss_vs_" + ref] = r["bss"] - refrow["bss"]
            r["dbss_lo"], r["dbss_hi"] = np.nanpercentile(db, [2.5, 97.5])
            r["dauc_vs_" + ref] = r["auc"] - refrow["auc"]
            r["dauc_lo"], r["dauc_hi"] = np.nanpercentile(da, [2.5, 97.5])
    return out


warnings.filterwarnings("ignore", category=RuntimeWarning)   # empty or one-class bootstrap draws give NaN, by design


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table_dir")
    ap.add_argument("--thr", type=int, default=C.THR_DEFAULT, help="target threshold, kt (must match the table)")
    ap.add_argument("--curves", default=None, help="P34 curves JSON for the calibrated reference (--thr 34)")
    ap.add_argument("--sets", default=",".join(C.SETS))
    ap.add_argument("--root", default=None, help="cache root (default: shared store extra/core-lift-retrain)")
    ap.add_argument("--results", default=str(C.HERE / "results"))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    root = Path(a.root) if a.root else C.default_root()
    bases = a.sets.split(",")
    for s in bases:
        if s not in C.SETS:
            raise SystemExit("unknown set %r; choose from %s" % (s, list(C.SETS)))
    d = tune_table(a.table_dir)
    if C.table_target(d)[0] != a.thr:
        raise SystemExit("table target is %d kt but --thr is %d" % (C.table_target(d)[0], a.thr))
    sets = [C.target_name(s, a.thr) for s in bases]
    lowm = C.table_low_models(d)
    print("table %s: %d tune rows (%d positive), low_models=%r, folds %s" % (
        a.table_dir, len(d), int(d.y.sum()), lowm, sorted(d.fold.unique().tolist())), flush=True)
    if lowm == "":
        skipped = [s for s in sets if set(C.SETS[C.split_target(s)[0]]) & set(features.LOW_FEATURES)]
        if skipped:
            print("*** NO-LOW table: the eight low-level columns are all NaN (sklearn cannot bin them), so "
                  "the sets %s are skipped; the live model is still scored with those inputs missing ***"
                  % skipped, flush=True)
        sets = [s for s in sets if s not in skipped]
        if not sets:
            raise SystemExit("nothing to train on a no-low table: use the store sets")
    folds = sorted(d.fold.unique().tolist())
    jobs = [(a.table_dir, s, k, str(root)) for s in sets for k in folds + ["final"]]
    t0 = time.time()
    if a.workers > 1:
        with mp.get_context("spawn").Pool(a.workers) as pool:
            res = pool.map(fit_job, jobs, chunksize=1)
    else:
        res = [fit_job(j) for j in jobs]
    print("fitted %d models in %.0fs" % (len(jobs), time.time() - t0), flush=True)
    oof = {s: np.full(len(d), np.nan) for s in sets}
    for name, k, idx, p in res:
        if idx is not None:
            oof[name][idx] = p
    for s in sets:
        meta = {"set": s, "thr": a.thr, "cand_rule": C.table_target(d)[1], "features": C.SETS[C.split_target(s)[0]], "params": C.HGB_PARAMS, "table": str(a.table_dir),
                "no_low": bool(d["no_low"].iloc[0]), "low_models": lowm, "folds": folds,
                "n_tune_rows": int(len(d)), "sklearn": __import__("sklearn").__version__}
        json.dump(meta, open(C.models_dir(root, s) / "meta.json", "w"), indent=1)
        o = d[["basin", "cycle", "step", "row", "col", "fold", "y", "w"]].copy()
        o["p"] = oof[s].astype(np.float32)
        (root / "oof").mkdir(parents=True, exist_ok=True)
        o.to_parquet(root / "oof" / (s + ".parquet"), index=False)
    # live model and the no-model reference on the same rows
    if a.thr == C.THR_DEFAULT:
        refs = {"live": C.live_predict_table(d), "p48_nb": d["p48_nb"].to_numpy()}
        ref_models, ref_name = ("live", "p48_nb"), "live"
    else:
        from rk import calib
        curves = calib.load_curves(a.curves or C.HERE.parents[0] / "2026-10-17-gale-core" / "p34_curves.json")
        cal = np.zeros(len(d), np.float32)
        for (b, st), g in d.groupby(["basin", "step"]):
            cal[g.index.to_numpy()] = calib.p34_remap(g["p34"].to_numpy(), b, st, curves)
        refs = {"p34": d["p34"].to_numpy(), "p34_nb": d["p34_nb"].to_numpy(), "p34_cal": cal}
        ref_models, ref_name = tuple(refs), "p34_cal"
    rows = []
    for scope, sub_idx in [("both", np.arange(len(d)))] + [(b, np.nonzero(d.basin.to_numpy() == b)[0])
                                                            for b in C.BASIN_LIST]:
        if len(sub_idx) == 0:
            continue
        sub = d.iloc[sub_idx]
        for s in sets:
            preds = {k: v[sub_idx] for k, v in refs.items()}
            preds[s] = oof[s][sub_idx]
            for r in metrics(sub, preds, a.boot, ref=ref_name):
                r.update(basin=scope, set=("reference" if r["model"] in ref_models else s))
                rows.append(r)
    out = pd.DataFrame(rows)
    ref = out[out["set"] == "reference"].drop_duplicates(["basin", "model"])
    out = pd.concat([ref, out[out["set"] != "reference"]], ignore_index=True)
    lead = ["basin", "set", "model", "n_rows", "n_pos", "n_weeks", "base_rate", "bss", "bss_lo", "bss_hi",
            "auc", "auc_lo", "auc_hi"]
    out = out[lead + [c for c in out.columns if c not in lead]]
    Path(a.results).mkdir(parents=True, exist_ok=True)
    out.to_csv(Path(a.results) / "cv_metrics.csv", index=False, float_format="%.4f")
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(out[lead[:3] + ["n_rows", "n_pos", "n_weeks", "bss", "bss_lo", "bss_hi", "auc", "auc_lo", "auc_hi"]]
          .round(3).to_string(index=False), flush=True)
    print("wrote %s" % (Path(a.results) / "cv_metrics.csv"), flush=True)


if __name__ == "__main__":
    main()
