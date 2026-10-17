"""Tests for rk.score and rk.compare on tiny synthetic data. Run: python3 tests/test_score.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from rk import score, compare


def test_counts_and_csi():
    ob = np.array([[40., 40., 10.], [10., 36., 10.]])
    fc = np.array([[40., 10., 40.], [10., 36., 10.]])
    assert score.contingency(fc, ob, 34) == (2, 1, 1)
    assert abs(score.csi(fc, ob, 34) - 0.5) < 1e-12
    assert abs(score.pod(fc, ob, 34) - 2 / 3) < 1e-12
    assert abs(score.far(fc, ob, 34) - 1 / 3) < 1e-12
    assert abs(score.area_ratio(fc, ob, 34) - 1.0) < 1e-12
    assert score.csi(ob, ob, 34) == 1.0
    m = np.zeros(ob.shape, bool); m[1] = True
    assert score.contingency(fc, ob, 34, mask=m) == (1, 0, 0)


def test_nan_on_empty():
    z = np.zeros((4, 4))
    for f in (score.csi, score.pod, score.far, score.area_ratio):
        assert np.isnan(f(z, z, 34))
    assert np.isnan(score.fss(z, z, 34))
    e = score.error(z, z, 25)
    assert e["n"] == 0 and np.isnan(e["bias"])


def test_fss_and_error():
    ob = np.zeros((20, 20)); ob[8:12, 8:12] = 40
    assert abs(score.fss(ob, ob, 34) - 1.0) < 1e-12
    assert abs(score.fss(np.roll(ob, 8, 1), ob, 34, n=3)) < 1e-9
    e = score.error(ob + 3, ob, 25)
    assert e["n"] == 16 and abs(e["bias"] - 3) < 1e-9 and abs(e["rmse"] - 3) < 1e-9


def test_tile_peaks():
    rng = np.random.default_rng(0)
    lat = rng.uniform(40, 44.99, 400); lon = rng.uniform(300, 304.99, 400)
    ob = rng.uniform(10, 30, 400); ob[0] = 50
    fc = ob - 5
    t = score.tile_peaks(fc, ob, lat, lon)
    assert len(t) == 1 and abs(t.err_max[0] + 5) < 1e-9 and t.n[0] == 400
    assert len(score.tile_peaks(fc, ob, lat, lon, min_n=500)) == 0


def test_tile_hits():
    lats = 49.75 - 0.25 * np.arange(20)                      # 49.75 .. 45.0: one 5 deg tile row (45-50)
    lons = 300.0 + 0.25 * np.arange(40)                      # 300 .. 309.75: two tiles (300-305, 305-310)
    shape = (20, 40)
    ob = np.full(shape, 20.0); fc = np.full(shape, 20.0)
    seen = np.ones(shape, bool)
    seen[:, 20:] = False; seen[:, 20:25] = True               # tile B has only 100 seen cells -> dropped at 150
    ob[3, 3] = 50.0                                           # tile A obs event
    fc[3, 3] = 50.0                                           # forecast hits it
    t = score.tile_hits(fc, ob, seen, lats, lons, 48)
    assert len(t) == 1 and t.n_seen[0] == 400 and t.ob_event[0] and t.fc_event[0]
    assert score.tile_counts(t) == (1, 0, 0)
    t = score.tile_hits(fc, ob, seen, lats, lons, 48, min_seen=100)
    assert len(t) == 2 and score.tile_counts(t) == (1, 0, 0) and list(t.lon0) == [300, 305]
    # forecast storm only outside the seen cells is not judged; a miss; a false alarm
    fc2 = np.full(shape, 20.0); fc2[10, 35] = 60.0            # unseen cell (col 35)
    t = score.tile_hits(fc2, ob, seen, lats, lons, 48, min_seen=100)
    assert score.tile_counts(t) == (0, 1, 0)
    ob3 = np.full(shape, 20.0); fc3 = fc.copy()
    t = score.tile_hits(fc3, ob3, seen, lats, lons, 48, min_seen=100)
    assert score.tile_counts(t) == (0, 0, 1)
    # NaN observation or forecast never counts; 2-D lat/lon and negative-longitude input agree
    ob4 = ob.copy(); ob4[0, 0] = np.nan; fc4 = fc.copy(); fc4[1, 1] = np.nan
    t4 = score.tile_hits(fc4, ob4, seen, lats, lons, 48)
    LA, LO = np.meshgrid(lats, lons - 360.0, indexing="ij")
    t5 = score.tile_hits(fc4, ob4, seen, LA, LO, 48)
    assert t4.equals(t5) and score.tile_counts(t4) == (1, 0, 0)
    # 34 kt threshold on the same grids
    assert score.tile_counts(score.tile_hits(fc, ob, seen, lats, lons, 34)) == (1, 0, 0)
    assert len(score.tile_hits(fc, ob, np.zeros(shape, bool), lats, lons, 48)) == 0


def test_brier_auc_reliability():
    rng = np.random.default_rng(0)
    p = rng.random(4000); y = (rng.random(4000) < p).astype(float)
    assert 0.2 < score.brier_skill(p, y) < 0.4          # calibrated: BSS = 1 - (1/6)/(1/4) = 0.333
    assert abs(score.brier_skill(np.full(100, 0.3), np.r_[np.ones(30), np.zeros(70)])) < 1e-12
    assert np.isnan(score.brier_skill(p, np.zeros(4000)))
    # weights: duplicating a row == weight 2
    w = np.ones(4000); w[:50] = 2
    p2, y2 = np.r_[p, p[:50]], np.r_[y, y[:50]]
    assert abs(score.brier_skill(p, y, w) - score.brier_skill(p2, y2)) < 1e-12
    assert abs(score.auc(p, y, w) - score.auc(p2, y2)) < 1e-12
    # AUC against the pair-counting definition, with ties
    a = np.array([0.1, 0.4, 0.4, 0.8, 0.8, 0.9]); b = np.array([0, 0, 1, 1, 0, 1])
    pos, neg = a[b == 1], a[b == 0]
    exp = np.mean([(x > z) + 0.5 * (x == z) for x in pos for z in neg])
    assert abs(score.auc(a, b) - exp) < 1e-12 and np.isnan(score.auc(a, np.ones(6)))
    # histogram form agrees when bins hold identical values
    pos_h = np.array([1.0, 2, 0, 3]); neg_h = np.array([4.0, 1, 2, 1])
    pp = np.repeat(np.arange(4), (pos_h + neg_h).astype(int))
    yy = np.concatenate([np.r_[np.ones(int(a_)), np.zeros(int(b_))] for a_, b_ in zip(pos_h, neg_h)])
    assert abs(score.auc_from_hist(pos_h, neg_h) - score.auc(pp, yy)) < 1e-12
    r = score.reliability(p, y, bins=10)
    assert r.n.sum() == 4000 and (np.abs(r.mean_p - r.freq) < 0.08).all()
    assert score.reliability(np.array([1.0, 0.0]), np.array([1, 0]), bins=10).n.tolist() == [1] + [0] * 8 + [1]


def test_paired_counts():
    rng = np.random.default_rng(2)
    days = pd.date_range("2025-11-01", periods=140, freq="D")
    rows = []
    for d in days:
        for m, pod in (("a", 0.4), ("b", 0.55)):
            n = 10
            h = int(rng.binomial(n, pod))
            rows.append(dict(cycle=d, step=24, method=m, h=h, m=n - h, fa=int(rng.binomial(10, 0.1))))
    df = pd.DataFrame(rows)
    pod = lambda c: c["h"] / (c["h"] + c["m"])
    r = compare.paired_counts(df, "b", "a", pod, ["h", "m", "fa"], by="step", seed=1).iloc[0]
    assert 0.1 < r["diff"] < 0.2 and r.lo < r["diff"] < r.hi and r.significant and r.n_cases == 140
    assert abs(r["diff"] - (df[df.method == "b"].h.sum() / 1400 - df[df.method == "a"].h.sum() / 1400)) < 1e-12
    z = compare.paired_counts(df, "a", "a", pod, ["h", "m", "fa"])
    assert z.iloc[0]["diff"] == 0 and not z.iloc[0].significant
    tot, dr = compare.boot_sums(np.repeat([1, 2, 3], 2), np.arange(6.0), n_boot=50, seed=0)
    assert tot[0] == 15 and dr.shape == (50, 1) and (dr[:, 0] % 1 == 0).all()


def test_paired_bootstrap():
    rng = np.random.default_rng(1)
    days = pd.date_range("2025-11-01", periods=140, freq="D")
    rows = []
    for d in days:
        base = rng.normal(5, 1)
        rows += [dict(cycle=d, step=24, method="a", v=base),
                 dict(cycle=d, step=24, method="b", v=base + 0.5 + rng.normal(0, 0.3))]
    df = pd.DataFrame(rows)
    r = compare.paired(df, "b", "a", "v", by="step", seed=3)
    row = r.iloc[0]
    assert row.lo < 0.5 < row.hi and row.significant and row.n_cases == 140 and row.n_weeks >= 20
    z = compare.paired(df, "a", "a", "v")
    assert z.iloc[0]["mean"] == 0 and not z.iloc[0]["significant"]
    t = compare.table(df, ["b"], "a", "v", by="step")
    assert t.loc[24, "b"].startswith("+0.5") and t.loc[24, "b"].endswith("*")


def _field(basin, lows, base=1012.0, sigma_deg=3.0):
    """Synthetic MSLP on the basin grid with Gaussian lows [(lat, lon, hpa)] (lon any convention)."""
    from rk.basins import grid
    lats, lons = grid(basin)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    f = np.full(LA.shape, base)
    for la, lo, p in lows:
        d = score.km(LA, LO, la, lo) / 111.0
        f = f + (p - base) * np.exp(-0.5 * (d / sigma_deg) ** 2)
    return f


def test_km_date_line():
    assert abs(score.km(50, 179, 50, -179) - score.km(50, 179, 50, 181)) < 1e-6
    assert abs(score.km(50, 179, 50, 181) - 2 * 111.19 * np.cos(np.radians(50))) < 2
    assert score.km(10, 10, 10, 10) == 0


def test_find_lows_two():
    f = _field("natl", [(50, 320, 970.0), (40, 340, 985.0)])
    L = score.find_lows(f, "natl")
    assert len(L) == 2 and list(L.columns) == ["lat", "lon", "hpa"]
    assert abs(L.hpa[0] - 970) < 0.5 and abs(L.hpa[1] - 985) < 0.5
    assert abs(L.lat[0] - 50) <= 0.25 and abs(L.lon[0] - 320) <= 0.25
    assert len(score.find_lows(f, "natl", below=980)) == 1
    assert len(score.find_lows(f, "natl", inset_deg=40)) == 0
    assert len(score.find_lows(np.full_like(f, 1010.0), "natl")) == 0


def test_match_shifted_100km():
    t = score.find_lows(_field("natl", [(50, 320, 970.0)]), "natl")
    dlon = 100 / (111.19 * np.cos(np.radians(50)))
    fcl = score.find_lows(_field("natl", [(50, 320 + dlon, 975.0)]), "natl")
    m = score.match_lows(t, fcl)
    assert len(m) == 1 and m.matched[0] and abs(m.pos_err_km[0] - 100) < 25
    assert abs(m.depth_err_hpa[0] - 5) < 0.5
    assert score.false_lows(t, fcl) == 0


def test_far_low_is_miss_and_false():
    t = score.find_lows(_field("natl", [(50, 320, 970.0)]), "natl")
    dlon = 500 / (111.19 * np.cos(np.radians(50)))
    fcl = score.find_lows(_field("natl", [(50, 320 + dlon, 970.0)]), "natl")
    m = score.match_lows(t, fcl)
    assert not m.matched[0] and np.isnan(m.pos_err_km[0])
    assert score.false_lows(t, fcl) == 1
    s = score.low_scores(_field("natl", [(50, 320, 970.0)]), _field("natl", [(50, 320 + dlon, 970.0)]), "natl")
    assert (s["hits"], s["misses"], s["false"], s["n_truth"]) == (0, 1, 1, 1)
    s0 = score.low_scores(_field("natl", [(50, 320, 970.0)]), _field("natl", [(50, 320, 970.0)]), "natl")
    assert (s0["hits"], s0["misses"], s0["false"]) == (1, 0, 0) and s0["pos_err_km_median"] == 0


def test_lows_across_date_line():
    # truth low west of 180, forecast low east of it, 120 km apart; npac covers lon 160-245
    dlon = 60 / (111.19 * np.cos(np.radians(50)))
    ft = _field("npac", [(50, 180 - dlon, 965.0)])
    ff = _field("npac", [(50, 180 + dlon, 970.0)])
    t, fcl = score.find_lows(ft, "npac"), score.find_lows(ff, "npac")
    assert len(t) == 1 and len(fcl) == 1
    m = score.match_lows(t, fcl)
    assert m.matched[0] and abs(m.pos_err_km[0] - 120) < 30
    # the same pair given in -180..180 longitudes
    t2 = t.assign(lon=(t.lon + 180) % 360 - 180)
    assert abs(score.match_lows(t2, fcl).pos_err_km[0] - m.pos_err_km[0]) < 1e-6
    s = score.low_scores(ft, ff, "npac")
    assert (s["hits"], s["misses"], s["false"]) == (1, 0, 0)


def test_miss_penalty_and_field_depth():
    tr = _field("natl", [(50, 320, 970.0)])
    dlon = 500 / (111.19 * np.cos(np.radians(50)))
    fc = _field("natl", [(50, 320 + dlon, 975.0)])
    t, fcl = score.find_lows(tr, "natl"), score.find_lows(fc, "natl")
    m = score.match_lows(t, fcl)                      # defaults unchanged
    assert np.isnan(m.pos_err_km[0]) and np.isnan(m.depth_err_hpa[0])
    m = score.match_lows(t, fcl, miss_penalty_km=1000)
    assert m.pos_err_km[0] == 1000 and np.isnan(m.depth_err_hpa[0])
    m = score.match_lows(t, fcl, miss_penalty_km=1000, miss_depth="field", fc_msl=fc, basin="natl")
    from rk.basins import sample
    assert abs(m.depth_err_hpa[0] - (sample(fc, "natl", 50, 320) - m.hpa[0])) < 1e-9
    assert m.depth_err_hpa[0] > 20                    # forecast is nearly flat at the analysed centre
    try:
        score.match_lows(t, fcl, miss_depth="field")
        assert False
    except ValueError:
        pass
    # no forecast lows at all: a miss costs the penalty
    m = score.match_lows(t, None, miss_penalty_km=1000)
    assert m.pos_err_km[0] == 1000
    # matched rows are untouched by the penalty
    m = score.match_lows(t, score.find_lows(tr, "natl"), miss_penalty_km=1000)
    assert m.pos_err_km[0] == 0


def test_low_scores_thresholds():
    tr = _field("natl", [(50, 320, 970.0)])
    # forecast low is shallow (1005) and 400 km away: needs fc_below 1010 and a 500 km radius
    dlon = 400 / (111.19 * np.cos(np.radians(50)))
    fc = _field("natl", [(50, 320 + dlon, 1005.0)])
    s = score.low_scores(tr, fc, "natl")
    assert (s["hits"], s["misses"], s["false"]) == (0, 1, 0) and np.isnan(s["pos_err_km_median"])
    s = score.low_scores(tr, fc, "natl", fc_below=1010, radius_km=500)
    assert s["hits"] == 1 and 390 < s["pos_err_km_median"] < 410
    # study call: miss filled with 1000 km and the field depth; the 1005 low is not "deeper than 1000"
    s = score.low_scores(tr, fc, "natl", fc_below=1010, false_radius_km=500, false_truth_below=1005,
                         miss_penalty_km=1000, miss_depth="field")
    assert (s["hits"], s["misses"], s["false"]) == (0, 1, 0)
    assert s["pos_err_km_median"] == 1000 and s["depth_err_hpa_mean"] > 20
    # false-low radius and truth threshold
    fc2 = _field("natl", [(50, 320, 970.0), (50, 320 + 2 * dlon, 990.0)], sigma_deg=1.5)      # second low 800 km away
    assert score.low_scores(tr, fc2, "natl")["false"] == 1
    assert score.low_scores(tr, fc2, "natl", false_radius_km=900)["false"] == 0
    tr2 = _field("natl", [(50, 320, 970.0), (50, 320 + 2 * dlon, 1003.0)], sigma_deg=1.5)
    assert score.low_scores(tr2, fc2, "natl")["false"] == 0                    # 1003 < below + 5
    assert score.low_scores(tr2, fc2, "natl", false_truth_below=1000)["false"] == 1


def test_low_case():
    tr = _field("natl", [(50, 320, 970.0)])
    # forecast low 450 km away: not a 300 km hit, but it supplies position and depth (study rule)
    dlon = 450 / (111.19 * np.cos(np.radians(50)))
    fc = _field("natl", [(50, 320 + dlon, 975.0)])
    rows, false, n_fc = score.low_case(tr, fc, "natl")
    assert len(rows) == 1 and not rows.hit[0]
    assert abs(rows.pos_km[0] - 450) < 15 and abs(rows.depth_err_hpa[0] - 5.0) < 0.05
    assert false == 0 and n_fc == 1
    # perfect forecast: hit, zero errors
    rows, false, n_fc = score.low_case(tr, tr, "natl")
    assert rows.hit[0] and rows.pos_km[0] < 1e-6 and rows.depth_err_hpa[0] == 0 and false == 0
    # no forecast low at all: miss charged 1000 km, depth from the field at the analysed centre
    rows, false, n_fc = score.low_case(tr, np.full_like(tr, 1012.0), "natl")
    assert rows.pos_km[0] == 1000.0 and not rows.hit[0] and abs(rows.depth_err_hpa[0] - 42.0) < 1e-3
    assert false == 0 and n_fc == 0
    # a forecast low far from every analysed low is a false low
    far = _field("natl", [(50, 320, 970.0), (40, 290, 985.0)])
    rows, false, n_fc = score.low_case(tr, far, "natl")
    assert false == 1 and n_fc == 2


def test_warning_events():
    ob = np.zeros((40, 40)); seen = np.ones(ob.shape, bool)
    ob[5:7, 5:7] = 50            # event A (4 cells)
    ob[30, 30] = 50              # single cell: below min_cells, not an event
    ob[20:22, 20:22] = 40        # event B at 34 only
    w = np.zeros(ob.shape, bool)
    w[8:12, 8:12] = True         # 2-5 cells from A: a hit within slack 4, not a false area
    w[30:34, 0:4] = True         # far from everything: false area
    r = score.warning_events(w, ob, seen, 48)
    assert (r["events"], r["hits"], r["areas"], r["judged"], r["false"]) == (1, 1, 2, 2, 1)
    assert r["cells"] == 32 and r["bad_cells"] == 16 + 7      # row 11 and column 11 lie beyond the slack
    # fair-reach scores: the slack ring is a free catching area, so count it, and count catches on the event
    assert (r["hits_on"], r["obs_cells"], r["obs_in"], r["bad_on"]) == (0, 5, 0, 32)
    assert r["reach_cells"] == 12 * 12 + 12 * 8                 # each 4x4 block grows to 12x12; one is cut at the edge
    w2 = w.copy(); w2[5, 5] = True
    r2 = score.warning_events(w2, ob, seen, 48)
    assert (r2["hits_on"], r2["obs_in"]) == (1, 1)
    r = score.warning_events(w, ob, seen, 34)
    assert (r["events"], r["hits"]) == (2, 1)
    # an area the observations did not see is not judged
    unseen = seen.copy(); unseen[28:36, 0:6] = False
    r = score.warning_events(w, ob, unseen, 48)
    assert (r["judged"], r["false"]) == (1, 0)
    # diagonal neighbours are one event (8-connected)
    ob2 = np.zeros((10, 10)); ob2[2, 2] = ob2[3, 3] = 50
    assert score.warning_events(np.zeros((10, 10), bool), ob2, np.ones((10, 10), bool), 48)["events"] == 1


def test_warning_points():
    from rk.basins import grid
    lats, lons = grid("natl")
    w = np.zeros((lats.size, lons.size), bool)
    w[40:44, 100:104] = True                       # around lat 57, lon 310
    w[120:123, 250:253] = True                     # far away: false
    r = score.warning_points(w, "natl", [57.0, 40.0], [310.5, 300.0], 300)
    assert (r["events"], r["hits"], r["areas"], r["false"]) == (2, 1, 2, 1)
    assert r["bad_cells"] == 9


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
