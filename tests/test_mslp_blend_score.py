"""Tests for studies/2026-11-16-mslp-blend-d7/score.py on synthetic MSLP maps. Run: python3 tests/test_mslp_blend_score.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-16-mslp-blend-d7"))
import numpy as np
from rk import basins, score as rks
import score as S

B = "natl"
LATS, LONS = basins.grid(B)
LA, LO = np.meshgrid(LATS, LONS, indexing="ij")
MASK = np.ones(LA.shape, np.uint8)


def low(lat, lon, depth=40.0, rad=500.0, base=1015.0, f=None):
    f = np.full(LA.shape, base) if f is None else f
    return f - depth * np.exp(-(rks.km(LA, LO, lat, lon) / rad) ** 2)


def test_perfect_and_field_stats():
    an = low(50., 320.)
    row, lows, fa, nf = S.case(an, an, MASK, B)
    assert row["rmse"] == 0 and row["bias"] == 0 and row["rmse_ls"] == 0 and abs(row["sharp"] - 1) < 1e-9
    assert len(lows) == 1 and lows.pos_km[0] < 1 and lows.pos_h[0] < 1 and lows.hit[0] and fa == 0 and nf == 1
    row, *_ = S.case(an + 2.0, an, MASK, B)
    assert abs(row["rmse"] - 2) < 1e-6 and abs(row["bias"] - 2) < 1e-6 and row["rmse_ls"] < 2.0 + 1e-6
    # a smooth offset survives smoothing, a fine-scale error does not
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, LA.shape)
    row, *_ = S.case(an + noise, an, MASK, B)
    assert row["rmse_ls"] < 0.2 * row["rmse"]


def test_open_water_mask():
    an = low(50., 320.)
    fc = an.copy(); fc[:, :100] += 5.0
    m = np.ones(LA.shape, np.uint8); m[:, :100] = 0
    row, *_ = S.case(fc, an, m, B)
    assert row["rmse"] == 0 and row["bias"] == 0


def test_position_and_cached_path_matches_low_case():
    an = low(50., 320., 45.)
    fc = low(50., 320. + 7.0, 30.)            # about 500 km east, and 15 hPa shallow
    row, lows, fa, nf = S.case(fc, an, MASK, B)
    ref, ref_fa, ref_nf = rks.low_case(an, fc, B)
    assert np.allclose(lows.pos_km, ref.pos_km) and np.allclose(lows.depth_err_hpa, ref.depth_err_hpa)
    assert (lows.hit == ref.hit).all() and fa == ref_fa and nf == ref_nf
    assert 400 < lows.pos_km[0] < 600 and abs(lows.depth_err_hpa[0] - 15) < 1.0
    assert row["sharp"] < 1.0               # shallower low, weaker gradient


def test_miss_costs_cap_and_false_low():
    an = low(50., 320., 40.)
    fc = np.full(LA.shape, 1015.0)            # no low at all
    row, lows, fa, nf = S.case(fc, an, MASK, B)
    assert lows.pos_km[0] == 1000 and lows.pos_h[0] == 1000 and not lows.hit[0] and nf == 0
    assert np.isnan(lows.along_km[0]) and lows.depth_err_hpa[0] > 30
    fc = low(40., 300., 30., f=low(50., 320., 40.))   # right low plus a far, deep extra
    row, lows, fa, nf = S.case(fc, an, MASK, B)
    assert fa == 1 and nf == 2


def test_hungarian_is_one_to_one():
    an = low(56., 312., 40., f=low(48., 328., 40.))
    fc = low(52., 320., 40.)                  # one forecast low between two analysed lows
    _, lows, _, _ = S.case(fc, an, MASK, B)
    assert len(lows) == 2
    assert (lows.pos_km < 1000).all()         # both take the single forecast low in the house form
    assert sorted(lows.pos_h)[1] == 1000      # only one gets it one-to-one


def test_along_cross_track():
    prev = low(50., 310.)
    an = low(50., 320.)                       # moved east
    # forecast ahead (east) and to the south: along > 0, cross: south of an eastward track is right = positive
    fc = low(47., 322.)
    _, lows, _, _ = S.case(fc, an, MASK, B, an_prev=prev)
    assert lows.along_km[0] > 100 and lows.cross_km[0] > 200, lows.to_dict("records")
    assert abs(np.hypot(lows.along_km[0], lows.cross_km[0]) - lows.pos_km[0]) < 60   # plane approximation
    _, lows, _, _ = S.case(low(53., 318.), an, MASK, B, an_prev=prev)
    assert lows.along_km[0] < 0 and lows.cross_km[0] < 0                             # behind, left (north)
    _, lows, _, _ = S.case(fc, an, MASK, B)                                          # no earlier map
    assert np.isnan(lows.along_km[0])
    _, lows, _, _ = S.case(fc, an, MASK, B, an_prev=an)                              # stationary
    assert np.isnan(lows.cross_km[0])


def test_strong_low_depth_both_directions():
    an = low(50., 320., 40.)                  # 975
    fc = low(50., 320., 33.)                  # 982: not a forecast low < 980
    r = S.case_full(fc, an, MASK, B)
    assert len(r["fdeep"]) == 0 and abs(r["lows"].depth_err_hpa[0] - 7) < 1
    fc = low(50., 320., 45.)                  # 970
    r = S.case_full(fc, an, MASK, B)
    assert len(r["fdeep"]) == 1 and abs(r["fdeep"].err_hpa[0] + 5) < 1


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
