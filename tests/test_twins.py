"""Tests for rk.twins on synthetic fields. Run: python3 tests/test_twins.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import datetime as dt
import numpy as np
from rk import twins


def test_geometry():
    la, lo = twins.destination(50.0, 330.0, 90.0 + twins.PBANG, twins.PR)
    assert abs(la[6, 6] - 50.0) < 1e-9 and abs(lo[6, 6] - 330.0) < 1e-9          # centre
    assert la[0, 6] > 50 > la[12, 6] or la[0, 6] < 50 < la[12, 6]                 # rows run north-south
    edge = twins.PR[6, 0]
    assert abs(edge - 6 * twins.DKM) < 1e-6 and abs(edge - 926.0) < 0.1


def test_sample_and_patch():
    lat = -90 + 1.5 * np.arange(121)
    f = np.repeat(lat[:, None], 240, 1)                                          # field = latitude
    assert abs(twins.sample(f, np.array([45.75]), np.array([10.0]))[0] - 45.75) < 1e-9
    fields = {c: f for c in twins.CH}
    p = twins.patch(fields, 45.0, 200.0)
    assert p.shape == (6, 13, 13) and abs(float(p[0, 6, 6]) - 45.0) < 0.05


def test_coarsen_constant_and_orientation():
    a = np.full((721, 1440), 7.0)
    c = twins.coarsen(a)
    assert c.shape == (121, 240) and np.allclose(c, 7.0)
    lat = np.linspace(90, -90, 721)
    c = twins.coarsen(np.repeat(lat[:, None], 1440, 1))
    assert c[0, 0] < -80 and c[-1, 0] > 80                                       # output runs south to north


def test_anomalies():
    clim = {"hour": np.array([0, 12]), "doy": np.arange(1, 367)}
    for k in ("z500", "msl", "u250", "v250"):
        clim[k] = np.ones((2, 366, 121, 240), np.float16)
    z = np.full((121, 240), 5.0)
    a = twins.anomalies(z, z, z, z, clim, dt.datetime(2026, 1, 15, 12))
    assert np.allclose(a["a_z500"], 4.0) and np.allclose(a["msl"], 5.0)


def test_twins_pick():
    lib = {"pcs": np.array([[0.0], [0.1], [0.2], [5.0]]), "track": np.array([1, 1, 2, 3]),
           "season": np.array([2015, 2015, 2016, 2017]), "gcls": np.array([3, 3, 2, 0], np.int8)}
    t = twins.twins(lib, np.array([0.0]), k=3, show=2)
    assert t["counts"] == [0, 0, 1, 2] and abs(t["hf_share"] - 2 / 3) < 1e-12
    assert t["closest"] == [0, 2]                                                # one per storm
    t = twins.twins(lib, np.array([0.0]), k=2, exclude_season=2015)
    assert t["counts"] == [1, 0, 1, 0]


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
