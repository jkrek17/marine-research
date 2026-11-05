"""Synoptic diagnostics on a regular latitude-longitude grid (rows north to south, columns west to east,
spacing in degrees): spherical derivatives, temperature advection, Eady growth rate, smoothing, block
coarsening. Inputs are plain 2-D numpy arrays plus the 1-D latitudes and longitudes of the grid.

Units: winds m/s, temperatures K, heights m (geopotential height), pressures hPa. Outputs SI (per second)
unless the name says otherwise; multiply by DAY for per day.
"""
import numpy as np

R_EARTH = 6.371e6
OMEGA = 7.292e-5
G = 9.80665
KAPPA = 0.2857
DAY = 86400.0


def coriolis(lats):
    """f (1/s) for latitudes in degrees."""
    return 2 * OMEGA * np.sin(np.radians(np.asarray(lats, float)))


def ddx(a, lats, lons):
    """d a / d x (per metre, eastward) by centred differences in longitude (one-sided at the edges)."""
    lats = np.asarray(lats, float)
    dlon = np.radians(np.gradient(np.asarray(lons, float)))
    da = np.gradient(np.asarray(a, float), axis=1)
    return da / (R_EARTH * np.cos(np.radians(lats))[:, None] * dlon[None, :])


def ddy(a, lats):
    """d a / d y (per metre, northward). Works for rows ordered either way."""
    dlat = np.radians(np.gradient(np.asarray(lats, float)))
    da = np.gradient(np.asarray(a, float), axis=0)
    return da / (R_EARTH * dlat[:, None])


def advection(s, u, v, lats, lons):
    """-(u ds/dx + v ds/dy): the local rate of change of s from the wind carrying it (s units per second).
    Positive = the wind brings higher values (warm advection for temperature)."""
    return -(u * ddx(s, lats, lons) + v * ddy(s, lats))


def theta(t_k, p_hpa):
    """Potential temperature (K)."""
    return t_k * (1000.0 / p_hpa) ** KAPPA


def eady(u_lo, v_lo, z_lo, t_lo, p_lo, u_hi, v_hi, z_hi, t_hi, p_hi, lats):
    """Maximum Eady growth rate 0.31 |f| |dV/dz| / N (1/s) for the layer between two pressure levels
    (lo = lower, e.g. 850 hPa; hi = upper, e.g. 500 hPa). dV/dz and N come from the two levels' winds,
    heights and potential temperatures. NaN where the layer is not statically stable (N^2 <= 0)."""
    dz = np.asarray(z_hi, float) - np.asarray(z_lo, float)
    th_lo, th_hi = theta(t_lo, p_lo), theta(t_hi, p_hi)
    n2 = G / (0.5 * (th_lo + th_hi)) * (th_hi - th_lo) / dz
    shear = np.hypot(u_hi - u_lo, v_hi - v_lo) / dz
    f = np.abs(coriolis(lats))[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = 0.31 * f * shear / np.sqrt(n2)
    return np.where(n2 > 0, out, np.nan)


def smooth(a, sigma):
    """Gaussian smoothing (sigma in grid cells) that ignores NaN cells and leaves them NaN."""
    from scipy.ndimage import gaussian_filter
    a = np.asarray(a, float)
    ok = np.isfinite(a)
    num = gaussian_filter(np.where(ok, a, 0.0), sigma, mode="nearest")
    den = gaussian_filter(ok.astype(float), sigma, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    return np.where(ok, out, np.nan)


def coarsen(a, k, how="mean"):
    """Block reduce by k x k cells, keeping only whole blocks ('mean' ignores NaN, 'max' too)."""
    a = np.asarray(a, float)
    ny, nx = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    b = a[:ny, :nx].reshape(ny // k, k, nx // k, k)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(b, axis=(1, 3)) if how == "max" else np.nanmean(b, axis=(1, 3))


def subsample(a, k):
    """Every k-th cell starting at the first (keeps cell centres on the coarser grid)."""
    return np.asarray(a)[::k, ::k]
