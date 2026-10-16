"""Shared field cache under DATA/fields, and the analysis (truth for WHERE).

fields/{basin}/{YYYYMMDDHH}/{model}_f{step:03d}.npz
  deterministic: u, v (float16 m/s), msl (float32 hPa)
  ensemble: mean_u, mean_v, spd_mean, spd_std (kt), p34, p48, p64 (fraction of members at or
            above the threshold in kt), msl_mean, msl_std (hPa), n (members)
"""
import datetime as dt
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import KT, fetch
from .basins import BASINS
from .cases import STEPS, available, tag
from .paths import data

DET = ("gfs", "ifs", "aifs")
ENS = ("gefs", "ens", "aifs-ens")
MIN_MEMBERS = 20


def _path(basin, cycle, name, step):
    return data("fields", basin, tag(cycle), "%s_f%03d.npz" % (name, step))


def _save(path, **arrays):
    """Write an npz atomically: temp file in the same directory, then rename."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, **arrays)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _det_dict(z):
    u, v = z["u"].astype(np.float32), z["v"].astype(np.float32)
    return {"u": u, "v": v, "speed": np.hypot(u, v) * KT, "msl": z["msl"].astype(np.float32)}


def load_det(basin, cycle, model, step):
    """Stored deterministic fields -> {'u','v','speed' (kt),'msl'} or None."""
    p = _path(basin, cycle, model, step)
    if not p.exists():
        return None
    with np.load(p) as z:
        return _det_dict(z)


def load_ens(basin, cycle, ens, step):
    """Stored ensemble statistics -> dict of arrays (n is an int) or None."""
    p = _path(basin, cycle, ens, step)
    if not p.exists():
        return None
    with np.load(p) as z:
        out = {k: z[k].astype(np.float32) for k in z.files if k != "n"}
        out["n"] = int(z["n"])
    return out


def _save_det(cycle, model, step, res, basins):
    for b in basins:
        r = res[b]
        _save(_path(b, cycle, model, step), u=r["u"].astype(np.float16), v=r["v"].astype(np.float16),
              msl=r["msl"].astype(np.float32))


def ens_stats(m):
    """Member arrays {'u','v','msl'} [n,y,x] -> the stored statistics."""
    u, v = m["u"].astype(np.float32), m["v"].astype(np.float32)
    spd = np.hypot(u, v) * KT
    out = {"mean_u": u.mean(0), "mean_v": v.mean(0), "spd_mean": spd.mean(0), "spd_std": spd.std(0),
           "p34": (spd >= 34).mean(0), "p48": (spd >= 48).mean(0), "p64": (spd >= 64).mean(0)}
    if "msl" in m:
        out["msl_mean"], out["msl_std"] = m["msl"].mean(0), m["msl"].std(0)
    out = {k: a.astype(np.float32) for k, a in out.items()}
    out["n"] = np.array(len(u))
    return out


def fill(cycle, steps=STEPS, models=DET, ens=ENS, workers=6, basins=tuple(BASINS)):
    """Fetch what is missing for the basins (both by default) from one cycle and store it.
    Skips an ensemble step when fewer than 20 members came back; each file comes from one run.
    Returns {'cycle', 'fetched', 'existing', 'missing', 'skipped_ens'} (lists of 'model_fSSS')."""
    rep = {"cycle": tag(cycle), "fetched": [], "existing": [], "missing": [], "skipped_ens": []}
    jobs = []
    for name in list(models) + list(ens):
        for step in steps:
            label = "%s_f%03d" % (name, step)
            if not available(name, cycle):
                rep["missing"].append(label)
            elif all(_path(b, cycle, name, step).exists() for b in basins):
                rep["existing"].append(label)
            else:
                jobs.append((name, step, label))

    def run(job):
        name, step, label = job
        inner = max(2, workers // 2)
        if name in models:
            res = fetch.det(name, cycle, step)
            if res is None:
                return label, "missing"
            _save_det(cycle, name, step, res, basins)
            return label, "fetched"
        res = fetch.members(name, cycle, step, msl=True, workers=inner)
        if res is None:
            return label, "missing"
        if len(next(iter(res.values()))["u"]) < MIN_MEMBERS:
            return label, "skipped_ens"
        for b in basins:
            _save(_path(b, cycle, name, step), **ens_stats(res[b]))
        return label, "fetched"

    with ThreadPoolExecutor(workers) as ex:
        for label, what in ex.map(run, jobs):
            rep[what].append(label)
    return rep


# ---- analysis: GFS and IFS step 0 at the valid time, plus the open-water mask ----

def _analysis_path(basin, valid):
    return data("truth", "analysis", basin, tag(valid) + ".npz")


def _load_analysis(z):
    g = {k: z["gfs_" + k] for k in ("u", "v", "msl")}
    i = {k: z["ifs_" + k] for k in ("u", "v", "msl")}
    for d in (g, i):
        d["u"], d["v"], d["msl"] = (d[k].astype(np.float32) for k in ("u", "v", "msl"))
        d["speed"] = np.hypot(d["u"], d["v"]) * KT
    return {"gfs": g, "ifs": i, "mean_speed": z["mean_speed"], "msl": z["msl"], "mask": z["mask"]}


def analysis_arrays(g, i, land, ice):
    """The arrays stored for one basin and valid time, from the GFS and IFS step-0 dicts (u, v m/s, msl hPa),
    GFS LAND and ICEC. mask = open, ice-free water; a NaN ice cell compares False, so it is masked out.
    Shared by analysis() and tools/import_wx_cache.py so the two always write the same thing."""
    gs = np.hypot(g["u"], g["v"]) * KT
    is_ = np.hypot(i["u"], i["v"]) * KT
    arrays = {"mean_speed": ((gs + is_) / 2).astype(np.float32),
              "msl": ((g["msl"] + i["msl"]) / 2).astype(np.float32),
              "mask": (land < 0.01) & (ice <= 0.15)}
    for name, r in (("gfs", g), ("ifs", i)):
        arrays.update({name + "_u": r["u"].astype(np.float16), name + "_v": r["v"].astype(np.float16),
                       name + "_msl": r["msl"].astype(np.float32)})
    return arrays


def analysis(basin, valid):
    """Analysis at the valid time -> {'gfs','ifs' (det dicts), 'mean_speed' (kt), 'msl' (hPa, mean of the
    two), 'mask' (open, ice-free water)} or None if either analysis or the mask is not posted.
    Cached under truth/analysis/{basin}/{YYYYMMDDHH}.npz; both basins are cached at once."""
    p = _analysis_path(basin, valid)
    if p.exists():
        with np.load(p) as z:
            return _load_analysis(z)
    if not (available("gfs", valid) and available("ifs", valid)):
        return None
    g, i, m = fetch.det("gfs", valid, 0), fetch.det("ifs", valid, 0), fetch.gfs_mask(valid)
    if g is None or i is None or m is None:
        return None
    for b in BASINS:
        _save(_analysis_path(b, valid), **analysis_arrays(g[b], i[b], m[b]["land"], m[b]["ice"]))
    with np.load(p) as z:
        return _load_analysis(z)
