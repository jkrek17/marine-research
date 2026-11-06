"""Draw the quick guide's schematic (guide_schematic.svg next to this file): a mature Northern Hemisphere ocean low
whose isobars come from a computed pressure field. Each front is a trough line (pressure rises with distance from
it), so the isobars kink into a V at every front, with the V pointing toward higher pressure.

    python3 make_schematic.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

here = Path(__file__).resolve().parent

COLD, WARM, OCC = "#1C5BB5", "#C92A2A", "#7B2D9E"


def curve(p, n=80):
    """Quadratic Bezier through control points p (3x2) -> n points."""
    p = np.asarray(p, float)
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t ** 2 * p[2]


LOW = np.array([0.0, 0.0])
TP = np.array([2.6, 0.9])
occ = curve([LOW, [1.3, 1.6], TP])
warm = curve([TP, [4.3, 0.9], [6.2, -0.6]])
cold = curve([TP, [2.7, -1.6], [0.6, -4.4]])


def dist(x, y, line):
    d = np.full(x.shape, np.inf)
    for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
        vx, vy = bx - ax, by - ay
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.minimum(d, np.hypot(x - ax - t * vx, y - ay - t * vy))
    return d


x, y = np.meshgrid(np.linspace(-4.5, 7.5, 700), np.linspace(-5.2, 3.8, 520))
r = np.hypot(x - LOW[0], y - LOW[1])
p = 1012 - 30 * np.exp(-(r / 2.6) ** 2) + 2.0 * (0.25 * x - 1.0 * y)   # deep low in westerlies (higher pressure to the south)


def taper(line, x, y, L=2.2):
    """1 along a front, fading to 0 past its outer end so the trough (and the front) dies out."""
    e = line[-1]
    d_end = np.hypot(x - e[0], y - e[1])
    d_start = np.hypot(x - line[0][0], y - line[0][1])
    return np.clip(1 - np.maximum(0, L - d_end) / L * (d_start > d_end), 0, 1) * 0.65 + 0.35


trough = np.zeros_like(p)
for f, k in ((occ, 6.0), (warm, 5.0), (cold, 7.0)):
    trough = np.maximum(trough, k * (1.0 - np.minimum(dist(x, y, f), 1.0)) * taper(f, x, y))
p -= trough                                                  # V-shaped trough along every front -> kinked isobars

fig, ax = plt.subplots(figsize=(7.8, 5.6), dpi=100)
cs = ax.contour(x, y, p, levels=np.arange(940, 1040, 4), colors="#46506A", linewidths=1.0)
ax.clabel(cs, fmt="%d", fontsize=8, inline_spacing=2)
for line, col in ((occ, OCC), (warm, WARM), (cold, COLD)):
    ax.plot(line[:, 0], line[:, 1], color="white", lw=7, solid_capstyle="round")
    ax.plot(line[:, 0], line[:, 1], color=col, lw=4, solid_capstyle="round")
ax.plot(*TP, "o", ms=11, mfc="white", mec="#17202F", mew=2)
ax.plot(*LOW, "o", ms=26, mfc="white", mec="#B3122B", mew=2.5)
ax.text(*LOW, "L", ha="center", va="center", fontsize=16, fontweight="bold", color="#B3122B")
kw = dict(fontsize=12, bbox=dict(fc="white", ec="none", pad=1.5, alpha=.85))
ax.text(TP[0] + 0.3, TP[1] + 0.35, "triple point", color="#17202F", **kw)
ax.text(0.7, 1.75, "occluded", color=OCC, **kw)
ax.text(5.0, 0.55, "warm", color=WARM, **kw)
ax.text(0.2, -3.6, "cold", color=COLD, **kw)
ax.text(3.6, -2.4, "warm sector", color="#46506A", fontsize=12, style="italic")
ax.text(-3.6, -3.2, "cold air", color="#46506A", fontsize=12, style="italic")
ax.set_xlim(-4.5, 7.5)
ax.set_ylim(-5.2, 3.8)
ax.set_aspect("equal")
ax.axis("off")
fig.subplots_adjust(0, 0, 1, 1)
out = here / "guide_schematic.svg"
fig.savefig(out, format="svg", metadata={"Date": None})
print(out)
