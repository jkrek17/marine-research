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


def test_names_roundtrip():
    for sp in S.grid_specs():
        assert S.spec_of(S.name(sp)) == sp


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
