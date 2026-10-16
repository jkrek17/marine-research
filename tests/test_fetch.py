"""Tests for rk.fetch. Run with pytest or `python3 tests/test_fetch.py`. Offline: nwp is monkeypatched."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nwp  # noqa: E402

from rk import fetch  # noqa: E402

C = dt.datetime(2026, 1, 15, 12)


def _patched():
    """Index found, every record request 404s (nwp.get -> None)."""
    saved = (nwp.ncep_index, nwp.ec_records, nwp.get)
    keys = ("UGRD:10 m above ground", "VGRD:10 m above ground", "PRMSL:mean sea level",
            "LAND:surface", "ICEC:surface")
    nwp.ncep_index = lambda url: {k: (i * 10, i * 10 + 9) for i, k in enumerate(keys)}
    nwp.ec_records = lambda base: [{"levtype": "sfc", "param": p, "_offset": 0, "_length": 10, "number": 0}
                                   for p in ("10u", "10v", "msl")]
    nwp.get = lambda url, rng=None, tries=8: None
    return saved


def _restore(saved):
    nwp.ncep_index, nwp.ec_records, nwp.get = saved


def test_record_404_is_missing_not_a_crash():
    saved = _patched()
    try:
        assert fetch.det("gfs", C, 24) is None
        assert fetch.det("ifs", C, 24) is None
        assert fetch.det("aifs", C, 24) is None
        assert fetch.gfs_mask(C) is None
        assert fetch.gdas_background(C) is None
        assert fetch.members("gefs", C, 24) is None
        assert fetch.members("ens", C, 24) is None
    finally:
        _restore(saved)


def test_other_errors_still_raise():
    saved = _patched()
    try:
        nwp.ncep_index = lambda url: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            fetch.det("gfs", C, 24)
        except RuntimeError:
            return
        raise AssertionError("RuntimeError was swallowed")
    finally:
        _restore(saved)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
