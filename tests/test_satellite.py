"""Tests for rk.satellite (no network). Run with pytest or `python3 tests/test_satellite.py`."""
import datetime as dt
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import satellite as s, store  # noqa: E402


def _global(res=0.5):
    """A gridsat_ir()-like global dict: lat south to north, lon -180..180, tb raw int16 = lon in hundredths."""
    lat = np.arange(-70, 70, res, dtype=np.float32)
    lon = np.arange(-180, 180, res, dtype=np.float32)
    tb = np.round((np.broadcast_to(lon, (lat.size, lon.size)) + 180) * 10).astype(np.int16)
    return {"lat": lat, "lon": lon, "tb": tb, "sat": np.zeros(tb.shape, np.int8),
            "satnames": np.array(["GOES-16"]), "satlon": np.array([-75.0], np.float32)}


def test_cut_wraps_and_orders():
    c = s.cut(_global(), "natl")                   # 255..375 crosses 360
    assert c["lat"][0] > c["lat"][-1]               # north to south
    assert np.all(np.diff(c["lon"]) > 0) and c["lon"][0] >= 255 and c["lon"][-1] <= 375
    # the column at continuous lon 365 (= 5E) carries the source value of lon 5
    j = int(np.argmin(abs(c["lon"] - 365)))
    assert c["tb"][0, j] == round((5 + 180) * 10)
    c = s.cut(_global(), "npac")                    # 130..265 crosses the date line
    j = int(np.argmin(abs(c["lon"] - 200)))         # 160W
    assert c["tb"][0, j] == round((-160 + 180) * 10)


def test_destination_and_heading():
    la, lo = s.destination(50.0, -30.0, 90.0, 0.0)
    assert abs(la - 50) < 1e-9 and abs(lo + 30) < 1e-9
    la, lo = s.destination(50.0, -30.0, 0.0, 111.195)   # one degree north
    assert abs(la - 51) < 1e-3 and abs(lo + 30) < 1e-9
    assert abs(s.heading(50, -30, 51, -30)) < 1e-9
    assert abs(s.heading(0, 179.5, 0, -179.5) - 90) < 1e-6  # east across the date line


def _box_with_spot(lat0, lon0):
    """A box() dict on a 0.1 deg grid, 250 K everywhere except 200 K at one point."""
    lat = np.arange(70, 19.95, -0.1).astype(np.float32)
    lon = np.arange(255, 375.01, 0.1).astype(np.float32)
    tb = np.full((lat.size, lon.size), 250.0, np.float32)
    tb[int(round((70 - lat0) / 0.1)), int(round((lon0 % 360 - 255) / 0.1))] = 200.0
    return {"lat": lat, "lon": lon, "tb": tb}


def test_crop_north_up_and_rotated():
    # a cold spot 300 km north of the centre (50N 30W)
    sl, so = s.destination(50.0, -30.0, 0.0, 300.0)
    b = _box_with_spot(round(float(sl), 1), round(float(so), 1))
    c = s.crop(b, 50.0, -30.0, half_km=500, res_km=10)
    n = c.shape[0]
    r, k = np.unravel_index(np.nanargmin(c), c.shape)
    assert k == (n - 1) // 2 and abs(((n - 1) // 2 - r) * 10 - 300) <= 20     # straight up, ~300 km
    # storm moving east: the spot to the north is left of track -> left of the image
    c = s.crop(b, 50.0, -30.0, half_km=500, res_km=10, head=90.0)
    r, k = np.unravel_index(np.nanargmin(c), c.shape)
    assert r == (n - 1) // 2 and abs(((n - 1) // 2 - k) * 10 - 300) <= 20


def test_crop_missing_stays_missing():
    b = _box_with_spot(50.0, 330.0)
    b["tb"][:, :] = np.nan
    assert np.isnan(s.crop(b, 50.0, -30.0, half_km=100)).all()
    c = s.crop(b, 68.0, -30.0, half_km=600)          # runs past the box's north edge
    assert np.isnan(c).all()


def test_view_zenith():
    lat = np.array([60.0, 0.0], np.float32)
    lon = np.array([285.0, 345.0], np.float32)
    b = {"lat": lat, "lon": lon, "sat": np.zeros((2, 2), np.int8), "satlon": np.array([-75.0], np.float32)}
    v = s.view_zenith(b)
    assert v[1, 0] < 0.01                             # sub-satellite point
    assert 60 < v[0, 0] < 75                          # 60N under the satellite is slanted
    b["sat"][:] = -1
    assert np.isnan(s.view_zenith(b)).all()


def test_truth_kind_and_hours():
    assert store.truth_tag("gridsat", "natl", "2025011012") == "truth-gridsat-natl-202501"
    import datetime as dt
    try:
        s.box("natl", dt.datetime(2025, 1, 10, 3))
    except ValueError:
        pass
    else:
        raise AssertionError("3-hourly times must be refused")


class _Resp:
    def __init__(self, data, total):
        self.content, self.headers = data, {"Content-Range": "bytes 0-0/%d" % total}


def test_range_file_reads_like_bytes():
    blob = bytes(range(256)) * 50
    calls = []

    def fake_get(url, rng=None, tries=8):
        calls.append(rng)
        return _Resp(blob[rng[0]:rng[1] + 1], len(blob))

    real = s.fetch.get
    s.fetch.get = fake_get
    try:
        f = s.RangeFile("x", block=1000)
        r = io.BufferedReader(f)
        r.seek(990)
        assert r.read(30) == blob[990:1020]
        f.seek(len(blob) - 5)
        assert f.read(100) == blob[-5:]
        n0 = len(calls)
        f.seek(995)
        assert f.read(10) == blob[995:1005]          # blocks already held: no new request
        assert len(calls) == n0
    finally:
        s.fetch.get = real


def test_abi_xy_pug_example():
    # GOES-R PUG vol. 3, 5.1.2.8.1 worked example
    x, y, seen = s.abi_xy(np.array(33.846162), np.array(-84.690932), -75.0, 35786023.0, 6378137.0, 6356752.31414)
    assert abs(x - -0.024052) < 1e-6 and abs(y - 0.095340) < 1e-6 and seen
    x, y, seen = s.abi_xy(np.array([0.0, 0.0]), np.array([-75.0, 105.0]), -75.0, 35786023.0, 6378137.0,
                          6356752.31414)
    assert abs(x[0]) < 1e-12 and abs(y[0]) < 1e-12 and seen[0] and not seen[1]


def test_goes_for_handover():
    t = dt.datetime
    assert s.goes_for("natl", t(2017, 1, 1)) == []
    assert s.goes_for("natl", t(2024, 12, 1, 0)) == [16, 19]
    assert s.goes_for("natl", t(2025, 12, 1, 0)) == [19, 16]
    assert s.goes_for("npac", t(2022, 12, 1, 0)) == [17, 18]
    assert s.goes_for("npac", t(2024, 12, 1, 0)) == [18, 17]


def test_airmass_rgb_ranges():
    rgb = s.airmass_rgb(np.array([243.0, 208.0]), np.array([268.0, 200.0]), np.array([240.0, 300.0]),
                        np.array([280.0, 250.0]))
    assert rgb.shape == (2, 3)
    assert np.allclose(rgb[0], [0.0, 0.0, 0.0]) and np.allclose(rgb[1], [1.0, 1.0, 1.0])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
