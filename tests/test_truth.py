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


def test_intercal():
    spd = np.array([50.0, 50.0, 50.0, 0.0, 0.0, 70.0, 70.0])
    sat = np.array([2, 3, 4, 2, 3, 2, 3])
    out = truth._intercal(spd, sat)
    assert abs(out[0] - (50 - 0.42)) < 1e-4 and abs(out[1] - (50 + 0.42)) < 1e-4
    assert out[2] == 50.0 and out[3] == 0.0 and out[4] == 0.0
    assert abs(out[5] - (70 - 0.625)) < 1e-4 and abs(out[6] - (70 + 0.625)) < 1e-4


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


def _smap_blob():
    """A tiny synthetic SMAP-layout netCDF (full 720 x 1440 x 2 grid, mostly missing) built in memory."""
    import netCDF4
    w = np.full((720, 1440, 2), -9999, np.int16)
    m = np.full((720, 1440, 2), -9999, np.int16)
    lat = -89.875 + 0.25 * np.arange(720)
    for la, lo, nd, wind, minute in ((50.125, 200.125, 0, 2500, 1100), (50.125, 200.125, 1, 1000, 370),
                                     (14.875, 10.125, 0, 500, 60), (70.125, 10.125, 1, 500, 60),
                                     (30.125, 359.875, 1, 0, 1439)):
        w[np.argmin(abs(lat - la)), int(round((lo - 0.125) / 0.25)), nd] = wind
        m[np.argmin(abs(lat - la)), int(round((lo - 0.125) / 0.25)), nd] = minute
    w[np.argmin(abs(lat - 40.125)), 5, 0] = 1500          # wind present, minute missing: dropped
    ds = netCDF4.Dataset("s.nc", "w", memory=1 << 20)
    for n, k in (("lat", 720), ("lon", 1440), ("node", 2)):
        ds.createDimension(n, k)
    ds.createVariable("lat", "f4", ("lat",))[:] = lat
    ds.createVariable("lon", "f4", ("lon",))[:] = 0.125 + 0.25 * np.arange(1440)
    for n, a in (("wind", w), ("minute", m)):
        v = ds.createVariable(n, "i2", ("lat", "lon", "node"))
        v.set_auto_maskandscale(False)
        v[:] = a
    blob = ds.close()
    return bytes(blob)


def test_smap_cells():
    c = truth._smap_cells(_smap_blob())
    assert len(c["lat"]) == 3, len(c["lat"])             # 14.875 and 70.125 cut, missing minute dropped
    o = np.argsort(c["node"].astype(int) * 10000 + c["t_min"])
    assert c["node"][o].tolist() == [0, 1, 1] and c["t_min"][o].tolist() == [1100, 370, 1439]
    assert np.allclose(c["spd_enw_kt"][o], np.array([25.0, 10.0, 0.0]) * KT)   # 0.01 m/s scale, 0 kept
    assert np.allclose(c["lat"][o][:2], 50.125) and np.allclose(c["lon"][o][:2], 200.125) and c["lon"].max() > 359
    assert c["spd_enw_kt"].dtype == np.float32 and c["t_min"].dtype == np.int16 and c["node"].dtype == np.uint8


def test_smap_not_posted_guard():
    class R:
        content = b"<html>404</html>"
    real = truth.fetch.get
    truth.fetch.get = lambda url, rng=None: R()
    try:
        assert truth._smap_get(__import__("datetime").date(2026, 1, 1), "FINAL") is None
    finally:
        truth.fetch.get = real


def test_ascat_grid_snaps_without_gaps():
    # two adjacent RSS rows/columns (centres at x.125 / x.375) must land on adjacent grid rows/columns
    from rk.basins import grid
    lats, lons = grid("natl")
    lat = np.array([60.125, 59.875, 60.125, 59.875], np.float32)
    lon = np.array([320.125, 320.125, 320.375, 320.375], np.float32)
    real = truth.ascat
    truth.ascat = lambda basin, valid, **kw: dict(lat=lat, lon=lon, spd_kt=np.array([50, 40, 30, 20], np.float32))
    try:
        seen, spd = truth.ascat_grid("natl", None)
    finally:
        truth.ascat = real
    iy, ix = np.nonzero(seen)
    assert seen.sum() == 4 and np.ptp(iy) == 1 and np.ptp(ix) == 1, (iy, ix)
    assert spd.max() == 50


def test_hf_archive_parse(tmp=None):
    import datetime as dt, tempfile
    from rk import paths
    old = truth.data
    with tempfile.TemporaryDirectory() as d:
        truth.data = lambda *p: Path(d).joinpath(*[str(x) for x in p])
        Path(d, "truth", "hf_lows").mkdir(parents=True)
        Path(d, "truth", "hf_lows", "HF_Data_-_Pac.csv").write_text(
            "ID,date,Latitude,Longitude,Category,Pressure\n"
            "1,2026010112,49.3,171.8,HF,982\n1,2026010112,45,-170,S,nopres\n2,2026010112,20,150,HF,990\n3,2018232906,50,180,HF,960\n")
        try:
            a = truth.hf_archive("npac")
            f = truth.hf_fixes("npac", dt.datetime(2026, 1, 1, 12))
        finally:
            truth.data = old
    assert len(a) == 3 and np.isnan(a["hpa"][1]) and a["lon"][1] == 190.0     # typo date 2018232906 dropped
    assert len(f) == 1 and f["hpa"][0] == 982          # S dropped; 20N lies outside the box


def test_ascat_fallback_06z():
    """Live check (needs the shared ASCAT cache): 06Z has cells via the 00Z mask; 00Z is unchanged by the fallback."""
    import datetime as dt
    try:
        a = truth.ascat("npac", dt.datetime(2026, 1, 16, 6))
        b = truth.ascat("natl", dt.datetime(2026, 1, 16, 0))
    except Exception as e:  # no network or cache
        print("note: live ascat check skipped:", repr(e)[:60])
        return
    if a is None:
        print("note: ASCAT cache not available, 06Z check skipped")
        return
    assert len(a["spd_kt"]) > 100
    assert truth.mask_time("natl", dt.datetime(2026, 1, 16, 0)) == dt.datetime(2026, 1, 16, 0)
    assert truth.mask_time("npac", dt.datetime(2026, 1, 16, 6)) == dt.datetime(2026, 1, 16, 0)
    assert b is not None and len(b["spd_kt"]) > 100


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
