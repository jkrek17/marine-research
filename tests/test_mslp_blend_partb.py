"""Tests for the mslp-blend-d7 Part B helpers (studies/2026-11-16-mslp-blend-d7/partb.py, partb_analyze.py) and the
rk helpers they use (rk.calibrate.isotonic_*, reliability_weeks, rk.score.crps_cdf). Offline.
Run with `python3 tests/test_mslp_blend_partb.py`."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "studies" / "2026-11-16-mslp-blend-d7"))

import numpy as np  # noqa: E402
from scipy.special import ndtr  # noqa: E402

from rk import calibrate as C, score as rks  # noqa: E402
import partb as PB  # noqa: E402
import partb_analyze as PA  # noqa: E402


def test_isotonic():
    r = np.random.default_rng(0)
    x = r.random(5000)
    y = (r.random(5000) < x ** 2).astype(float)
    xk, yk = C.isotonic_fit(x, y)
    assert np.all(np.diff(yk) >= 0) and np.all(np.diff(xk) > 0)
    p = C.isotonic_apply(np.array([0.1, 0.5, 0.95]), xk, yk)
    assert abs(p[0] - 0.01) < 0.05 and abs(p[1] - 0.25) < 0.07 and abs(p[2] - 0.9) < 0.08
    assert np.all(np.diff(C.isotonic_apply(np.linspace(0, 1, 50), xk, yk)) >= 0)
    assert C.isotonic_fit([0.1, 0.2, 0.3], [0, 0, 0]) is None and C.isotonic_fit([0.1], [1]) is None
    # decreasing data pools to the mean
    xk, yk = C.isotonic_fit([1, 2, 3, 4], [1, 1, 0, 0])
    xk, yk = C.isotonic_fit([1, 2, 3, 4], [1, 1, 0, 0])      # fully reversed: pooled to one block
    assert len(xk) == 1 and abs(yk[0] - 0.5) < 1e-12 and abs(xk[0] - 2.5) < 1e-12
    xk, yk = C.isotonic_fit([1, 2, 3, 4], [0, 1, 0, 1])
    assert np.allclose(yk, [0, 0.5, 0.5][:len(yk)]) or np.all(np.diff(yk) >= 0)


def test_reliability_weeks():
    r = np.random.default_rng(1)
    n = 4000
    p = r.random(n)
    y = (r.random(n) < p).astype(float)
    wk = r.integers(0, 40, n)
    t, v = C.reliability_weeks(p, y, wk)
    assert v == "pass" and t.n.sum() == n and t.judged.all()
    y2 = (r.random(n) < np.clip(p + 0.3, 0, 1)).astype(float)
    assert C.reliability_weeks(p, y2, wk)[1] == "fail"
    # a thin product: events in only 3 weeks -> not verifiable
    p3 = np.full(100, 0.5)
    y3 = np.zeros(100); y3[:5] = 1
    w3 = np.r_[[1, 1, 2, 2, 3], np.arange(95) + 10]
    t3, v3 = C.reliability_weeks(p3, y3, w3)
    assert v3 == "not verifiable" and t3.event_weeks.max() == 3


def test_crps_cdf():
    grid = np.linspace(-20, 20, 4001)
    # step forecast at x vs y: CRPS = |x - y|
    cdf = (grid[None, :] >= np.array([[1.0], [-2.0]])).astype(float)
    c = rks.crps_cdf(cdf, grid, np.array([3.0, -1.0]))
    assert np.allclose(c, [2.0, 1.0], atol=0.01)
    # normal(0, 1) vs y = 0.5: closed form
    cdf = ndtr(grid)[None, :]
    y = 0.5
    from math import sqrt, pi, exp
    phi = exp(-y * y / 2) / sqrt(2 * pi)
    exact = y * (2 * ndtr(y) - 1) + 2 * phi - 1 / sqrt(pi)
    assert abs(rks.crps_cdf(cdf, grid, np.array([y]))[0] - exact) < 5e-3


def test_wmedian():
    assert PB.wmedian([1, 2, 3], [1, 1, 1]) == 2.0
    assert PB.wmedian([1, 2, 3], [0.1, 0.1, 0.8]) == 3.0


def _V(spec):
    return [(w, np.array([[la, lo, p]], float)) for w, la, lo, p in spec]


def test_alternatives():
    # main low 50N 330E, 980; 55% of voters agree; 30% have it 700 km east (985); 15% too few to show
    V = _V([(0.55, 50, 330, 980), (0.30, 50, 340, 985), (0.15, 58, 330, 975)])
    main = (50.0, 330.0, 980.0)
    a = PB.alternatives(main, V)
    assert len(a) == 1 and a[0]["kind"] == "pos" and abs(a[0]["share"] - 0.30) < 1e-9
    assert abs(a[0]["lon"] - 340) < 0.5 and abs(a[0]["hpa"] - 985) < 1e-9 and a[0]["dist_km"] > 600
    # same place, 15 hPa deeper, 25% of voters -> a depth alternative
    V = _V([(0.75, 50, 330, 980), (0.25, 50.5, 330.5, 965)])
    a = PB.alternatives(main, V)
    assert len(a) == 1 and a[0]["kind"] == "depth" and a[0]["dist_km"] < 300
    # within both tolerances -> agrees, nothing shown
    assert PB.alternatives(main, _V([(0.6, 50, 330, 980), (0.4, 50.5, 330.5, 986)])) == []
    # at most two, the best supported first
    V = _V([(0.2, 50, 330, 980), (0.25, 50, 340, 985), (0.2, 56, 330, 985), (0.2, 44, 330, 985), (0.15, 50, 320, 985)])
    a = PB.alternatives(main, V)
    assert len(a) == 2 and a[0]["share"] >= a[1]["share"]
    # a group sitting on another map low is not repeated
    V = _V([(0.5, 50, 330, 980), (0.5, 50, 340, 985)])
    assert PB.alternatives(main, V, others=[(50, 340)]) == []
    # voters farther than the reach are ignored
    assert PB.alternatives(main, _V([(0.5, 50, 330, 980), (0.5, 50, 380, 985)])) == []


def test_alt_geometry_and_verify():
    la, lo = PA.dest(50.0, 330.0, 90.0, 500.0)
    assert abs(float(rks.km(50.0, 330.0, la, lo)) - 500.0) < 1.0
    assert abs(PA.bearing(50.0, 330.0, la, lo) - 90.0) < 3.0
    T = np.array([[50.0, 340.0, 985.0]])
    assert PA.verify_pos(T, 50.0, 339.0, 50.0, 330.0)             # near the alternative, far from the main low
    assert not PA.verify_pos(T, 50.0, 339.0, 50.0, 339.5)         # the main low is there too
    assert not PA.verify_pos(np.zeros((0, 3)), 50.0, 339.0, 50.0, 330.0)

    class R:
        pass
    r = R()
    r.kind, r.alat, r.alon, r.ahpa, r.mlat, r.mlon, r.mhpa, r.adist_km = "pos", 50.0, 340.0, 985.0, 50.0, 330.0, 980.0, 715.0
    v, pl = PA.alt_verify(r, T)
    assert v and 0.0 <= pl <= 1.0 / 7 + 1e-9
    r.kind, r.alat, r.alon, r.ahpa, r.mlat, r.mlon, r.mhpa, r.adist_km = "depth", 50.0, 340.0, 985.0, 50.0, 340.5, 965.0, 40.0
    assert PA.alt_verify(r, T)[0]                                   # analysed 985 is closer to 985 than to 965
    r.ahpa, r.mhpa = 965.0, 985.0
    assert not PA.alt_verify(r, T)[0]


def test_depth_distribution():
    r = np.random.default_rng(2)
    n, nv = 1500, 30
    m = r.uniform(960, 1000, n)
    sig = 3.0
    X = m[:, None] + r.normal(0, sig, (n, nv))
    W = np.ones((n, nv))
    mm = np.median(X, 1)                                           # the map low = the voters' median
    y = mm + r.normal(0, 3 * sig, n)                               # the analysis scatters three times wider
    f = PA.fit_spread(mm, X, W, y)
    pit = PA.cdf_voters(mm, X, W, f, y)
    cov = ((pit >= 0.1) & (pit <= 0.9)).mean()
    assert abs(cov - 0.8) < 0.01 and 2.2 < f < 3.6, (cov, f)
    hist = np.histogram(pit, bins=10, range=(0, 1))[0] / n
    assert np.abs(hist - 0.1).max() < 0.045
    F = PA.cdf_grid(mm[:50], X[:50], W[:50], f)
    assert np.all(np.diff(F, axis=1) >= -1e-6) and F[:, 0].max() < 0.01 and F[:, -1].min() > 0.99
    q50 = PA.quantile_from_cdf(F, 0.5)
    assert np.abs(q50 - mm[:50]).max() < 1.0                        # the map low sits at the 50% depth
    q10, q90 = PA.quantile_from_cdf(F, 0.1), PA.quantile_from_cdf(F, 0.9)
    assert np.all(q10 < q50) and np.all(q90 > q50)
    # climatology rival is centred on the vote depth and a proper CDF
    u, G = PA.clim_cdf(np.array([-3.0, 0.0, 2.0, 5.0]))
    assert np.all(np.diff(G) >= 0) and G[0] < 0.01 and G[-1] > 0.99


def test_skill_and_pinball():
    r = np.random.default_rng(3)
    wk = np.repeat(np.arange(30), 20)
    rival = r.random(600) + 1.0
    s, lo, hi = PA.skill(rival * 0.7, rival, wk, 300)
    assert abs(s - 0.3) < 1e-9 and lo <= s + 1e-9 and s <= hi + 1e-9
    s, lo, hi = PA.skill(rival, rival, wk, 300)
    assert abs(s) + abs(lo) + abs(hi) < 1e-9
    assert PA.pinball(np.array([10.0]), np.array([4.0]), 0.8)[0] == 0.8 * 6
    assert abs(PA.pinball(np.array([2.0]), np.array([4.0]), 0.8)[0] - 0.2 * 2) < 1e-12


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
