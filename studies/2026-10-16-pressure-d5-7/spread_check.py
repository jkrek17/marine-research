"""Spread display check (preregistration.md, 'Spread display check'): do position ellipses and depth ranges
from the voters' own lows hold their stated share of analysed lows? Scales fitted on tuning lows, judged held-out.

Run: python3 spread_check.py  -> results/spread_check.md, results/spread_lows.csv
"""
import os, sys, json, datetime as dt
from multiprocessing import Pool
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib, method as M, evaluate as E

HERE = os.path.dirname(os.path.abspath(__file__))
FJ = json.load(open(os.path.join(HERE, "results", "final.json")))
P = FJ["P"]
T = {int(k): v for k, v in FJ["T"].items()}
FLOOR = 50.0
CHI50, CHI90 = 1.3863, 4.6052          # chi-square 2 dof


def wq(x, w, q):
    return M.wquant(np.asarray(x, float), np.asarray(w, float), q)


def run_cycle(ymd):
    out = []
    for dom in lib.DOMS:
        for step in lib.STEPS:
            valid = dt.datetime.strptime(ymd, "%Y%m%d") + dt.timedelta(hours=12 + step)
            an = M.analysis(valid.strftime("%Y%m%d"), dom)
            c = M.case(ymd, dom, step, lag=False) if an is not None else None
            if c is None:
                continue
            truth_all = lib.find_lows(an, dom, 1005.0)
            V = M.voters(c, dom, P["w"], use_lag=False)
            mem = []
            L = M.consensus(V, R=P["R"], T=T[step], q=P["q"], members=mem)
            cyc = dt.datetime.strptime(ymd, "%Y%m%d")
            for low, ms in zip(L, mem):
                la0, lo0 = low[0], low[1]
                w = np.array([V[v][0] for v, _, _ in ms])
                x = np.array([((lo - lo0 + 180) % 360 - 180) * 111.2 * np.cos(np.radians(la0)) for _, _, lo in ms])
                y = np.array([(la - la0) * 111.2 for _, la, _ in ms])
                p = []
                for v, la, lo in ms:
                    Lv = V[v][1]
                    p.append(Lv[np.argmin(np.abs(Lv[:, 0] - la) + np.abs(Lv[:, 1] - lo)), 2])
                wn = w / w.sum()
                mx, my = (wn * x).sum(), (wn * y).sum()
                cxx = (wn * (x - mx) ** 2).sum() + FLOOR ** 2
                cyy = (wn * (y - my) ** 2).sum() + FLOOR ** 2
                cxy = (wn * (x - mx) * (y - my)).sum()
                row = dict(ymd=ymd, dom=dom, step=step, held=lib.held_out(cyc), tune=lib.tune_ok(cyc, valid),
                           lat=la0, lon=lo0, hpa=low[2], support=low[3], cxx=cxx, cyy=cyy, cxy=cxy,
                           p10=wq(p, w, .1), p25=wq(p, w, .25), p50=wq(p, w, .5), p75=wq(p, w, .75), p90=wq(p, w, .9),
                           an_km=np.nan, d2=np.nan, an_hpa=np.nan)
                if len(truth_all):
                    d = lib.km(la0, lo0, truth_all[:, 0], truth_all[:, 1]); j = int(d.argmin())
                    if d[j] <= 1000:
                        ax = ((truth_all[j, 1] - lo0 + 180) % 360 - 180) * 111.2 * np.cos(np.radians(la0))
                        ay = (truth_all[j, 0] - la0) * 111.2
                        C = np.array([[cxx, cxy], [cxy, cyy]])
                        row.update(an_km=d[j], d2=float(np.array([ax, ay]) @ np.linalg.solve(C, [ax, ay])), an_hpa=truth_all[j, 2])
                out.append(row)
    return out


def main():
    cyc = [c for c in E.cycles() if c <= os.environ.get("LAST", "99999999")]
    csv = os.path.join(HERE, "results", "spread_lows.csv")
    if os.environ.get("REUSE"):
        df = pd.read_csv(csv)
    else:
        with Pool(4) as pool:
            rows = [r for rs in pool.imap_unordered(run_cycle, cyc, chunksize=4) for r in rs]
        df = pd.DataFrame(rows)
        df.to_csv(csv, index=False, float_format="%.2f")
    lines = ["# Spread display check", "", "Cycles %s-%s; settings and keep thresholds from final.json. Ellipse and depth scales fitted on tuning lows, coverage judged on held-out lows." % (cyc[0], cyc[-1]), "",
             "| lead | held-out lows (verified / all) | position scale | 50% ellipse | 90% ellipse | 90% ellipse, misses outside | median 50% ellipse area, 1000 km2 | depth scale | 50% depth range | 80% depth range | median 80% range width hPa |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    res = {}
    for step in lib.STEPS:
        d = df[df.step == step]
        tv = d[d.tune & d.d2.notna()]; hv = d[d.held & d.d2.notna()]; ha = d[d.held]
        k = float(np.quantile(tv.d2, 0.5) / CHI50)          # inflate covariance by k
        k90 = float(np.quantile(tv.d2, 0.9))                 # added after the check: 90% scale fitted on its own
        def dcov(s, f):
            lo = s.p50 - f * (s.p50 - s.p10); hi = s.p50 + f * (s.p90 - s.p50)
            return ((s.an_hpa >= lo) & (s.an_hpa <= hi)).mean()
        fs = np.linspace(0.5, 6, 221)
        f80 = float(fs[np.argmin([abs(dcov(tv, f) - 0.8) for f in fs])])
        lo50 = hv.p50 - f80 * (hv.p50 - hv.p25) / 1.0; hi50 = hv.p50 + f80 * (hv.p75 - hv.p50)
        c50 = (hv.d2 <= k * CHI50).mean(); c90 = (hv.d2 <= k * CHI90).mean()
        c90all = (ha.d2 <= k * CHI90).sum() / len(ha)
        c90own = (hv.d2 <= k90).mean()
        area = np.median(np.pi * k * CHI50 * np.sqrt(hv.cxx * hv.cyy - hv.cxy ** 2)) / 1000
        d80 = dcov(hv, f80); d50 = ((hv.an_hpa >= lo50) & (hv.an_hpa <= hi50)).mean()
        width = np.median(f80 * (hv.p90 - hv.p10))
        res[step] = dict(k90=k90, c90own=c90own, k=k, f80=f80, c50=c50, c90=c90, c90all=c90all, d50=d50, d80=d80, n=len(hv), nall=len(ha))
        lines.append("| +%d | %d / %d | %.2f | %.0f%% | %.0f%% | %.0f%% | %.0f | %.2f | %.0f%% | %.0f%% | %.1f |" % (
            step, len(hv), len(ha), k, 100 * c50, 100 * c90, 100 * c90all, area, f80, 100 * d50, 100 * d80, width))
    # does a wider spread mean a bigger error? held-out lows split into thirds by spread
    df["size"] = np.sqrt(df.cxx + df.cyy - 2 * FLOOR ** 2); df["width"] = df.p90 - df.p10; df["derr"] = (df.hpa - df.an_hpa).abs()
    lines += ["", "Added after the check: the 90% ellipse with its own scale fitted on tuning lows holds " + ", ".join("%.0f%% at +%d h" % (100 * res[s]["c90own"], s) for s in lib.STEPS) + "."]
    lines += ["", "Added after the preregistered check: held-out lows split into thirds by member spread (median error to the verifying analysed low).", "",
              "| lead | position spread km (tight / mid / wide) | position error km | depth range hPa (tight / mid / wide) | depth error hPa |", "|---|---|---|---|---|"]
    for step in lib.STEPS:
        h = df[(df.step == step) & df.held & df.an_km.notna()]
        a = h.groupby(pd.qcut(h["size"], 3), observed=True).agg(s=("size", "median"), e=("an_km", "median"))
        b = h.groupby(pd.qcut(h["width"], 3), observed=True).agg(s=("width", "median"), e=("derr", "median"))
        lines.append("| +%d | %s | %s | %s | %s |" % (step, " / ".join("%.0f" % v for v in a.s), " / ".join("%.0f" % v for v in a.e),
                                                     " / ".join("%.1f" % v for v in b.s), " / ".join("%.1f" % v for v in b.e)))
    open(os.path.join(HERE, "results", "spread_check.md"), "w").write("\n".join(lines) + "\n")
    json.dump(res, open(os.path.join(HERE, "results", "spread_check.json"), "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
