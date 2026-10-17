"""Tests for the lower-level fields (rk.fetch.low key maps, rk.store.save_low / load_low). Offline.
Run with pytest or `python3 tests/test_low.py`."""
import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nwp  # noqa: E402
import numpy as np  # noqa: E402

from rk import fetch, store  # noqa: E402

C = dt.datetime(2025, 12, 1, 12)


def _r(gfs):
    rng = np.random.default_rng(1)
    r = {k: (270 + 10 * rng.random((6, 8))).astype(np.float32) for k in store.LOW_T}
    r.update({k: (30 * rng.standard_normal((6, 8))).astype(np.float32) for k in store.LOW_W})
    if gfs:
        r["land"] = (rng.random((6, 8)) > 0.5).astype(np.float32)
        r["ice"] = np.where(r["land"] > 0, 0, rng.random((6, 8))).astype(np.float32)
    return r


def test_roundtrip_gfs_and_ec():
    with tempfile.TemporaryDirectory() as d:
        for model, gfs in (("gfs", True), ("ifs", False)):
            r = _r(gfs)
            assert store.load_low("natl", C, model, 24, root=d) is None
            store.save_low("natl", C, model, 24, r, root=d)
            z = store.load_low("natl", C, model, 24, root=d)
            for k in store.LOW_T:   # temperatures keep full float32 precision
                assert z[k].dtype == np.float32 and np.array_equal(z[k], r[k])
            for k in store.LOW_W:   # winds float16
                assert np.allclose(z[k], r[k], atol=0.05, rtol=1e-3)
            assert ("land" in z) == gfs and ("ice" in z) == gfs
            if gfs:
                assert z["land"].dtype == bool and np.array_equal(z["land"], r["land"] >= 0.5)
                assert np.abs(z["ice"] - r["ice"]).max() <= 0.005 + 1e-6
        assert (Path(d) / "fields/natl/2025120112/gfs_low_f024.npz").exists()
        assert store.load_low("npac", C, "gfs", 24, root=d) is None


def test_key_maps():
    assert set(fetch.GFS_LOW.values()) == set(fetch.LOW_NAMES) | {"land", "ice"}
    assert "LAND:surface" in fetch.GFS_LOW and "ICEC:surface" in fetch.GFS_LOW
    assert fetch.GFS_LOW["TMP:925 mb"] == "t925"
    assert set(fetch._EC_LOW.values()) == set(fetch.LOW_NAMES)
    assert ("pl", "t", "925") in fetch._EC_LOW and ("sfc", "2t", None) in fetch._EC_LOW


def test_incomplete_or_unposted_is_none():
    saved = (nwp.ncep_index, nwp.ec_records, nwp.get)
    try:
        nwp.ncep_index = lambda url: {k: (i * 10, i * 10 + 9) for i, k in enumerate(fetch.GFS_LOW)}
        nwp.ec_records = lambda base: [{"levtype": "sfc", "param": "2t", "_offset": 0, "_length": 10, "number": 0}]
        nwp.get = lambda url, rng=None, tries=8: None
        for m in ("gfs", "ifs", "aifs"):
            assert fetch.low(m, C, 24) is None
    finally:
        nwp.ncep_index, nwp.ec_records, nwp.get = saved


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
