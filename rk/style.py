"""Light figure style for studies: white background, quiet axes, fixed method colours.

Call use() once before plotting. Colours per method never change.
"""
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np

INK = "#1f1f1d"
INK2 = "#5f5e5a"
SPINE = "#bdbcb6"
GRID = "#ecebe7"

METHOD_COLORS = {
    "ifs": "#2a78d6", "ecmwf": "#2a78d6", "gfs": "#eb6834", "aifs": "#6250d6",
    "blend": "#1baf7a", "corelift": "#008300", "mean3": "#7a7974",
    "gefs": "#eb6834", "ens": "#2a78d6", "aifs-ens": "#6250d6",
    "desk": "#1f1f1d", "analysis": "#5f5e5a", "ascat": "#e34948", "buoys": "#eda100",
}
# Ensemble means use their parent's hue, dashed. Everything else is solid.
METHOD_DASHES = {"gefs": (4, 2), "ens": (4, 2), "aifs-ens": (4, 2)}
METHOD_LABELS = {
    "gfs": "GFS", "ifs": "ECMWF", "ecmwf": "ECMWF", "aifs": "AIFS", "blend": "Blend",
    "corelift": "Core Lifted", "mean3": "3-model mean", "gefs": "GEFS mean", "ens": "ENS mean",
    "aifs-ens": "AIFS ENS mean", "desk": "Desk", "analysis": "Analysis", "ascat": "ASCAT",
    "buoys": "Buoys",
}

WIND_LEVELS = [0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80]
# 11 intervals need 11 colours: six below gale (0-34) and five from 34 up
# (34-41, 41-48, 48-56, 56-64, 64-80). The page has six gale-and-above colours;
# its last one (the 80+ violet) is the overflow colour.
WIND_COLORS = ["#f4f6f8", "#dde6ef", "#c3d4e6", "#9fbbd9", "#7aa0c9", "#5683b5",
               "#e8d27a", "#e8a93f", "#e06f2e", "#c9372c", "#9b1f5e"]
WIND_OVER = "#c86fd8"

HAZARD_COLORS = {"gale": "#c98500", "storm": "#d9480f", "hf": "#b5179e"}
HAZARD_THRESHOLDS = {"gale": 34, "storm": 48, "hf": 64}

DIV_LOW, DIV_MID, DIV_HIGH = "#2b5fa8", "#f0efec", "#a8301f"


def use():
    """Apply the house matplotlib style."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.facecolor": "#ffffff", "axes.facecolor": "#ffffff", "savefig.facecolor": "#ffffff",
        "figure.dpi": 150, "savefig.dpi": 150,
        "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "font.family": "sans-serif", "font.size": 10,
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "axes.titlesize": 12, "axes.titleweight": "normal", "axes.titlelocation": "left",
        "axes.edgecolor": SPINE, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round",
        "legend.frameon": False, "legend.labelcolor": INK,
    })


def method_line(ax, x, y, method, **kw):
    """Plot a line in the method's fixed colour (dashed for ensemble means)."""
    kw.setdefault("color", METHOD_COLORS[method])
    kw.setdefault("label", METHOD_LABELS[method])
    if method in METHOD_DASHES:
        kw.setdefault("dashes", METHOD_DASHES[method])
    return ax.plot(x, y, **kw)


def wind_cmap():
    """Wind colour map: light blues below gale, the page's colours from 34 kt."""
    from matplotlib.colors import ListedColormap
    cm = ListedColormap(WIND_COLORS, name="rk_wind")
    cm.set_over(WIND_OVER)
    cm.set_under(WIND_COLORS[0])
    return cm


def wind_norm():
    from matplotlib.colors import BoundaryNorm
    return BoundaryNorm(WIND_LEVELS, len(WIND_COLORS))


def wind_colorbar(fig, mappable, ax):
    """Colour bar with ticks at the knot breaks, labelled '10 m wind (kt)'."""
    cb = fig.colorbar(mappable, ax=ax, ticks=WIND_LEVELS, spacing="uniform",
                      fraction=0.04, pad=0.02, extend="max")
    cb.set_label("10 m wind (kt)", color=INK2)
    cb.outline.set_edgecolor(SPINE)
    cb.ax.tick_params(length=2)
    return cb


def diverging_cmap():
    """Blue - gray - red for errors (forecast minus truth). Use with a symmetric norm."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("rk_div", [DIV_LOW, DIV_MID, DIV_HIGH], N=256)


def title(ax, finding, detail=None):
    """Finding as the left title; detail (cases, period, basin, hour) smaller beneath."""
    ax.set_title(finding, loc="left", fontsize=12, color=INK, pad=22 if detail else 8)
    if detail:
        ax.text(0, 1.02, detail, transform=ax.transAxes, ha="left", va="bottom",
                fontsize=9, color=INK2)
    return ax


def save(fig, path):
    """Write PNG (150 dpi) and an SVG with the same stem. Returns both paths."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    png, svg = p.with_suffix(".png"), p.with_suffix(".svg")
    fig.savefig(png, dpi=150, bbox_inches="tight", facecolor="#ffffff")
    fig.savefig(svg, bbox_inches="tight", facecolor="#ffffff")
    return png, svg


def _land_path():
    env = os.environ.get("RK_LAND_JSON")
    if env and Path(env).is_file():
        return Path(env)
    cand = Path(__file__).resolve().parents[2] / "awips-tools" / "globe_kit" / "land.json"
    return cand if cand.is_file() else None


_LAND = None


def _land_rings():
    """List of (n,2) lon/lat arrays: outer rings of Natural Earth land."""
    global _LAND
    if _LAND is None:
        p = _land_path()
        if p is None:
            warnings.warn("land.json not found (set RK_LAND_JSON); drawing no land")
            _LAND = []
        else:
            gj = json.loads(p.read_text())
            geoms = []
            def walk(o):
                t = o.get("type")
                if t == "FeatureCollection":
                    for f in o["features"]:
                        walk(f)
                elif t == "Feature":
                    walk(o["geometry"])
                elif t == "GeometryCollection":
                    for g in o["geometries"]:
                        walk(g)
                elif t == "Polygon":
                    geoms.append(o["coordinates"])
                elif t == "MultiPolygon":
                    geoms.extend(o["coordinates"])
            walk(gj)
            _LAND = [np.asarray(poly[0], float) for poly in geoms]
    return _LAND


def map_axes(basin, fig=None, ax=None, land=True):
    """Plain lat/lon axes for a basin box, land filled, longitudes 0-360.

    Returns (fig, ax). No projection; a fixed aspect keeps shapes sensible at 30-67 N.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from rk.basins import BASINS
    b = BASINS[basin] if isinstance(basin, str) else basin
    if ax is None:
        fig, ax = plt.subplots(figsize=(7.2, 4.6)) if fig is None else (fig, fig.add_subplot())
    fig = ax.figure
    ax.set_xlim(b["west"], b["east"])
    ax.set_ylim(b["south"], b["north"])
    ax.set_aspect(1 / np.cos(np.radians((b["north"] + b["south"]) / 2)))
    if land:
        for ring in _land_rings():
            lo = ring[:, 0]
            for shift in (-360.0, 0.0, 360.0):
                x = lo + shift
                if x.max() < b["west"] or x.min() > b["east"]:
                    continue
                ax.add_patch(Polygon(np.column_stack([x, ring[:, 1]]), closed=True, fc="#e9e7e1",
                                     ec=SPINE, lw=0.6, zorder=3))
    ax.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}°E" if v <= 180 else f"{360 - v:.0f}°W")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}°N")
    return fig, ax
