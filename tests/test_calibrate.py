"""Tests for rk.calibrate and the ASCAT grid helpers in rk.truth. Run with pytest or `python3 tests/test_calibrate.py`.
Offline."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import calibrate as C  # noqa: E402
from rk import truth  # noqa: E402


def _sample(n=200000, bias=0.8, seed=0):
    """Chances that are too low: the event happens at p**bias."""
    r = np.random.default_rng(seed)
    p = np.round(r.beta(0.6, 4.0, n) * 31) / 31
    e = (r.random(n) < np.clip(p ** bias, 0, 1)).astype(float)
    return p, e


def test_reliability_bins():
    p = np.array([0.0, 0.005, 0.015, 0.5, 1.0])
    e = np.array([0, 1, 0, 1, 1])
    r = C.reliability(p, e)
    assert r["n"].sum() == 5 and r["events"].sum() == 3
    assert r["n"][0] == 2 and r["events"][0] == 1 and abs(r["mean_fc"][0] - 0.0025) < 1e-12
    assert r["n"][-1] == 1 and r["events"][-1] == 1      # p = 1.0 lands in the last bin
    assert len(r["n"]) == len(C.EDGES) - 1 and np.isnan(r["obs_freq"][3])


def test_tables_add_and_weights():
    p, e = _sample(20000)
    t1, t2 = C.table(p[:9000], e[:9000]), C.table(p[9000:], e[9000:])
    tt, ta = C.table(p, e), C.add_tables(t1, t2)
    for f in tt:
        assert np.allclose(tt[f], ta[f])
    # weighted form: counts per distinct value give the same table
    v = np.unique(p)
    n = np.array([(p == x).sum() for x in v])
    ev = np.array([e[p == x].sum() for x in v])
    tw = C.table(np.r_[v, v], np.r_[np.ones(len(v)), np.zeros(len(v))], w=np.r_[ev, n - ev])
    for f in tt:
        assert np.allclose(tt[f], tw[f])
    assert abs(C.brier(p, e) - C.brier(np.r_[v, v], np.r_[np.ones(len(v)), np.zeros(len(v))], w=np.r_[ev, n - ev])) < 1e-12


def test_fit_properties():
    p, e = _sample()
    raw, cal = C.fit(C.table(p, e), nmin=2000)
    assert raw[0] == 0 and cal[0] == 0 and raw[-1] == 100 and cal[-1] == 100
    assert all(b >= a for a, b in zip(cal, cal[1:])) and all(b >= a for a, b in zip(raw, raw[1:]))
    # chances were too low: the remap lifts the middle
    assert C.cal_at(30, raw, cal) > 30
    # the fit accepts a reliability() dict as well
    raw2, cal2 = C.fit(C.reliability(p, e))
    assert raw2 == raw and cal2 == cal


def test_fit_shrinks_small_bins():
    # 10 forecasts of 50%, all events: n/nmin = 0.005 -> stays at the raw chance
    raw, cal = C.fit(C.table(np.full(10, 0.5), np.ones(10)), nmin=2000)
    k = raw.index(50.0)
    assert abs(cal[k] - (0.005 * 100 + 0.995 * 50)) < 0.1


def test_fit_monotone_when_noisy():
    t = {"n": np.array([5000.0, 5000, 5000]), "events": np.array([2500.0, 500, 4000]),
         "sum_p": np.array([500.0, 1000, 1500])}
    raw, cal = C.fit(t, nmin=2000)
    assert all(b >= a for a, b in zip(cal, cal[1:]))


def test_apply_and_inverse():
    raw, cal = [0, 10, 30, 100], [0, 20, 50, 100]
    assert abs(C.apply(0.2, raw, cal) - 0.35) < 1e-12 and C.apply(0.0, raw, cal) == 0
    assert C.cal_at(10, raw, cal) == 20
    assert abs(C.raw_for(35, raw, cal) - 20.0) < 1e-9
    assert abs(C.cal_at(C.raw_for(30, raw, cal), raw, cal) - 30) < 1e-9
    assert np.isnan(C.raw_for(110, [0, 50], [0, 80]))
    # flat stretch: the lowest raw share that reaches the target
    assert C.raw_for(40, [0, 10, 20, 30, 100], [0, 40, 40, 60, 100]) == 10


def test_scores():
    p = np.array([0.0, 1.0, 0.5, 0.5])
    e = np.array([0, 1, 1, 0])
    assert abs(C.brier(p, e) - 0.125) < 1e-12
    assert abs(C.brier_skill(p, e, 0.5) - 0.5) < 1e-12        # climate Brier is 0.25
    assert C.brier_skill(np.full(4, 0.5), e, 0.5) == 0
    assert np.isnan(C.brier_skill(p, np.zeros(4), 0.0))


def test_reliability_error():
    n = 1000
    p = np.full(n, 0.3)
    assert C.reliability_error(C.table(p, np.r_[np.ones(300), np.zeros(700)])) < 1e-9
    assert abs(C.reliability_error(C.table(p, np.r_[np.ones(500), np.zeros(500)])) - 0.2) < 1e-9


def test_remap_improves_held_out():
    p, e = _sample(300000)
    k = np.arange(len(p)) % 2 == 0
    raw, cal = C.fit(C.table(p[k], e[k]))
    q = C.apply(p[~k], raw, cal)
    clim = e[~k].mean()
    assert C.brier_skill(q, e[~k], clim) > C.brier_skill(p[~k], e[~k], clim)
    assert C.reliability_error(C.table(q, e[~k])) < C.reliability_error(C.table(p[~k], e[~k]))


def test_page_json_layout():
    cur = {(48, "natl", "le48"): ([0, 50, 100], [0, 60, 100]), (48, "natl", "72"): ([0, 100], [0, 100]),
           (34, "npac", "ge96"): ([0, 100], [0, 100]), (64, "natl", "ge96"): ([0, 100], [0, 90])}
    with tempfile.TemporaryDirectory() as d:
        out = C.to_page_json(cur, note="x", path=Path(d) / "c.json")
        back = json.loads((Path(d) / "c.json").read_text())
    assert back == out and out["note"] == "x" and list(out["thresholds"]) == ["34", "48", "64"]
    assert out["thresholds"]["48"]["natl"]["le48"] == {"raw": [0.0, 50.0, 100.0], "cal": [0.0, 60.0, 100.0]}
    assert set(out["thresholds"]["48"]["natl"]) == {"le48", "72"}


def test_lead_group():
    assert [C.lead_group(s) for s in (24, 48, 72, 96, 120)] == ["le48", "le48", "72", "ge96", "ge96"]


# ---- ASCAT grid helpers (rk.truth) ----

def test_snap_floor_not_rint():
    # RSS centres at .125: every other row/column must not be dropped. 160.125 .. 160.875 -> 4 distinct columns
    lon = 160.125 + 0.25 * np.arange(4)
    lat = np.full(4, 66.875)
    g, c = truth.ascat_to_grid("npac", lat, lon, np.arange(4, dtype=float))
    assert c.sum() == 4 and (c > 0).sum() == 4
    assert np.count_nonzero(~np.isnan(g[1])) == 4 and np.nanmax(c) == 1
    # two cells in one grid cell are averaged
    g, c = truth.ascat_to_grid("npac", np.array([66.875, 66.875]), np.array([160.125, 160.125]), np.array([40.0, 44.0]))
    assert g[1, 1] == 42.0 and c[1, 1] == 2
    # outside the box and NaN are dropped
    g, c = truth.ascat_to_grid("npac", np.array([10.0, 50.0]), np.array([200.0, 200.0]), np.array([30.0, np.nan]))
    assert c.sum() == 0


def test_box_mean_rule():
    g = np.full((7, 7), np.nan)
    g[2:5, 2:5] = 40.0
    m, n = truth.box_mean(g)
    assert m[3, 3] == 40 and n[3, 3] == 9
    g[2:5, 2:5].flat[:3] = np.nan                      # 6 of 9 valid: kept
    m, n = truth.box_mean(g)
    assert n[3, 3] == 6 and m[3, 3] == 40
    g[3, 3] = g[3, 2] = np.nan                         # 4 of 9... centre need not be valid but 6 are needed
    m, n = truth.box_mean(g)
    assert np.isnan(m[3, 3]) and n[3, 3] == 4
    # a neighbouring empty centre can still pass when 6+ neighbours are valid
    h = np.full((5, 5), 30.0)
    h[2, 2] = np.nan
    m, n = truth.box_mean(h)
    assert n[2, 2] == 8 and m[2, 2] == 30
    # edges count missing cells as invalid: corner 4 of 9 dropped, edge cell 6 of 9 kept
    m, n = truth.box_mean(np.full((5, 5), 30.0))
    assert np.isnan(m[0, 0]) and n[0, 0] == 4 and m[0, 2] == 30 and n[0, 2] == 6


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
