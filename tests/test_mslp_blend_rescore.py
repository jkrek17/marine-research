"""Tests for the prominence re-score in studies/2026-11-16-mslp-blend-d7/rescore.py. Run: python3 tests/test_mslp_blend_rescore.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-16-mslp-blend-d7"))
import numpy as np
from rk import basins, score as rks
import candidates as cm
import rescore as RS

B = "natl"
LATS, LONS = basins.grid(B)
LA, LO = np.meshgrid(LATS, LONS, indexing="ij")


def low(lat, lon, depth, rad=500.0, f=None):
    f = np.full(LA.shape, 1015.0) if f is None else f
    return f - depth * np.exp(-(rks.km(LA, LO, lat, lon) / rad) ** 2)


def lows_of(f):
    lw = rks.find_lows(f, B, 1010.0)
    g = cm.geo(B)
    return lw, np.array([cm._drop_hpa(f, g, a, b) for a, b in zip(lw.lat, lw.lon)])


def test_drop_matches_rk_helper():
    f = low(45., 330., 15., f=low(55., 315., 40.))
    lw, drop = lows_of(f)
    for (a, b), d in zip(zip(lw.lat, lw.lon), drop):
        ref = rks.pressure_drop(f, B, a, b)[0]
        assert abs(ref - d) < 0.5, (ref, d)


def test_match_equals_low_case_at_T0_and_thinning():
    an = low(50., 320., 45., f=low(58., 300., 25.))
    fc = low(52., 326., 35., f=low(40., 340., 6., f=low(58., 303., 20.)))   # right lows plus a weak extra (drop ~6)
    lw, drop = lows_of(fc)
    tl = rks.find_lows(an, B, 1000.0, inset_deg=3.0)
    D = rks.km(tl.lat.to_numpy()[:, None], tl.lon.to_numpy()[:, None], lw.lat.to_numpy()[None], lw.lon.to_numpy()[None])
    fat = basins.sample(fc, B, tl.lat.to_numpy(), tl.lon.to_numpy())
    pos, hung, hit, dep = RS.match_all(D, lw.hpa.to_numpy(), drop, tl.hpa.to_numpy(), fat)
    ref, fa, nf = rks.low_case(an, fc, B)
    assert np.allclose(pos[:, 0], ref.pos_km) and np.allclose(dep[:, 0], ref.depth_err_hpa, atol=1e-3)
    assert (hit[:, 0].astype(bool) == ref.hit.to_numpy()).all()
    # a high threshold removes every low: all misses at 1000 km
    pos10, _, hit10, _ = RS.match_all(D, lw.hpa.to_numpy(), drop, tl.hpa.to_numpy(), fat, Ts=(100,))
    assert (pos10 == 1000).all() and not hit10.any()
    # hungarian never beats the nearest match
    assert (hung >= pos - 1e-6).all()


def test_false_count_thins_with_T():
    an = low(50., 320., 45.)
    fc = low(40., 340., 28., f=low(50., 320., 45.))              # deep extra low 28 hPa deep: false and prominent
    lw, drop = lows_of(fc)
    ta = rks.find_lows(an, B, 1005.0)
    dmin = rks.km(lw.lat.to_numpy()[:, None], lw.lon.to_numpy()[:, None], ta.lat.to_numpy()[None], ta.lon.to_numpy()[None]).min(1)
    f0 = int(((lw.hpa.to_numpy() < 1000) & (drop >= 0) & (dmin > 500)).sum())
    f40 = int(((lw.hpa.to_numpy() < 1000) & (drop >= 40) & (dmin > 500)).sum())
    assert f0 == 1 and f40 == 0
    assert f0 == rks.low_case(an, fc, B)[1]


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
