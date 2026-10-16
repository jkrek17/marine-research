"""Final score. Settings P are fixed from tuning; the keep-threshold T per lead is set on tuning cases so
the vote's false-low rate equals the LOWEST of the three models' (AIFS in practice), so it never wins by
drawing more lows. Then on held-out weeks: vote vs GFS, IFS, AIFS on position error (miss = 1000 km),
depth MAE, hits within 300 km and false lows, all lows and deep (< 980 hPa) lows, per lead and basin,
with 95% intervals from resampling whole weeks. Confidence: logistic fit on tuning lows of
P(analysed low within 300 km) from support, spread and lead; reliability on held-out lows.

Run: python3 final.py '<json P>'   -> results/final.md, results/final.json
"""
import sys, json, os
import numpy as np
from sklearn.linear_model import LogisticRegression
import evaluate as E, summary as S, tune, lib

import lib
OUT = lib.RECORDS
rng = np.random.default_rng(0)


def per_case(recs, sysname, step, sel, T=None):
    """list of (week, dom, rows, fa) for one system"""
    out = []
    for r in recs:
        if r["sys"] != sysname or r["step"] != step or not sel(r):
            continue
        if T is None:
            rows, fa = r["rows"], r["fa"]
        else:
            rows, fa = tune.rescore(r, T)
        wk = tuple(__import__("datetime").datetime.strptime(r["ymd"], "%Y%m%d").isocalendar()[:2])
        out.append((wk, r["dom"], r["ymd"], rows, fa))
    return out


def metrics(cases, deep=False):
    R = [c[3] for c in cases if len(c[3])]
    R = np.concatenate(R) if R else np.zeros((0, 4))
    if deep:
        R = R[R[:, 3] < 980]
    return np.array([R[:, 0].mean(), np.nanmean(np.abs(R[:, 1])), R[:, 2].mean(),
                     sum(c[4] for c in cases) / max(len(cases), 1), len(R)])


def paired(a, b, deep=False, n=2000):
    """vote minus model, resampling weeks; cases matched by (ymd, dom)."""
    kb = {(c[2], c[1]): c for c in b}
    pairs = [(x, kb[(x[2], x[1])]) for x in a if (x[2], x[1]) in kb]
    weeks = sorted({p[0][0] for p in pairs})
    byw = {w: [p for p in pairs if p[0][0] == w] for w in weeks}
    d0 = metrics([p[0] for p in pairs], deep)[:4] - metrics([p[1] for p in pairs], deep)[:4]
    boot = []
    for _ in range(n):
        ws = [weeks[i] for i in rng.integers(0, len(weeks), len(weeks))]
        ps = [p for w in ws for p in byw[w]]
        boot.append(metrics([p[0] for p in ps], deep)[:4] - metrics([p[1] for p in ps], deep)[:4])
    lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
    return d0, lo, hi, len(weeks), len(pairs)


def main(P):
    cyc = E.cycles()
    P = dict(E.DEFAULT, **P, T=0.08)
    tag = "final_dry" if os.environ.get("DRY") else "final"
    if os.environ.get("REUSE"):
        recs = S.load(tag)
    else:
        recs = E.main(tag, P, only=cyc)
    tune_sel = lambda r: r["tune"]
    held_sel = lambda r: r["held"]
    if os.environ.get("DRY"):          # code check without looking at held-out weeks
        held_sel = lambda r: r["tune"] and r["ymd"][6:8] < "08"
        tune_sel = lambda r: r["tune"] and r["ymd"][6:8] >= "08"
    winter = lambda r: held_sel(r) and r["ymd"][4:6] in ("10", "11", "12", "01", "02", "03")
    lines = ["# Day 5-7 lows: final score on held-out weeks", "",
             "Settings: %s" % json.dumps({k: v for k, v in P.items() if k != "T"}), ""]
    Ts, Tm, res = {}, {}, {}
    for step in lib.STEPS:
        fa_models = {m: S.stats([r for r in recs if r["sys"] == m and r["step"] == step and r["tune"]])["fa"] for m in ("gfs", "ifs", "aifs")}
        c = tune.curve(recs, step)
        o = np.argsort(c[:, 4])
        Ts[step] = float(np.interp(fa_models["ifs"], c[o, 4], c[o, 0]))
        for m, f in fa_models.items():
            Tm[(step, m)] = float(np.interp(f, c[o, 4], c[o, 0]))
    lines.append("Keep threshold (share of weighted members), set on tuning weeks to match IFS's false-low rate: " + ", ".join("+%dh %.2f" % (s, t) for s, t in Ts.items()))
    lines.append("")
    for label, sel in (("All held-out weeks", held_sel), ("Held-out winter weeks (Oct-Mar runs)", winter)):
        for deep in (False, True):
            lines += ["## %s, %s" % (label, "deep lows (< 980 hPa)" if deep else "all lows (< 1000 hPa)"), "",
                      "| lead | basin | system | lows | position km | depth MAE hPa | hit 300 km | false lows / map |", "|---|---|---|---|---|---|---|---|"]
            for step in lib.STEPS:
                for dom in ("both", "natl", "npac"):
                    dsel = lambda r, s=sel, d=dom: s(r) and (d == "both" or r["dom"] == d)
                    v = per_case(recs, "vote", step, dsel, Ts[step])
                    mv = metrics(v, deep)
                    lines.append("| +%d | %s | **vote** | %d | %.0f | %.1f | %.0f%% | %.2f |" % (step, dom, mv[4], mv[0], mv[1], 100 * mv[2], mv[3]))
                    for m in ("gfs", "ifs", "aifs", "gmean"):
                        b = per_case(recs, m, step, dsel)
                        mb = metrics(b, deep)
                        d0, lo, hi, nw, npair = paired(v, b, deep, n=1000 if dom == "both" else 300)
                        res[(label, deep, step, dom, m)] = (d0.tolist(), lo.tolist(), hi.tolist(), nw)
                        lines.append("| | | %s | %d | %.0f (vote %+.0f, %+.0f..%+.0f) | %.1f (vote %+.1f, %+.1f..%+.1f) | %.0f%% | %.2f |" % (
                            m, mb[4], mb[0], d0[0], lo[0], hi[0], mb[1], d0[1], lo[1], hi[1], 100 * mb[2], mb[3]))
            lines.append("")
    # each model against the vote held at that model's own false-low rate
    for label, sel in (("All held-out weeks", held_sel), ("Held-out winter weeks (Oct-Mar runs)", winter)):
        lines += ["## %s: vote at each model's own false-low rate (both basins)" % label, "",
                  "| lead | model | vote keep threshold | position km model / vote (diff, 95%%) | depth MAE model / vote (diff, 95%%) | false lows model / vote |", "|---|---|---|---|---|---|"]
        for step in lib.STEPS:
            for m in ("gfs", "ifs", "aifs"):
                v = per_case(recs, "vote", step, sel, Tm[(step, m)])
                b = per_case(recs, m, step, sel)
                mv, mb = metrics(v), metrics(b)
                d0, lo, hi, nw, npair = paired(v, b, False, n=1000)
                res[(label, "eqfa", step, m)] = (d0.tolist(), lo.tolist(), hi.tolist(), nw)
                lines.append("| +%d | %s | %.2f | %.0f / %.0f (%+.0f, %+.0f..%+.0f) | %.1f / %.1f (%+.1f, %+.1f..%+.1f) | %.2f / %.2f |" % (
                    step, m, Tm[(step, m)], mb[0], mv[0], d0[0], lo[0], hi[0], mb[1], mv[1], d0[1], lo[1], hi[1], mb[3], mv[3]))
        lines.append("")
    # confidence
    def feats(sel):
        X, y = [], []
        for r in recs:
            if r["sys"] != "vote" or not sel(r) or not len(r["lows"]):
                continue
            keep = r["lows"][:, 3] >= Ts[r["step"]]
            for l, vv in zip(r["lows"][keep], r["ver"][keep]):
                X.append((l[3], np.log(max(l[4], 20)), (r["step"] - 144) / 24, l[2] - 1000)); y.append(vv[0] <= 300)
        return np.array(X), np.array(y)
    Xt, yt = feats(tune_sel)
    Xh, yh = feats(held_sel)
    lr = LogisticRegression(C=1.0).fit(Xt, yt)
    ph = lr.predict_proba(Xh)[:, 1]
    lines += ["## Confidence score: chance an analysed low is within 300 km", "",
              "Logistic fit on tuning lows (%d) from member support, spread, lead and depth; coefficients %s, intercept %.2f." % (len(yt), np.round(lr.coef_[0], 2).tolist(), lr.intercept_[0]),
              "", "| stated chance | held-out lows | verified |", "|---|---|---|"]
    for a, b in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
        m = (ph >= a) & (ph < b)
        if m.sum():
            lines.append("| %d-%d%% | %d | %.0f%% |" % (100 * a, min(100, 100 * b), m.sum(), 100 * yh[m].mean()))
    bs = np.mean((ph - yh) ** 2); bs0 = np.mean((yt.mean() - yh) ** 2)
    lines += ["", "Brier skill vs the overall hit rate: %.2f" % (1 - bs / bs0), ""]
    open(os.path.join(lib.RESULTS, "final%s.md" % ("_dry" if os.environ.get("DRY") else "")), "w").write("\n".join(lines))
    json.dump({"T": Ts, "P": {k: v for k, v in P.items()}, "conf": {"coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])},
               "res": {"|".join(map(str, k)): v for k, v in res.items()}}, open(os.path.join(lib.RESULTS, "final%s.json" % ("_dry" if os.environ.get("DRY") else "")), "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main(json.loads(sys.argv[1]) if len(sys.argv) > 1 else {})
