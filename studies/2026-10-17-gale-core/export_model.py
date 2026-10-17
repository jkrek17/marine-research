#!/usr/bin/env python3
"""Export the gale-core model (final.joblib, fit on all tune weeks) to the marine wind page's tree JSON format
(awips-tools marine_wind/pipeline/core_model.json, read by storm.core_predict), and check the export.

  python3 export_model.py MODEL_DIR OUT_JSON [--table TABLE_DIR] [--rows 200000]

MODEL_DIR holds final.joblib and meta.json (train.py --thr 34). The check evaluates the JSON with the page's
own storm.core_predict (AWIPS_TOOLS) and compares with sklearn predict_proba on table rows; it fails above
1e-6. Features in model order; "basin_pac" is 0 for the Atlantic, 1 for the Pacific."""
import argparse
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-16-core-lift-retrain"))
sys.path.insert(0, str(HERE.parent.parent))


def export(model, features, note):
    trees = []
    for (pred,) in model._predictors:
        n = pred.nodes
        trees.append({"f": n["feature_idx"].astype(int).tolist(), "t": n["num_threshold"].astype(float).tolist(),
                      "ml": n["missing_go_to_left"].astype(int).tolist(), "l": n["left"].astype(int).tolist(),
                      "r": n["right"].astype(int).tolist(), "leaf": n["is_leaf"].astype(int).tolist(),
                      "v": n["value"].astype(float).tolist()})
    return {"features": list(features), "baseline": float(np.ravel(model._baseline_prediction)[0]),
            "trees": trees, "note": note}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_dir")
    ap.add_argument("out")
    ap.add_argument("--table", default=None)
    ap.add_argument("--rows", type=int, default=200000)
    a = ap.parse_args()
    md = Path(a.model_dir)
    model = joblib.load(md / "final.joblib")
    meta = json.load(open(md / "meta.json"))
    feats = meta["features"]
    note = ("HistGradientBoosting (sklearn) trained on winter 2025-26 both basins (tune weeks), truth = ASCAT real "
            "10 m wind 34+ within ~50 km; candidate cells blend >= 24 kt or any model >= 30 kt; feature basin_pac "
            "0 Atlantic, 1 Pacific. marine-research studies/2026-10-17-gale-core")
    m = export(model, feats, note)
    with open(a.out, "w") as fh:
        json.dump(m, fh, separators=(",", ":"))
    print("wrote %s: %d trees, %d features, %.1f MB" % (a.out, len(m["trees"]), len(feats), os.path.getsize(a.out) / 1e6))
    if a.table:
        import common as C
        sys.path.insert(0, str(Path(os.environ.get("AWIPS_TOOLS", HERE.parents[3] / "awips-tools")) / "marine_wind" / "pipeline"))
        import storm
        d = C.load_table(a.table)
        d = d.sample(min(a.rows, len(d)), random_state=0)
        X = d[feats].to_numpy(np.float64)
        p_sk = model.predict_proba(X)[:, 1]
        p_js = storm.core_predict(X, json.load(open(a.out)))
        err = float(np.max(np.abs(p_sk - p_js)))
        print("check on %d table rows: max |sklearn - page core_predict| = %.2e" % (len(X), err))
        if err > 1e-6:
            sys.exit("export check FAILED")


if __name__ == "__main__":
    main()
