"""Tests for studies/2026-11-05-core-lift-bias/fit_score.py. Offline. Run with pytest or directly."""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-05-core-lift-bias"))

import numpy as np  # noqa: E402

import fit_score as F  # noqa: E402
from rk import cases, score  # noqa: E402
from rk.basins import grid  # noqa: E402


def test_tiles_match_rk_tile_hits():
    for basin in ("natl", "npac"):
        lats, lons = grid(basin)
        r = np.random.default_rng(3)
        shape = (len(lats), len(lons))
        seen = r.random(shape) < 0.5
        ob = np.where(seen, r.gamma(6, 5, shape), np.nan)
        fc = r.gamma(6, 5, shape)
        t = F.Tiles(basin, seen)
        for thr in (34, 48, 64):
            ref = score.tile_counts(score.tile_hits(fc, ob, seen, lats, lons, thr))
            nt, h, m, fa = t.counts(fc, ob, thr)
            assert (h, m, fa) == tuple(ref), (basin, thr, (h, m, fa), ref)
            assert nt == len(score.tile_hits(fc, ob, seen, lats, lons, thr))


def test_corelift_matches_page_rule():
    r10 = np.array([30.0, 30.0, 30.0, 31.0])
    P = np.array([0.34, 0.35, 0.9, 0.0])
    Pg = np.array([0.0, 0.0, 0.0, 0.6])
    assert F.corelift(r10, P, Pg).tolist() == [30.0, 35.0, 35.0, 34.0]
    assert F.corelift(r10, P, Pg, L=8).tolist() == [30.0, 38.0, 38.0, 34.0]


def test_folds_are_whole_weeks_and_spread():
    days = [dt.datetime(2025, 11, 1) + dt.timedelta(days=i) for i in range(151)]
    tune = [d for d in days if cases.split(d) == "tune"]
    f = {F.folds(d) for d in tune}
    assert f == set(range(F.FOLDS))
    for d in tune:   # same ISO week -> same fold
        assert F.folds(d) == F.folds(d - dt.timedelta(days=d.weekday()))


def test_group_of_covers_steps():
    for s in (24, 30, 48, 54, 72, 78, 96, 102, 120, 126):
        assert F.group_of(s) in F.GROUPS


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
