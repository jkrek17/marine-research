"""Shared pieces of the GEFS-only core-lift scripts (design card section 2).

Reuses the 2026-10-16 retrain's `common` (folds, HGB settings, cache layout, week ids) and `build_table` /
`train` code, and the 2026-10-17 gale-core scorer. What is new here:
  * `install()`: patches (in the calling process) rk.features.core to the GFE inputs (GFS + IFS, GEFS only; no
    AIFS, ENS or AIFS ENS), optionally with the GEFS inputs at 0.5 deg (rk.features.half_deg), and the store
    pull to unpack only the members this study reads (gfs, ifs, gefs and their low files);
  * the feature set `gefs26+basin`: the live 28 minus s10_aifs and pa48 (which exist only with AIFS / AIFS ENS),
    plus the basin flag;
  * layout of the study's cache under rk.paths.data("extra", "gefs-only-gfe", "core").
Every worker process calls install() (Pool initializer), because the retrain code reads `common.SETS` inside
the workers.
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
# The local disk is shared and nearly full: this study keeps its own field cache (the slim members it reads) in
# the shared data folder, before rk is imported. An RK_CACHE set by the caller wins.
if not os.environ.get("RK_CACHE"):
    os.environ["RK_CACHE"] = str(Path(os.environ.get("RK_DATA", "/mnt/project-files/research-data"))
                                 / "extra" / "gefs-only-gfe" / "core" / "cache")
RETRAIN = REPO / "studies" / "2026-10-16-core-lift-retrain"
GALE = REPO / "studies" / "2026-10-17-gale-core"
for p in (str(GALE), str(RETRAIN)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import common as C  # noqa: E402
from rk import features, paths, store  # noqa: E402

MODELS = ("gfs", "ifs")
ENS = ("gefs",)
DROP = ("s10_aifs", "pa48")
SET = "gefs26+basin"
SET_COLS = [f for f in features.FEATURES if f not in DROP] + ["basin_pac"]
KEEP_RE = re.compile(r"^(gfs|ifs|gefs)(_low)?_f\d+\.npz$")
# GEFS grids that come from the stored ensemble statistics (store.load_ens keys)
GEFS_KEYS = ("p34", "p48", "p64", "spd_mean", "spd_std")

STATE = {"half": False, "low_models": MODELS}
_ORIG = {}


def root():
    return paths.data("extra", "gefs-only-gfe", "core")


def awips_pipeline():
    """awips-tools marine_wind/pipeline: AWIPS_TOOLS, else an awips-tools folder beside any parent of this repo."""
    cands = [os.environ.get("AWIPS_TOOLS")] + [str(p / "awips-tools") for p in REPO.parents]
    for c in cands:
        if c and (Path(c) / "marine_wind" / "pipeline" / "storm.py").exists():
            return str(Path(c) / "marine_wind" / "pipeline")
    raise SystemExit("awips-tools checkout not found: set AWIPS_TOOLS")


def _slim_pull(basin, cycle):
    """store._pull that unpacks only KEEP_RE members (gfs, ifs, gefs fields and low files)."""
    import io
    import zipfile
    key = (basin, store._tag(cycle))
    with store._pull_guard:
        lock = store._pull_locks.setdefault(key, __import__("threading").Lock())
    with lock:
        if key in store._pulled:
            return False
        if os.environ.get("RK_OFFLINE") == "1":
            return False
        for attempt in range(6):
            try:
                blob = store._http_get(store.release_url(basin, cycle))
                break
            except Exception:
                if attempt == 5:
                    raise
                __import__("time").sleep(3 * (attempt + 1))
        if blob is not None:
            d = store._cache_dir(basin, cycle)
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for info in z.infolist():
                    n = info.filename
                    if KEEP_RE.match(n) and not (d / n).exists():
                        store._write_bytes(d / n, z.read(info))
        store._pulled.add(key)
        return blob is not None


def _half_ens(basin, cycle, ens, step):
    d = _ORIG["load_ens"](basin, cycle, ens, step)
    if d is None or ens != "gefs":
        return d
    for k in GEFS_KEYS:
        d[k] = features.half_deg(d[k])
    return d


_LAST = {}


def _core(basin, cycle, step, low_root=None, models=None, ens=None, low=True, low_models=None, det_weights=None):
    """Patched rk.features.core: the GFE inputs, optionally with GEFS at 0.5 deg. The last result is kept, so
    the storm and gale table builds of one case compute the features once."""
    lm = tuple(low_models) if low_models else STATE["low_models"]
    key = (basin, cycle, step, STATE["half"], lm, bool(low))
    if _LAST.get("key") == key:
        return _LAST["val"]
    f = _ORIG["core"](basin, cycle, step, low_root=low_root, models=MODELS, ens=ENS, low=low, low_models=lm)
    _LAST.clear()
    _LAST.update(key=key, val=f)
    return f


def install(half=None, low_models=None):
    """Patch this process (idempotent). half / low_models set the variant of this process's jobs."""
    if "core" not in _ORIG:
        _ORIG["core"] = features.core
        _ORIG["load_ens"] = store.load_ens
        _ORIG["pull"] = store._pull
        features.core = _core
        store._pull = _slim_pull
        store.load_ens = _half_ens_dispatch
        C.SETS[SET] = list(SET_COLS)
    set_variant(half, low_models)


def _half_ens_dispatch(basin, cycle, ens, step):
    return _half_ens(basin, cycle, ens, step) if STATE["half"] else _ORIG["load_ens"](basin, cycle, ens, step)


def set_variant(half=None, low_models=None):
    if half is not None:
        STATE["half"] = bool(half)
    if low_models is not None:
        STATE["low_models"] = tuple(low_models)


def raw_core(*a, **k):
    """The unpatched rk.features.core (all models and ensembles by default): the live page's inputs."""
    return _ORIG["core"](*a, **k)


def pull_full(basin, cycle):
    """Unpack EVERY member of the cycle's release zip (the live page inputs need AIFS, ENS, AIFS ENS)."""
    store._pulled.discard((basin, store._tag(cycle)))
    return _ORIG["pull"](basin, cycle)


def trim(basin, cycle):
    """Delete the members this study does not read from a cycle's cache folder."""
    d = store._cache_dir(basin, cycle)
    n = 0
    if d.exists():
        for p in d.iterdir():
            if p.suffix == ".npz" and not KEEP_RE.match(p.name):
                p.unlink()
                n += 1
    return n


def purge(basin, keep=()):
    """Delete the cached cycle folders of a basin except those in `keep` (cycle tags). The shared machine's RAM
    holds the data folder's write cache, so big runs work in blocks of cycles and clear each block."""
    import shutil
    d = store._cache_dir(basin, "2000010100").parent
    n = 0
    if d.exists():
        for p in d.iterdir():
            if p.is_dir() and p.name not in keep:
                shutil.rmtree(p, ignore_errors=True)
                n += 1
    return n


# ---- layout ----

def variant_name(half):
    return "h" if half else "q"


def table_dir(half, kind):
    """Training table (parquet) of a variant and target: kind 'storm' (48 kt) or 'gale' (34 kt)."""
    return root() / "table" / ("%s-%s" % (variant_name(half), kind))


def models_root(half):
    return root() / ("models-" + variant_name(half))


def grids_dir(basin):
    return root() / "grids" / basin


def live_path(basin, cycle, step):
    from rk import cases
    return root() / "live" / basin / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def grid_path(basin, cycle, step):
    from rk import cases
    return grids_dir(basin) / ("%s_f%03d.npz" % (cases.tag(cycle), step))


def heldout_live_path(basin, cycle, step):
    from rk import cases
    return paths.data("extra", "core-lift-retrain", "corelift-heldout", basin,
                      "%s_f%03d.npz" % (cases.tag(cycle), step))
