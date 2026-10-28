"""Tests for rk.storm_read (tracking one low through runs and members) and the tools/storm_read.py page, on synthetic
MSLP fields. Run: python3 tests/test_storm_read.py"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import numpy as np

from rk import basins, storm_read as sr
from rk.score import km

LATS, LONS = basins.grid("natl")
T0 = dt.datetime(2026, 11, 1, 0)
H6 = dt.timedelta(hours=6)
TIMES = [T0 + H6 * i for i in range(-4, 9)]


def low_field(centres, base=1016.0):
    """MSLP with Gaussian lows centred exactly on grid points: centres [(lat, lon, depth hPa)]."""
    y, x = np.meshgrid(np.arange(len(LATS)), np.arange(len(LONS)), indexing="ij")
    f = np.full(y.shape, base, np.float32)
    for la, lo, d in centres:
        cy, cx = int(round((LATS[0] - la) / 0.25)), int(round((lo - LONS[0]) / 0.25))
        f -= (d * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / 400.0)).astype(np.float32)
    return f


def moving_low(lat=45.0, lon0=315.0, dlon=1.0, deepen=6.0, far=True):
    """A low moving east dlon per 6 h and deepening `deepen` hPa per 6 h from 1004 at the first time; a second, deeper
    low parked far to the west."""
    out = {}
    for i, t in enumerate(TIMES):
        c = [(lat, lon0 + dlon * i, 12.0 + deepen * i)]
        if far:
            c.append((55.0, 295.0, 40.0))
        out[t] = low_field(c)
    return out


def test_moving_low_is_tracked_forward_and_far_low_ignored():
    msl = moving_low()
    t0 = TIMES[4]                                    # parent at T0 = index 4 (lon 319)
    pts = sr.track(msl, {}, LATS, LONS, t0, 45.5, 318.0)   # given position about 90 km off
    assert pts is not None and len(pts) == len(TIMES)
    assert all(abs(p["lat"] - 45.0) < 0.3 for p in pts)                # never the deeper low at 55N 295E
    lons = [p["lon"] for p in pts]
    assert all(b > a for a, b in zip(lons, lons[1:]))                  # moves east, both directions followed
    assert abs(lons[0] - 315.0) < 0.3 and abs(lons[-1] - 327.0) < 0.3
    ps = [p["p"] for p in pts]
    assert all(b < a for a, b in zip(ps, ps[1:]))                      # deepening
    assert all(p["wmax"] is None for p in pts)                         # no wind given


def test_parent_must_be_near_and_lost_low_ends_the_track():
    msl = moving_low()
    assert sr.track(msl, {}, LATS, LONS, TIMES[4], 38.0, 318.0) is None   # nearest low over 700 km away
    assert sr.track(msl, {}, LATS, LONS, TIMES[4], 55.0, 295.0) is not None  # the far low is a valid parent too
    msl[TIMES[7]] = low_field([(55.0, 295.0, 40.0)])                   # the low vanishes at index 7
    pts = sr.track(msl, {}, LATS, LONS, TIMES[4], 45.0, 319.0)
    assert [p["t"] for p in pts][-1] == sr.tstr(TIMES[6])              # forward stops at the gap
    assert sr.tstr(TIMES[0]) == pts[0]["t"]                            # backward still reaches the start


def test_jump_over_800_km_ends_the_track():
    msl = moving_low(dlon=1.0)
    msl[TIMES[6]] = low_field([(45.0, 315.0 + 25.0, 40.0)])            # next point ~1,950 km east
    pts = sr.track(msl, {}, LATS, LONS, TIMES[4], 45.0, 319.0)
    assert pts[-1]["t"] == sr.tstr(TIMES[5])


def test_bergeron_along_track():
    pts = [{"t": sr.tstr(T0 + H6 * i), "lat": 45.0, "lon": 315.0 + i, "p": 1000.0 - 6.0 * i, "wmax": None}
           for i in range(8)]
    b, bk = sr.bergeron(pts, T0 + dt.timedelta(hours=24))
    want = 24.0 * np.sin(np.radians(60)) / np.sin(np.radians(45)) / 24.0
    assert abs(b - want) < 1e-9 and abs(bk - want) < 1e-9 and b > 1.2
    # deepening only in the middle: the largest window is not the one at the key time
    p = [1000, 1000, 1000, 1000, 1000, 990, 980, 970, 965, 964, 964, 964, 964]
    pts = [{"t": sr.tstr(T0 + H6 * i), "lat": 60.0, "lon": 320.0, "p": float(v), "wmax": None} for i, v in enumerate(p)]
    b, bk = sr.bergeron(pts, T0 + H6 * 12)
    assert abs(b - 35.0 / 24.0) < 1e-9                                  # 35 hPa in 24 h at 60N (sin60 / sin60)
    assert abs(bk - 1.0 / 24.0) < 1e-9                                  # the 24 h ending at the key time: 1 hPa
    assert sr.bergeron(pts[:3], T0) == (None, None)                     # under 24 h of track: no pair
    assert sr.bergeron(None, T0) == (None, None)


def test_wind_max_radius():
    S = np.full(LATS.shape + LONS.shape, 20.0, np.float32)
    la, lo = 45.0, 315.0
    LA, LO = np.meshgrid(LATS, LONS, indexing="ij")
    d = km(LA, LO, la, lo)
    iy, ix = np.unravel_index(np.argmin(np.abs(d - 500.0)), d.shape)
    S[iy, ix] = 70.0                                                    # 500 km out: counted
    iy2, ix2 = np.unravel_index(np.argmin(np.abs(d - 700.0)), d.shape)
    S[iy2, ix2] = 99.0                                                  # 700 km out: not counted
    assert abs(d[iy, ix] - 500) < 15 and abs(d[iy2, ix2] - 700) < 15
    assert sr.wind_max(S, LATS, LONS, la, lo) == 70.0
    assert sr.wind_max(S, LATS, LONS, la, lo, radius_km=800) == 99.0
    assert np.isnan(sr.wind_max(S, LATS, LONS, 10.0, 315.0))             # point outside the grid


def test_track_carries_wind():
    msl = moving_low()
    spd = {t: np.full(LATS.shape + LONS.shape, 30.0 + 5 * i, np.float32) for i, t in enumerate(TIMES) if i != 2}
    pts = sr.track(msl, spd, LATS, LONS, TIMES[4], 45.0, 319.0)
    w = {p["t"]: p["wmax"] for p in pts}
    assert w[sr.tstr(TIMES[2])] is None and w[sr.tstr(TIMES[5])] == 55.0


def _rows(tracks, key, w0, w1):
    return [sr.point_summary(t, key, w0, w1) for t in tracks]


def test_shares_count_untracked_members_as_nothing():
    key, w0, w1 = TIMES[6], TIMES[4], TIMES[8]
    def pts(deep, wind):
        return [{"t": sr.tstr(T0 + H6 * i), "lat": 50.0, "lon": 320.0, "p": 1000.0 - deep * i, "wmax": wind} for i in range(-4, 9)]
    members = [pts(8.0, 70.0), pts(8.0, 50.0), pts(1.0, 36.0), None]   # bomb+HF, bomb+storm, weak gale, lost
    s = sr.ens_summary(_rows(members, key, w0, w1))
    assert s["n"] == 4 and s["tracked"] == 3 and s["bomb"] == 2 and s["bomb_share"] == 0.5
    assert s["key"] == {"34": 0.75, "48": 0.5, "64": 0.25} and s["life"] == s["key"]
    both = sr.pooled({"a": _rows(members, key, w0, w1), "b": _rows(members[:2], key, w0, w1)})
    assert both["n"] == 6 and abs(both["bomb_share"] - 4 / 6) < 1e-12 and abs(both["key"]["64"] - 2 / 6) < 1e-12
    empty = sr.ens_summary(_rows([None, None], key, w0, w1))
    assert empty["bomb_share"] == 0 and empty["p"] is None and empty["key"]["34"] == 0


def _synthetic(valid):
    """Two deterministic cycles and a 6-member ensemble (one member without a low) around a deepening low."""
    steps = [valid + H6 * i for i in range(-8, 5)]
    t0 = valid - dt.timedelta(hours=24)
    def run(deepen, dlon=1.0):
        out = {}
        for i, t in enumerate(steps):
            f = low_field([(45.0, 312.0 + dlon * i, 10.0 + deepen * i)])
            out[t] = (f, np.full(f.shape, 30.0 + 4 * i, np.float32))
        return out
    det = {"gfs": {"2026103100": run(3.0), "2026103112": run(4.0)}, "ifs": {"2026103112": run(6.0)}}
    ens = {}
    for e, dp in (("gefs", 2.5), ("ens", 5.0)):
        fl = {}
        for i, t in enumerate(steps):
            msl = np.stack([low_field([(45.0, 312.0 + i, 10.0 + (dp + 0.4 * m) * i)]) for m in range(5)]
                           + [low_field([(60.0, 300.0, 30.0)])])           # last member: no low near the parent
            fl[t] = (msl, np.stack([np.full(msl.shape[1:], 30.0 + 4 * i + m, np.float32) for m in range(6)]))
        ens[e] = fl
    return t0, det, ens


def test_tool_writes_summary_figures_and_page():
    import types
    import storm_read as tool
    valid = dt.datetime(2026, 11, 1, 12)
    t0, det, ens = _synthetic(valid)
    lats, lons = basins.grid("natl")
    with tempfile.TemporaryDirectory() as d:
        args = types.SimpleNamespace(page_run="none", name="Synthetic low", runs=2, no_ens=False)
        s = tool.finish(args, valid, t0, 45.0, 312.0, "natl", lats, lons, Path(d), dt.datetime(2026, 10, 31, 12), det, ens)
        for f in ("summary.json", "tracks.json", "page.html", "pressure.png", "bomb.png", "wind.png", "runs.png"):
            assert (Path(d) / f).exists(), f
        page = (Path(d) / "page.html").read_text()
        assert "{{" not in page and "Forecaster read" in page and "Synthetic low" in page
        assert 'alt="Map of' not in page and "fields not drawn" in page    # page fields skipped, said so
        summ = json.loads((Path(d) / "summary.json").read_text())
        assert summ["ens"]["gefs"]["n"] == 6 and summ["ens"]["gefs"]["tracked"] == 5
        assert summ["pooled"]["n"] == 12 and summ["narrative"]["bomb"] and len(summ["narrative"]["caveats"]) == 4
    assert s["det"]["ifs"]["2026103112"]["tracked"] and s["latest"] == "2026103112"


def test_steps_and_cycles():
    import storm_read as tool
    v = dt.datetime(2026, 11, 1, 12)
    st = tool.steps_of(v)
    assert len(st) == 13 and st[0] == v - dt.timedelta(hours=48) and st[-1] == v + dt.timedelta(hours=24)
    w0, w1 = tool.wind_window(v)
    assert [t for t in st if w0 <= t <= w1] == st[4:11]
    assert tool.det_cycles(dt.datetime(2026, 10, 28, 0), 3) == [dt.datetime(2026, 10, 27, 0), dt.datetime(2026, 10, 27, 12),
                                                                dt.datetime(2026, 10, 28, 0)]
    assert tool.latest_cycle(dt.datetime(2026, 10, 28, 8, 40)) == dt.datetime(2026, 10, 28, 0)
    assert tool.latest_cycle(dt.datetime(2026, 10, 28, 12, 5)) == dt.datetime(2026, 10, 28, 12)
    assert tool.parse_parent("2026103112,36,-50") == (dt.datetime(2026, 10, 31, 12), 36.0, 310.0)


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
