"""Story figures for the companion PDF (figures-and-cases): part 1, the scoring figures (1-8), then the storm storyboards.

Every plotted number comes from results/*.csv (plus findings.md for the 119 km lower edge of the analysis floor and the
72-88% coverage band, which findings.md states). The storyboard data (tracks by lead) come from the MSLP-only extract
files and the Part B vote files, and are written to results/story_tracks.csv and results/story_false_deep.csv.
Outputs: figs/story/*.png (each under 1 MB). Usage: python3 make_story_figs.py [scores|cases|all]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = HERE / "results"
OUTD = HERE / "figs" / "story"
OUTD.mkdir(parents=True, exist_ok=True)
CREAM, NAVY, OX, SAND, MID, GOLD = "#F6F0E1", "#16294D", "#6B1D2A", "#E8DFC8", "#6F7A93", "#B08A3C"
LEADS = (24, 48, 72, 96, 120, 144, 168)
DAYS = [l / 24 for l in LEADS]
FLOOR_LO, FLOOR_HI = 119.0, 130.0      # km: GFS vs IFS analysis low-position difference (findings.md: 119-130; noise_floor.csv 130)

# ------------------------------------------------------------------ data
R2 = pd.read_csv(RES / "by_lead_raw2.csv")
R2 = R2[(R2.truth == "mean") & (R2.basin == "all")].set_index(["entry", "lead"])
BL = pd.read_csv(RES / "by_lead.csv")
BL = BL[(BL.truth == "mean") & (BL.basin == "all")].set_index(["entry", "lead"])
NF = pd.read_csv(RES / "noise_floor.csv")
assert abs(float(NF[NF.lead == 24].pos_km.iloc[0]) - FLOOR_HI) < 1.0


def r2(e, col):
    return [float(R2.loc[(e, l), col]) for l in LEADS]


def bl(e, col, leads=LEADS):
    return [float(BL.loc[(e, l), col]) for l in leads]


NAMES = {"ifs": "ECMWF", "gfs": "GFS", "aifs": "AIFS", "m_gi": "GFS+ECMWF mean", "m_gif": "GFS+ECMWF+AIFS mean", "ens": "ECMWF ens. mean",
         "gefs": "GEFS mean", "al": "Aligned blend, all runs", "ald": "Aligned blend + depth fix", "od": "Outlier-drop blend", "vote": "Member vote (12Z)"}
STY = {"ifs": dict(color=NAVY, lw=2.0), "gfs": dict(color=MID, lw=1.5, ls="--"), "aifs": dict(color=GOLD, lw=1.3), "m_gi": dict(color=OX, lw=2.0),
       "m_gif": dict(color="#A5555F", lw=1.4, ls="-."), "ens": dict(color="#8E8A78", lw=1.2, ls=":"), "gefs": dict(color="#B7B3A0", lw=1.2, ls=":"),
       "al": dict(color="#C58D93", lw=1.3), "ald": dict(color="#C58D93", lw=1.3, ls="--"), "od": dict(color="#7D6A4A", lw=1.2)}


def setup():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8.2, "axes.titleweight": "bold", "axes.titlecolor": NAVY,
                         "axes.labelcolor": NAVY, "xtick.color": NAVY, "ytick.color": NAVY, "text.color": NAVY})


def ax_style(a, xlab="forecast day", grid=True):
    a.set_facecolor("#FBF8EF")
    for s in ("top", "right"):
        a.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        a.spines[s].set_color(NAVY)
    if grid:
        a.grid(axis="y", color=SAND, lw=0.6)
    if xlab:
        a.set_xlabel(xlab, fontsize=7.5)


def newfig(w, h, nr=1, nc=1, **kw):
    fig, axs = plt.subplots(nr, nc, figsize=(w, h), dpi=200, **kw)
    fig.patch.set_facecolor(CREAM)
    for a in np.atleast_1d(axs).ravel():
        ax_style(a)
    return fig, axs


def save(fig, name):
    p = OUTD / name
    fig.tight_layout(pad=0.7)
    fig.savefig(p, facecolor=CREAM)
    plt.close(fig)
    assert p.stat().st_size < 1_000_000, name
    return p


# ------------------------------------------------------------------ 1 who puts the lows best
def fig1():
    fig, (a, b) = newfig(7.3, 2.7, 1, 2, gridspec_kw=dict(width_ratios=[1.25, 1]))
    for e in ("ifs", "gfs", "aifs", "m_gi", "ens", "gefs"):
        a.plot(DAYS, r2(e, "pos_km"), label=NAMES[e], **STY[e])
    V = BL.xs("vote", level="entry")
    a.plot([5, 6, 7], [V.loc[l, "pos_km"] for l in (120, 144, 168)], color=OX, marker="D", ms=5, lw=0, label="Member vote (12Z, days 5-7)")
    a.axhspan(FLOOR_LO, FLOOR_HI, color=GOLD, alpha=0.35, lw=0)
    a.text(1.05, FLOOR_HI + 12, "analyses disagree by 119-130 km", fontsize=6.3, color="#7D6A4A")
    a.set_ylabel("mean low position error, km")
    a.set_title("Mean error (a missed low counts 1000 km)", loc="left")
    a.legend(frameon=False, fontsize=6.0, loc="upper left", bbox_to_anchor=(0.0, 0.93))
    for e in ("ifs", "gfs", "aifs", "m_gi", "ens", "gefs"):
        b.plot(DAYS, r2(e, "pos_median_km"), **STY[e])
    b.plot([5, 6, 7], [V.loc[l, "pos_median_km"] for l in (120, 144, 168)], color=OX, marker="D", ms=5, lw=0)
    med = float(NF[NF.lead == 24].pos_median_km.iloc[0])
    b.axhline(med, color=GOLD, lw=1.4)
    b.text(1.05, med + 12, "analyses disagree by %d km (median)" % round(med), fontsize=6.3, color="#7D6A4A")
    b.set_title("Typical low (median error)", loc="left")
    for x in (a, b):
        x.set_xticks(range(1, 8))
    return save(fig, "s1_position_by_day.png")


# ------------------------------------------------------------------ 2 field vs placement
def fig2():
    fig, axs = newfig(7.3, 2.6, 1, 4, sharey=False)
    ents = ("ifs", "gfs", "aifs", "m_gi", "m_gif", "ens", "gefs", "al", "od")
    for a, L in zip(axs, (24, 72, 120, 168)):
        for e in ents:
            x, y = R2.loc[(e, L), "rmse"], R2.loc[(e, L), "pos_km"]
            blend = e in ("m_gi", "m_gif", "al", "od")
            a.scatter(x, y, s=34, color=OX if blend else NAVY, marker="D" if blend else "o", zorder=3, edgecolor="none")
            lab = {"ifs": "E", "gfs": "G", "aifs": "AI", "m_gi": "G+E", "m_gif": "G+E+AI", "ens": "ENS", "gefs": "GEFS", "al": "aligned", "od": "drop"}[e]
            a.annotate(lab, (x, y), textcoords="offset points", xytext=(4, 3), fontsize=5.8, color=NAVY)
        a.margins(x=0.18, y=0.1)
        a.set_title("Day %d" % (L // 24), loc="left")
        a.set_xlabel("field error (RMSE), hPa", fontsize=7)
        a.grid(axis="x", color=SAND, lw=0.5)
    axs[0].set_ylabel("position error, km")
    return save(fig, "s2_field_vs_position.png")


# ------------------------------------------------------------------ 3 why blends look smooth
def fig3():
    fig, (a, b) = newfig(7.3, 2.5, 1, 2)
    for e in ("ifs", "m_gi", "m_gif", "al", "ald"):
        a.plot(DAYS, bl(e, "sharp"), label=NAMES[e], **STY[e])
        b.plot(DAYS, bl(e, "strong_bias"), **STY[e])
    a.axhline(1.0, color=MID, lw=0.8)
    a.set_ylabel("sharpness (1 = as sharp as analysis)")
    a.set_title("Blends are smoother", loc="left")
    a.legend(frameon=False, fontsize=6.0, loc="lower left")
    b.axhline(0, color=MID, lw=0.8)
    b.set_ylabel("too shallow, hPa (analysed lows < 980)")
    b.set_title("and shallower on strong lows", loc="left")
    for x in (a, b):
        x.set_xticks(range(1, 8))
    return save(fig, "s3_smooth_blends.png")


# ------------------------------------------------------------------ 4 too shallow or too deep
def fig4():
    fig, axs = newfig(7.3, 2.5, 1, 4, sharey=True)
    for a, e in zip(axs, ("ifs", "gfs", "m_gi", "m_gif")):
        a.plot(DAYS, bl(e, "strong_bias"), color=OX, lw=2.0, label="analysed lows < 980")
        a.plot(DAYS, bl(e, "fdeep_bias"), color=NAVY, lw=2.0, ls="--", label="forecast lows < 980")
        a.axhline(0, color=MID, lw=0.8)
        a.set_title(NAMES[e], loc="left")
        a.set_xticks(range(1, 8))
        a.fill_between(DAYS, bl(e, "strong_bias"), bl(e, "fdeep_bias"), color=SAND, alpha=0.6, lw=0)
    axs[0].set_ylabel("forecast minus analysed, hPa\n(+ = too shallow, - = too deep)")
    axs[0].legend(frameon=False, fontsize=5.8, loc="lower left")
    return save(fig, "s4_shallow_or_deep.png")


# ------------------------------------------------------------------ 5 warp
def fig5():
    W = pd.read_csv(RES / "warp_effect.csv")
    W = W[~W.over_water_only]
    fig, (a, b) = newfig(7.3, 2.4, 1, 2, sharey=True)
    for ax, (m, r, t) in zip((a, b), (("al_gi", "m_gi", "Two runs (GFS, ECMWF)"), ("al_det", "m_gif", "Det. runs (GFS, ECMWF, AIFS)"))):
        w = W[(W.method == m) & (W.reference == r)].set_index("lead")
        ax.bar(DAYS, [w.loc[l, "dpos_km"] for l in LEADS], width=0.6, color=OX,
               yerr=[[w.loc[l, "dpos_km"] - w.loc[l, "lo"] for l in LEADS], [w.loc[l, "hi"] - w.loc[l, "dpos_km"] for l in LEADS]], error_kw=dict(ecolor=NAVY, lw=0.9, capsize=2))
        ax.axhline(0, color=NAVY, lw=0.8)
        ax.axhspan(-5, 5, color=GOLD, alpha=0.25, lw=0)
        ax.set_title(t, loc="left")
        ax.set_xticks(range(1, 8))
    a.set_ylabel("position change from moving lows, km\n(- = closer)")
    return save(fig, "s5_warp_effect.png"), W


# ------------------------------------------------------------------ 6 outlier habit
def fig6():
    O = pd.read_csv(RES / "outlier_risk.csv")
    O = O[(O.cand == "od") & (O.setting == "X=300")]
    allr = O[(O.basin == "all") & (O.model == "all")].set_index("lead")
    fig, (a, b) = newfig(7.3, 2.6, 1, 2)
    m = O[(O.model != "all") & (O.basin != "all")].copy()
    m["w"] = m.n_dropped * m.share_closest
    g = m.groupby(["model", "lead"]).agg(w=("w", "sum"), n=("n_dropped", "sum")).reset_index()
    g["share"] = g.w / g.n
    cols = {"ifs": NAVY, "gfs": MID, "aifs": GOLD, "aigfs": "#8E8A78"}
    lab = {"ifs": "ECMWF dropped", "gfs": "GFS dropped", "aifs": "AIFS dropped", "aigfs": "AI-GFS dropped"}
    for mm in ("ifs", "gfs", "aifs", "aigfs"):
        s = g[g.model == mm].set_index("lead")
        ls = [l for l in LEADS if l in s.index and s.loc[l, "n"] >= 20]
        a.plot([l / 24 for l in ls], [100 * s.loc[l, "share"] for l in ls], color=cols[mm], lw=1.2, marker="o", ms=3, label=lab[mm])
    a.plot(DAYS, [100 * allr.loc[l, "share_closest"] for l in LEADS], color=OX, lw=2.4, label="All dropped runs")
    a.set_ylim(0, max(30, a.get_ylim()[1]))
    a.set_ylabel("% of drops where the dropped run was closest")
    a.set_title("Dropping is usually right", loc="left")
    a.legend(frameon=False, fontsize=5.8, loc="upper left", ncol=2)
    x = np.arange(len(LEADS))
    b.bar(x - 0.2, [allr.loc[l, "drop_err_km"] for l in LEADS], width=0.4, color=OX, label="dropped run's low")
    b.bar(x + 0.2, [allr.loc[l, "best_other_km"] for l in LEADS], width=0.4, color=NAVY, label="best other run's low")
    b.set_xticks(x)
    b.set_xticklabels([str(int(l / 24)) for l in LEADS])
    b.set_ylabel("km from the analysed low")
    b.set_title("...because it is usually far off", loc="left")
    b.legend(frameon=False, fontsize=6.0, loc="upper left")
    return save(fig, "s6_outlier_habit.png"), allr, g


# ------------------------------------------------------------------ 7 how many lows
def fig7():
    fig, (a, b) = newfig(7.3, 2.6, 1, 2)
    for e in ("ifs", "gfs", "aifs", "m_gi", "m_gif", "ens", "gefs"):
        a.plot(DAYS, bl(e, "fc_lows_per_map"), label=NAMES[e], **STY[e])
        b.plot(DAYS, bl(e, "false_per_map"), **STY[e])
    nl = [float(BL.loc[("ifs", l), "n_lows"]) / float(BL.loc[("ifs", l), "n_cases"]) for l in LEADS]
    a.plot(DAYS, nl, color="black", lw=1.0, ls=(0, (1, 1)), label="Analysed lows (< 1000)")
    a.set_ylabel("lows per map (forecast < 1010)")
    a.set_title("ECMWF draws the most lows", loc="left")
    a.set_ylim(1, 7.6)
    a.legend(frameon=False, fontsize=5.8, loc="upper center", ncol=2)
    b.set_ylabel("false lows per map")
    b.set_title("...and most of the false ones", loc="left")
    for x in (a, b):
        x.set_xticks(range(1, 8))
    return save(fig, "s7_lows_per_map.png"), nl


# ------------------------------------------------------------------ 8 probability
def fig8():
    REL = pd.read_csv(RES / "partb_reliability.csv")
    REL = REL[(REL["product"] == "exist") & (REL.basin == "both")]
    CIRC = pd.read_csv(RES / "partb_circles.csv")
    CIRC = CIRC[(CIRC.subset == "winter") & (CIRC.truth == "mean") & (CIRC.basin == "both")].set_index("lead")
    RNG = pd.read_csv(RES / "partb_range.csv")
    RNG = RNG[(RNG.subset == "winter") & (RNG.truth == "mean") & (RNG.basin == "both") & (RNG.direction == "forecast_low")].set_index("lead")
    ALT = pd.read_csv(RES / "partb_alt.csv")
    ALT = ALT[(ALT.subset == "winter") & (ALT.truth == "mean") & (ALT.basin == "both") & (ALT.kind == "pos")].set_index("lead")
    fig, axs = newfig(7.3, 5.0, 2, 2)
    a, b, c, d = axs.ravel()
    # reliability: day 5 winter and year, plus days 6, 7 winter
    a.plot([0, 1], [0, 1], color=MID, lw=0.8)
    for (sub, L, col, mk, lab) in (("winter", 120, OX, "o", "winter day 5"), ("year", 120, NAVY, "s", "whole year day 5"), ("winter", 168, GOLD, "^", "winter day 7")):
        r = REL[(REL.subset == sub) & (REL.lead == L) & (REL.n > 0) & REL.freq.notna()]
        a.plot(r.mean_p, r.freq, color=col, marker=mk, ms=4, lw=1.2, label=lab)
        if (sub, L) in (("winter", 120), ("year", 120)):
            for _, q in r.iterrows():
                a.annotate("%d/%d" % (q.events, q.n), (q.mean_p, q.freq), textcoords="offset points", xytext=(3, -8 if sub == "year" else 4), fontsize=5.0, color=col)
    a.set_xlabel("stated chance the low exists")
    a.set_ylabel("how often a low was there")
    a.set_xlim(0, 1)
    a.set_ylim(0, 1)
    a.set_title("Chance it exists (labels: events/lows)", loc="left")
    a.legend(frameon=False, fontsize=5.8, loc="lower right")
    # range coverage
    ls = (120, 144, 168)
    b.axhspan(72, 88, color=GOLD, alpha=0.3, lw=0)
    b.bar(range(3), [100 * RNG.loc[l, "cov80"] for l in ls], width=0.5, color=OX,
          yerr=[[100 * (RNG.loc[l, "cov80"] - RNG.loc[l, "cov80_lo"]) for l in ls], [100 * (RNG.loc[l, "cov80_hi"] - RNG.loc[l, "cov80"]) for l in ls]], error_kw=dict(ecolor=NAVY, lw=0.9, capsize=2))
    b.set_xticks(range(3))
    b.set_xticklabels(["day 5", "day 6", "day 7"])
    b.set_ylim(50, 100)
    b.set_ylabel("% of analysed depths inside the 10-90% range")
    b.set_title("Depth range holds (band = 72-88%)", loc="left")
    b.set_xlabel("")
    # circles by tercile
    w = 0.12
    for j, (t, col) in enumerate((("terc0", "#C58D93"), ("terc1", OX), ("terc2", NAVY))):
        for k, (rr, hatch) in enumerate((("r50", None), ("r80", "//"))):
            xs = np.arange(3) + (j * 2 + k - 2.5) * w
            c.bar(xs, [CIRC.loc[l, "%s_%s" % (t, rr)] for l in ls], width=w, color=col, hatch=hatch, edgecolor=CREAM, lw=0.3)
    c.set_xticks(range(3))
    c.set_xticklabels(["day 5", "day 6", "day 7"])
    c.set_ylim(0, 1150)
    c.set_ylabel("circle radius, km")
    c.set_title("Circles shrink when members agree", loc="left")
    c.set_xlabel("")
    from matplotlib.patches import Patch
    c.legend(handles=[Patch(color="#C58D93", label="few members carry it"), Patch(color=OX, label="middle"), Patch(color=NAVY, label="most members carry it"),
                      Patch(facecolor="white", edgecolor=NAVY, label="solid = 50%, hatched = 80%", hatch="//")], frameon=False, fontsize=5.6, loc="upper left", ncol=2)
    # alternatives
    d.bar(np.arange(3) - 0.18, [100 * ALT.loc[l, "verified"] for l in ls], width=0.34, color=OX, label="alternative was right")
    d.bar(np.arange(3) + 0.18, [100 * ALT.loc[l, "placebo"] for l in ls], width=0.34, color=NAVY, label="chance alone")
    d.set_xticks(range(3))
    d.set_xticklabels(["day 5", "day 6", "day 7"])
    d.set_ylabel("% of alternative lows verified")
    d.set_title("Alternative scenarios beat chance", loc="left")
    d.set_xlabel("")
    d.legend(frameon=False, fontsize=6, loc="upper right")
    return save(fig, "s8_probability.png"), REL, CIRC, RNG, ALT


def scores():
    setup()
    out = {"1": fig1(), "2": fig2(), "3": fig3(), "4": fig4()}
    out["5"] = fig5()
    out["6"] = fig6()
    out["7"] = fig7()
    out["8"] = fig8()
    print({k: v[0] if isinstance(v, tuple) else v for k, v in out.items()})


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("scores", "all"):
        scores()
    if what in ("cases", "all"):
        import story_cases
        story_cases.main()
