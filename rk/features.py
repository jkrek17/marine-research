"""Storm-core features from the shared store: the marine wind page's 28 core-model features, rebuilt from
ensemble STATISTICS (the store keeps no members).

core(basin, cycle, step) returns the feature grids of storm.core_features (awips-tools
marine_wind/pipeline/storm.py) plus the ocean mask and the candidate mask, or None when a required
input is missing. Nothing is filled in silently.

Definitions copied from awips-tools (numbers and file lines as of the pinned nwp commit b38f9d4):
  storm.py  NB = (9, 13) neighbourhood box; r10_nbmax box (21, 31); _sm sigma 1.5; 21600 s (6 h) advection
            scale; gradT850 floor 1e-7, x1e5; candidate rule in core_grid (r10 >= 28 or mod_max >= 34).
  build.py  SUPPORT_KT = 5.0, CAP_KT = 5.0, k_for(step) = 0.15 at +24 h and earlier else 0.25;
            step_values (wind = support_base + min(k x sigma, CAP)); core_layers (low-level means,
            winds x KT, ocean = GFS land < 0.5 and ice < 0.5).
  core_model.json  the feature order (FEATURES below).

Approximations against the live page (the only places the numbers can differ):
  1. Ensemble members are not stored. The GEFS + ENS "members" are the pooled statistics of the two
     ensembles (n-weighted): p34/p48/p64 are the n-weighted mean of the two member fractions (exact),
     mmean the pooled mean (exact), sigma the pooled SD (exact, ddof 0 like numpy .std), mod_* unaffected.
  2. m90 (live: 90th percentile of the pooled members) = pooled mean + 1.2816 x pooled SD, i.e. the
     percentile of a normal distribution. Skewed member distributions (storm cores, a few members far
     above the rest) make the live percentile differ; the retrained model sees this definition.
  3. support_base (live: Gaussian kernel averaged over members) uses the closed form for a normal member
     distribution per ensemble, n-weighted:  E[exp(-0.5 ((X - s) / h)^2)] = h / sqrt(h^2 + sd^2) x
     exp(-0.5 (m - s)^2 / (h^2 + sd^2)).  Exact for normal members, smoother than the member average.
  4. pa48 is the AIFS ensemble's stored p48 (member fraction), the same as live; NaN when aifs-ens is not
     in the store (the live page also passes NaN then).
  5. spd_mean/spd_std in the store are float32 of the member speeds; det u, v are float16 m/s, so speeds
     differ from live by about 0.01 kt. Low-level winds are float16 m/s in the cache.
  6. The grid is the basin box, filters use mode "nearest" (live WRAP False). The page zeroes the core
     below 25 degrees latitude; the boxes start at 30 N, so that never applies.
  6b. low_models (default the live three) restricts the low-level 3-model mean to a subset (GFS only while
     only GFS low fields exist); the result's "low_models" records it. A GFS-only mean is not the live feature.
  7. models/ens subsets (degraded runs): speeds of an absent model are NaN in its s10_ column and left out
     of mod_max/mod_min/mod_sd/support weights; absent low-level means are over the models present. Used only
     when asked for; the default is the live 3 models and GEFS + ENS.
  8. low=False (no lower-level fields): the eight low-level features (s925, s925_minus_r10, sst_t850,
     sst_t925, dT, tadv925, tadv850, gradT850) are NaN, and the ocean mask comes from rk.truth.analysis at
     the valid time (land < 0.01 and ice <= 0.15) instead of the GFS land/ice of the forecast. Labelled
     "no_low" in the result.
"""
import datetime as dt

import numpy as np
from scipy import ndimage

from . import KT, store
from .basins import grid

# core_model.json "features", in the model's column order.
FEATURES = ("r10", "boost", "s10_gfs", "s10_ifs", "s10_aifs", "mod_max", "mod_min", "mod_sd", "p34", "p48",
            "p64", "pa48", "m90", "mmean", "p48_nb", "p34_nb", "modmax_nb", "m90_nb", "r10_nbmax", "lat",
            "s925", "s925_minus_r10", "sst_t850", "sst_t925", "dT", "tadv925", "tadv850", "gradT850")
LOW_FEATURES = ("s925", "s925_minus_r10", "sst_t850", "sst_t925", "dT", "tadv925", "tadv850", "gradT850")

R_EARTH = 6371000.0          # storm.py
NB = (9, 13)                 # storm.py
NB_WIDE = (21, 31)           # storm.py core_features r10_nbmax
SUPPORT_KT = 5.0             # build.py
CAP_KT = 5.0                 # build.py
CAND_R10, CAND_MOD = 28.0, 34.0   # storm.py core_grid
Z90 = 1.2815515655446004     # standard normal 90th percentile
MODELS = ("gfs", "ifs", "aifs")
ENSEMBLES = ("gefs", "ens")


def k_for(step):
    """build.py k_for: the boost multiplier on the member SD."""
    return 0.15 if step <= 24 else 0.25


def pool(stats):
    """Pool the stored statistics of several ensembles (list of store.load_ens dicts) as if their members
    were one set. Returns n, spd_mean, spd_sd (population SD, ddof 0, exact), p34, p48, p64 (n-weighted
    fractions, exact)."""
    n = np.array([s["n"] for s in stats], np.float64)
    w = n / n.sum()
    m = [s["spd_mean"].astype(np.float64) for s in stats]
    sd = [s["spd_std"].astype(np.float64) for s in stats]
    mean = sum(wi * mi for wi, mi in zip(w, m))
    second = sum(wi * (si ** 2 + mi ** 2) for wi, si, mi in zip(w, sd, m))
    out = {"n": int(n.sum()), "mean": mean, "sd": np.sqrt(np.maximum(second - mean ** 2, 0.0))}
    for k in ("p34", "p48", "p64"):
        out[k] = sum(wi * s[k].astype(np.float64) for wi, s in zip(w, stats))
    return out


def support_closed_form(speeds, stats, h=SUPPORT_KT):
    """build.support_base with the member average of the Gaussian kernel replaced by its expectation under
    a normal member distribution per ensemble (n-weighted). speeds [k, y, x] kt; stats list of
    store.load_ens dicts. Returns the weighted mean speed [y, x] (the page's `mean`)."""
    n = np.array([s["n"] for s in stats], np.float64)
    w = n / n.sum()
    wt = []
    for sp in speeds:
        acc = 0.0
        for wi, s in zip(w, stats):
            var = h * h + s["spd_std"].astype(np.float64) ** 2
            acc = acc + wi * h / np.sqrt(var) * np.exp(-0.5 * (s["spd_mean"].astype(np.float64) - sp) ** 2 / var)
        wt.append(acc)
    wt = np.array(wt) + 1e-6
    return (wt * speeds).sum(0) / wt.sum(0)


def _sm(a, s=1.5):
    a = np.asarray(a, np.float32)
    return ndimage.gaussian_filter(np.nan_to_num(a, nan=float(np.nanmean(a))), s, mode="nearest")


def assemble(lats, speeds, pooled, stats, step, pa48=None, low=None, names=MODELS):
    """The feature dict from already-loaded pieces (core() and the tests call this).

    lats [y]; speeds [k, y, x] kt for the models in `names`; pooled = pool(stats); stats the list of ensemble
    dicts; pa48 [y, x] or None; low = dict of 3-model means (winds kt, temperatures K) or None."""
    shape = speeds.shape[1:]
    LAT = np.repeat(np.asarray(lats, np.float64)[:, None], shape[1], 1)
    dx = R_EARTH * np.cos(np.deg2rad(LAT)) * np.deg2rad(0.25)
    dy = R_EARTH * np.deg2rad(0.25)
    ddx = lambda a: np.gradient(a, axis=1) / dx
    ddy = lambda a: -np.gradient(a, axis=0) / dy

    mean = support_closed_form(speeds, stats)
    sigma = pooled["sd"]
    boost = np.minimum(k_for(step) * sigma, CAP_KT)
    wind = mean + boost
    nan = np.full(shape, np.nan)
    c = {"r10": wind, "boost": boost}
    for m in MODELS:
        c["s10_" + m] = speeds[names.index(m)] if m in names else nan
    c.update({"mod_max": speeds.max(0), "mod_min": speeds.min(0), "mod_sd": speeds.std(0),
              "p34": pooled["p34"], "p48": pooled["p48"], "p64": pooled["p64"],
              "pa48": nan if pa48 is None else pa48,
              "m90": pooled["mean"] + Z90 * sigma, "mmean": pooled["mean"], "lat": LAT})
    for k in ("p48", "p34", "m90"):
        c[k + "_nb"] = ndimage.maximum_filter(c[k], size=NB, mode="nearest")
    c["modmax_nb"] = ndimage.maximum_filter(c["mod_max"], size=NB, mode="nearest")
    c["r10_nbmax"] = ndimage.maximum_filter(wind, size=NB_WIDE, mode="nearest")
    if low is None:
        for k in LOW_FEATURES:
            c[k] = nan
    else:
        c["s925"] = np.hypot(low["u925"], low["v925"])
        c["s925_minus_r10"] = c["s925"] - wind
        c["dT"] = low["t2"] - low["skt"]
        c["sst_t850"] = low["skt"] - low["t850"]
        c["sst_t925"] = low["skt"] - low["t925"]
        t9, u9, v9 = _sm(low["t925"]), _sm(low["u925"]) / KT, _sm(low["v925"]) / KT
        c["tadv925"] = -(u9 * ddx(t9) + v9 * ddy(t9)) * 21600
        t8, u8, v8 = _sm(low["t850"]), _sm(low["u850"]) / KT, _sm(low["v850"]) / KT
        tx, ty = ddx(t8), ddy(t8)
        c["gradT850"] = np.maximum(np.hypot(tx, ty), 1e-7) * 1e5
        c["tadv850"] = -(u8 * tx + v8 * ty) * 21600
    return {k: np.asarray(c[k], np.float32) for k in FEATURES}


def core(basin, cycle, step, low_root=None, models=MODELS, ens=ENSEMBLES, low=True, low_models=MODELS):
    """Storm-core features for one basin, cycle and lead from the store -> dict or None.

    Keys: the 28 FEATURES (float32 [y, x] on the basin grid), "ocean" (bool), "cand" (ocean & (r10 >= 28 |
    mod_max >= 34), the cells the live model scores), "basin_pac" (0 natl, 1 npac), "no_low" (True when
    low=False). Returns None if any required input is missing: a deterministic model in `models`, an
    ensemble in `ens` (aifs-ens is optional: pa48 is NaN without it), or, with low=True, a model's lower-level
    file (rk.store.load_low, from low_root or the shared store) or the GFS land/ice for the ocean mask.
    `low_models` (default the live three) picks which models' lower-level fields form the 3-model mean of the
    eight low-level features, e.g. ("gfs",) while only GFS low fields are in the store; it must include "gfs"
    (land/ice) and be a subset of `models`. The result's "low_models" says which were used (empty tuple when
    low=False), so a table never passes a GFS-only mean off as the live one.
    See the module docstring for every approximation."""
    models, ens = tuple(models), tuple(ens)
    low_models = tuple(low_models)
    if low and (not low_models or not set(low_models) <= set(models) or "gfs" not in low_models):
        raise ValueError("low_models must be a non-empty subset of models that includes gfs")
    if not models or not ens:
        raise ValueError("need at least one model and one ensemble")
    dets = [store.load_det(basin, cycle, m, step) for m in models]
    stats = [store.load_ens(basin, cycle, e, step) for e in ens]
    if any(d is None for d in dets) or any(s is None for s in stats):
        return None
    if any(s["n"] < store.MIN_MEMBERS for s in stats):
        return None
    speeds = np.array([d["speed"] for d in dets], np.float32)
    aens = store.load_ens(basin, cycle, "aifs-ens", step)
    pa48 = None if aens is None else aens["p48"]
    lows = None
    if low:
        lows = [store.load_low(basin, cycle, m, step, root=low_root) for m in low_models]
        if any(x is None for x in lows):
            return None
        gfs = lows[low_models.index("gfs")]
        if "land" not in gfs:
            return None
        lw = {k: np.mean([x[k] for x in lows], 0) for k in ("t2", "skt", "t925", "t850")}
        for k in ("u925", "v925", "u850", "v850"):
            lw[k] = np.mean([x[k] for x in lows], 0) * KT
        ocean = (~gfs["land"]) & ~(gfs["ice"] >= 0.5)
    else:
        from . import truth
        valid = cycle + dt.timedelta(hours=step)
        an = truth.analysis(basin, valid)
        if an is None:
            return None
        lw, ocean = None, an["mask"].astype(bool)
    lats, _ = grid(basin)
    f = assemble(lats, speeds, pool(stats), stats, step, pa48=pa48, low=lw, names=models)
    if f["r10"].shape != ocean.shape:
        return None
    f["ocean"] = ocean
    f["cand"] = ocean & ((f["r10"] >= CAND_R10) | (f["mod_max"] >= CAND_MOD))
    f["basin_pac"] = int(basin == "npac")
    f["no_low"] = not low
    f["low_models"] = low_models if low else ()
    return f
