"""Tests for rk.style. Run: python3 tests/test_style.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import numpy as np
from rk import style


def test_wind_cmap():
    cm, norm = style.wind_cmap(), style.wind_norm()
    assert cm.N == 11 and len(style.WIND_LEVELS) == 12
    assert cm(norm(33.9)) != cm(norm(34.0))
    assert matplotlib.colors.to_hex(cm(norm(34.0))) == "#e8d27a"
    assert matplotlib.colors.to_hex(cm(norm(33.9))) == "#5683b5"
    assert matplotlib.colors.to_hex(cm(norm(70))) == "#9b1f5e"


def test_colors():
    assert style.METHOD_COLORS["gefs"] == style.METHOD_COLORS["gfs"]
    assert style.METHOD_COLORS["ens"] == style.METHOD_COLORS["ecmwf"]
    assert set(style.HAZARD_COLORS) == {"gale", "storm", "hf"} and set(style.BASIN_COLORS) == {"natl", "npac"}
    d = style.diverging_cmap()
    assert matplotlib.colors.to_hex(d(0.0)) == "#2b5fa8" and matplotlib.colors.to_hex(d(1.0)) == "#a8301f"


def test_use_and_save():
    import matplotlib.pyplot as plt
    style.use()
    assert matplotlib.rcParams["axes.spines.top"] is False and matplotlib.rcParams["figure.dpi"] == 150
    fig, ax = plt.subplots(); ax.plot([0, 1], [0, 1]); style.title(ax, "Finding", "10 cases")
    with tempfile.TemporaryDirectory() as d:
        style.save(fig, Path(d) / "sub" / "x.png")
        assert (Path(d) / "sub" / "x.png").exists() and (Path(d) / "sub" / "x.svg").exists()


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
