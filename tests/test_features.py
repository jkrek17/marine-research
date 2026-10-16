"""Tests for rk.features and rk.truth.ascat_target. Offline, synthetic. Run with pytest or
`python3 tests/test_features.py`."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import features, truth  # noqa: E402
from rk.basins import grid  # noqa: E402


def _members(rng, n, shape, loc, scale):
    return np.maximum(rng.normal(loc, scale, (n,) + shape), 0).astype(np.float32)


def _stats(m):
    return {"spd_mean": m.mean(0), "spd_std": m.std(0), "p34": (m >= 34).mean(0), "p48": (m >= 48).mean(0),
            "p64": (m >= 64).mean(0), "n": len(m)}


def test_pool_matches_brute_force():
    rng = np.random.default_rng(0)
    a, b = _members(rng, 31, (6, 7), 40, 9), _members(rng, 51, (6, 7), 44, 6)
    allm = np.concatenate([a, b])
    p = features.pool([_stats(a), _stats(b)])
    assert p["n"] == 82
    assert np.allclose(p["mean"], allm.mean(0), atol=1e-4)
    assert np.allclose(p["sd"], allm.std(0), atol=1e-3)
    for k, t in (("p34", 34), ("p48", 48), ("p64", 64)):
        assert np.allclose(p[k], (allm >= t).mean(0), atol=1e-6)


def test_support_closed_form_vs_monte_carlo():
    rng = np.random.default_rng(1)
    shape = (4, 5)
    mu1, sd1 = rng.uniform(20, 60, shape), rng.uniform(1, 10, shape)
    mu2, sd2 = rng.uniform(20, 60, shape), rng.uniform(1, 10, shape)
    n1, n2 = 31, 51
    # draw many members from the two normals, kernel-average them exactly as build.support_base does
    big1 = rng.normal(mu1, sd1, (40000,) + shape)
    big2 = rng.normal(mu2, sd2, (40000,) + shape)
    speeds = np.array([mu1 + 2, mu2 - 1, 0.5 * (mu1 + mu2)])

    def kern(m, s):
        return np.exp(-0.5 * ((m - s[None]) / features.SUPPORT_KT) ** 2).mean(0)

    w = np.array([(n1 * kern(big1, s) + n2 * kern(big2, s)) / (n1 + n2) for s in speeds]) + 1e-6
    mc = (w * speeds).sum(0) / w.sum(0)
    st = [{"spd_mean": mu1, "spd_std": sd1, "n": n1}, {"spd_mean": mu2, "spd_std": sd2, "n": n2}]
    cf = features.support_closed_form(speeds, st)
    assert np.abs(cf - mc).max() < 0.15, np.abs(cf - mc).max()
    # one ensemble with zero spread: kernel is evaluated at the mean
    z = features.support_closed_form(speeds, [{"spd_mean": mu1, "spd_std": 0 * sd1, "n": 30}])
    wz = np.array([np.exp(-0.5 * ((mu1 - s) / 5.0) ** 2) for s in speeds]) + 1e-6
    assert np.allclose(z, (wz * speeds).sum(0) / wz.sum(0))


def test_assemble_keys_and_live_formulas():
    rng = np.random.default_rng(2)
    shape = (30, 40)
    lats = 60 - 0.25 * np.arange(shape[0])
    a, b = _members(rng, 31, shape, 35, 8), _members(rng, 51, shape, 36, 6)
    st = [_stats(a), _stats(b)]
    sp = np.array([a.mean(0) + 1, b.mean(0), 0.5 * (a.mean(0) + b.mean(0))], np.float32)
    low = {k: 270 + 10 * rng.random(shape) for k in ("t2", "skt", "t925", "t850")}
    low.update({k: 40 * rng.standard_normal(shape) for k in ("u925", "v925", "u850", "v850")})
    f = features.assemble(lats, sp, features.pool(st), st, 48, pa48=None, low=low)
    assert tuple(f) == features.FEATURES and len(f) == 28
    allm = np.concatenate([a, b])
    assert np.allclose(f["boost"], np.minimum(0.25 * allm.std(0), 5.0), atol=1e-3)
    assert np.allclose(f["m90"], allm.mean(0) + features.Z90 * allm.std(0), atol=1e-3)
    assert np.allclose(f["mod_sd"], sp.std(0)) and np.allclose(f["mod_max"], sp.max(0))
    assert np.isnan(f["pa48"]).all() and np.isfinite(f["gradT850"]).all()
    assert np.allclose(f["s925_minus_r10"], f["s925"] - f["r10"], atol=1e-4)
    assert (f["p48_nb"] >= f["p48"] - 1e-6).all()
    # boost is 0.15 sigma at +24 h
    f24 = features.assemble(lats, sp, features.pool(st), st, 24, low=None)
    assert np.allclose(f24["boost"], np.minimum(0.15 * allm.std(0), 5.0), atol=1e-3)
    assert all(np.isnan(f24[k]).all() for k in features.LOW_FEATURES)


def test_feature_list_matches_live_model_when_present():
    # the repo does not depend on awips-tools; compare only if a checkout sits beside this one
    p = Path(__file__).resolve().parents[2] / "awips-tools" / "marine_wind" / "pipeline" / "core_model.json"
    if p.exists():
        assert tuple(json.load(open(p))["features"]) == features.FEATURES


def test_k_for_and_constants():
    assert features.k_for(24) == 0.15 and features.k_for(48) == 0.25
    assert features.SUPPORT_KT == 5.0 and features.CAP_KT == 5.0 and features.NB == (9, 13)


def test_ascat_target_box_logic():
    lats, lons = grid("natl")
    # three ASCAT cells: centres 0.125 deg off the grid; (lat 60.125 -> row at 60.25 or 60.0?) check snapping
    r0, c0 = 40, 100
    lat = np.array([lats[r0] - 0.125, lats[r0 + 2] + 0.125, lats[r0 + 30] - 0.125], np.float32)
    lon = np.array([lons[c0] + 0.125, lons[c0 + 3] - 0.125, lons[c0 + 50] + 0.125], np.float32)
    spd = np.array([30.0, 52.0, 20.0], np.float32)
    fake = {"lat": lat, "lon": lon, "spd_kt": spd}
    orig = truth.ascat
    truth.ascat = lambda *a, **k: fake
    try:
        t = truth.ascat_target("natl", None)
    finally:
        truth.ascat = orig
    # floor(x + 0.5): a centre 0.125 south of a grid row (x = r + 0.5) snaps to row r + 1; a centre 0.125
    # north (x = r - 0.5) snaps to row r. east 0.125 -> col c + 1 (x = c + 0.5) ; west 0.125 -> col c.
    seen_rc = {(r0 + 1, c0 + 1), (r0 + 2, c0 + 3), (r0 + 31, c0 + 51)}
    got = set(zip(*np.nonzero(t["seen"])))
    assert got == seen_rc, got
    assert t["spd"][r0 + 2, c0 + 3] == 52.0 and np.isnan(t["spd"][0, 0])
    # a cell at (r0+1, c0+1) is within +-2 rows and +-3 cols of (r0+2, c0+3): it sees the 52
    assert t["max_nb"][r0 + 1, c0 + 1] == 52.0 and t["y"][r0 + 1, c0 + 1] and t["y"][r0 + 2, c0 + 3]
    assert t["max_nb"][r0 + 31, c0 + 51] == 20.0 and not t["y"][r0 + 31, c0 + 51]
    # unseen cells are NaN and never positive, even next to the 52
    assert np.isnan(t["max_nb"][r0 + 2, c0 + 4]) and not t["y"][r0 + 2, c0 + 4]
    # box edge: (5, 7) reaches 2 rows and 3 cols; one further does not
    far = {"lat": np.array([lats[r0 + 3] - 0.125 + 0.0, lats[r0] - 0.125], np.float32),
           "lon": np.array([lons[c0] - 0.125, lons[c0 + 4] + 0.125], np.float32),
           "spd_kt": np.array([10.0, 60.0], np.float32)}
    truth.ascat = lambda *a, **k: far
    try:
        t2 = truth.ascat_target("natl", None, thr=48.0)
    finally:
        truth.ascat = orig
    # obs A -> (r0+4, c0), obs B (60 kt) -> (r0+1, c0+5): rows differ by 3 (outside 5 rows), so A is not positive
    assert t2["seen"][r0 + 4, c0] and t2["seen"][r0 + 1, c0 + 5]
    assert not t2["y"][r0 + 4, c0] and t2["y"][r0 + 1, c0 + 5]
    # none seen
    truth.ascat = lambda *a, **k: {"lat": np.zeros(0, np.float32), "lon": np.zeros(0, np.float32),
                                   "spd_kt": np.zeros(0, np.float32)}
    try:
        t3 = truth.ascat_target("natl", None)
    finally:
        truth.ascat = orig
    assert not t3["seen"].any() and np.isnan(t3["max_nb"]).all() and not t3["y"].any()
    truth.ascat = lambda *a, **k: None
    try:
        assert truth.ascat_target("natl", None) is None
    finally:
        truth.ascat = orig


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
