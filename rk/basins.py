"""The two study boxes, on the global 0.25 deg grid (721 x 1440, north to south, lon 0..359.75)."""
import numpy as np

BASINS = {
    "natl": {"name": "North Atlantic", "north": 67, "south": 30, "west": 285.0, "east": 359.75, "hour": 12},
    "npac": {"name": "North Pacific", "north": 67, "south": 30, "west": 160.0, "east": 245.0, "hour": 0},
}


def _b(basin):
    try:
        return BASINS[basin]
    except KeyError:
        raise KeyError("unknown basin %r (use one of %s)" % (basin, sorted(BASINS))) from None


def crop(basin):
    """Indices of the box in the global grid: (row slice, column index array)."""
    b = _b(basin)
    iy = slice(int(round((90 - b["north"]) * 4)), int(round((90 - b["south"]) * 4)) + 1)
    ix = np.arange(int(round(b["west"] * 4)), int(round(b["east"] * 4)) + 1)
    return iy, ix


def grid(basin):
    """Latitudes (north to south) and longitudes (0-360, west to east) of the box, 1-D."""
    b = _b(basin)
    iy, ix = crop(basin)
    lats = 90 - np.arange(iy.start, iy.stop) * 0.25
    return lats, ix * 0.25


def inside(basin, lat, lon):
    """True where the point is within the box (lon in any convention)."""
    b = _b(basin)
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float) % 360
    return (lat >= b["south"]) & (lat <= b["north"]) & (lon >= b["west"]) & (lon <= b["east"])


def sample(field, basin, lat, lon):
    """Bilinear sample of a field on the box grid at points; NaN outside the box."""
    lats, lons = grid(basin)
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float) % 360
    g = np.asarray(field, float)
    fy = (lats[0] - lat) / 0.25
    fx = (lon - lons[0]) / 0.25
    ny, nx = g.shape
    y0 = np.clip(np.floor(fy).astype(int), 0, ny - 2)
    x0 = np.clip(np.floor(fx).astype(int), 0, nx - 2)
    wy = np.clip(fy - y0, 0, 1)
    wx = np.clip(fx - x0, 0, 1)
    out = ((1 - wy) * (1 - wx) * g[y0, x0] + (1 - wy) * wx * g[y0, x0 + 1]
           + wy * (1 - wx) * g[y0 + 1, x0] + wy * wx * g[y0 + 1, x0 + 1])
    return np.where(inside(basin, lat, lon), out, np.nan)


def to_quarter(field_half, basin):
    """0.5 deg field -> the basin's 0.25 deg grid by bilinear interpolation.

    field_half holds every second 0.25 deg point of the box (rows [::2], columns [::2]) with the same
    north/west origin. Points shared with the 0.5 deg grid are returned unchanged. When the box has
    an even number of 0.25 deg columns or rows (natl: 300 columns) the last 0.25 point lies past the
    last 0.5 point and repeats it (constant, as in the day 5-7 study's lib.to_quarter).
    """
    lats, lons = grid(basin)
    ny, nx = len(lats), len(lons)
    f = np.asarray(field_half, float)
    if f.shape != (len(lats[::2]), len(lons[::2])):
        raise ValueError("field shape %s does not match the 0.5 deg %s grid %s"
                         % (f.shape, basin, (len(lats[::2]), len(lons[::2]))))
    yi, xi = np.arange(ny) / 2.0, np.arange(nx) / 2.0
    y0 = np.clip(np.floor(yi).astype(int), 0, f.shape[0] - 1)
    y1 = np.clip(y0 + 1, 0, f.shape[0] - 1)
    wy = (yi - y0)[:, None]
    x0 = np.clip(np.floor(xi).astype(int), 0, f.shape[1] - 1)
    x1 = np.clip(x0 + 1, 0, f.shape[1] - 1)
    wx = (xi - x0)[None, :]
    g = f[y0] * (1 - wy) + f[y1] * wy
    return g[:, x0] * (1 - wx) + g[:, x1] * wx
