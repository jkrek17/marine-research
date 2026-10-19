"""Tests for rk.fetch. Run with pytest or `python3 tests/test_fetch.py`. Offline: nwp is monkeypatched.
The record-404 case is handled inside nwp (awips-tools PR #108); rk must just report "not posted" (None)."""
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


def test_nwp_record_404_reports_not_posted():
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


class _R:
    def __init__(self, text):
        self.text = text


def test_reforecast_url_and_index():
    d = dt.datetime(2010, 1, 1)
    assert fetch.reforecast_url(d, "p01") == (fetch.REFORECAST + "/2010/2010010100/p01/Days:1-10/"
                                              "pres_msl_2010010100_p01.grib2")
    idx = "\n".join(["1:0:d=2010010100:PRES:mean sea level:3 hour fcst:ENS=+1",
                      "2:100:d=2010010100:PRES:mean sea level:6 hour fcst:ENS=+1",
                      "3:250:d=2010010100:PRES:mean sea level:9 hour fcst:ENS=+1"])
    saved = fetch.get
    fetch.get = lambda url, rng=None, tries=8: _R(idx) if url.endswith(".idx") else None
    try:
        assert fetch.reforecast_index("x") == {3: (0, 99), 6: (100, 249), 9: (250, None)}
        assert fetch.gefs_reforecast(d, "c00", (6, 12)) == {}      # record not there: step left out
        fetch.get = lambda url, rng=None, tries=8: None
        assert fetch.gefs_reforecast(d, "c00", (6,)) is None      # no file: None
    finally:
        fetch.get = saved


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
