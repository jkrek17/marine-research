"""Tests for rk.diag. Run with pytest or `python3 tests/test_diag.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import diag  # noqa: E402

LATS = np.arange(60, 39.75, -0.25)
LONS = np.arange(300, 330.25, 0.25)
LA, LO = np.meshgrid(LATS, LONS, indexing="ij")


def test_ddy_linear_in_latitude():
    a = LA * 1.0  # 1 unit per degree latitude, northward
    g = diag.ddy(a, LATS)
    assert np.allclose(g, 1.0 / (diag.R_EARTH * np.radians(1.0)))


def test_ddx_linear_in_longitude():
    a = LO * 1.0
    g = diag.ddx(a, LATS, LONS)
    want = 1.0 / (diag.R_EARTH * np.cos(np.radians(LA)) * np.radians(1.0))
    assert np.allclose(g, want)


def test_warm_advection_sign():
    t = 280.0 - (LA - 50.0)  # colder to the north
    adv = diag.advection(t, np.zeros_like(t), np.full_like(t, 10.0), LATS, LONS)  # southerly wind
    # 10 m/s across 1 K per degree latitude (~111 km): about +7.8 K/day
    assert np.allclose(adv * diag.DAY, 10.0 / (diag.R_EARTH * np.radians(1.0)) * diag.DAY)
    assert (adv > 0).all()


def test_eady_textbook_value():
    # 850 -> 500 hPa, 20 m/s shear over 4000 m, N about 0.0115 /s at 45N: sigma ~ 0.31 f 0.005 / N
    shp = (3, 3)
    lats = np.array([45.0, 45.0, 45.0])
    z_lo, z_hi = np.full(shp, 1500.0), np.full(shp, 5500.0)
    t_lo, t_hi = np.full(shp, 273.0), np.full(shp, 250.0)
    u_lo, u_hi = np.full(shp, 10.0), np.full(shp, 30.0)
    zero = np.zeros(shp)
    s = diag.eady(u_lo, zero, z_lo, t_lo, 850.0, u_hi, zero, z_hi, t_hi, 500.0, lats)
    th_lo, th_hi = diag.theta(273.0, 850.0), diag.theta(250.0, 500.0)
    n = np.sqrt(diag.G / ((th_lo + th_hi) / 2) * (th_hi - th_lo) / 4000.0)
    want = 0.31 * diag.coriolis(45.0) * (20.0 / 4000.0) / n
    assert np.allclose(s, want)
    assert 0.5 < want * diag.DAY < 1.5  # per day, the usual range


def test_eady_unstable_is_nan():
    shp = (2, 2)
    s = diag.eady(np.zeros(shp), np.zeros(shp), np.full(shp, 1500.0), np.full(shp, 300.0), 850.0,
                  np.ones(shp), np.zeros(shp), np.full(shp, 5500.0), np.full(shp, 230.0), 500.0, np.array([50.0, 50.0]))
    assert np.isnan(s).all()


def test_smooth_keeps_nan_and_constant():
    a = np.full((20, 20), 5.0)
    a[3, 4] = np.nan
    s = diag.smooth(a, 2.0)
    assert np.isnan(s[3, 4]) and np.allclose(s[np.isfinite(s)], 5.0)


def test_coarsen_and_subsample():
    a = np.arange(16.0).reshape(4, 4)
    assert np.allclose(diag.coarsen(a, 2), [[2.5, 4.5], [10.5, 12.5]])
    assert np.allclose(diag.coarsen(a, 2, "max"), [[5, 7], [13, 15]])
    assert np.allclose(diag.subsample(a, 2), [[0, 2], [8, 10]])


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("ok")
