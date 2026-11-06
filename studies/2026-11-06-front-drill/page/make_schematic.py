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
    """Distance to a polyline and the fraction along it (0 at its first point, 1 at its last) of the nearest point."""
    seg = np.hypot(*np.diff(line, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    d = np.full(x.shape, np.inf)
    s = np.zeros(x.shape)
    for i, ((ax, ay), (bx, by)) in enumerate(zip(line[:-1], line[1:])):
        vx, vy = bx - ax, by - ay
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        di = np.hypot(x - ax - t * vx, y - ay - t * vy)
        m = di < d
        d = np.where(m, di, d)
        s = np.where(m, cum[i] + t * (cum[i + 1] - cum[i]), s)
    return d, s


x, y = np.meshgrid(np.linspace(-4.5, 7.5, 700), np.linspace(-5.2, 3.8, 520))
r = np.hypot(x - LOW[0], y - LOW[1])
p = 1012 - 30 * np.exp(-(r / 2.6) ** 2) + 2.0 * (0.25 * x - 1.0 * y)   # deep low in westerlies (higher pressure to the south)

# Each front is a trough: a V-shaped dip (sharp at the front, fading smoothly away from it) that weakens over the
# outer 40% of the front, so the isobars kink at the front and straighten again past its end.
W = 0.7
for f, k, fade in ((occ, 6.0, False), (warm, 7.0, True), (cold, 8.0, True)):
    d, s = dist(x, y, f)
    w = np.where(s < 0.6, 1.0, 0.5 + 0.5 * np.cos(np.pi * np.clip((s - 0.6) / 0.4, 0, 1))) if fade else 1.0
    p -= k * W * np.exp(-d / W) * w

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
