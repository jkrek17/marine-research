"""Tests for rk.classes. Run with pytest or `python3 tests/test_classes.py`.
Compared cell for cell with awips-tools' focus_grid when that checkout sits beside this repository."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from rk import classes as C  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO.parent / "awips-tools" / "marine_wind" / "pipeline" / "build.py"


def _flat(v, shape=(21, 21)):
    return np.full((3,) + shape, float(v))


def test_constants():
    assert (C.RIDE, C.AGREE, C.FOCUS, C.HIGH) == (0, 1, 2, 3)
    assert C.NAMES == ("ride", "agree", "focus", "high impact")


def test_hand_made():
    s = _flat(20)
    assert (C.classes(s) == C.RIDE).all()                    # all below 30 kt
    s = _flat(36)
    assert (C.classes(s) == C.AGREE).all()                   # all above 30, all agree
    s = _flat(20)
    s[0, 10, 10] = 36                                        # one model has a gale the others lack nearby
    s[0, 10, 11] = 36
    assert C.classes(s)[10, 10] == C.FOCUS
    s = _flat(20)
    s[:, :, :] = 40
    s[0, 10, 10] = 55                                        # 15 kt above the others' neighbourhood max
    assert C.classes(s)[10, 10] == C.HIGH                    # 48 kt category vs 34 kt everywhere else
    s = _flat(33)
    s[0, 10, 10] = 44                                        # spread of 11 kt, same category (34-48)
    assert C.classes(s)[10, 10] == C.FOCUS


def _page_rule():
    """focus_grid and its constants from awips-tools, without importing the pipeline (it loads data)."""
    import ast
    from scipy import ndimage
    src = BUILD.read_text()
    tree = ast.parse(src)
    keep = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "focus_grid":
            keep.append(n)
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("RIDE_BELOW", "TOL_CELLS", "SPREAD_KT")
                                               or isinstance(t, ast.Tuple) for t in n.targets):
            if "RIDE_BELOW" in ast.unparse(n.targets[0]):
                keep.append(n)
    ns = {"np": np, "ndimage": ndimage, "FMODE": "reflect"}
    exec(compile(ast.Module(keep, []), str(BUILD), "exec"), ns)
    return ns


def test_against_page():
    if not BUILD.exists():
        print("note: awips-tools checkout not found beside this repo; page comparison skipped")
        return
    ns = _page_rule()
    assert (ns["RIDE_BELOW"], ns["SPREAD_KT"], ns["TOL_CELLS"]) == (C.RIDE_BELOW, C.SPREAD_KT, C.TOL_CELLS)
    rng = np.random.default_rng(3)
    fields = []
    for _ in range(6):                                   # random, with a wide range so every class occurs
        fields.append(rng.uniform(0, 80, (3, 40, 50)))
    base = rng.uniform(10, 60, (1, 40, 50))
    fields.append(base + rng.normal(0, 4, (3, 40, 50)))   # models close to each other
    yy, xx = np.mgrid[0:40, 0:50]                         # structured: shifted blobs
    for dx in (0, 1, 2, 3, 5):
        fields.append(np.array([30 + 40 * np.exp(-((xx - 20 - k * dx) ** 2 + (yy - 20) ** 2) / 60.0) for k in range(3)]))
    seen = set()
    for f in fields:
        a, b = C.classes(f), ns["focus_grid"](f)
        assert a.dtype == b.dtype and np.array_equal(a, b)
        seen |= set(np.unique(a).tolist())
    assert seen == {0, 1, 2, 3}, seen


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
