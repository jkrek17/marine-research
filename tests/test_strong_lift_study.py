"""Tests for studies/2026-11-06-strong-core-lift/score.py. Offline. Run with pytest or directly."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "studies" / "2026-11-06-strong-core-lift"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STUDY))

import numpy as np  # noqa: E402

import score as S  # noqa: E402
from rk.basins import grid  # noqa: E402


def _case(basin="natl", seed=5):
    lats, lons = grid(basin)
    shape = (len(lats), len(lons))
    r = np.random.default_rng(seed)
    seen = r.random(shape) < 0.5
    d = {"seen": seen, "ocean": np.ones(shape, bool), "spd": np.where(seen, r.gamma(6, 5, shape), np.nan).astype(np.float32),
         "anl": np.where(r.random(shape) < 0.5, r.gamma(6, 5, shape), np.nan).astype(np.float32),
         "det": r.gamma(6, 5, shape).astype(np.float32), "gfs": r.gamma(6, 5, shape).astype(np.float32),
         "ifs": r.gamma(6, 5, shape).astype(np.float32), "p48nb_h": r.random(shape).astype(np.float32),
         "s925": r.gamma(6, 6, shape).astype(np.float32), "sa": r.normal(4, 4, shape).astype(np.float32),
         "has_low": True}
    d["strong"] = np.fmax(d["gfs"], d["ifs"])
    return d


def test_counter_matches_fit_score():
    import fit_score as F
    d = _case()
    cnt = S.Counter("natl", d)
    f = d["det"] + 3
    ref = F.case_counts(d, F.Tiles("natl", d["seen"]), f)
    got = dict(zip(S.COLS, cnt.counts(f)))
    assert all(got[k] == ref[k] for k in ref)


def test_sea_air_factor_bands():
    f = S.sea_air_factor(np.array([-3, 1.9, 2, 4.9, 5, 7.9, 8, 12], np.float32))
    assert np.allclose(f, [0.87, 0.87, 0.94, 0.94, 1.04, 1.04, 1.13, 1.13])


def test_mixdown_raises_only_on_candidates():
    d = _case()
    base = d["det"]
    out = S.mixdown(base, d["strong"], d["s925"], d["sa"], d["ocean"], 0.5)
    assert (out >= base).all()
    quiet = (base < 28) & (d["strong"] < 34)
    assert (out[quiet] == base[quiet]).all()
    full = S.mixdown(base, d["strong"], d["s925"], d["sa"], d["ocean"], 1.0)
    cand = ~quiet
    tgt = d["s925"] * S.sea_air_factor(d["sa"])
    assert np.allclose(full[cand], np.maximum(base, tgt)[cand])


def test_products_follow_definitions():
    d = _case()
    D, s = d["det"], d["strong"]
    assert np.array_equal(S.make(("DS1", 6, 44, None), d), np.where(s >= 44, D + 6, D).astype(np.float32))
    assert np.array_equal(S.make(("DS2", None, 44, None), d), np.where(s >= 44, np.maximum(D, s), D).astype(np.float32))
    dg = S.make(("DG", None, None, None), d)
    cand = (D >= 28) | (s >= 34)
    assert np.array_equal(dg, np.where(cand & (d["p48nb_h"] >= 0.25), D + 5, D).astype(np.float32))
    d.pop("det")
    assert S.make(("DS1", 6, 44, None), d) is None and S.make(("CLS1", 6, 44, None), d) is None


def test_desk_stability_mask_taper_and_theta():
    n = 21
    base = np.full((n, n), 30.0, np.float32)
    t925 = np.full((n, n), 275.0)
    p = np.full((n, n), 1000.0)
    tsfc = np.full((n, n), 270.0)          # theta_sfc 270 < theta925 ~ 279.6: stable
    assert np.array_equal(S.desk_stability_wind(base, tsfc, p, t925), base)
    tsfc[10, 10] = 285.0                    # theta_sfc 285 >= theta925: one unstable cell
    out = S.desk_stability_wind(base, tsfc, p, t925)
    fac = 3.0 ** 0.15
    assert np.isclose(out[10, 10], 30 * fac, rtol=1e-5)          # full factor in the mask
    assert np.isclose(fac, 1.179, atol=1e-3)
    assert 30 < out[10, 11] < out[10, 10] and 30 < out[10, 12] < out[10, 11]   # taper over the 2-cell rim
    assert out[10, 13] == 30.0 and out[13, 13] == 30.0                         # nothing beyond the rim
    assert (out >= base).all()
    # equal theta counts as unstable (<=): T925 (1000/925)^(2/7) == T_sfc at p = 1000
    t = np.full((n, n), 280.0)
    tsfc2 = t * (1000.0 / 925.0) ** (2.0 / 7.0)
    assert (S.desk_stability_wind(base, tsfc2, p, t) > base).all()
    # pressure matters: lower surface pressure raises theta_sfc
    assert (S.desk_stability_wind(base, np.full((n, n), 275.0), np.full((n, n), 925.0), t925) > base).all()
    assert not np.isnan(S.desk_stability_wind(base, np.full((n, n), np.nan), p, t925)).any()


def test_gated_mixdown():
    ocean = np.ones((1, 5), bool)
    s925 = np.array([[40, 40, 30, 50, 45]], np.float32)
    sa = np.array([[4.9, 6, 6, 9, np.nan]], np.float32)
    base = np.full((1, 5), 41.0, np.float32)
    out = S.gated_mixdown(base, s925, sa, ocean)
    assert np.allclose(out[0], [41, 41.6, 41, 56.5, 41])      # 40 x 1.04 = 41.6; 50 x 1.13 = 56.5; raise only
    assert (S.gated_mixdown(base, s925, sa, ~ocean) == base).all()


def test_lift_columns_and_sHe():
    d = _case()
    D = d["det"]
    she = S.make(("SHe", None, None, None), d)
    assert np.allclose(she, D * 3.0 ** 0.15, rtol=1e-5)
    c = dict(zip(S.LIFT_COLS, S.lift_columns(she, D, d)))
    assert c["n_lift"] == int((she > D + 0.05).sum()) and c["n_lift_seen"] == int(((she > D + 0.05) & d["seen"]).sum())
    assert c["n_lift_a48"] <= c["n_lift_a34"] <= c["n_lift_seen"] <= c["n_lift"]
    low = (she > D + 0.05) & d["seen"] & (D < 34)
    assert c["n_err_low"] == int(low.sum()) and np.isclose(c["sum_err_low"], (she - d["spd"])[low].sum(), rtol=1e-4)


def test_names_roundtrip():
    for sp in S.grid_specs():
        assert S.spec_of(S.name(sp)) == sp


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
