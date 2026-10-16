"""Model-field store (GitHub Releases + local cache) and the analysis (truth for WHERE).

fields/{basin}/{YYYYMMDDHH}/{name}.npz     name = {model}_f{step:03d}, or any name a study adds with put()
  deterministic: u, v (float16 m/s), msl (float32 hPa)
  low (storm-core inputs): {model}_low_f{step:03d}.npz, t2 skt t925 t850 float32 K; u925 v925 u850 v850
            float16 m/s; gfs also land (uint8, 0/1: GFS LAND >= 0.5) and ice (uint8, ICEC fraction x100)
  ensemble: mean_u, mean_v, spd_mean, spd_std (kt), p34, p48, p64 (fraction of members at or
            above the threshold in kt), msl_mean, msl_std (hPa), n (members)
Remote: release fields-{basin}-{YYYYMM} on jkrek17/marine-research-data, asset {basin}_{YYYYMMDDHH}.zip
(ZIP_STORED zip of the cycle's npz files). Local: rk.paths.CACHE. Legacy: DATA/fields (read only).
Truth (analysis, obs, airsea, ascat, smap) follows the same pattern, one plain npz asset per valid time or
day in release truth-{kind}[-{basin}]-{YYYYMM}; see the "truth files" section.
See rk/CONTRACT.md.
"""
import datetime as dt
import io
import os
import re
import tempfile
import threading
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import KT, fetch, paths
from .basins import BASINS
from .cases import STEPS, available, tag

DET = ("gfs", "ifs", "aifs")
ENS = ("gefs", "ens", "aifs-ens")
MIN_MEMBERS = 20
FULL_MEMBERS = {"gefs": 31, "ens": 51, "aifs-ens": 51}   # control + perturbed; fill(complete=True) needs all of them

RELEASES = os.environ.get("RK_RELEASES", "https://github.com/jkrek17/marine-research-data/releases/download")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


# ---- naming: release, asset, URL ----

def _tag(cycle):
    return cycle if isinstance(cycle, str) else tag(cycle)


def release_tag(basin, cycle):
    """Release tag holding a basin-cycle: fields-{basin}-{YYYYMM}."""
    return "fields-%s-%s" % (basin, _tag(cycle)[:6])


def asset_name(basin, cycle):
    return "%s_%s.zip" % (basin, _tag(cycle))


def release_url(basin, cycle):
    return "%s/%s/%s" % (RELEASES.rstrip("/"), release_tag(basin, cycle), asset_name(basin, cycle))


# ---- HTTP: one pooled session with retries ----

_session = None
_session_lock = threading.Lock()


def _get_session():
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            retry = Retry(total=6, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                          allowed_methods=("GET",), respect_retry_after_header=True)
            for scheme in ("https://", "http://"):
                s.mount(scheme, HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=retry))
            _session = s
        return _session


def _http_get(url):
    """Body of url as bytes; None on 403/404 (not posted); other failures raise."""
    r = _get_session().get(url, timeout=(10, 180))
    if r.status_code in (403, 404):
        return None
    r.raise_for_status()
    return r.content


# ---- local files: cache, legacy, dirty marks ----

def _cache_dir(basin, cycle):
    return paths.CACHE / "fields" / basin / _tag(cycle)


def _cache_path(basin, cycle, name):
    return _cache_dir(basin, cycle) / (name + ".npz")


def _legacy_path(basin, cycle, name):
    return paths.DATA / "fields" / basin / _tag(cycle) / (name + ".npz")


def _check_name(name):
    if name.endswith(".npz"):
        name = name[:-4]
    if not _NAME_RE.match(name):
        raise ValueError("bad field name %r (letters, digits, _ - . only)" % name)
    return name


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


def _write_bytes(path, blob):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _mark_dirty(basin, cycle, name):
    d = _cache_dir(basin, cycle) / ".dirty"
    d.mkdir(parents=True, exist_ok=True)
    (d / (name + ".npz")).touch()


def put(basin, cycle, name, **arrays):
    """Add or replace field file `name`.npz (e.g. 'gfs_low_f024') for a basin-cycle in the local cache,
    atomically, and mark it unpublished (see dirty). Returns the path."""
    name = _check_name(name)
    if basin not in BASINS:
        raise ValueError("unknown basin %r" % basin)
    p = _cache_path(basin, cycle, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    _mark_dirty(basin, cycle, name)   # marked first: a stale mark is harmless, a missing one loses a file
    _save(p, **arrays)
    return p


def dirty(basin=None):
    """Cache cycles holding files not yet published -> {(basin, 'YYYYMMDDHH'): sorted member file names}.
    Marks whose file is gone are ignored."""
    out = {}
    root = paths.CACHE / "fields"
    for b in ([basin] if basin else sorted(BASINS)):
        for d in sorted((root / b).glob("*/.dirty")):
            names = sorted(m.name for m in d.iterdir() if (d.parent / m.name).is_file())
            if names:
                out[(b, d.parent.name)] = names
    return out


def mark_clean(basin, cycle, names):
    """Clear the unpublished marks of member file names (with or without .npz) of a cache cycle."""
    d = _cache_dir(basin, cycle) / ".dirty"
    for n in names:
        n = n if n.endswith(".npz") else n + ".npz"
        try:
            (d / n).unlink()
        except FileNotFoundError:
            pass
    try:
        d.rmdir()
    except OSError:
        pass


# ---- release zips ----

_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def build_zip(out, local, remote=None):
    """Write the release zip for one cycle to `out`: ZIP_STORED, members `{name}.npz` sorted, fixed
    timestamps (same content, same bytes). `local` is {member file name: Path}; `remote` the bytes of the
    published zip, or None. Remote-only members are kept; local ones add or replace.
    Returns {'size', 'kept', 'new', 'replaced', 'same'} (member counts; 'same' = local file identical to the
    published member)."""
    members = {}
    old = {}
    if remote is not None:
        with zipfile.ZipFile(io.BytesIO(remote)) as z:
            for info in z.infolist():
                if _NAME_RE.match(info.filename) and info.filename.endswith(".npz"):
                    members[info.filename] = z.read(info)
                    old[info.filename] = True
    st = {"kept": 0, "new": 0, "replaced": 0, "same": 0}
    for n, p in local.items():
        blob = Path(p).read_bytes()
        if n in old:
            st["same" if zlib.crc32(blob) == zlib.crc32(members[n]) and blob == members[n] else "replaced"] += 1
        else:
            st["new"] += 1
        members[n] = blob
    st["kept"] = len(old) - st["same"] - st["replaced"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for n in sorted(members):
            zi = zipfile.ZipInfo(n, _ZIP_TIME)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, members[n])
    st["size"] = Path(out).stat().st_size
    return st


_pulled = set()      # (basin, cycle tag) already asked for in this process (zip unpacked, or 404)
_pull_locks = {}
_pull_guard = threading.Lock()


def _pull(basin, cycle):
    """Download the cycle's release zip once per process and unpack it into the cache (members already in
    the cache stay). A 404 is remembered too. Returns True when a zip was unpacked."""
    key = (basin, _tag(cycle))
    with _pull_guard:
        lock = _pull_locks.setdefault(key, threading.Lock())
    with lock:
        if key in _pulled:
            return False
        if os.environ.get("RK_OFFLINE") == "1":
            return False
        blob = _http_get(release_url(basin, cycle))
        if blob is not None:
            d = _cache_dir(basin, cycle)
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for info in z.infolist():
                    n = info.filename
                    if not (_NAME_RE.match(n) and n.endswith(".npz")):
                        continue
                    if not (d / n).exists():
                        _write_bytes(d / n, z.read(info))
        _pulled.add(key)
        return blob is not None


def _locate(basin, cycle, name):
    """Path of a field file: cache, then legacy DATA/fields, then the release. None if nowhere."""
    for p in (_cache_path(basin, cycle, name), _legacy_path(basin, cycle, name)):
        if p.exists():
            return p
    _pull(basin, cycle)
    p = _cache_path(basin, cycle, name)
    return p if p.exists() else None


def _det_dict(z):
    u, v = z["u"].astype(np.float32), z["v"].astype(np.float32)
    return {"u": u, "v": v, "speed": np.hypot(u, v) * KT, "msl": z["msl"].astype(np.float32)}


def load_det(basin, cycle, model, step):
    """Stored deterministic fields -> {'u','v','speed' (kt),'msl'} or None."""
    p = _locate(basin, cycle, "%s_f%03d" % (model, step))
    if p is None:
        return None
    with np.load(p) as z:
        return _det_dict(z)


def load_ens(basin, cycle, ens, step):
    """Stored ensemble statistics -> dict of arrays (n is an int) or None."""
    p = _locate(basin, cycle, "%s_f%03d" % (ens, step))
    if p is None:
        return None
    with np.load(p) as z:
        out = {k: z[k].astype(np.float32) for k in z.files if k != "n"}
        out["n"] = int(z["n"])
    return out


LOW_T = ("t2", "skt", "t925", "t850")
LOW_W = ("u925", "v925", "u850", "v850")


def save_low(basin, cycle, model, step, r, root=None):
    """Store one basin's fetch.low() dict (atomic). Temperatures float32 K, winds float16 m/s, land uint8
    (1 where LAND >= 0.5), ice uint8 (ICEC x100, rounded; NaN -> 0). root overrides rk.paths.DATA."""
    arrays = {k: np.asarray(r[k], np.float32) for k in LOW_T}
    arrays.update({k: np.asarray(r[k]).astype(np.float16) for k in LOW_W})
    if "land" in r:
        arrays["land"] = (np.nan_to_num(np.asarray(r["land"], np.float32)) >= 0.5).astype(np.uint8)
        arrays["ice"] = np.clip(np.rint(np.nan_to_num(np.asarray(r["ice"], np.float32)) * 100), 0, 100).astype(np.uint8)
    if root is None:
        put(basin, cycle, "%s_low_f%03d" % (model, step), **arrays)
        return
    p = low_path(basin, cycle, model, step, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    _save(p, **arrays)


def low_path(basin, cycle, model, step, root):
    """Path of a low file under a local root laid out as fields/{basin}/{cycle}/ (the pre-Releases layout)."""
    return Path(root, "fields", basin, tag(cycle), "%s_low_f%03d.npz" % (model, step))


def load_low(basin, cycle, model, step, root=None):
    """Stored lower-level fields -> dict (temperatures K, winds m/s, float32; gfs also land bool and
    ice fraction 0-1 float32) or None. root overrides rk.paths.DATA."""
    if root is None:
        z = load(basin, cycle, "%s_low_f%03d" % (model, step))
    else:
        p = low_path(basin, cycle, model, step, root)
        if not p.exists():
            return None
        with np.load(p) as f:
            z = {k: f[k] for k in f.files}
    if z is None:
        return None
    out = {k: v.astype(np.float32) for k, v in z.items() if k not in ("land", "ice")}
    if "land" in z:
        out["land"] = z["land"].astype(bool)
        out["ice"] = z["ice"].astype(np.float32) / 100.0
    return out


def load(basin, cycle, name):
    """Any stored field file by name (e.g. 'gfs_low_f024') -> {key: array} as written, or None."""
    p = _locate(basin, cycle, _check_name(name))
    if p is None:
        return None
    with np.load(p) as z:
        return {k: z[k] for k in z.files}


def _save_det(cycle, model, step, res, basins):
    for b in basins:
        r = res[b]
        put(b, cycle, "%s_f%03d" % (model, step), u=r["u"].astype(np.float16), v=r["v"].astype(np.float16),
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


def fill(cycle, steps=STEPS, models=DET, ens=ENS, workers=6, basins=tuple(BASINS), complete=False):
    """Fetch what is missing (in no cache, legacy dir or release) for the basins (both by default) from one
    cycle and store it in the local cache, marked unpublished.
    Skips an ensemble step when fewer than 20 members came back (complete=True: when fewer than FULL_MEMBERS,
    so a step still being posted is not stored short and then treated as existing; the next run retries it);
    each file comes from one run.
    Returns {'cycle', 'fetched', 'existing', 'missing', 'skipped_ens'} (lists of 'model_fSSS')."""
    rep = {"cycle": tag(cycle), "fetched": [], "existing": [], "missing": [], "skipped_ens": []}
    jobs = []
    for name in list(models) + list(ens):
        for step in steps:
            label = "%s_f%03d" % (name, step)
            if not available(name, cycle):
                rep["missing"].append(label)
            elif all(_locate(b, cycle, label) is not None for b in basins):
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
        if len(next(iter(res.values()))["u"]) < (FULL_MEMBERS[name] if complete else MIN_MEMBERS):
            return label, "skipped_ens"
        for b in basins:
            put(b, cycle, "%s_f%03d" % (name, step), **ens_stats(res[b]))
        return label, "fetched"

    with ThreadPoolExecutor(workers) as ex:
        for label, what in ex.map(run, jobs):
            rep[what].append(label)
    return rep


# ---- truth files: cache, legacy DATA/truth, release (plain npz assets, one per valid time or day) ----
#
# truth/{kind}/[{basin}/]{stem}.npz, stem = YYYYMMDDHH (analysis, obs, airsea) or YYYYMMDD (ascat, smap).
# Release truth-{kind}[-{basin}]-{YYYYMM} (month of the stem), asset {stem}.npz. Kinds that differ by basin
# (analysis, obs, airsea) get one release per basin. Read order: CACHE/truth, legacy DATA/truth, release.

TRUTH_KINDS = {"analysis": (True, 10), "obs": (True, 10), "airsea": (True, 10),
               "ascat": (False, 8), "smap": (False, 8)}   # kind: (per basin, stem length)


def truth_key(kind, basin, stem):
    """Validate and normalise -> (kind, basin or None, stem). stem may be a datetime/date or a string
    (with or without .npz); a basin is required for per-basin kinds and ignored for the others."""
    if kind not in TRUTH_KINDS:
        raise ValueError("unknown truth kind %r (%s)" % (kind, ", ".join(TRUTH_KINDS)))
    per_basin, n = TRUTH_KINDS[kind]
    if not isinstance(stem, str):
        stem = stem.strftime("%Y%m%d%H" if n == 10 else "%Y%m%d")
    elif stem.endswith(".npz"):
        stem = stem[:-4]
    if len(stem) != n or not stem.isdigit():
        raise ValueError("bad %s stem %r (expected %d digits)" % (kind, stem, n))
    if per_basin and basin not in BASINS:
        raise ValueError("%s needs a basin (natl or npac), got %r" % (kind, basin))
    return kind, (basin if per_basin else None), stem


def _truth_rel(kind, basin, stem):
    return Path("truth", kind, *([basin] if basin else []), stem + ".npz")


def truth_tag(kind, basin, stem):
    """Release tag: truth-{kind}[-{basin}]-{YYYYMM}, e.g. truth-ascat-202511, truth-analysis-natl-202511."""
    kind, basin, stem = truth_key(kind, basin, stem)
    return "truth-%s-%s%s" % (kind, basin + "-" if basin else "", stem[:6])


def truth_asset(kind, basin, stem):
    return truth_key(kind, basin, stem)[2] + ".npz"


def truth_url(kind, basin, stem):
    return "%s/%s/%s" % (RELEASES.rstrip("/"), truth_tag(kind, basin, stem), truth_asset(kind, basin, stem))


def truth_cache_path(kind, basin, stem):
    return paths.CACHE / _truth_rel(*truth_key(kind, basin, stem))


def truth_legacy_path(kind, basin, stem):
    return paths.DATA / _truth_rel(*truth_key(kind, basin, stem))


def truth_local(kind, basin, stem):
    """Existing cache or legacy file (no network), else None."""
    for p in (truth_cache_path(kind, basin, stem), truth_legacy_path(kind, basin, stem)):
        if p.exists():
            return p
    return None


_truth_absent = set()    # release URLs that answered 403/404 in this process
_truth_lock = threading.Lock()


def _http_exists(url):
    """True when the URL answers 200 (the body is not read); False on 403/404; other failures raise."""
    r = _get_session().get(url, timeout=(10, 60), stream=True)
    try:
        if r.status_code in (403, 404):
            return False
        r.raise_for_status()
        return True
    finally:
        r.close()


def truth_locate(kind, basin, stem, download=True):
    """Path of a truth file: cache, then legacy DATA/truth, then the release (download=True; the asset is
    saved into the cache, not marked dirty). None if nowhere. A 404 is remembered for the process.
    RK_OFFLINE=1 skips the release."""
    p = truth_local(kind, basin, stem)
    if p is not None or not download or os.environ.get("RK_OFFLINE") == "1":
        return p
    url = truth_url(kind, basin, stem)
    with _truth_lock:
        if url in _truth_absent:
            return None
    blob = _http_get(url)
    if blob is None:
        with _truth_lock:
            _truth_absent.add(url)
        return None
    p = truth_cache_path(kind, basin, stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(p, blob)
    return p


def truth_exists(kind, basin, stem):
    """Is the truth file in the cache, the legacy dir or the release? Asks the release with a request that
    does not download the file. Offline: cache and legacy only."""
    if truth_local(kind, basin, stem) is not None:
        return True
    if os.environ.get("RK_OFFLINE") == "1":
        return False
    url = truth_url(kind, basin, stem)
    with _truth_lock:
        if url in _truth_absent:
            return False
    if _http_exists(url):
        return True
    with _truth_lock:
        _truth_absent.add(url)
    return False


def truth_save(kind, basin, stem, **arrays):
    """Write a truth file into the local cache atomically and mark it unpublished (truth_dirty). Returns the path."""
    k, b, s = truth_key(kind, basin, stem)
    p = truth_cache_path(k, b, s)
    p.parent.mkdir(parents=True, exist_ok=True)
    d = p.parent / ".dirty"
    d.mkdir(exist_ok=True)
    (d / p.name).touch()          # marked first, as in put()
    _save(p, **arrays)
    return p


def truth_dirty():
    """Cache truth files not yet published -> {(kind, basin or None): sorted file names ('YYYYMMDDHH.npz')}."""
    out = {}
    for kind, (per_basin, _) in TRUTH_KINDS.items():
        for b in (sorted(BASINS) if per_basin else [None]):
            d = paths.CACHE / "truth" / kind / (b or "") / ".dirty"
            if d.is_dir():
                names = sorted(m.name for m in d.iterdir() if (d.parent / m.name).is_file())
                if names:
                    out[(kind, b)] = names
    return out


def truth_mark_clean(kind, basin, names):
    """Clear the unpublished marks of truth file names (with or without .npz)."""
    kind, basin, _ = truth_key(kind, basin, "0" * TRUTH_KINDS[kind][1])
    d = paths.CACHE / "truth" / kind / (basin or "") / ".dirty"
    for n in names:
        try:
            (d / (n if n.endswith(".npz") else n + ".npz")).unlink()
        except FileNotFoundError:
            pass
    try:
        d.rmdir()
    except OSError:
        pass


def truth_merge(kind, local, remote):
    """Compare a local truth file (Path) with the published asset (bytes or None) ->
    'new' (nothing published), 'same' (identical arrays), 'kept' (publish nothing: the published smap day is
    FINAL and the local one is NRT) or 'replaced' (local differs; local wins, as for field files).
    Arrays are compared, not bytes: npz bytes carry a timestamp."""
    if remote is None:
        return "new"
    with np.load(local) as a, np.load(io.BytesIO(remote)) as b:
        if kind == "smap" and "final" in a.files and "final" in b.files and int(b["final"]) > int(a["final"]):
            return "kept"
        if sorted(a.files) == sorted(b.files) and all(
                a[k].dtype == b[k].dtype and np.array_equal(a[k], b[k], equal_nan=a[k].dtype.kind == "f")
                for k in a.files):
            return "same"
    return "replaced"


# ---- analysis: GFS and IFS step 0 at the valid time, plus the open-water mask ----

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
    Cached as truth file kind 'analysis' (see truth_locate); both basins are cached at once."""
    p = truth_locate("analysis", basin, valid)
    if p is not None:
        with np.load(p) as z:
            return _load_analysis(z)
    if not (available("gfs", valid) and available("ifs", valid)):
        return None
    g, i, m = fetch.det("gfs", valid, 0), fetch.det("ifs", valid, 0), fetch.gfs_mask(valid)
    if g is None or i is None or m is None:
        return None
    for b in BASINS:
        p = truth_save("analysis", b, valid, **analysis_arrays(g[b], i[b], m[b]["land"], m[b]["ice"]))
    p = truth_cache_path("analysis", basin, valid)
    with np.load(p) as z:
        return _load_analysis(z)
