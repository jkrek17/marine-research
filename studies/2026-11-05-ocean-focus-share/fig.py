import sys, pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
src, tag, boxes, out = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4]
d = pd.read_csv(src)
LAY = [("focus_union", "Everything flagged (union)", "#111827"),
       ("gale_line", "Gale warning area", "#fbbf24"), ("models_split", "Models split", "#2563eb"),
       ("storm_up_union", "Storm or HF in play (union)", "#7c2d12"),
       ("storm_line", "Storm warning area", "#f97316"), ("core35", "Core likelihood 35%+", "#dc2626"),
       ("hf_line", "HF warning area", "#e879f9")]
NAME = {"natl": "Atlantic", "npac": "Pacific", "natl_core": "Atlantic 30-67N", "npac_core": "Pacific 30-67N"}
fig, axs = plt.subplots(1, len(boxes), figsize=(6.2 * len(boxes), 4.6), sharey=False, facecolor="white")
for ax, b in zip(np.atleast_1d(axs), boxes):
    for i, (k, lab, col) in enumerate(LAY):
        s = d[(d.basin == b) & (d.layer == k)]
        if s.empty: continue
        g = s.groupby("step").share
        x = np.array(sorted(s.step.unique())) + (i - 3) * 1.4
        med, lo, hi = 100 * g.median(), 100 * g.quantile(0.1), 100 * g.quantile(0.9)
        ax.vlines(x, lo.values, hi.values, color=col, lw=5, alpha=0.45)
        ax.plot(x, med.values, "o-", color=col, lw=1.6, ms=5, label=lab)
    ax.set_title(NAME[b] + (sys.argv[5] if len(sys.argv) > 5 else ""), fontsize=12); ax.set_xticks([24, 48, 72, 96, 120])
    ax.set_xticklabels(["+24", "+48", "+72", "+96", "+120"]); ax.set_xlabel("forecast hour")
    ax.grid(alpha=0.3); ax.set_ylim(0, None); ax.set_ylabel("% of open water")
np.atleast_1d(axs)[0].set_ylabel("% of open water")
np.atleast_1d(axs)[0].legend(fontsize=8.5, loc="upper left", frameon=True)
fig.suptitle("How much of the ocean is flagged: %s (dot = typical run, bar = 1 in 10 to 9 in 10 runs)" % tag, fontsize=11)
fig.tight_layout(); fig.savefig(out, dpi=110)
