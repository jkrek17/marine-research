"""Move this study's MSLP cache into the shared field store (rk.store) and read it back.

Each local file fc_{src}_{YYYYMMDD}.npz / an_{src}_{YYYYMMDD}.npz (both basins, see the cache README) is split
by basin into store file mslpd57_{src} / mslpd57_an_{src} of basin-cycle (basin, 'YYYYMMDD12'), keeping the
array names and the int16 encoding (hPa*10 - 10000). Analyses go under their valid date.

  python3 store_io.py put        -> rk.store.put for every local file not yet in the store cache
  then: python3 tools/publish_store.py --repo <clone of jkrek17/marine-research-data>
"""
import os, sys, glob
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from rk import store

DOMS = ("natl", "npac")


def _name(kind, src):
    return ("mslpd57_an_%s" if kind == "an" else "mslpd57_%s") % src


def get(kind, src, ymd):
    """{array name: int16 array} for local file {kind}_{src}_{ymd}.npz rebuilt from the store, or None."""
    out = {}
    for dom in DOMS:
        z = store.load(dom, ymd + "12", _name(kind, src))
        if z:
            out.update(z)
    return out or None


def put_all():
    n = 0
    for p in sorted(glob.glob(os.path.join(lib.CACHE, "*_*_????????.npz"))):
        kind, src, ymd = os.path.basename(p)[:-4].split("_")
        z = np.load(p)
        for dom in DOMS:
            arrs = {k: z[k] for k in z.files if "_%s" % dom in k}
            if arrs and not store._cache_path(dom, ymd + "12", _name(kind, src)).exists():
                store.put(dom, ymd + "12", _name(kind, src), **arrs)
                n += 1
    print(n, "files put")


if __name__ == "__main__" and sys.argv[1:] == ["put"]:
    put_all()
