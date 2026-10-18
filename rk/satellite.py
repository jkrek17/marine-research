"""Geostationary infrared imagery around storms: GridSat-B1 boxes and storm-centred crops.

gridsat_ir()  one GridSat-B1 v02r01 time, global 11 um IR window brightness temperature (limb corrected,
              `irwin_cdr`), read with byte ranges so only the IR chunk (~9 MB of a 30-55 MB file) is streamed
box()         the IR over a basin box with margins, cached as truth kind `gridsat` (int16, ~1-2 MB per file)
crop()        a storm-centred azimuthal-equidistant crop, north-up or rotated so the storm moves up the image
heading()     direction of motion (degrees clockwise from north) from two positions

GridSat-B1 (NOAA CDR, Knapp et al. 2011): 0.07 deg, 3-hourly, 70S-70N, 1980 onward, GOES, Himawari and Meteosat
merged; the water-vapour channel is empty in recent years, so only IR is read. Views are slanted north of about
60N; `sat` says which satellite filled each pixel.
"""
import datetime as dt
import io
import math
import re

import numpy as np

from . import fetch
from .store import truth_locate, truth_save

URL = ("https://noaa-cdr-gridsat-b1-pds.s3.amazonaws.com/data/{t:%Y}/"
       "GRIDSAT-B1.{t:%Y.%m.%d.%H}.v02r01.nc")
FILL = -31999
SCALE, OFFSET = 0.01, 200.0          # irwin_cdr int16 -> K
EARTH_KM = 6371.0
# Boxes the crops are cut from: the basin boxes (rk.basins) widened so a 1200 km crop of a low at the box edge
# stays whole. (south, north, west, east), longitudes 0-360 continuous (natl runs past 360).
SAT_BOX = {"natl": (20.0, 70.0, 255.0, 375.0), "npac": (20.0, 70.0, 130.0, 265.0)}


class RangeFile(io.RawIOBase):
    """Read-only file over HTTP byte ranges, in blocks, for h5py. `fetched` counts bytes downloaded."""

    def __init__(self, url, block=1 << 20):
        r = fetch.get(url, (0, 0))
        if r is None:
            raise FileNotFoundError(url)
        self.url, self.block, self.pos, self.fetched = url, block, 0, 0
        self.size = int(r.headers["Content-Range"].rsplit("/", 1)[1])
        self._blocks = {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def _fetch(self, b0, b1):
        """Download blocks b0..b1 (inclusive) that are not held yet, in one request per missing run."""
        b = b0
        while b <= b1:
            if b in self._blocks:
                b += 1
                continue
            e = b
            while e + 1 <= b1 and e + 1 not in self._blocks:
                e += 1
            lo, hi = b * self.block, min((e + 1) * self.block, self.size) - 1
            data = fetch.get(self.url, (lo, hi)).content
            if len(data) != hi - lo + 1:
                raise IOError("short read %d of %d bytes: %s" % (len(data), hi - lo + 1, self.url))
            self.fetched += len(data)
            for k in range(b, e + 1):
                self._blocks[k] = data[(k - b) * self.block:(k - b + 1) * self.block]
            b = e + 1

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        b0, b1 = self.pos // self.block, (self.pos + n - 1) // self.block
        self._fetch(b0, b1)
        out = b"".join(self._blocks[k] for k in range(b0, b1 + 1))
        s = self.pos - b0 * self.block
        buf[:n] = out[s:s + n]
        self.pos += n
        return n


def gridsat_ir(valid):
    """Global GridSat-B1 IR at a valid time -> {"lat" (south to north), "lon" (-180..180), "tb" int16 raw
    (K = tb * 0.01 + 200, FILL missing), "sat" int8 (primary satellite, index into satnames and satlon, -1 none;
    unpacked from satid_ir), "satnames", "satlon" (sub-satellite longitude), "bytes"} or
    None when the file is not posted."""
    import h5py
    try:
        f = RangeFile(URL.format(t=valid))
    except FileNotFoundError:
        return None
    with h5py.File(f, "r") as h:
        names = [bytes(row).replace(b"\x00", b"").decode().strip() for row in h["satname"][0]]
        packed = h["satid_ir"][0].astype(np.int16) & 0xFF            # signed byte -> unsigned
        sat = (packed // 15).astype(np.int8)                           # primary satellite; 14 = none
        sat[sat >= len(names)] = -1
        out = {"lat": h["lat"][:].astype(np.float32), "lon": h["lon"][:].astype(np.float32),
               "tb": h["irwin_cdr"][0], "sat": sat, "satnames": np.array(names),
               "satlon": h["satlon"][0].astype(np.float32)}
    out["bytes"] = f.fetched
    return out


def cut(g, basin):
    """A gridsat_ir() dict -> the SAT_BOX of a basin: rows north to south, columns west to east with
    longitudes continuous from the box's west edge (natl runs past 360)."""
    s, n, w, e = SAT_BOX[basin]
    rel = (g["lon"].astype(np.float64) - w) % 360.0
    ix = np.nonzero(rel <= e - w)[0]
    ix = ix[np.argsort(rel[ix], kind="stable")]
    iy = np.nonzero((g["lat"] >= s) & (g["lat"] <= n))[0][::-1]
    return {"lat": g["lat"][iy], "lon": (w + rel[ix]).astype(np.float32),
            "tb": g["tb"][np.ix_(iy, ix)], "sat": g["sat"][np.ix_(iy, ix)], "satnames": g["satnames"],
            "satlon": g["satlon"]}


def _check_hour(valid):
    if valid.hour % 6 or valid.minute:
        raise ValueError("gridsat truth files are 00/06/12/18 UTC only (a release holds 124 assets): %s" % valid)


def box(basin, valid, download=True):
    """IR over the basin's SAT_BOX at a valid time -> {"lat", "lon", "tb" (K, float32, NaN missing), "sat",
    "satnames", "satlon", "vza" (view zenith angle, degrees, NaN where no satellite)} or None. Cache, legacy, release (truth kind `gridsat`); with download=True a missing file is
    built from GridSat-B1 for BOTH basins (one read serves both) and marked unpublished."""
    _check_hour(valid)
    p = truth_locate("gridsat", basin, valid)
    if p is None:
        if not download:
            return None
        g = gridsat_ir(valid)
        if g is None:
            return None
        for b in SAT_BOX:
            c = cut(g, b)
            truth_save("gridsat", b, valid, **c)
        p = truth_locate("gridsat", basin, valid, download=False)
    with np.load(p) as z:
        tb = z["tb"]
        k = np.where(tb == FILL, np.nan, tb * SCALE + OFFSET).astype(np.float32)
        b = {"lat": z["lat"], "lon": z["lon"], "tb": k, "sat": z["sat"], "satnames": z["satnames"],
             "satlon": z["satlon"]}
    b["vza"] = view_zenith(b)
    return b


def view_zenith(b):
    """Geostationary view zenith angle (degrees) of each pixel of a box() dict from its satellite's
    sub-satellite longitude; NaN where no satellite. Large angles (> ~65) mean a slanted, smeared view."""
    lat = np.radians(b["lat"])[:, None]
    sl = np.where(b["sat"] >= 0, b["satlon"][np.clip(b["sat"], 0, None)], np.nan)
    g = np.arccos(np.clip(np.cos(lat) * np.cos(np.radians(b["lon"][None, :] - sl)), -1, 1))
    v = np.degrees(np.arctan2(np.sin(g), np.cos(g) - 6378.0 / (6378.0 + 35786.0)))
    return v.astype(np.float32)


def destination(lat, lon, bearing_deg, dist_km):
    """Great-circle destination (arrays broadcast) -> (lat, lon in -180..180)."""
    p1, l1 = np.radians(lat), np.radians(lon)
    th, d = np.radians(bearing_deg), np.asarray(dist_km) / EARTH_KM
    p2 = np.arcsin(np.sin(p1) * np.cos(d) + np.cos(p1) * np.sin(d) * np.cos(th))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(d) * np.cos(p1), np.cos(d) - np.sin(p1) * np.sin(p2))
    return np.degrees(p2), (np.degrees(l2) + 180.0) % 360.0 - 180.0


def heading(lat0, lon0, lat1, lon1):
    """Initial bearing from point 0 to point 1, degrees clockwise from north (0-360)."""
    p0, p1 = math.radians(lat0), math.radians(lat1)
    dl = math.radians(lon1 - lon0)
    y = math.sin(dl) * math.cos(p1)
    x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def grid_offsets(half_km=1200.0, res_km=10.0):
    """Pixel offsets of a square crop -> (x_km east of centre, y_km up), rows top to bottom."""
    n = int(round(2 * half_km / res_km)) + 1
    v = (np.arange(n) - (n - 1) / 2) * res_km
    return np.meshgrid(v, v[::-1])


def crop(b, lat, lon, half_km=1200.0, res_km=10.0, head=None):
    """Storm-centred crop of a box() dict -> float32 [n, n] K (NaN outside the box or missing). Azimuthal
    equidistant around (lat, lon): pixel (row, col) is res_km apart; north is up, or, with head (degrees
    clockwise from north), the direction of motion is up and the right of track is to the right. Bilinear."""
    from scipy.ndimage import map_coordinates
    x, y = grid_offsets(half_km, res_km)
    brg = np.degrees(np.arctan2(x, y)) + (head or 0.0)
    plat, plon = destination(lat, lon, brg, np.hypot(x, y))
    la, lo = b["lat"], b["lon"]
    dy = float(la[0] - la[1])                      # rows run north to south
    dx = float(lo[1] - lo[0])
    fy = (la[0] - plat) / dy
    fx = ((plon - lo[0]) % 360.0) / dx
    tb = b["tb"]
    ok = np.isfinite(tb)
    out = map_coordinates(np.where(ok, tb, 0.0), [fy, fx], order=1, mode="constant", cval=np.nan)
    w = map_coordinates(ok.astype(np.float32), [fy, fx], order=1, mode="constant", cval=0.0)
    out = np.where(w > 0.999, out, np.nan)         # any missing neighbour -> missing
    return out.astype(np.float32)


# ---- ABI air-mass bands (GOES-East and GOES-West, AWS noaa-goes16/17/18/19) ----
#
# Air-mass RGB inputs: band 8 (6.2 um upper-level water vapour), 10 (7.3 um lower-level WV), 12 (9.6 um ozone) and
# 13 (10.3 um clean IR window). ABI-L2-CMIPF files are chunked 226 x 226, so only the rows and columns over the
# SAT_BOX are read by byte range (~5-7 MB per band of 17-23 MB). Values are put on the same 0.07 deg SAT_BOX grid
# as gridsat (nearest ABI pixel), so crop() and view_zenith() work unchanged.

ABI_URL = "https://noaa-goes{n}.s3.amazonaws.com/"
ABI_BANDS = (8, 10, 12, 13)
ABI_MAX_VZA = 80.0                       # beyond this the pixel is left missing
GOES_EAST_SWITCH = dt.datetime(2025, 4, 7, 15)   # GOES-19 replaced GOES-16 as GOES-East
GOES_WEST_SWITCH = dt.datetime(2023, 1, 4, 18)   # GOES-18 replaced GOES-17 as GOES-West
ABI_START = {"natl": dt.datetime(2017, 12, 18), "npac": dt.datetime(2019, 2, 12)}   # operational GOES-16 / -17


def goes_for(basin, valid):
    """The GOES satellite numbers to try for a basin and time, preferred first: GOES-East for the Atlantic,
    GOES-West for the Pacific; the other one of the pair as a fallback around a handover. [] before ABI_START."""
    if valid < ABI_START[basin]:
        return []
    if basin == "natl":
        return [16, 19] if valid < GOES_EAST_SWITCH else [19, 16]
    return [17, 18] if valid < GOES_WEST_SWITCH else [18, 17]


def abi_key(n, band, valid):
    """S3 key of the first full-disk CMIP file of a band starting in the valid hour, or None."""
    prefix = "ABI-L2-CMIPF/%s/%02d/OR_ABI-L2-CMIPF-M" % (valid.strftime("%Y/%j"), valid.hour)
    r = fetch.get(ABI_URL.format(n=n) + "?list-type=2&max-keys=200&prefix=" + prefix)
    if r is None:
        return None
    keys = sorted(k for k in re.findall(r"<Key>([^<]+)</Key>", r.text) if "C%02d_G%d_" % (band, n) in k)
    return keys[0] if keys else None


def abi_xy(lat, lon, lon0, h, a, b):
    """GOES-R fixed-grid scan angles (x, y, radians) of lat/lon (degrees) for a satellite over lon0 (degrees)
    at perspective height h above an ellipsoid (a, b), and a mask of the points the satellite sees
    (GOES-R PUG vol. 3, 5.1.2.8.1)."""
    H = h + a
    phi, lam = np.radians(lat), np.radians(lon - lon0)
    phic = np.arctan((b * b) / (a * a) * np.tan(phi))
    e2 = 1 - (b * b) / (a * a)
    rc = b / np.sqrt(1 - e2 * np.cos(phic) ** 2)
    sx = H - rc * np.cos(phic) * np.cos(lam)
    sy = -rc * np.cos(phic) * np.sin(lam)
    sz = rc * np.sin(phic)
    seen = H * (H - sx) - sy * sy - (a * a) / (b * b) * sz * sz >= 0
    x = np.arcsin(-sy / np.sqrt(sx * sx + sy * sy + sz * sz))
    y = np.arctan(sz / sx)
    return x, y, seen


def _prefetch(f, ds, r0, r1, c0, c1):
    """Download the byte span holding every chunk of ds that meets rows r0:r1, columns c0:c1 in one request
    (h5py would otherwise ask for each ~50 kB chunk separately, which is latency-bound)."""
    ch = ds.chunks
    spans = []
    for i in range(ds.id.get_num_chunks()):
        ci = ds.id.get_chunk_info(i)
        r, c = ci.chunk_offset
        if r < r1 and r + ch[0] > r0 and c < c1 and c + ch[1] > c0:
            spans.append((ci.byte_offset, ci.byte_offset + ci.size))
    if spans:
        lo, hi = min(a for a, _ in spans), max(b for _, b in spans)
        f._fetch(lo // f.block, (hi - 1) // f.block)


def _abi_band(url, lat2, lon2):
    """One CMIP band on a lat/lon grid (2-D arrays) -> (K float32 with NaN, sub-satellite lon, bytes read)."""
    import h5py
    f = RangeFile(url, block=1 << 18)
    with h5py.File(f, "r") as h:
        p = h["goes_imager_projection"].attrs
        lon0 = float(p["longitude_of_projection_origin"][0])
        hgt, a, b = (float(p[k][0]) for k in ("perspective_point_height", "semi_major_axis", "semi_minor_axis"))
        xs, ys = h["x"].attrs, h["y"].attrs
        sx, ox = float(xs["scale_factor"][0]), float(xs["add_offset"][0])
        sy, oy = float(ys["scale_factor"][0]), float(ys["add_offset"][0])
        nx, ny = h["x"].shape[0], h["y"].shape[0]
        x, y, seen = abi_xy(lat2, lon2, lon0, hgt, a, b)
        col = np.rint((x - ox) / sx).astype(np.int64)
        row = np.rint((y - oy) / sy).astype(np.int64)
        ok = seen & (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
        out = np.full(lat2.shape, np.nan, np.float32)
        if ok.any():
            r0, r1, c0, c1 = row[ok].min(), row[ok].max() + 1, col[ok].min(), col[ok].max() + 1
            c = h["CMI"]
            _prefetch(f, c, r0, r1, c0, c1)
            raw = c[r0:r1, c0:c1]
            fill = int(c.attrs["_FillValue"][0])
            val = raw[row[ok] - r0, col[ok] - c0]
            k = val * float(c.attrs["scale_factor"][0]) + float(c.attrs["add_offset"][0])
            out[ok] = np.where(val == fill, np.nan, k)
    return out, lon0, f.fetched


def abi_airmass(basin, valid):
    """The four air-mass bands over the basin's SAT_BOX (0.07 deg, same grid as gridsat) -> {"lat", "lon",
    "b08", "b10", "b12", "b13" (K float32, NaN missing or view zenith > ABI_MAX_VZA), "sat", "satnames",
    "satlon", "bytes"} or None when no satellite has all four bands for the hour."""
    s, n, w, e = SAT_BOX[basin]
    lat = np.round(np.arange(n, s - 1e-6, -0.07), 4).astype(np.float32)
    lon = np.round(np.arange(w, e + 1e-6, 0.07), 4).astype(np.float32)
    lat2, lon2 = np.meshgrid(lat.astype(np.float64), lon.astype(np.float64), indexing="ij")
    for sat in goes_for(basin, valid):
        keys = [abi_key(sat, b, valid) for b in ABI_BANDS]
        if any(k is None for k in keys):
            continue
        out, nbytes = {"lat": lat, "lon": lon}, 0
        for b, k in zip(ABI_BANDS, keys):
            out["b%02d" % b], lon0, got = _abi_band(ABI_URL.format(n=sat) + k, lat2, lon2)
            nbytes += got
        out.update(satnames=np.array(["GOES-%d" % sat]), satlon=np.array([lon0], np.float32))
        out["sat"] = np.where(np.isfinite(out["b13"]), 0, -1).astype(np.int8)
        v = view_zenith(out)
        for b in ABI_BANDS:
            out["b%02d" % b][~(v <= ABI_MAX_VZA)] = np.nan
        out["sat"][~(v <= ABI_MAX_VZA)] = -1
        out["bytes"] = nbytes
        return out
    return None


def airmass_box(basin, valid, download=True):
    """Air-mass bands over the basin's SAT_BOX -> abi_airmass() keys (K float32, NaN missing) plus "vza", or None.
    Cache, legacy, release (truth kind `airmass`, int16 K = v * 0.01 + 200 like gridsat); with download=True a
    missing time is built from ABI and marked unpublished. 00/06/12/18 UTC only."""
    _check_hour(valid)
    p = truth_locate("airmass", basin, valid)
    if p is None:
        if not download:
            return None
        m = abi_airmass(basin, valid)
        if m is None:
            return None
        enc = {k: np.where(np.isfinite(m[k]), np.round((m[k] - OFFSET) / SCALE), FILL).astype(np.int16)
               for k in ("b08", "b10", "b12", "b13")}
        truth_save("airmass", basin, valid, lat=m["lat"], lon=m["lon"], sat=m["sat"], satnames=m["satnames"],
                   satlon=m["satlon"], **enc)
        p = truth_locate("airmass", basin, valid, download=False)
    with np.load(p) as z:
        b = {k: z[k] for k in ("lat", "lon", "sat", "satnames", "satlon")}
        for k in ("b08", "b10", "b12", "b13"):
            v = z[k]
            b[k] = np.where(v == FILL, np.nan, v * SCALE + OFFSET).astype(np.float32)
    b["vza"] = view_zenith(b)
    return b


def airmass_rgb(b08, b10, b12, b13):
    """EUMETSAT air-mass RGB (0-1 per channel, gamma 1) from the four bands in K: red = WV6.2 - WV7.3 over
    -25..0 K, green = O3 9.6 - IR 10.3 over -40..+5 K, blue = WV6.2 inverted over 243..208 K."""
    r = np.clip((b08 - b10 + 25.0) / 25.0, 0, 1)
    g = np.clip((b12 - b13 + 40.0) / 45.0, 0, 1)
    bl = np.clip((243.0 - b08) / 35.0, 0, 1)
    return np.stack([r, g, bl], -1)
