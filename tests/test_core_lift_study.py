"""Offline tests of the core-lift study's own pieces (fold assignment, lift products, train metrics).
Run: python3 tests/test_core_lift_study.py"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-16-core-lift-retrain"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import score as S  # noqa: E402
import train as T  # noqa: E402
from rk import cases  # noqa: E402


def test_folds():
    ws = C.tune_weeks()
    assert len(ws) > 15 and all(not cases.held_out(dt.datetime.fromisocalendar(y, w, 3)) for y, w in ws)
    f = [C.fold_of(dt.datetime.fromisocalendar(y, w, 3)) for y, w in ws]
    assert f == [i % 5 for i in range(len(ws))] and set(f) == set(range(5))
    held = next(dt.datetime(2025, 11, 1) + dt.timedelta(days=i) for i in range(30)
                if cases.held_out(dt.datetime(2025, 11, 1) + dt.timedelta(days=i)))
    assert C.fold_of(held) is None
    # a whole ISO week shares one fold
    d = dt.datetime(2025, 12, 1)
    assert len({C.fold_of(d + dt.timedelta(days=i)) for i in range(7)}) == 1


def test_sets():
    assert len(C.SETS["live28"]) == 28 and C.SETS["live28+basin"][-1] == "basin_pac"
    assert len(C.SETS["store"]) == 20 and not set(C.SETS["store"]) & set(__import__("rk").features.LOW_FEATURES)


def test_products():
    r10 = np.array([[40., 46.], [30., 50.]], np.float32)
    cand = np.ones((2, 2), bool)
    Pl = np.array([[0.4, 0.1], [0.9, 0.0]], np.float16)
    Pn = np.array([[0.1, 0.6], [0.25, 0.0]], np.float16)
    p48 = np.array([[0.0, 0.0], [0.25, 0.5]])
    pr = S.products(r10, p48, cand, Pl, Pn)
    assert set(pr) == set(S.product_names())
    assert np.allclose(pr["blend"], r10)
    assert np.allclose(pr["live_lift"], [[45, 46], [35, 50]])                 # Pl >= 0.35
    assert np.allclose(pr["lift5@0.35"], [[40, 51], [30, 50]])
    assert np.allclose(pr["lift3@0.20"], [[40, 49], [33, 50]])
    assert np.allclose(pr["lift8@0.50"], [[40, 54], [30, 50]])
    assert np.allclose(pr["kP10"], r10 + 10 * np.array([[0.1, 0.6], [0.25, 0.0]]), atol=2e-2)
    assert np.allclose(pr["member@0.2"], [[40, 46], [35, 55]]) and np.allclose(pr["member@0.1"], pr["member@0.2"])
    assert np.allclose(pr["member@0.3"], [[40, 46], [30, 55]])
    off = S.products(r10, p48, np.zeros((2, 2), bool), Pl, Pn)               # member rule only on candidates
    assert np.allclose(off["member@0.1"], r10)


def test_train_metrics():
    rng = np.random.default_rng(0)
    cyc = [dt.datetime(2025, 12, 1) + dt.timedelta(days=int(i)) for i in rng.integers(0, 60, 3000)]
    sub = pd.DataFrame({"cycle": [cases.tag(c.replace(hour=0)) for c in cyc]})
    p = rng.random(3000)
    sub["y"] = (rng.random(3000) < p).astype(int)
    sub["w"] = np.where(rng.random(3000) < 0.5, 1.0, 6.67)
    rows = T.metrics(sub, {"live": np.clip(p + rng.normal(0, 0.3, 3000), 0, 1), "good": p}, 200)
    live, good = rows
    assert good["bss"] > live["bss"] and good["auc"] > live["auc"]
    assert good["bss_lo"] < good["bss"] < good["bss_hi"] and good["auc_lo"] < good["auc"] < good["auc_hi"]
    assert good["dbss_lo"] > 0 and good["dauc_lo"] > 0 and good["n_weeks"] >= 8


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
