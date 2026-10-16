"""Tests for rk.truth. Run with pytest or `python3 tests/test_truth.py`. Offline unit tests only;
the live checks are in the study notes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import KT, truth  # noqa: E402


def test_enw_to_real_direction():
    unst = float(truth.enw_to_real(20.0, -4.0))
    stab = float(truth.enw_to_real(20.0, 3.0))
    assert 0.3 / KT < (20.0 - unst) / KT < 1.2 and unst < 20.0, unst
    assert 0.2 / KT < (stab - 20.0) / KT < 1.2 and stab > 20.0, stab


def test_enw_to_real_neutral():
    for v in (10.0, 20.0, 45.0):
        assert abs(float(truth.enw_to_real(v, 0.0)) - v) < 0.3, v


def test_enw_to_real_array():
    out = truth.enw_to_real(np.array([20.0, 20.0, 20.0]), np.array([-4.0, 0.0, 3.0]))
    assert out[0] < out[1] < out[2]


def test_charnock_factor():
    f = truth.charnock_factor(np.array([5.0, 10.0, 20.0]), 4.0)
    assert np.all(f > 1.0) and np.all(f < 1.3)


def test_canon_and_lists():
    assert truth.canon(["4400123", "ABCD1", "1234567"]).tolist() == ["44123", "ABCD1", "1234567"]
    assert len(truth.fixed_stations()) == 75
    assert len(truth.blacklist()) > 100 and "NTKM3" in truth.blacklist()


def test_platform():
    sid = np.array(["41001", "41001", "SHIP1", "SHIP1", "ABCD1", "ABCD1"])
    lat = np.array([30.0, 30.0, 40.0, 41.0, 50.0, 50.0])
    lon = np.array([300.0] * 6)
    assert truth._platform(sid, lat, lon).tolist() == ["buoy", "buoy", "ship", "ship", "fixed", "fixed"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
