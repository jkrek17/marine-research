"""fig1: drill score per test case, agent vs TFP and persistence. fig2: four test cases, agent fronts over the analysed ones.
  python3 figures.py
"""
import io
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
import deck  # noqa: E402
import panels  # noqa: E402
from rk import style  # noqa: E402

HERE = common.HERE
COL = {"cold": "#1565c0", "warm": "#d32f2f", "occluded": "#7b1fa2"}


def fig1():
    style.use()
    a, t, p = (pd.read_csv(HERE / f"{m}_test.csv").set_index("id") for m in ("agent", "tfp", "persist"))
    order = a.sort_values("pct").index
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(order))
    ax.scatter(x, t.loc[order, "pct"], s=18, color="#9a9a94", label=f"Thermal front parameter (mean {t.pct.mean():.0f})")
    ax.scatter(x, p.loc[order, "pct"], s=18, marker="s", facecolor="none", edgecolor="#0e7c86", label=f"Analysis 6 h earlier, moved with the low (mean {p.pct.mean():.0f})")
    ax.scatter(x, a.loc[order, "pct"], s=26, color="#7a1f2b", label=f"Claude agent, blind (mean {a.pct.mean():.0f})", zorder=3)
    ax.set_xticks([])
    ax.set_xlabel("50 held-out drill cases, sorted by the agent's score")
    ax.set_ylabel("Front drill score (%)")
    ax.set_ylim(-3, 103)
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    style.title(ax, "The agent beats the objective front finder by 16 points and ties the previous analysis",
                "Scored by the front drill's own scorer against the Unified Surface Analysis (CODSUS)")
    style.save(fig, HERE / "fig1_scores.png")


def fig2(ids):
    man = deck.manifest()
    by = {c["id"]: c for c in man["cases"]}
    ans = json.loads((HERE / "agent_answers.json").read_text())
    sc = pd.read_csv(HERE / "agent_test.csv").set_index("id")
    fig, axs = plt.subplots(2, 2, figsize=(13, 8.8))
    for ax, i in zip(axs.ravel(), ids):
        c = by[i]
        img = plt.imread(io.BytesIO(panels.draw(c, "te850", man=man)))
        F = deck.fields(c, man)
        x0, x1 = F["lon"][0] - 0.25, F["lon"][-1] + 0.25
        y0, y1 = F["lat"][-1] - 0.25, F["lat"][0] + 0.25
        H, W = img.shape[:2]
        tx = lambda la, lo: ((0.06 + 0.92 * (np.asarray(lo) % 360 - x0) / (x1 - x0)) * W, (1 - (0.07 + 0.86 * (np.asarray(la) - y0) / (y1 - y0))) * H)
        ax.imshow(img)
        for f in deck.system_fronts(c):
            p = np.array(f["pts"])
            ax.plot(*tx(p[:, 0], p[:, 1]), color=COL[f["type"]], lw=7, alpha=0.35, solid_capstyle="round")
        for f in ans[i]["fronts"]:
            p = np.array(f["pts"])
            ax.plot(*tx(p[:, 0], p[:, 1]), color=COL[f["type"]], lw=1.8, dashes=(5, 2))
        ax.set_title(f"{i} ({'N Atl' if c['basin'] == 'natl' else 'N Pac'}): agent {sc.loc[i, 'pct']:.0f}%", fontsize=10, loc="left")
        ax.axis("off")
    fig.suptitle("Agent fronts (dashed) over the analysed fronts (wide, pale): blue cold, red warm, purple occluded", fontsize=11, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(HERE / "fig2_cases.png", dpi=72)


if __name__ == "__main__":
    fig1()
    a = pd.read_csv(HERE / "agent_test.csv").sort_values("pct")
    pick = [a.iloc[-1].id, a.iloc[len(a) // 2 + 5].id, a.iloc[len(a) // 2 - 5].id, a.iloc[0].id]
    fig2(pick)
    print("figures", pick)
