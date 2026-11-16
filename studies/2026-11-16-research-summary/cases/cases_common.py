"""Shared pieces for the three worked cases (case1_hf_core.py, case2_cold_outbreak.py, case3_goa_jet.py).

Each case script writes one PNG (200 dpi, under 1 MB), a PDF and a caption .md to RK_SUMMARY_OUT (default
<RK_DATA>/../research-summary/cases). Per-case model inputs for cases 1 and 2 are the two existing builders' npz
(most-likely-wind and strong-core-lift case_job); ensure_case() runs them if the cache lacks them and then drops
the unpacked store cycles. Nothing here changes a study folder or the store.
"""
import datetime as dt
import importlib.util
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDIES = REPO / "studies"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(STUDIES / "2026-10-16-core-lift-retrain"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from rk import basins, paths, store, style  # noqa: E402

OUT = Path(os.environ.get("RK_SUMMARY_OUT") or paths.DATA.parent / "research-summary" / "cases")
NM2_PER_CELL_EQ = 15.0 * 15.0          # 0.25 deg cell: 15' x 15' cos(lat), nautical miles squared
_MODS = {}


def load_study(name, rel):
    """Import a study file by path under its own name (studies reuse the module names score, build ...)."""
    if name not in _MODS:
        spec = importlib.util.spec_from_file_location(name, STUDIES / rel)
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
        _MODS[name] = m
    return _MODS[name]


def mlw_build():
    return load_study("mlw_build_cases", "2026-11-07-most-likely-wind/build_cases.py")


def mlw_score():
    return load_study("mlw_score_cells", "2026-11-07-most-likely-wind/score_cells.py")


def rescore():
    """studies/2026-11-16-desk-30m-vs-best-wind/score.py (read only): load(basin, cyc, step) -> case dict and
    products(d) -> ({name: grid}, common) with Best Wind as the page draws it (gale floor at 80%) and desk practice
    (sh_avg: Stability Height on GFS strict and ECMWF loose, then averaged)."""
    return load_study("resc_score", "2026-11-16-desk-30m-vs-best-wind/score.py")


def slc_build():
    return load_study("slc_build", "2026-11-06-strong-core-lift/build.py")


def slc_score():
    return load_study("slc_score", "2026-11-06-strong-core-lift/score.py")


def ensure_case(basin, cyc, step):
    """Paths of the most-likely-wind and strong-core-lift npz of one case; built (about 15 MB per cycle from the
    store releases, plus the lag cycles) when the cache lacks them, then the unpacked cycles are deleted."""
    a = paths.cache("extra", "most-likely-wind", basin) / ("%s_f%03d.npz" % (cyc.strftime("%Y%m%d%H"), step))
    b = paths.cache("extra", "strong-core-lift", basin) / ("%s_f%03d.npz" % (cyc.strftime("%Y%m%d%H"), step))
    if not (a.exists() and b.exists()):
        r1 = mlw_build().case_job((basin, cyc, step))
        r2 = slc_build().case_job((basin, cyc, step))
        if not (a.exists() and b.exists()):
            raise RuntimeError("case build failed: %s %s" % (r1, r2))
        for h in (0, 12, 24):
            d = store._cache_dir(basin, cyc - dt.timedelta(hours=h))
            if d.exists() and not (d / ".dirty").exists():
                shutil.rmtree(d, ignore_errors=True)
    return a, b


def cell_area_nm2(basin):
    """Area of every 0.25 deg cell in nm^2 (225 cos(lat)), [ny, nx]."""
    lats, lons = basins.grid(basin)
    return np.repeat((NM2_PER_CELL_EQ * np.cos(np.radians(lats)))[:, None], len(lons), 1)


def area_k(mask, area):
    """Thousand nm^2 of a boolean mask."""
    return float(area[mask].sum()) / 1000.0


def crop_box(basin, mask, pad_lat=5.0, pad_lon=12.0):
    """(west, east, south, north) around the True cells of mask, clipped to the basin box."""
    lats, lons = basins.grid(basin)
    iy, ix = np.where(mask)
    b = basins.BASINS[basin]
    return (max(lons[ix].min() - pad_lon, b["west"]), min(lons[ix].max() + pad_lon, b["east"]),
            max(lats[iy].min() - pad_lat, b["south"]), min(lats[iy].max() + pad_lat, b["north"]))


def base_map(basin, ax, box):
    style.map_axes(basin, ax=ax)
    ax.set_xlim(box[0], box[1])
    ax.set_ylim(box[2], box[3])
    ax.set_aspect(1 / np.cos(np.radians((box[2] + box[3]) / 2)))
    ax.grid(True, color=style.GRID, lw=0.5, zorder=0)
    ax.tick_params(labelsize=7.5, length=2)
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(10))
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
    return ax


def draw_wind(ax, basin, field, seen=None, faint=None, contours=True):
    """Wind shading with the house knot breaks. field [ny, nx] (NaN = nothing). `seen` (bool): cells drawn at full
    strength; `faint` (bool): cells drawn pale beneath (model fields outside the ASCAT swath). 34/48/64 kt contours
    on the full-strength cells, in the hazard hues."""
    lats, lons = basins.grid(basin)
    cmap, norm = style.wind_cmap(), style.wind_norm()
    f = np.asarray(field, np.float32)
    if faint is not None:
        ax.pcolormesh(lons, lats, np.where(faint, f, np.nan), cmap=cmap, norm=norm, shading="nearest",
                      alpha=0.30, zorder=1, rasterized=True)
    shown = f if seen is None else np.where(seen, f, np.nan)
    m = ax.pcolormesh(lons, lats, shown, cmap=cmap, norm=norm, shading="nearest", zorder=2, rasterized=True)
    if contours:
        z = np.nan_to_num(shown, nan=0.0)
        for t, key in ((34, "gale"), (48, "storm"), (64, "hf")):
            if (z >= t).any() and (z < t).any():
                ax.contour(lons, lats, z, [t - 0.01], colors=style.HAZARD_COLORS[key],
                           linewidths=(0.9, 1.1, 1.4)[(34, 48, 64).index(t)], zorder=4)
    return m


def wind_legend(fig, mappable, axes, label="10 m wind (kt)"):
    cb = fig.colorbar(mappable, ax=axes, ticks=style.WIND_LEVELS, spacing="uniform", orientation="horizontal",
                      fraction=0.05, pad=0.10, aspect=45, extend="max")
    cb.set_label(label, color=style.INK2, fontsize=9)
    cb.outline.set_edgecolor(style.SPINE)
    cb.ax.tick_params(length=2, labelsize=8)
    return cb


def contour_note(fig, y=0.005):
    fig.text(0.5, y, "Contours: gale 34 kt (amber), storm 48 kt (orange-red), hurricane force 64 kt (magenta)",
             ha="center", va="bottom", fontsize=8.5, color=style.INK2)


def save_all(fig, stem):
    """PNG at 200 dpi (checked under 1 MB), PDF; returns paths."""
    OUT.mkdir(parents=True, exist_ok=True)
    png, pdf = OUT / (stem + ".png"), OUT / (stem + ".pdf")
    fig.savefig(png, dpi=200, bbox_inches="tight", facecolor="#ffffff")
    fig.savefig(pdf, bbox_inches="tight", facecolor="#ffffff")
    kb = png.stat().st_size / 1024
    print("%s %.0f KB, pdf %.0f KB" % (png, kb, pdf.stat().st_size / 1024))
    assert kb < 1024, "PNG over 1 MB"
    return png, pdf


def write_caption(stem, text):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (stem + ".md")).write_text(text)
