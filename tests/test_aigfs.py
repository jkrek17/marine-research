"""Offline tests for the aigfs model (cases, fetch dispatch, store names) and rk.features.det_blend against a
direct numpy copy of awips-tools build.py nomem_blend / support_base. Run: python3 tests/test_aigfs.py"""
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import cases, features, fetch, store  # noqa: E402

SUPPORT_KT, CAP_KT, NOMEM_K = 5.0, 5.0, 0.3   # build.py
CYCLE = dt.datetime(2026, 1, 15, 12)
STEP = 48
SHAPE = (5, 6)


def _fake_loader(models, lags=(0, 12, 24), seed=0):
    """store.load_det stand-in: one random speed grid per (model, cycle, step) actually requested."""
    rng = np.random.default_rng(seed)
    table = {}
    for lag in lags:
        for m in models:
            table[(m, CYCLE - dt.timedelta(hours=lag), STEP + lag)] = rng.uniform(5, 60, SHAPE).astype(np.float32)

    def load(basin, cycle, model, step):
        s = table.get((model, cycle, step))
        return None if s is None else {"speed": s}
    return table, load


def _build_py(speeds, lagged, model_weight):
    """build.py: nomem_blend + support_base, with MODEL_WEIGHT as an array per model."""
    runs = np.concatenate([speeds] + lagged)
    mw = np.array(model_weight, float)[:, None, None]
    w = np.array([np.exp(-0.5 * ((runs - s[None]) / SUPPORT_KT) ** 2).mean(0) for s in speeds]) * mw + 1e-6
    return (w * speeds).sum(0) / w.sum(0) + np.minimum(NOMEM_K * runs.std(0), CAP_KT)


def _run(models, weights, monkey_seed=0):
    table, load = _fake_loader(models, seed=monkey_seed)
    old, store.load_det = store.load_det, load
    try:
        out = features.det_blend("natl", CYCLE, STEP, models=models, weights=weights)
    finally:
        store.load_det = old
    speeds = np.array([table[(m, CYCLE, STEP)] for m in models])
    lagged = [np.array([table[(m, CYCLE - dt.timedelta(hours=lag), STEP + lag)] for m in models]) for lag in (12, 24)]
    return out, speeds, lagged


def test_three_models_match_build_py():
    models = ("gfs", "ifs", "aigfs")
    out, speeds, lagged = _run(models, {"aigfs": 0.5})
    ref = _build_py(speeds, lagged, [1, 1, 0.5])
    assert out["runs"] == 9 and out["r10"].dtype == np.float32 and out["r10"].shape == SHAPE
    assert np.allclose(out["r10"], ref, atol=1e-4)
    # the weights matter: equal weights differ
    eq, _, _ = _run(models, None)
    assert not np.allclose(eq["r10"], out["r10"], atol=1e-3)
    assert np.allclose(eq["r10"], _build_py(speeds, lagged, [1, 1, 1]), atol=1e-4)


def test_default_models_aifs_half():
    out, speeds, lagged = _run(("gfs", "ifs", "aifs"), {"aifs": 0.5}, monkey_seed=3)
    assert np.allclose(out["r10"], _build_py(speeds, lagged, [1, 1, 0.5]), atol=1e-4)


def test_two_models_six_runs():
    out, speeds, lagged = _run(("gfs", "ifs"), None, monkey_seed=5)
    assert out["runs"] == 6
    assert np.allclose(out["r10"], _build_py(speeds, lagged, [1, 1]), atol=1e-4)


def test_weight_zero_removes_the_model_from_the_base():
    models = ("gfs", "ifs", "aigfs")
    out, speeds, lagged = _run(models, {"aigfs": 0.0}, monkey_seed=7)
    runs = np.concatenate([speeds] + lagged)
    w = np.array([np.exp(-0.5 * ((runs - s[None]) / SUPPORT_KT) ** 2).mean(0) for s in speeds[:2]]) + 1e-6
    base2 = (w * speeds[:2]).sum(0) / w.sum(0)     # AI-GFS still shapes the spread, never the base
    # its weight is 1e-6, so the base is the two-model base to within 1e-4 kt of rounding
    assert np.allclose(out["r10"], base2 + np.minimum(NOMEM_K * runs.std(0), CAP_KT), atol=1e-3)


def test_cap_and_missing():
    models = ("gfs", "ifs")
    table, load = _fake_loader(models)
    table[("gfs", CYCLE - dt.timedelta(hours=24), STEP + 24)] = np.full(SHAPE, 200, np.float32)  # huge spread
    old, store.load_det = store.load_det, load
    try:
        out = features.det_blend("natl", CYCLE, STEP, models=models)
        assert (out["r10"] - np.array([table[(m, CYCLE, STEP)] for m in models]).max(0) <= CAP_KT + 1e-3).all()
        assert features.det_blend("natl", CYCLE, STEP, models=("gfs", "ifs", "aigfs")) is None   # no aigfs runs
        assert features.det_blend("natl", CYCLE, STEP, models=models, lags=(12, 24, 36)) is None  # a lagged run missing
    finally:
        store.load_det = old


def test_available_aigfs():
    assert cases.available("aigfs", dt.datetime(2025, 1, 1, 0))
    assert cases.available("aigfs", dt.datetime(2026, 1, 15, 12))
    assert not cases.available("aigfs", dt.datetime(2024, 12, 31, 18))
    assert not cases.available("gfs", dt.datetime(2025, 1, 1))   # the others are unchanged


def test_aigfs_not_in_default_det():
    assert "aigfs" not in store.DET and "aigfs" in store.EXTRA_DET


def test_fetch_det_and_fill_names():
    """fetch.det('aigfs') cuts both basins from nwp.fields and converts Pa to hPa; fill(models=('aigfs',))
    stores aigfs_f{step}, load_det reads it back."""
    import tempfile
    calls = []
    g = np.ones((721, 1440), np.float32)

    def fields(src, cyc, step, names, **kw):
        calls.append((src, cyc, step, dict(names)))
        return {"u": g * 3, "v": g * 4, "msl": g * 101300}
    cyc = dt.datetime(2026, 1, 15, 0)
    saved = (fetch.nwp.fields, fetch.wait_for_quiet, store.paths.CACHE, os.environ.get("RK_OFFLINE"))
    fetch.nwp.fields, fetch.wait_for_quiet = fields, lambda: None
    os.environ["RK_OFFLINE"] = "1"
    try:
        with tempfile.TemporaryDirectory() as d:
            store.paths.CACHE = Path(d)
            res = fetch.det("aigfs", cyc, 24)
            assert calls[0][:3] == ("aigfs", "2026011500", 24)
            assert set(calls[0][3].values()) == {"u", "v", "msl"}
            assert set(res) == {"natl", "npac"} and abs(res["natl"]["msl"].mean() - 1013.0) < 1e-3
            rep = store.fill(cyc, steps=(24,), models=("aigfs",), ens=())
            assert rep["fetched"] == ["aigfs_f024"] and not rep["missing"]
            assert (Path(d) / "fields" / "npac" / "2026011500" / "aigfs_f024.npz").exists()
            got = store.load_det("natl", cyc, "aigfs", 24)
            assert abs(got["speed"].mean() - 5 * 1.943844) < 0.02 and abs(got["msl"].mean() - 1013.0) < 1e-2
            assert store.fill(cyc, steps=(24,), models=("aigfs",), ens=())["existing"] == ["aigfs_f024"]
    finally:
        fetch.nwp.fields, fetch.wait_for_quiet, store.paths.CACHE = saved[:3]
        if saved[3] is None:
            os.environ.pop("RK_OFFLINE", None)
        else:
            os.environ["RK_OFFLINE"] = saved[3]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
