"""The marine wind page's routine / attention classes.

Copied from awips-tools `marine_wind/pipeline/build.py` (`focus_grid`, constants RIDE_BELOW, SPREAD_KT,
TOL_CELLS, and FMODE for a basin box) at commit 3eb2ff5. It is the page rule and must stay identical to it.
"""
import numpy as np
from scipy import ndimage

RIDE, AGREE, FOCUS, HIGH = 0, 1, 2, 3
NAMES = ("ride", "agree", "focus", "high impact")
RIDE_BELOW, SPREAD_KT, TOL_CELLS = 30.0, 10.0, 2
FMODE = "reflect"   # a basin box (the page's global grid wraps in x; these boxes do not)


def classes(speeds):
    """speeds [3, y, x] kt (GFS, IFS, AIFS) -> 0 ride / 1 agree / 2 focus / 3 high impact.
    A model only counts as disagreeing if it has no such wind within TOL_CELLS,
    so a gale edge drawn 25 km differently is not flagged."""
    cats = (34.0, 48.0, 64.0)
    mx = speeds.max(0)
    near = np.array([ndimage.maximum_filter(s, size=2 * TOL_CELLS + 1, mode=FMODE) for s in speeds])
    cmax, cmin = np.digitize(speeds, cats).max(0), np.digitize(near, cats).min(0)
    out = np.ones(mx.shape, np.uint8)
    out[mx < RIDE_BELOW] = 0
    out[((cmax >= 1) & (cmin == 0)) | ((mx - near.min(0) >= SPREAD_KT) & (mx >= RIDE_BELOW))] = 2
    out[(cmax >= 2) & (cmin < cmax)] = 3
    return out
