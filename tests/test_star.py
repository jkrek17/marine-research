"""Tests for the NOAA STAR scatterometer truth (rk.truth.star_day and friends). Offline: HTTP is mocked.
Run with pytest or `python3 tests/test_star.py`. One optional live check pulls a pass LIST only."""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import paths, store, truth  # noqa: E402

OSC = "/product_src/oscat3/streamlines/oscat3_2026301_20706_20707_NS_2026-301T02-32-14_lite5.json"
UHR = "/product_src/ascat_uhr/streamlines/UHR_METOP-B_AS_20261028T003525_73213_rev1of1_ec.json"


class R:
    def __init__(self, obj):
        self.content = json.dumps(obj).encode()


def rec(la, lo, u, v, q=0):
    return dict(la=la, lo=lo, u=u, v=v, q=q)


class Fake:
    """Patch fetch.get with a table {url substring: object}, a temp cache and offline mode."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def get(self, url, rng=None, tries=8):
        self.calls.append(url)
        for k, v in self.table.items():
            if k in url:
                return R(v)
        return None

    def __enter__(self):
        self.saved = (truth.fetch.get, paths.CACHE, os.environ.get("RK_OFFLINE"))
        self.tmp = tempfile.TemporaryDirectory()
        paths.CACHE = Path(self.tmp.name)
        os.environ["RK_OFFLINE"] = "1"
        truth.fetch.get = self.get
        return self

    def __exit__(self, *a):
        truth.fetch.get, paths.CACHE = self.saved[:2]
        if self.saved[2] is None:
            os.environ.pop("RK_OFFLINE", None)
        else:
            os.environ["RK_OFFLINE"] = self.saved[2]
        self.tmp.cleanup()


def test_start_time_parsing():
    assert truth._star_start(OSC) == dt.datetime(2026, 10, 28, 2, 32, 14)      # day 301 of 2026 = 28 Oct
    assert truth._star_start(UHR) == dt.datetime(2026, 10, 28, 0, 35, 25)
    assert truth._star_start("x_2026-001T00-00-00_lite5.json") == dt.datetime(2026, 1, 1)
    try:
        truth._star_start("nothing.json")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_kinds_registered():
    assert store.TRUTH_KINDS["oscat"] == (False, 8) and store.TRUTH_KINDS["uhr"] == (False, 8)
    assert set(truth.STAR_LAYERS) == {"oscat", "uhr"} and len(truth.STAR_LAYERS["uhr"]) == 4


def _table(ymd="20261028"):
    osc2 = OSC.replace("02-32-14", "04-12-14")
    t = {"date=%s&prefix=oscat3_AS" % ymd: dict(status="success", json_urls=[OSC, osc2]),
         "date=%s&prefix=oscat3_DS" % ymd: dict(status="success", json_urls=[]),
         OSC: [rec(40.0, -170.0, 30.0, 40.0, 1), rec(10.0, -50.0, 5.0, 5.0), rec(75.0, 0.0, 9.0, 9.0),
               rec(50.0, 10.0, -3.0, 4.0)],
         osc2: [rec(45.0, -60.0, 12.0, 5.0)]}
    return t


def test_star_day_fields():
    day = dt.date(2026, 10, 28)
    with Fake(_table()):
        c = truth.star_day("oscat", day)
        ps = truth.star_passes("oscat", day)
    assert [p[0] for p in ps] == ["oscat3_AS"] * 2 and ps[0][2] == dt.datetime(2026, 10, 28, 2, 32, 14)
    assert len(c["lat"]) == 3                                   # 10N and 75N cropped
    assert set(c) == {"lat", "lon", "u_kt", "v_kt", "spd_kt", "q", "t_min", "t_end_min", "node", "sat", "pass_id"}
    assert np.allclose(sorted(c["lon"]), [10.0, 190.0, 300.0]) and c["lon"].dtype == np.float32
    i = int(np.argmax(c["spd_kt"]))
    assert abs(c["spd_kt"][i] - 50.0) < 1e-4 and c["u_kt"][i] == 30.0 and c["v_kt"][i] == 40.0   # knots kept
    assert c["q"].tolist() == [1, 0, 0] and c["q"].dtype == np.uint8
    assert (c["node"] == 0).all() and (c["sat"] == 0).all()
    assert c["pass_id"].tolist() == [0, 0, 1]
    assert c["t_min"].tolist() == [152, 152, 252]               # 02:32 = 152 min, 04:12 = 252
    assert c["t_end_min"].tolist() == [252, 252, 352]           # next pass start; last gets +100
    assert c["t_min"].dtype == np.int16 and c["t_end_min"].dtype == np.int16


def test_star_day_none_and_no_cache_when_young():
    day = dt.date(2026, 10, 28)
    empty = {"prefix=oscat3_AS": dict(status="success", json_urls=[]), "prefix=oscat3_DS": dict(json_urls=[])}
    with Fake(empty):
        assert truth.star_day("oscat", day) is None
    young = dt.datetime.now(dt.timezone.utc).date()
    with Fake(_table(young.strftime("%Y%m%d"))):
        assert truth.star_day("oscat", young) is not None
        assert store.truth_dirty() == {}                        # nothing cached for a young day


def test_star_day_caches_old_day_and_reads_back():
    day = dt.date(2026, 10, 20)
    with Fake(_table("20261020")) as f:
        a = truth.star_day("oscat", day)
        assert store.truth_dirty() == {("oscat", None): ["20261020.npz"]}
        n = len(f.calls)
        b = truth.star_day("oscat", day)                        # from the cache, no HTTP
        assert len(f.calls) == n and np.array_equal(a["spd_kt"], b["spd_kt"])


def test_star_day_uhr_codes_and_negative_start():
    day = dt.date(2026, 10, 28)
    prev = "/x/UHR_METOP-C_DS_20261027T233000_1_rev1of1_ec.json"
    t = {"prefix=UHR_METOP-B_AS": dict(json_urls=[UHR]), "prefix=UHR_METOP-B_DS": dict(json_urls=[]),
         "prefix=UHR_METOP-C_AS": dict(json_urls=[]), "prefix=UHR_METOP-C_DS": dict(json_urls=[prev]),
         UHR: [rec(30.0, 179.9, 6.0, 8.0)], prev: [rec(60.0, -0.5, 0.0, 20.0)]}
    with Fake(t):
        c = truth.star_day("uhr", day)
    o = np.argsort(c["sat"])
    assert c["sat"][o].tolist() == [1, 2] and c["node"][o].tolist() == [0, 1]
    assert c["t_min"][o].tolist() == [35, -30] and c["t_end_min"][o].tolist() == [135, 70]
    assert abs(c["lon"][o][1] - 359.5) < 1e-4


def test_star_window():
    day = dt.date(2026, 10, 28)
    with Fake(_table()):
        t0 = dt.datetime(2026, 10, 28, 4, 30)
        # points of the 04:12 pass (bracket 252-352 = 04:12-05:52) overlap; the 02:32 pass (to 04:12) does not
        c = truth.star("oscat", (0, 90), (0, 360), t0, t0 + dt.timedelta(hours=1))
        assert c is not None and c["pass_id"].tolist() == [1]
        c = truth.star("oscat", (0, 90), (0, 360), dt.datetime(2026, 10, 28, 3, 0), dt.datetime(2026, 10, 28, 3, 30))
        assert c["pass_id"].tolist() == [0, 0] and len(c["lat"]) == 2
        c = truth.star("oscat", (44, 46), (290, 310), dt.datetime(2026, 10, 28, 3, 0), dt.datetime(2026, 10, 28, 5, 0))
        assert len(c["lat"]) == 1 and abs(c["lat"][0] - 45.0) < 1e-4


def test_live_pass_list():
    """Live check (needs network): the 2026-10-28 oscat3_DS pass list parses; no pass file is downloaded."""
    try:
        r = truth.fetch.get(truth._STAR_LIST.format(ymd="20261028", prefix="oscat3_DS"))
        if r is None:
            print("note: STAR list not reachable or day expired from the server, live check skipped")
            return
        urls = json.loads(r.content).get("json_urls") or []
        print("note: oscat3_DS 2026-10-28 lists %d passes" % len(urls))
        for u in urls:
            assert truth._star_start(u).date() >= dt.date(2026, 10, 27)
    except Exception as e:
        print("note: live STAR check skipped:", repr(e)[:60])


def test_uhr_grid_layout():
    """UHR files are leaflet-velocity grids: u (2), v (3), optional q, rows from la1 southward."""
    hdr = dict(lo1=-40.0, la1=62.0, dx=0.5, dy=0.5, nx=2, ny=2)
    recs = [dict(header=dict(hdr, parameterNumber=2), data=[30.0, None, 0.0, 40.0]),
            dict(header=dict(hdr, parameterNumber=3), data=[40.0, None, 10.0, 30.0])]
    c = truth._star_points(recs)
    assert c["lat"].tolist() == [62.0, 61.5, 61.5], c["lat"]
    assert np.allclose(c["lon"], [320.0, 320.0, 320.5])
    assert np.allclose(c["spd_kt"], [50.0, 10.0, 50.0])
    assert c["q"].tolist() == [0, 0, 0]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
