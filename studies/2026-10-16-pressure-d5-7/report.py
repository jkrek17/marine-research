"""Write-up tables, CSVs and figures from the final score records (records_final.pkl, made by final.py with the
locked settings in results/final.json). Comparisons use rk.compare.paired (whole-week resampling).

    python3 report.py      -> results/*.csv, results/fig_*.png
"""
import os, sys, json, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import lib, summary as S, tune, method as M, bestguess as BG
from rk import compare, style

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
FIN = json.load(open(RES / "final.json"))
T = {int(k): v for k, v in FIN["T"].items()}
MODELS = ("gfs", "ifs", "aifs")
WINTER = ("10", "11", "12", "01", "02", "03")


def long_tables(recs):
    """lows: one row per analysed low x method; maps: one row per case x method (false lows).
    Methods: models, gmean, 'vote' (product threshold) and 'vote@<model>' (threshold matching that
    model's tuning false-low rate, from the curve in tune.py)."""
    Tm = {}
    for step in lib.STEPS:
        c = tune.curve(recs, step)
        o = np.argsort(c[:, 4])
        for m in MODELS:
            fa = S.stats([r for r in recs if r["sys"] == m and r["step"] == step and r["tune"]])["fa"]
            Tm[(step, m)] = float(np.interp(fa, c[o, 4], c[o, 0]))
    L, F = [], []
    for r in recs:
        if not (r["held"] or r["tune"]):
            continue
        key = dict(cycle=dt.datetime.strptime(r["ymd"], "%Y%m%d"), basin=r["dom"], step=r["step"],
                   split="held_out" if r["held"] else "tune", winter=r["ymd"][4:6] in WINTER)
        variants = [(r["sys"], r["rows"], r["fa"])]
        if r["sys"] == "vote":
            variants = []
            rows, fa = tune.rescore(r, T[r["step"]])
            variants.append(("vote", rows, fa))
            for m in MODELS:
                rows, fa = tune.rescore(r, Tm[(r["step"], m)])
                variants.append(("vote@" + m, rows, fa))
        for name, rows, fa in variants:
            F.append({**key, "method": name, "false_lows": fa})
            for i, (pos, dp, hit, p) in enumerate(rows):
                L.append({**key, "low": i, "method": name, "an_hpa": p, "pos_km": pos, "depth_abs_hpa": abs(dp),
                          "depth_err_hpa": dp, "hit300": float(hit)})
    return pd.DataFrame(L), pd.DataFrame(F), Tm


def comparisons(lows, maps):
    out = []
    for label, sel in (("held_out_all", lambda d: d.split == "held_out"),
                       ("held_out_winter", lambda d: (d.split == "held_out") & d.winter)):
        lw, mp = lows[sel(lows)], maps[sel(maps)]
        for deep in (False, True):
            l2 = lw[lw.an_hpa < 980] if deep else lw
            for m in MODELS + ("gmean",):
                for vname in ("vote", "vote@" + m if m in MODELS else None):
                    if vname is None:
                        continue
                    for val, df in (("pos_km", l2), ("depth_abs_hpa", l2), ("hit300", l2), ("false_lows", mp)):
                        if deep and val == "false_lows":
                            continue
                        cc = ["cycle", "basin", "step", "low"] if val != "false_lows" else ["cycle", "basin", "step"]
                        r = compare.paired(df[cc + ["method", val]], vname, m, val, by="step", case_cols=cc)
                        for x in r.itertuples():
                            base = df[(df.method == m) & (df.step == x.step)][val].mean()
                            out.append(dict(set=label, lows="deep<980" if deep else "all<1000", vote=vname, model=m,
                                            step=x.step, score=val, model_mean=base, vote_minus_model=x.mean,
                                            lo=x.lo, hi=x.hi, n=x.n_cases, weeks=x.n_weeks, significant=x.significant))
    return pd.DataFrame(out)


def fig_tradeoff(recs, maps, lows):
    style.use()
    import matplotlib.pyplot as plt
    sel = lambda r: r["held"] and r["ymd"][4:6] in WINTER
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True)
    rows = []
    for ax, step in zip(axs, lib.STEPS):
        c = tune.curve(recs, step, sel=sel)
        ax.plot(c[:, 4], c[:, 1], color=style.METHOD_COLORS["vote"], label=style.METHOD_LABELS["vote"])
        for t, x, y in zip(c[:, 0], c[:, 4], c[:, 1]):
            rows.append(dict(step=step, method="vote", keep_threshold=t, false_lows=x, pos_km=y))
        k = np.argmin(np.abs(c[:, 0] - T[step]))
        ax.plot(c[k, 4], c[k, 1], "o", ms=7, color=style.METHOD_COLORS["vote"])
        ax.annotate("best guess", (c[k, 4], c[k, 1]), xytext=(6, 6), textcoords="offset points", fontsize=8, color=style.INK2)
        for m in MODELS:
            mm = maps[(maps.method == m) & (maps.step == step) & (maps.split == "held_out") & maps.winter]
            ll = lows[(lows.method == m) & (lows.step == step) & (lows.split == "held_out") & lows.winter]
            ax.plot(mm.false_lows.mean(), ll.pos_km.mean(), "s", ms=8, color=style.METHOD_COLORS[m])
            ax.annotate(style.METHOD_LABELS[m], (mm.false_lows.mean(), ll.pos_km.mean()), xytext=(6, -10),
                        textcoords="offset points", fontsize=9, color=style.METHOD_COLORS[m])
            rows.append(dict(step=step, method=m, keep_threshold=np.nan, false_lows=mm.false_lows.mean(), pos_km=ll.pos_km.mean()))
        ax.set_xlabel("false lows per map")
        ax.set_title("+%d h" % step, loc="left", fontsize=10, color=style.INK2)
        ax.set_xlim(0, 4)
    axs[0].set_ylabel("position error, km (miss = 1000)")
    nruns = len({r["ymd"] for r in recs if sel(r)})
    fig.subplots_adjust(top=0.78, wspace=0.08)
    fig.text(0.125, 0.95, "At any number of false lows, the member vote places lows closer than each model", fontsize=12, color=style.INK)
    fig.text(0.125, 0.895, "Held-out winter runs (%d, 6 weeks) · both basins, 12 UTC · truth: GFS+IFS analysis lows below 1000 hPa" % nruns, fontsize=9, color=style.INK2)
    style.save(fig, RES / "fig_tradeoff.png")
    pd.DataFrame(rows).to_csv(RES / "fig_tradeoff.csv", index=False)


def confidence(lows, step):
    """chance (0-1) that an analysed low verifies within 300 km, from the logistic fit in final.json"""
    co = FIN["conf"]
    out = []
    for la, lo, p, sup, spr in lows:
        z = co["intercept"] + np.dot(co["coef"], [sup, np.log(max(spr, 20)), (step - 144) / 24, p - 1000])
        out.append(1 / (1 + np.exp(-z)))
    return np.array(out)


def fig_confidence(recs):
    style.use()
    import matplotlib.pyplot as plt
    co = FIN["conf"]
    X, y = [], []
    for r in recs:
        if r["sys"] != "vote" or not r["held"] or not len(r["lows"]):
            continue
        keep = r["lows"][:, 3] >= T[r["step"]]
        for l, v in zip(r["lows"][keep], r["ver"][keep]):
            z = co["intercept"] + np.dot(co["coef"], [l[3], np.log(max(l[4], 20)), (r["step"] - 144) / 24, l[2] - 1000])
            X.append(1 / (1 + np.exp(-z))); y.append(v[0] <= 300)
    X, y = np.array(X), np.array(y)
    edges = np.array([0, .2, .4, .6, .8, 1.0001])
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (X >= a) & (X < b)
        if m.sum():
            rows.append(dict(bin_lo=a, bin_hi=min(b, 1), stated=X[m].mean(), verified=y[m].mean(), n=int(m.sum())))
    d = pd.DataFrame(rows)
    d.to_csv(RES / "fig_confidence.csv", index=False)
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.plot([0, 1], [0, 1], color=style.SPINE, lw=1)
    ax.plot(d.stated, d.verified, "o-", color=style.METHOD_COLORS["vote"])
    for x in d.itertuples():
        ax.annotate("%d" % x.n, (x.stated, x.verified), xytext=(5, -10), textcoords="offset points", fontsize=8, color=style.INK2)
    ax.set_xlabel("stated chance the low is real"); ax.set_ylabel("share with an analysed low within 300 km")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    style.title(ax, "The confidence score means what it says", "%d held-out lows, all weeks, both basins, +120-168 h" % len(y))
    style.save(fig, RES / "fig_confidence.png")


def fig_example(ymd="20251208", dom="natl", step=144):
    """one held-out case: analysis, best guess, ECMWF"""
    style.use()
    import matplotlib.pyplot as plt
    P = dict(FIN["P"], T=T[step])
    c = M.case(ymd, dom, step, lag=False)
    valid = dt.datetime.strptime(ymd, "%Y%m%d") + dt.timedelta(hours=12 + step)
    an = M.analysis(valid.strftime("%Y%m%d"), dom)
    bg, lows = BG.best_guess(c, dom, P)
    conf = confidence(lows, step)
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.6))
    lat, lon = lib.LAT[dom], lib.LON[dom]
    lev = np.arange(940, 1048, 4)
    for ax, (name, f, col) in zip(axs, (("Analysis (truth)", an, style.METHOD_COLORS["analysis"]),
                                        ("Best guess (member vote)", bg, style.METHOD_COLORS["vote"]),
                                        ("ECMWF", c["det"]["ifs"], style.METHOD_COLORS["ifs"]))):
        style.map_axes(dom, ax=ax)
        cs = ax.contour(lon, lat, f, levels=lev, colors=col, linewidths=0.9, zorder=4)
        ax.clabel(cs, fmt="%d", fontsize=6)
        for la, lo, p in lib.analysed_lows(an, dom):
            ax.plot(lo, la, "x", color=style.INK, ms=7, mew=1.5, zorder=6)
        ax.set_title(name, loc="left", fontsize=10, color=style.INK2)
    for (la, lo, p, sup, spr), cf in zip(lows, conf):
        strong = sup >= BG.SHAPE_MIN
        axs[1].plot(lo, la, "o" if strong else "o", ms=5 if strong else 4, mfc=style.METHOD_COLORS["vote"] if strong else "none",
                    mec=style.METHOD_COLORS["vote"], zorder=7)
        axs[1].annotate("%d %d%%" % (round(p), round(100 * cf)), (lo, la), xytext=(4, 4), textcoords="offset points",
                        fontsize=7.5, color=style.INK if strong else style.INK2, zorder=7)
    fig.subplots_adjust(top=0.80)
    fig.text(0.125, 0.95, "Example: run of %s, +%d h, valid %s (held-out week)" % (dt.datetime.strptime(ymd, "%Y%m%d").strftime("%d %b %Y 12 UTC"), step, valid.strftime("%d %b %Y 12 UTC")), fontsize=12, color=style.INK)
    fig.text(0.125, 0.905, "x = analysed lows below 1000 hPa. Best guess labels: central pressure and confidence; open circles are lows below %d%% member support, marked but not drawn into the isobars." % round(100 * BG.SHAPE_MIN), fontsize=9, color=style.INK2)
    style.save(fig, RES / "fig_example.png")


def equal_false_lows_check(recs, lows, maps):
    """Check only, not a tuned setting: the vote's threshold is set ON THE HELD-OUT WEEKS so it draws exactly as
    many false lows per map as each model there, removing 'more lows drawn' as an explanation."""
    rows = []
    for label, sel in (("held_out_all", lambda r: r["held"]), ("held_out_winter", lambda r: r["held"] and r["ymd"][4:6] in WINTER)):
        for step in lib.STEPS:
            c = tune.curve(recs, step, sel=sel)
            o = np.argsort(c[:, 4])
            for m in MODELS:
                mm = [r for r in recs if r["sys"] == m and r["step"] == step and sel(r)]
                fa = np.mean([r["fa"] for r in mm])
                t = float(np.interp(fa, c[o, 4], c[o, 0]))
                L = []
                for r in recs:
                    if r["sys"] != "vote" or r["step"] != step or not sel(r):
                        continue
                    key = dict(cycle=dt.datetime.strptime(r["ymd"], "%Y%m%d"), basin=r["dom"], step=step)
                    vr, vfa = tune.rescore(r, t)
                    mr = next(x for x in mm if x["ymd"] == r["ymd"] and x["dom"] == r["dom"])
                    for i, ((p1, d1, h1, _), (p2, d2, h2, _)) in enumerate(zip(vr, mr["rows"])):
                        L += [{**key, "low": i, "method": "vote", "pos_km": p1, "depth_abs_hpa": abs(d1)},
                              {**key, "low": i, "method": m, "pos_km": p2, "depth_abs_hpa": abs(d2)}]
                    L += [{**key, "low": -1, "method": "vote", "fa": vfa}, {**key, "low": -1, "method": m, "fa": mr["fa"]}]
                df = pd.DataFrame(L)
                for val in ("pos_km", "depth_abs_hpa"):
                    d = df[df.low >= 0][["cycle", "basin", "step", "low", "method", val]]
                    x = compare.paired(d, "vote", m, val, case_cols=["cycle", "basin", "step", "low"]).iloc[0]
                    rows.append(dict(set=label, step=step, model=m, keep_threshold=t, score=val,
                                     model_mean=d[d.method == m][val].mean(), vote_minus_model=x["mean"], lo=x["lo"], hi=x["hi"],
                                     significant=x["significant"], model_false=fa,
                                     vote_false=df[(df.low < 0) & (df.method == "vote")].fa.mean()))
    pd.DataFrame(rows).to_csv(RES / "equal_false_lows_heldout_check.csv", index=False)


if __name__ == "__main__":
    recs = S.load("final")
    lows, maps, Tm = long_tables(recs)
    lows[lows.split == "held_out"].to_csv(RES / "lows_heldout.csv", index=False)
    maps[maps.split == "held_out"].to_csv(RES / "maps_heldout.csv", index=False)
    comp = comparisons(lows, maps)
    comp.to_csv(RES / "comparisons.csv", index=False)
    json.dump({"%d|%s" % k: v for k, v in Tm.items()}, open(RES / "thresholds_equal_false_lows.json", "w"), indent=1)
    equal_false_lows_check(recs, lows, maps)
    fig_tradeoff(recs, maps, lows)
    fig_confidence(recs)
    fig_example(*(sys.argv[1:4] if len(sys.argv) > 3 else ()))
    print(comp[(comp.set == "held_out_winter") & (comp.lows == "all<1000")].round(2).to_string())
