"""How rare is a low: its central pressure against the ERA5 cyclone record (a proxy, not the archive).

The reference population is every in-domain pipeline A cyclone 1979-2025 in jkrek17/hf-low
(`docs/data/era5-peaks.js`, 75,087 cyclones, one row each: the position of its peak gust and the lowest
pressure it reached). A percentile here answers "what share of past lows near here, at this time of year,
never got as deep as this one", so a low part way through its life is compared with other lows' lifetime
minimum: the number is conservative while a low is still deepening.
"""
import json
import re

import numpy as np

from . import fetch, paths
from .score import km

PEAKS_URL = "https://raw.githubusercontent.com/jkrek17/hf-low/main/docs/data/era5-peaks.js"
RADIUS_KM = 1000.0     # reference lows within this distance of the low
MIN_N = 150            # widen the month window until at least this many reference lows
MAX_MONTHS = 2         # at most +-2 months around the low's own month


def _parse(text):
    """The era5-peaks.js payload -> dict of numpy arrays (lat, lon 0-360, month, hpa, gust_kt, basin, season)."""
    body = text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1]
    d = json.loads(body)
    f = d["meta"]["fields"]
    ev = np.asarray(d["ev"], dtype=np.int64)
    col = {name.split("(")[0].split("*")[0]: ev[:, i] for i, name in enumerate(f)}
    start = col["start"]
    return {
        "basin": col["basin"].astype(np.int8),
        "season": col["season"].astype(np.int16),
        "month": ((start // 10000) % 100).astype(np.int8),
        "lat": col["peak_lat"] / 4.0,
        "lon": (col["peak_lon"] / 4.0) % 360.0,
        "gust_kt": col["gust800_kt"] / 10.0,
        "hpa": col["minp_hPa"] / 10.0,
    }


_PEAKS = None


def era5_peaks(refresh=False):
    """The ERA5 pipeline A cyclone peaks (dict of arrays, see `_parse`), read from hf-low over HTTPS and cached
    under CACHE/truth/hf_lows/era5-peaks.js. None if it cannot be read."""
    global _PEAKS
    if _PEAKS is not None and not refresh:
        return _PEAKS
    p = paths.cache("truth", "hf_lows", "era5-peaks.js")
    if refresh or not p.exists():
        r = fetch.get(PEAKS_URL)
        if r is not None:
            p.write_bytes(r.content)
        elif not p.exists():
            return None
    _PEAKS = _parse(p.read_text())
    return _PEAKS


def _month_mask(months, month, w):
    d = np.abs(((months.astype(int) - month + 6) % 12) - 6)
    return d <= w


def rarity(lat, lon, month, hpa, ref=None, radius_km=RADIUS_KM, min_n=MIN_N, max_months=MAX_MONTHS):
    """One low -> {"pct": share (0-100) of reference lows within radius_km whose lowest pressure stayed above
    hpa, "n": reference lows used, "months": half-width of the month window used, "deepest": lowest
    reference pressure}. The month window starts at the low's own month and widens by one month each side
    until n >= min_n (at most max_months); pct is NaN if even then n < min_n / 3."""
    ref = era5_peaks() if ref is None else ref
    near = km(ref["lat"], ref["lon"], lat, lon % 360.0) <= radius_km
    for w in range(max_months + 1):
        k = near & _month_mask(ref["month"], month, w)
        if k.sum() >= min_n:
            break
    n = int(k.sum())
    if n < max(1, min_n // 3):
        return {"pct": np.nan, "n": n, "months": w, "deepest": np.nan}
    p = ref["hpa"][k]
    return {"pct": float(100.0 * (p > hpa).mean()), "n": n, "months": w, "deepest": float(p.min())}


def rarity_table(lows, month, ref=None, **kw):
    """A lows table (columns lat, lon, hpa) -> the same table with pct, n, months, deepest added."""
    out = lows.copy()
    r = [rarity(a, o, month, h, ref=ref, **kw) for a, o, h in zip(lows.lat, lows.lon, lows.hpa)]
    for key in ("pct", "n", "months", "deepest"):
        out[key] = [x[key] for x in r]
    return out
