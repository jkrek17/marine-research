"""Shared pieces of the core-lift retrain scripts (train.py, predict.py, score.py): feature sets, the live
model, the training table, the whole-week folds and the cache layout. Study-only; the general pieces
(features, truth, tile and Brier scores, week bootstraps) live in rk/."""
import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import cases, features, paths  # noqa: E402

WINDOW = (dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31))
STEPS = cases.STEPS
BASIN_LIST = ("natl", "npac")
N_FOLDS = 5

# Feature sets by name. "+basin" adds the 0/1 Pacific flag (one model for both basins, Jason 2026-10-16).
SETS = {
    "live28": list(features.FEATURES),
    "live28+basin": list(features.FEATURES) + ["basin_pac"],
    "store": [f for f in features.FEATURES if f not in features.LOW_FEATURES],
    "store+basin": [f for f in features.FEATURES if f not in features.LOW_FEATURES] + ["basin_pac"],
}
# The live page's settings (core_model.json note / lift.py): never tuned here.
HGB_PARAMS = dict(max_iter=300, max_depth=4, learning_rate=0.08, min_samples_leaf=200, l2_regularization=1.0,
                  max_bins=64, early_stopping=False, random_state=0)


def default_root():
    return paths.data("extra", "core-lift-retrain")


def low_tag(low_models):
    """'gfs+ifs+aifs' style string for the table column / flag; '' when there are no low-level features."""
    return "+".join(low_models)


def make_model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(**HGB_PARAMS)


# ---- the table ----

def load_table(table_dir):
    files = sorted(Path(table_dir).glob("*/*.parquet"))
    if not files:
        raise SystemExit("no parquet files under %s" % table_dir)
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if "low_models" not in d:    # tables built before the column existed: the live three, or none
        d["low_models"] = np.where(d["no_low"] == 1, "", low_tag(features.MODELS))
    return d


def table_low_models(d):
    u = sorted(d["low_models"].unique())
    if len(u) != 1:
        raise SystemExit("table mixes low-level feature definitions: %s" % u)
    return u[0]


def cycle_dt(tag):
    return cases.parse(tag)


def iso_week(cycle):
    y, w, _ = cycle.isocalendar()
    return (int(y), int(w))


def tune_weeks():
    """Sorted ISO weeks (year, week) of the study window that are not held out. Fixed by the calendar, not by
    what a partial table happens to hold, so a case's fold never changes."""
    ws = set()
    d = WINDOW[0]
    while d <= WINDOW[1]:
        if not cases.held_out(d):
            ws.add(iso_week(d))
        d += dt.timedelta(days=1)
    return sorted(ws)


_FOLD = {w: i % N_FOLDS for i, w in enumerate(tune_weeks())}


def fold_of(cycle):
    """Fold 0..4 of a tune-week cycle (tune week index mod 5); None for a held-out week."""
    if cases.held_out(cycle):
        return None
    return _FOLD[iso_week(cycle)]


def week_id(cycle_tags):
    """Array of year*100+week for a Series of cycle tags (the id rk.compare uses)."""
    u = {t: iso_week(cycle_dt(t)) for t in pd.unique(cycle_tags)}
    return np.array([u[t][0] * 100 + u[t][1] for t in cycle_tags])


def add_fold(d):
    u = {t: fold_of(cycle_dt(t)) for t in d["cycle"].unique()}
    d["fold"] = d["cycle"].map(u)
    return d


# ---- the live model ----

def find_awips(arg=None):
    for p in (arg, os.environ.get("AWIPS_TOOLS"), HERE.parents[2] / "awips-tools"):
        if p and (Path(p) / "marine_wind" / "pipeline" / "storm.py").exists():
            return Path(p) / "marine_wind" / "pipeline"
    raise SystemExit("awips-tools checkout not found: set AWIPS_TOOLS or put it beside this repo")


_LIVE = {}


def live_model():
    """(model dict, storm module) of the live page's core model."""
    if not _LIVE:
        pipe = find_awips()
        sys.path.insert(0, str(pipe))
        import importlib
        _LIVE["storm"] = importlib.import_module("storm")
        _LIVE["model"] = json.load(open(pipe / "core_model.json"))
        assert tuple(_LIVE["model"]["features"]) == features.FEATURES, "live feature order changed"
    return _LIVE["model"], _LIVE["storm"]


def live_predict(X):
    """Live probability for X [n, 28] in core_model.json feature order (storm.core_predict)."""
    m, storm = live_model()
    X = np.asarray(X, np.float64)
    out = np.empty(len(X))
    for i in range(0, len(X), 200000):
        out[i:i + 200000] = storm.core_predict(X[i:i + 200000], m)
    return out


def live_predict_table(d):
    m, _ = live_model()
    return live_predict(d[list(m["features"])].to_numpy(np.float64))


# ---- cache layout ----

def models_dir(root, name):
    return Path(root) / "models" / name


def p_path(root, name, basin, cycle, step):
    return Path(root) / "P" / name / basin / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def all_cases(basins, steps, start=None, end=None):
    start, end = start or WINDOW[0], end or WINDOW[1]
    out = []
    for b in basins:
        cyc = sorted(cases.cycles(b, start, end, hour=0) + cases.cycles(b, start, end, hour=12))
        out += [(b, c, s) for c in cyc for s in steps]
    return out


def save_npz(path, **arrays):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)
