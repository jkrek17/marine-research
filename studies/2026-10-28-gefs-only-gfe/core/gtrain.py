#!/usr/bin/env python3
"""Train and cross-validate the GEFS-only core models on the TUNE weeks (the retrain's train.py: same learner,
settings, basin feature and 5 whole-week folds; only the feature set differs).

  python3 gtrain.py [--workers 3] [--boot 1000]

For each variant (q 0.25 deg GEFS, h 0.5 deg GEFS) and target (storm 48 kt, gale 34 kt): fit the 5 fold models and the
final model on the tune table (feature set gcommon.SET = the live 28 minus s10_aifs and pa48, plus the basin flag),
write the out-of-fold probability of every tune row, and score it (weighted Brier skill and ROC area with
whole-week 95% intervals; train.metrics) beside the raw GEFS share used directly as a probability (p48_nb for
storm, p34 and p34_nb for gale). The live model is not scored here: its inputs (AIFS, ENS) are not in this table.
  <core root>/models-{q,h}/<set>[@34]/fold{k}.joblib, final.joblib, meta.json
  <core root>/oof/{q,h}-{storm,gale}.parquet
  results/cv_metrics.csv
"""
import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np
import pandas as pd

import gcommon as G
import common as C
import train as T

TARGETS = (("storm", 48), ("gale", 34))


def init():
    G.install()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--results", default=str(G.HERE / "results"))
    a = ap.parse_args()
    G.install()
    plan = [(half, kind, thr) for half in (False, True) for kind, thr in TARGETS]
    rows = []
    for half, kind, thr in plan:
        td = str(G.table_dir(half, kind))
        name = C.target_name(G.SET, thr)
        d = T.tune_table(td)
        if C.table_target(d)[0] != thr:
            raise SystemExit("table %s is not a %d kt table" % (td, thr))
        print("%s-%s: %d tune rows (%d positive), low_models=%r" % (
            G.variant_name(half), kind, len(d), int(d.y.sum()), C.table_low_models(d)), flush=True)
        folds = sorted(d.fold.unique().tolist())
        jobs = [(td, name, k, str(G.models_root(half))) for k in folds + ["final"]]
        t0 = time.time()
        # one table at a time: the main process and each worker hold one copy (the machine's memory is shared)
        with mp.get_context("spawn").Pool(a.workers, initializer=init) as pool:
            res = pool.map(T.fit_job, jobs, chunksize=1)
        print("fitted %d models in %.0fs" % (len(jobs), time.time() - t0), flush=True)
        oof = np.full(len(d), np.nan)
        for r in res:
            if r[2] is not None:
                oof[r[2]] = r[3]
        root = G.models_root(half)
        meta = {"set": name, "thr": thr, "cand_rule": kind, "features": G.SET_COLS, "params": C.HGB_PARAMS,
                "table": td, "no_low": bool(d["no_low"].iloc[0]), "low_models": C.table_low_models(d),
                "gefs_half_deg": half, "folds": folds, "n_tune_rows": int(len(d)),
                "sklearn": __import__("sklearn").__version__}
        json.dump(meta, open(C.models_dir(root, name) / "meta.json", "w"), indent=1)
        o = d[["basin", "cycle", "step", "row", "col", "fold", "y", "w"]].copy()
        o["p"] = oof.astype(np.float32)
        (G.root() / "oof").mkdir(parents=True, exist_ok=True)
        o.to_parquet(G.root() / "oof" / ("%s-%s.parquet" % (G.variant_name(half), kind)), index=False)
        refs = ({"p48_nb": d["p48_nb"].to_numpy()} if thr == 48
                else {"p34": d["p34"].to_numpy(), "p34_nb": d["p34_nb"].to_numpy()})
        ref = next(iter(refs))
        for scope, idx in [("both", np.arange(len(d)))] + [(b, np.nonzero(d.basin.to_numpy() == b)[0])
                                                          for b in C.BASIN_LIST]:
            sub = d.iloc[idx]
            preds = {k: v[idx] for k, v in refs.items()}
            preds["gefs-core"] = oof[idx]
            for r in T.metrics(sub, preds, a.boot, ref=ref):
                r.update(variant=G.variant_name(half), target=kind, basin=scope)
                rows.append(r)
        T._TABLE.clear()
        del d, o
    out = pd.DataFrame(rows)
    lead = ["variant", "target", "basin", "model", "n_rows", "n_pos", "n_weeks", "base_rate", "bss", "bss_lo", "bss_hi",
            "auc", "auc_lo", "auc_hi"]
    out = out[lead + [c for c in out.columns if c not in lead]]
    Path(a.results).mkdir(parents=True, exist_ok=True)
    out.to_csv(Path(a.results) / "cv_metrics.csv", index=False, float_format="%.4f")
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(out[lead].round(3).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
