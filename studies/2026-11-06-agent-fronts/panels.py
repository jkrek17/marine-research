"""Draw a drill case as the six panels a trainee sees (PNG), with a labelled lat/lon grid so the agent can name points.

Same fields and contour choices as the drill page (MSLP every 4 hPa on every panel; thickness blue at/below 540 dam;
theta-e banded every 3 K; 3 h tendency 1 hPa bands; GFS 10 m wind in the page's wind colours), drawn from the
deck's own arrays, so nothing is downloaded. The analysed L(s) and the system's stationary fronts are drawn
(given to the trainee), as is the ring. Truth fronts are never drawn.
  python3 panels.py <case_id> [outdir]
"""
import io
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

import deck  # noqa: E402

VIEWS = ["msl", "img", "te850", "te700", "dp3", "wind"]
TITLES = {"msl": "MSLP (hPa, every 4) + 1000-500 thickness (dam, dashed; blue <=540) + GFS 10 m barbs (kt)",
          "img": "Satellite imagery + MSLP", "te850": "850 hPa theta-e (K, shaded every 3 K) + MSLP",
          "te700": "700 hPa theta-e (K, shaded every 3 K) + MSLP", "dp3": "3 h MSLP change (hPa; red falls, blue rises) + MSLP",
          "wind": "GFS 10 m wind speed (kt, shaded) + barbs + MSLP"}
WIND_LEVELS = [0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80, 200]
WIND_COLORS = ['#f4f6f8', '#dde6ef', '#c3d4e6', '#9fbbd9', '#7aa0c9', '#5683b5', '#f7e68a', '#f2a93b', '#d4531f', '#9e1f1f', '#5c0f45', '#c86fd8']
NAVY, OX = "#1b2a4a", "#7a1f2b"


def _lonlab(x):
    x = ((x + 180) % 360) - 180
    return f"{abs(x):.0f}{'W' if x < 0 else 'E' if x > 0 else ''}"


def draw(case, view, F=None, man=None, dpi=100, size=(10.0, 6.6)):
    """PNG bytes of one panel."""
    F = F or deck.fields(case, man)
    lat, lon = F["lat"], F["lon"]
    LON, LAT = np.meshgrid(lon, lat)
    fig = plt.figure(figsize=size, dpi=dpi)
    ax = fig.add_axes([0.06, 0.07, 0.92, 0.86])
    ax.set_facecolor("#f7f3ea")
    half = 0.25
    ext = [lon[0] - half, lon[-1] + half, lat[-1] - half, lat[0] + half]
    land = F["land"] > 0.5
    if view == "img" and deck.image_path(case) and deck.image_path(case).exists():
        img = plt.imread(deck.image_path(case))
        ax.imshow(img, extent=ext, origin="upper", cmap="gray", aspect="auto")
    elif view in ("te850", "te700"):
        a = F[view]
        lo = np.floor(np.nanmin(a) / 3) * 3
        lv = np.arange(lo, np.nanmax(a) + 3, 3)
        ax.contourf(LON, LAT, a, levels=lv, cmap="RdYlBu_r")
        cs = ax.contour(LON, LAT, a, levels=lv[lv % 6 == 0], colors="#32190a", linewidths=0.5, alpha=0.7)
        ax.clabel(cs, fmt="%d", fontsize=7)
    elif view == "dp3":
        lv = [-30, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 30]
        cols = plt.get_cmap("RdBu")(np.linspace(0.05, 0.95, len(lv) - 1))
        cols[6] = (1, 1, 1, 0)
        ax.contourf(LON, LAT, F["dp3"], levels=lv, colors=cols)
    elif view == "wind":
        ax.contourf(LON, LAT, F["ws10_kt"], levels=WIND_LEVELS, cmap=ListedColormap(WIND_COLORS),
                    norm=BoundaryNorm(WIND_LEVELS, len(WIND_COLORS)))
    if view != "img":
        ax.contourf(LON, LAT, land.astype(float), levels=[0.5, 1.5], colors=["#dde0e4"])
    # MSLP every 4 hPa on every panel
    cs = ax.contour(LON, LAT, F["msl"], levels=np.arange(900, 1080, 4), colors=NAVY if view != "img" else "#ffd54a", linewidths=0.9)
    ax.clabel(cs, fmt="%d", fontsize=7)
    if view == "msl":
        thk = F["thk"]
        lv = np.arange(480, 600, 6)
        ax.contour(LON, LAT, thk, levels=lv[lv <= 540], colors="#1565c0", linewidths=0.8, linestyles="--")
        c2 = ax.contour(LON, LAT, thk, levels=lv[lv > 540], colors="#d32f2f", linewidths=0.8, linestyles="--")
        ax.clabel(c2, fmt="%d", fontsize=6)
    if view in ("msl", "wind"):
        s = slice(None, None, 3)
        ax.barbs(LON[s, s], LAT[s, s], F["u10"][s, s] * 1.94384, F["v10"][s, s] * 1.94384, length=4.6, linewidth=0.5, color="#222")
    # given: lows and the system's stationary fronts, and the ring
    st, lows = deck.given(case)
    for f in st:
        p = np.array(f["pts"])
        ax.plot(p[:, 1], p[:, 0], color="#d32f2f", lw=2.4)
        ax.plot(p[:, 1], p[:, 0], color="#1565c0", lw=2.4, dashes=(4, 4))
    for l in lows:
        ax.text(l["lon"], l["lat"], "L", color="#c62828", fontsize=17, fontweight="bold", ha="center", va="center")
        ax.text(l["lon"], l["lat"] - 0.9, f"{l['hpa']:.0f}", color="#c62828", fontsize=8, ha="center", va="top")
    if case.get("sys_r_nm"):
        t = np.linspace(0, 2 * np.pi, 180)
        r = case["sys_r_nm"] / 60.0
        c0 = case["low"]
        ax.plot(c0["lon"] + r * np.sin(t) / np.cos(np.radians(c0["lat"] + r * np.cos(t))), c0["lat"] + r * np.cos(t),
                color=OX, lw=1.2, dashes=(6, 4))
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    xt = np.arange(np.ceil(ext[0] / 5) * 5, ext[1], 5)
    yt = np.arange(np.ceil(ext[2] / 5) * 5, ext[3], 5)
    ax.set_xticks(xt)
    ax.set_xticklabels([_lonlab(x) for x in xt], fontsize=8)
    ax.set_yticks(yt)
    ax.set_yticklabels([f"{y:.0f}N" for y in yt], fontsize=8)
    ax.grid(color="#555", lw=0.4, alpha=0.5)
    ax.set_title(TITLES[view], fontsize=9, color=NAVY, loc="left")
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def available(case):
    return [v for v in VIEWS if v != "img" or (deck.image_path(case) and deck.image_path(case).exists())]


if __name__ == "__main__":
    man = deck.manifest()
    case = next(c for c in man["cases"] if c["id"] == sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else ".")
    out.mkdir(parents=True, exist_ok=True)
    F = deck.fields(case, man)
    for v in available(case):
        (out / f"{case['id']}_{v}.png").write_bytes(draw(case, v, F, man))
    print("wrote", available(case))
