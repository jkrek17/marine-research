"""Objective surface fronts from a gridded thermal field: the thermal front parameter (TFP) method.

The textbook rule-based front finder (Renard and Clarke 1965; Hewson 1998), used as the baseline any
learned or agentic front analysis has to beat. On a regular lat-lon box:

    g   = |grad theta|                      (K per 100 km), theta smoothed first
    n   = grad theta / g                    unit vector pointing to the WARM side
    TFP = -grad(g) . n

The front line is where TFP = 0 at the strongest gradient (TFP goes from negative to positive walking
toward the warm air), kept only where g is at least `grad_min`, optionally moved `shift_cells` grid cells
toward the warm side (analysts draw the front on the warm edge of the zone, not in its middle). Each
point is typed by the 10 m wind blowing across the line: from the cold side toward the warm side = cold
front, the other way = warm front, under `stat_ms` either way = stationary. Lines are split where the
type changes and pieces shorter than `min_len_nm` are dropped.

Returns plain dicts {"type", "lat", "lon"} (lon 0-360) so callers can curve them with rk.fronts.smooth.
Occlusions are not found here: that needs the low and the 700 hPa warm tongue, which callers have.
"""
import numpy as np

from rk import diag

NM_PER_KM = 1 / 1.852


def tfp_fields(theta, lat, lon, sigma=1.5):
    """(g K/100 km, nx, ny unit vector to warm, TFP K/(100 km)^2) on the box; NaN where theta is NaN."""
    th = diag.smooth(theta, sigma) if sigma else np.asarray(theta, float)
    gx = diag.ddx(th, lat, lon) * 1e5
    gy = diag.ddy(th, lat) * 1e5
    g = np.hypot(gx, gy)
    with np.errstate(invalid="ignore", divide="ignore"):
        nx, ny = gx / g, gy / g
    tfp = -(diag.ddx(g, lat, lon) * 1e5 * nx + diag.ddy(g, lat) * 1e5 * ny)
    return g, nx, ny, tfp


def _interp(a, lat, lon):
    from scipy.interpolate import RegularGridInterpolator
    la = np.asarray(lat, float)
    if la[0] > la[-1]:
        la, a = la[::-1], a[::-1]
    f = RegularGridInterpolator((la, np.asarray(lon, float)), a, bounds_error=False, fill_value=np.nan)
    return lambda plat, plon: f(np.column_stack([plat, plon]))


def _len_nm(la, lo):
    if len(la) < 2:
        return 0.0
    p = np.radians(la)
    dl = np.radians(np.diff(lo))
    h = np.sin(np.diff(p) / 2) ** 2 + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dl / 2) ** 2
    return float(np.sum(6371.0 * NM_PER_KM * 2 * np.arcsin(np.minimum(1, np.sqrt(h)))))


def _runmean(a, w):
    if w <= 1 or len(a) < 2:
        return a
    k = np.ones(min(w, len(a))) / min(w, len(a))
    num = np.convolve(a, k, mode="same")
    den = np.convolve(np.ones_like(a), k, mode="same")
    return num / den


def find_fronts(theta, u, v, lat, lon, sigma=1.5, grad_min=4.0, min_len_nm=250.0, shift_cells=0.0,
                stat_ms=1.5, wind_sigma=1.0, type_window=9):
    """TFP fronts on a lat-lon box. theta (K), u/v (m/s) shaped (len(lat), len(lon)); lat either order.
    grad_min in K per 100 km. Returns [{"type": cold|warm|stationary, "lat": array, "lon": array}]."""
    import contourpy
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    g, nx, ny, tfp = tfp_fields(theta, lat, lon, sigma)
    # where TFP rises toward the warm side: the zero there is the gradient maximum, not the edge minimum
    dtfp = diag.ddx(tfp, lat, lon) * nx + diag.ddy(tfp, lat) * ny
    us = diag.smooth(u, wind_sigma) if wind_sigma else u
    vs = diag.smooth(v, wind_sigma) if wind_sigma else v
    LON, LAT = np.meshgrid(lon, lat)
    z = np.where(np.isfinite(tfp), tfp, np.nan)
    lines = contourpy.contour_generator(x=LON, y=LAT, z=np.ma.masked_invalid(z)).lines(0.0)
    I = {k: _interp(a, lat, lon) for k, a in (("g", g), ("nx", nx), ("ny", ny), ("d", dtfp), ("u", us), ("v", vs))}
    res = abs(lat[1] - lat[0])
    out = []
    for ln in lines:
        if len(ln) < 3:
            continue
        plon, plat = ln[:, 0], ln[:, 1]
        gg, ex, ey, dd = I["g"](plat, plon), I["nx"](plat, plon), I["ny"](plat, plon), I["d"](plat, plon)
        keep = (gg >= grad_min) & (dd > 0) & np.isfinite(ex)
        if shift_cells:
            plat = plat + shift_cells * res * np.nan_to_num(ey)
            plon = plon + shift_cells * res * np.nan_to_num(ex) / np.maximum(np.cos(np.radians(plat)), 0.2)
        vn = I["u"](plat, plon) * ex + I["v"](plat, plon) * ey      # + = blowing toward the warm side
        vn = _runmean(np.nan_to_num(vn), type_window)                 # type follows the along-front mean, not one point
        typ = np.where(vn > stat_ms, "cold", np.where(vn < -stat_ms, "warm", "stationary"))
        # runs of kept points with one type
        start = None
        for i in range(len(plat) + 1):
            same = i < len(plat) and keep[i] and (start is None or typ[i] == typ[start])
            if start is not None and not same:
                la, lo = plat[start:i], plon[start:i]
                if _len_nm(la, lo) >= min_len_nm:
                    out.append({"type": str(typ[start]), "lat": la.copy(), "lon": lo.copy()})
                start = None
            if i < len(plat) and keep[i] and start is None:
                start = i
    return out
