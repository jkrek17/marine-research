"""Part B scoring and calibration (design.md "Part B"), from the per-case files that partb.py --build wrote.

    python3 partb_analyze.py [--draws 2000]

Products per lead (+120/+144/+168), both basins pooled for the fits (reported per basin too):
  exist   chance the vote low exists: isotonic recalibration of the vote support; event = an analysed low
          < 1000 hPa within 300 km of it. Rival: tuning-week hit rate by lead.
  depth   predictive distribution = the voters' own depths, widened about the 50% depth (the map low) by one
          spread factor per lead (fitted so the 10-90% range holds 80% on training lows, aiming at a flat PIT),
          each voter smoothed by a fixed 2 hPa normal kernel. Chance below 990/980/970/960 = exist chance x
          P(depth < t | exists); event = an analysed low < t within 300 km. Variants: "direct" and "iso"
          (isotonic recalibration of that product, fitted on the training lows). Rival: the lead's tuning-week
          error climatology (analysed minus vote depth) around the vote depth, times the base hit rate.
  circle  50% / 80% position error circles per lead and by support tercile (training quantiles of the distance
          from a vote low to the nearest analysed low < 1000 hPa within 1000 km). Rival: the lead circle.
  alt     alternative scenarios (partb.alternatives), verified by an analysed low within 300 km of the
          alternative and not of the main low; rival: the same offset at 7 other bearings around the main low.
Fits: leave-one-month-out on tuning weeks (7-day purge at the month's edges; tuning = cycle and valid time both
outside rk.cases.held_out weeks); held-out weeks are predicted from the fit on all tuning weeks (sign check).
Truth: headline = mean of the GFS and IFS analyses (fits use it); every score is also computed against each.
Subsets: winter (cycles 2025-11-01 .. 2026-03-31, tuning-week out-of-fold), year (all tuning-week out-of-fold),
held (held-out weeks). Intervals: whole-week bootstrap (rk.compare.boot_sums), week = ISO week of the cycle.
"""
import argparse
import json
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (str(REPO), str(HERE), str(HERE.parents[0] / "2026-10-16-pressure-d5-7")):
    if p not in sys.path:
        sys.path.insert(0, p)
import numpy as np
import pandas as pd
from scipy.special import ndtr
from rk import cases as rkc, compare as rkcmp, score as rks, calibrate as rkcal
import partb as PB

LEADS = PB.LEADS
TRUTHS = ("mean", "gfs", "ifs")
THRS = (990, 980, 970, 960)
GRID = np.arange(900.0, 1040.01, 0.5)
S0 = 2.0                       # hPa, fixed kernel on each voter's depth
RES = HERE / "results"
WINTER = (datetime(2025, 11, 1), datetime(2026, 3, 31, 23))


# ---------------------------------------------------------------- tables from the case files

def load():
    """-> forecast-low table F (one row per vote low), padded voter arrays X, W, analysed-low table A, alt table L."""
    rows, X, W, alts, ana = [], [], [], [], []
    fid = 0
    for basin in PB.BASINS:
        for p in sorted((PB.CASES / basin).glob("*.pkl")):
            r = pickle.load(open(p, "rb"))
            if r is None:
                continue
            cyc = r["cycle"]
            for lead, d in r["leads"].items():
                if d["truth"] is None:
                    continue
                lows = d["lows"]
                f0 = fid
                for k in range(len(lows)):
                    row = dict(fid=fid, basin=basin, cycle=cyc, lead=lead, k=k, lat=lows[k, 0], lon=lows[k, 1], hpa=lows[k, 2],
                               support=lows[k, 3], spread=lows[k, 4], nvote=len(d["vd"][k][0]), n_alt=len(d["alts"][k]))
                    for t in TRUTHS:
                        T = d["truth"][t]
                        T = np.asarray(T, float).reshape(-1, 3)
                        if len(T):
                            dd = rks.km(lows[k, 0], lows[k, 1], T[:, 0], T[:, 1])
                            near = dd <= 300.0
                            row["amin_" + t] = float(T[near, 2].min()) if near.any() else np.nan
                            row["dn_" + t] = float(dd.min())
                        else:
                            row["amin_" + t] = np.nan
                            row["dn_" + t] = np.inf
                    rows.append(row)
                    w, x = d["vd"][k]
                    X.append(x); W.append(w)
                    for a in d["alts"][k]:
                        alts.append(dict(fid=fid, basin=basin, cycle=cyc, lead=lead, mlat=lows[k, 0], mlon=lows[k, 1], mhpa=lows[k, 2],
                                         **{"a" + kk: v for kk, v in a.items() if kk != "kind"}, kind=a["kind"],
                                         truth={t: np.asarray(d["truth"][t], float).reshape(-1, 3) for t in TRUTHS}))
                    fid += 1
                for t in TRUTHS:
                    T = np.asarray(d["truth"][t], float).reshape(-1, 3)
                    for la, lo, hp in T:
                        if len(lows):
                            dd = rks.km(la, lo, lows[:, 0], lows[:, 1])
                            ana.append(dict(truth=t, basin=basin, cycle=cyc, lead=lead, lat=la, lon=lo, hpa=hp, f0=f0, nf=len(lows),
                                            dists=dd))
                        else:
                            ana.append(dict(truth=t, basin=basin, cycle=cyc, lead=lead, lat=la, lon=lo, hpa=hp, f0=f0, nf=0,
                                            dists=np.zeros(0)))
    F = pd.DataFrame(rows)
    nv = max(len(x) for x in X)
    Xp = np.full((len(X), nv), np.nan); Wp = np.zeros((len(X), nv))
    for i, (x, w) in enumerate(zip(X, W)):
        Xp[i, :len(x)] = x; Wp[i, :len(w)] = w
    F["week"] = [(c.isocalendar()[0] * 100 + c.isocalendar()[1]) for c in F.cycle]
    F["month"] = [c.year * 100 + c.month for c in F.cycle]
    F["held"] = [rkc.held_out(c) for c in F.cycle]
    F["tune"] = [(not rkc.held_out(c)) and (not rkc.held_out(c + timedelta(hours=int(l)))) for c, l in zip(F.cycle, F.lead)]
    F["winter"] = [(WINTER[0] <= c <= WINTER[1]) for c in F.cycle]
    return F, Xp, Wp, pd.DataFrame(ana), pd.DataFrame(alts)


# ---------------------------------------------------------------- depth distributions

def cdf_voters(m, X, W, f, t):
    """P(depth < t) for rows: voters' depths widened about m by f, each smoothed with a S0 normal kernel.
    m [n], X, W [n, V] (nan-padded, weight 0), t [n] or [n, T] -> same shape as t."""
    Xs = np.where(np.isnan(X), 0.0, X)
    mu = m[:, None] + f * (Xs - m[:, None])
    t2 = t if t.ndim == 2 else t[:, None]
    z = (t2[:, :, None] - mu[:, None, :]) / S0
    F = (W[:, None, :] * ndtr(z)).sum(2) / W.sum(1)[:, None]
    return F if t.ndim == 2 else F[:, 0]


def cdf_grid(m, X, W, f, chunk=400):
    out = np.empty((len(m), len(GRID)), np.float32)
    for i in range(0, len(m), chunk):
        s = slice(i, i + chunk)
        out[s] = cdf_voters(m[s], X[s], W[s], f, np.broadcast_to(GRID, (len(m[s]), len(GRID))))
    return out


def fit_spread(m, X, W, y, target=0.80, lo=0.2, hi=8.0):
    """Spread factor f so the 10-90% range of the widened distribution holds `target` of the analysed depths y
    (bisection on the PIT coverage; coverage grows with f)."""
    def cov(f):
        pit = cdf_voters(m, X, W, f, y)
        return float(((pit >= 0.1) & (pit <= 0.9)).mean())
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        if cov(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def quantile_from_cdf(F, q):
    """F [n, len(GRID)] -> depth at chance q per row (linear interpolation)."""
    i = np.clip((F < q).sum(1), 1, F.shape[1] - 1)
    r = np.arange(len(F))
    f0, f1 = F[r, i - 1], F[r, i]
    w = np.where(f1 > f0, (q - f0) / np.maximum(f1 - f0, 1e-9), 0.0)
    return GRID[i - 1] + np.clip(w, 0, 1) * (GRID[i] - GRID[i - 1])


def clim_cdf(e):
    """CDF G(u) of (analysed minus vote depth) climatology on a grid of u, each error smoothed with S0."""
    u = np.arange(-80, 80.01, 0.5)
    G = ndtr((u[:, None] - e[None, :]) / S0).mean(1)
    return u, G


# ---------------------------------------------------------------- fit and predict for one lead

def fit_model(a, tr):
    """a: dict of arrays for one lead; tr: boolean training mask. Everything from the headline truth."""
    mdl = {}
    sup, ex = a["support"][tr], a["exist"][tr]
    mdl["base"] = float(ex.mean())
    mdl["iso"] = rkcal.isotonic_fit(sup, ex)
    d = tr & a["exist"].astype(bool)
    mdl["n_depth"] = int(d.sum())
    mdl["f"] = fit_spread(a["hpa"][d], a["X"][d], a["W"][d], a["y"][d])
    e = a["y"][d] - a["hpa"][d]
    mdl["e_med"] = float(np.median(e))
    mdl["clim"] = clim_cdf(e)
    mdl["eq"] = np.quantile(e, [0.1, 0.9])
    p = tr & np.isfinite(a["pos"])
    pe = a["pos"][p]
    mdl["r50"], mdl["r80"] = float(np.quantile(pe, 0.5)), float(np.quantile(pe, 0.8))
    mdl["terc"] = np.quantile(a["support"][p], [1 / 3, 2 / 3])
    tc = np.searchsorted(mdl["terc"], a["support"][p], side="right")
    mdl["rt"] = [(float(np.quantile(pe[tc == j], 0.5)), float(np.quantile(pe[tc == j], 0.8))) for j in range(3)]
    # recalibration of the depth-threshold product, fitted on the training lows themselves
    P = predict_raw(a, mdl, tr)
    mdl["iso_t"] = {t: rkcal.isotonic_fit(P["p%d" % t], a["E%d" % t][tr]) for t in THRS}
    return mdl


def pex_of(mdl, sup):
    return rkcal.isotonic_apply(sup, *mdl["iso"]) if mdl["iso"] is not None else np.full(len(sup), mdl["base"])


def predict_raw(a, mdl, idx):
    o = {}
    sup, m, X, W = a["support"][idx], a["hpa"][idx], a["X"][idx], a["W"][idx]
    o["pex"] = pex_of(mdl, sup)
    o["pex_r"] = np.full(len(sup), mdl["base"])
    Tm = np.stack([np.full(len(m), float(t)) for t in THRS], 1)
    Fc = cdf_voters(m, X, W, mdl["f"], Tm)
    u, G = mdl["clim"]
    Fr = np.interp(Tm - m[:, None], u, G)
    for j, t in enumerate(THRS):
        o["p%d" % t] = o["pex"] * Fc[:, j]
        o["r%d" % t] = o["pex_r"] * Fr[:, j]
    sh = mdl["e_med"]                     # variant beyond the spec: depth centre shifted by the training median error
    Fb = cdf_voters(m + sh, X + sh, W, mdl["f"], Tm)
    for j, t in enumerate(THRS):
        o["b%d" % t] = o["pex"] * Fb[:, j]
    return o


def predict(a, mdl, idx):
    o = predict_raw(a, mdl, idx)
    for t in THRS:
        xk = mdl["iso_t"][t]
        o["i%d" % t] = rkcal.isotonic_apply(o["p%d" % t], *xk) if xk is not None else o["p%d" % t]
    m, X, W = a["hpa"][idx], a["X"][idx], a["W"][idx]
    Fg = cdf_grid(m, X, W, mdl["f"])
    o["Fg"] = Fg
    sh = mdl["e_med"]
    Fb = cdf_grid(m + sh, X + sh, W, mdl["f"])
    o["Fg_bc"] = Fb
    o["q10_bc"], o["q90_bc"] = quantile_from_cdf(Fb, 0.1), quantile_from_cdf(Fb, 0.9)
    o["q10"], o["q90"] = quantile_from_cdf(Fg, 0.1), quantile_from_cdf(Fg, 0.9)
    u, G = mdl["clim"]
    o["Fgr"] = np.interp(GRID[None, :] - m[:, None], u, G).astype(np.float32)
    o["q10_r"], o["q90_r"] = quantile_from_cdf(o["Fgr"], 0.1), quantile_from_cdf(o["Fgr"], 0.9)
    o["r50"] = np.full(len(m), mdl["r50"]); o["r80"] = np.full(len(m), mdl["r80"])
    tc = np.searchsorted(mdl["terc"], a["support"][idx], side="right")
    o["terc"] = tc
    o["t50"] = np.array([mdl["rt"][j][0] for j in tc]); o["t80"] = np.array([mdl["rt"][j][1] for j in tc])
    return o


def oof(a):
    """Out-of-fold predictions for one lead: leave-one-month-out on tuning rows (7-day purge), full tuning fit for
    held-out rows. Returns dict of arrays (nan/0 where a row has no prediction) and the full-fit model."""
    n = len(a["support"])
    out = {}
    def put(o, idx):
        for k, v in o.items():
            if k not in out:
                out[k] = np.full((n,) + v.shape[1:], np.nan, np.float32 if v.ndim > 1 else float)
            out[k][idx] = v
    tune = a["tune"]
    cyc = a["cycle"]
    for mo in sorted(set(a["month"][tune])):
        y, m = divmod(mo, 100)
        s0 = datetime(y, m, 1) - timedelta(days=7)
        s1 = (datetime(y + (m == 12), m % 12 + 1, 1)) + timedelta(days=7)
        test = tune & (a["month"] == mo)
        train = tune & ~((cyc >= np.datetime64(s0)) & (cyc < np.datetime64(s1)))
        mdl = fit_model(a, train)
        put(predict(a, mdl, np.where(test)[0]), np.where(test)[0])
    full = fit_model(a, tune)
    h = np.where(a["held"])[0]
    put(predict(a, full, h), h)
    return out, full


# ---------------------------------------------------------------- scoring helpers

def skill(ours, rival, weeks, draws):
    """1 - sum(ours)/sum(rival) with a whole-week bootstrap interval. -> (skill, lo, hi)."""
    st = np.stack([ours, rival], 1)
    tot, dr = rkcmp.boot_sums(weeks, st, n_boot=draws)
    s = 1 - tot[0] / tot[1]
    ds = 1 - dr[:, 0] / dr[:, 1]
    return float(s), float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))


def pinball(e, r, q):
    d = e - r
    return np.where(d >= 0, q * d, (q - 1) * d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=2000)
    args = ap.parse_args()
    F, X, W, A, L = load()
    print("forecast lows", len(F), "analysed-low rows", len(A), "alts", len(L), flush=True)
    RES.mkdir(exist_ok=True)
    pred = {}                       # lead -> dict of arrays aligned with F rows of that lead
    rows = {}                       # lead -> positions in F
    models = {}
    for lead in LEADS:
        ix = np.where(F.lead.values == lead)[0]
        rows[lead] = ix
        S = F.iloc[ix]
        a = dict(support=S.support.values, hpa=S.hpa.values, X=X[ix], W=W[ix], tune=S.tune.values, held=S.held.values,
                 month=S.month.values, cycle=np.array([np.datetime64(c) for c in S.cycle]))
        h = "mean"
        a["exist"] = np.isfinite(S["amin_" + h].values).astype(float)
        a["y"] = S["amin_" + h].values
        a["pos"] = np.where(S["dn_" + h].values <= 1000.0, S["dn_" + h].values, np.nan)
        for t in THRS:
            a["E%d" % t] = (S["amin_" + h].values < t).astype(float)
        o, full = oof(a)
        pred[lead] = o
        models[lead] = full
        print("lead", lead, "rows", len(ix), "base", round(full["base"], 3), "f", round(full["f"], 2), "r50/r80", round(full["r50"]), round(full["r80"]), flush=True)
    json.dump({str(l): dict(base=m["base"], f=m["f"], r50=m["r50"], r80=m["r80"], terc=list(map(float, m["terc"])),
                            rt=m["rt"], e_med=m["e_med"], n_depth=m["n_depth"],
                            iso_knots=None if m["iso"] is None else [list(map(float, m["iso"][0])), list(map(float, m["iso"][1]))])
               for l, m in models.items()}, open(RES / "partb_params.json", "w"), indent=1)

    subsets = {"winter": lambda S: S.tune.values & S.winter.values, "year": lambda S: S.tune.values, "held": lambda S: S.held.values}
    rel_rows, ver_rows, sk_rows, rng_rows, circ_rows = [], [], [], [], []
    for lead in LEADS:
        ix, o = rows[lead], pred[lead]
        S = F.iloc[ix].reset_index(drop=True)
        wk = S.week.values
        for sname, sf in subsets.items():
            sel0 = sf(S)
            for basin in ("both", "natl", "npac"):
                bsel = sel0 & ((S.basin.values == basin) if basin != "both" else True)
                for truth in TRUTHS:
                    am = S["amin_" + truth].values
                    ex = np.isfinite(am)
                    prods = {"exist": (o["pex"], o["pex_r"], ex.astype(float))}
                    for t in THRS:
                        ev = (am < t).astype(float)
                        prods["lt%d" % t] = (o["p%d" % t], o["r%d" % t], ev)
                        prods["lt%d_iso" % t] = (o["i%d" % t], o["r%d" % t], ev)
                        prods["lt%d_bc" % t] = (o["b%d" % t], o["r%d" % t], ev)
                    for pn, (p, r, ev) in prods.items():
                        s = bsel & np.isfinite(p)
                        if s.sum() == 0:
                            continue
                        if truth == "mean":
                            t_, verdict = rkcal.reliability_weeks(p[s], ev[s], wk[s])
                            for rr in t_.itertuples():
                                rel_rows.append(dict(subset=sname, lead=lead, basin=basin, product=pn, bin_lo=rr.lo, bin_hi=min(rr.hi, 1.0),
                                                     n=rr.n, events=rr.events, event_weeks=rr.event_weeks,
                                                     mean_p=round(rr.mean_p, 3) if rr.n else np.nan, freq=round(rr.freq, 3) if rr.n else np.nan,
                                                     ok=rr.ok, judged=rr.judged))
                            ver_rows.append(dict(subset=sname, lead=lead, basin=basin, product=pn, verdict=verdict, n=int(s.sum()),
                                                 events=int(ev[s].sum()), event_weeks=len(np.unique(wk[s & (ev > 0.5)])),
                                                 mean_p=round(float(p[s].mean()), 3), freq=round(float(ev[s].mean()), 3)))
                        sk, lo, hi = skill((p[s] - ev[s]) ** 2, (r[s] - ev[s]) ** 2, wk[s], args.draws)
                        sk_rows.append(dict(subset=sname, truth=truth, lead=lead, basin=basin, product=pn, metric="brier",
                                            ours=float(((p[s] - ev[s]) ** 2).mean()), rival=float(((r[s] - ev[s]) ** 2).mean()),
                                            skill=sk, lo=lo, hi=hi, n=int(s.sum()), weeks=len(np.unique(wk[s]))))
                    # depth distribution given the low exists: CRPS, coverage, PIT
                    s = bsel & ex
                    if s.sum() > 0:
                        y = am[s]
                        for var, Fk, k10, k90 in (("", "Fg", "q10", "q90"), ("_bc", "Fg_bc", "q10_bc", "q90_bc")):
                            c1 = rks.crps_cdf(o[Fk][s], GRID, y)
                            c0 = rks.crps_cdf(o["Fgr"][s], GRID, y)
                            sk, lo, hi = skill(c1, c0, wk[s], args.draws)
                            sk_rows.append(dict(subset=sname, truth=truth, lead=lead, basin=basin, product="depth_dist" + var, metric="crps",
                                                ours=float(c1.mean()), rival=float(c0.mean()), skill=sk, lo=lo, hi=hi, n=int(s.sum()),
                                                weeks=len(np.unique(wk[s]))))
                            cov = ((y >= o[k10][s]) & (y <= o[k90][s]))
                            cov_r = ((y >= o["q10_r"][s]) & (y <= o["q90_r"][s]))
                            pit = np.array([np.interp(v, GRID, f) for v, f in zip(y, o[Fk][s])])
                            hist = np.histogram(pit, bins=10, range=(0, 1))[0] / len(pit)
                            _, wlo, whi = skill(cov.astype(float), np.ones(len(cov)), wk[s], args.draws)   # interval for coverage
                            rng_rows.append(dict(subset=sname, truth=truth, lead=lead, basin=basin, direction="forecast_low" + var,
                                                 n=int(s.sum()), weeks=len(np.unique(wk[s])), cov80=float(cov.mean()), cov80_lo=1 - whi, cov80_hi=1 - wlo,
                                                 cov80_rival=float(cov_r.mean()), pit_maxdev=float(np.abs(hist - 0.1).max()),
                                                 pit_lo=float(hist[0]), pit_hi=float(hist[-1]), bias_hpa=float(np.median(y - S.hpa.values[s])),
                                                 width80=float(np.median(o[k90][s] - o[k10][s])), width80_rival=float(np.median(o["q90_r"][s] - o["q10_r"][s])),
                                                 mean_abs_err=float(np.abs(y - S.hpa.values[s]).mean())))
                # position circles (headline truth for the fits; coverage on each truth)
                for truth in TRUTHS:
                    dn = S["dn_" + truth].values
                    s = bsel & (dn <= 1000.0)
                    if s.sum() == 0:
                        continue
                    e = dn[s]
                    row = dict(subset=sname, truth=truth, lead=lead, basin=basin, direction="forecast_low", n=int(s.sum()),
                               weeks=len(np.unique(wk[s])), r50=float(o["r50"][s][0]), r80=float(o["r80"][s][0]),
                               cov50=float((e <= o["r50"][s]).mean()), cov80=float((e <= o["r80"][s]).mean()),
                               cov50_t=float((e <= o["t50"][s]).mean()), cov80_t=float((e <= o["t80"][s]).mean()), med_err=float(np.median(e)))
                    for q, rr_, rt_ in ((0.5, "r50", "t50"), (0.8, "r80", "t80")):
                        sk, lo, hi = skill(pinball(e, o[rt_][s], q), pinball(e, o[rr_][s], q), wk[s], args.draws)
                        row.update({"pin%d_skill" % (q * 100): sk, "pin%d_lo" % (q * 100): lo, "pin%d_hi" % (q * 100): hi})
                    for j in range(3):
                        sj = s & (o["terc"] == j)
                        row["terc%d_n" % j] = int(sj.sum())
                        row["terc%d_cov50" % j] = float((dn[sj] <= o["t50"][sj]).mean()) if sj.any() else np.nan
                        row["terc%d_cov80" % j] = float((dn[sj] <= o["t80"][sj]).mean()) if sj.any() else np.nan
                        row["terc%d_r50" % j] = float(o["t50"][sj][0]) if sj.any() else np.nan
                        row["terc%d_r80" % j] = float(o["t80"][sj][0]) if sj.any() else np.nan
                    circ_rows.append(row)

    # ---------------- the other direction: every analysed low
    Fq = F.copy()
    for lead in LEADS:
        for k, v in pred[lead].items():
            if v.ndim == 1:
                Fq.loc[F.index[rows[lead]], "pr_" + k] = v
    Fq["pr_q10"] = Fq["pr_q10"]; ana_rows = []
    A = A.copy()
    A["week"] = [(c.isocalendar()[0] * 100 + c.isocalendar()[1]) for c in A.cycle]
    A["month"] = [c.year * 100 + c.month for c in A.cycle]
    A["held"] = [rkc.held_out(c) for c in A.cycle]
    A["tune"] = [(not rkc.held_out(c)) and (not rkc.held_out(c + timedelta(hours=int(l)))) for c, l in zip(A.cycle, A.lead)]
    A["winter"] = [(WINTER[0] <= c <= WINTER[1]) for c in A.cycle]
    near = np.array([d.min() if len(d) else np.inf for d in A.dists])
    kn = np.array([int(d.argmin()) if len(d) else -1 for d in A.dists])
    A["dn"] = near
    A["fid_near"] = [f0 + k if k >= 0 else -1 for f0, k in zip(A.f0, kn)]
    fi = Fq.set_index("fid")
    def pick(col):
        return np.array([fi[col].get(i, np.nan) if i >= 0 else np.nan for i in A.fid_near])
    for col in ("pr_pex", "pr_q10", "pr_q90", "pr_t50", "pr_t80", "pr_r50", "pr_r80"):
        A[col] = pick(col)
    # any vote low whose own circle holds the analysed low
    def covered(r, which):
        out = []
        for d, f0, nf in zip(A.dists, A.f0, A.nf):
            if nf == 0:
                out.append(False); continue
            rr = np.array([fi[which].get(f0 + k, np.nan) for k in range(nf)])
            out.append(bool(np.nanmin(d / rr) <= 1.0) if np.isfinite(rr).any() else False)
        return np.array(out)
    A["in_t50"], A["in_t80"] = covered(A, "pr_t50"), covered(A, "pr_t80")
    A["in_r50"], A["in_r80"] = covered(A, "pr_r50"), covered(A, "pr_r80")
    ana_out = []
    for lead in LEADS:
        for sname, key in (("winter", None), ("year", None), ("held", None)):
            for basin in ("both", "natl", "npac"):
                for truth in TRUTHS:
                    s = (A.lead == lead) & (A.truth == truth)
                    s &= A.held if sname == "held" else A.tune
                    if sname == "winter":
                        s &= A.winter
                    if basin != "both":
                        s &= A.basin == basin
                    g = A[s]
                    if not len(g):
                        continue
                    fnd = g.dn <= 300.0
                    mt = g[fnd]
                    mt_ok = mt.pr_q10.notna()
                    inr = ((mt.hpa >= mt.pr_q10) & (mt.hpa <= mt.pr_q90))[mt_ok]
                    ana_out.append(dict(subset=sname, truth=truth, lead=lead, basin=basin, n_analysed=len(g), weeks=g.week.nunique(),
                                        found300=float(fnd.mean()), mean_pex_when_found=float(mt.pr_pex.mean()) if len(mt) else np.nan,
                                        range80_cov_found=float(inr.mean()) if len(inr) else np.nan,
                                        circle50_cov=float(g.in_t50.mean()), circle80_cov=float(g.in_t80.mean()),
                                        lead_circle50_cov=float(g.in_r50.mean()), lead_circle80_cov=float(g.in_r80.mean()),
                                        median_miss_km=float(g.dn.clip(upper=1000).median())))

    # ---------------- alternative scenarios
    alt_out = []
    if len(L):
        L["week"] = [(c.isocalendar()[0] * 100 + c.isocalendar()[1]) for c in L.cycle]
        L["held"] = [rkc.held_out(c) for c in L.cycle]
        L["winter"] = [(WINTER[0] <= c <= WINTER[1]) for c in L.cycle]
        for truth in TRUTHS:
            ver, plc = [], []
            for r in L.itertuples():
                T = r.truth[truth]
                v, pl = alt_verify(r, T)
                ver.append(v); plc.append(pl)
            L["ver_" + truth], L["plc_" + truth] = ver, plc
        # main-low and rescue bookkeeping per case
        for lead in LEADS:
            for sname in ("winter", "year", "held"):
                for basin in ("both", "natl", "npac"):
                    for truth in TRUTHS:
                        s = (L.lead == lead)
                        s &= L.held if sname == "held" else ~L.held
                        if sname == "winter":
                            s &= L.winter
                        if basin != "both":
                            s &= L.basin == basin
                        g = L[s]
                        nlows = ((F.lead == lead) & (F.held if sname == "held" else ~F.held)
                                 & (F.winter if sname == "winter" else True) & ((F.basin == basin) if basin != "both" else True)).sum()
                        for kind in ("pos", "depth", "all"):
                            gg = g if kind == "all" else g[g.kind == kind]
                            if not len(gg):
                                continue
                            v = gg["ver_" + truth].values.astype(float)
                            ok = np.isfinite(v)
                            alt_out.append(dict(subset=sname, truth=truth, lead=lead, basin=basin, kind=kind, vote_lows=int(nlows), alts_shown=len(gg),
                                                alt_per_low=len(gg) / max(nlows, 1), weeks=gg.week.nunique(),
                                                verified=float(np.nanmean(v)) if ok.any() else np.nan, n_verified=int(np.nansum(v)),
                                                placebo=float(np.nanmean(gg["plc_" + truth].values.astype(float))) if kind != "depth" else np.nan,
                                                mean_share=float(gg.ashare.mean()), mean_dist_km=float(gg.adist_km.mean())))
    out = {"partb_reliability": rel_rows, "partb_verdict": ver_rows, "partb_skill": sk_rows, "partb_range": rng_rows,
           "partb_circles": circ_rows, "partb_analysed_dir": ana_out, "partb_alt": alt_out}
    for k, v in out.items():
        pd.DataFrame(v).to_csv(RES / (k + ".csv"), index=False, float_format="%.4g")
        print(k, len(v))


def dest(lat, lon, bearing_deg, dist_km):
    """great-circle destination from (lat, lon) along a bearing"""
    R = 6371.0
    la, lo, b, d = np.radians(lat), np.radians(lon), np.radians(bearing_deg), dist_km / R
    la2 = np.arcsin(np.sin(la) * np.cos(d) + np.cos(la) * np.sin(d) * np.cos(b))
    lo2 = lo + np.arctan2(np.sin(b) * np.sin(d) * np.cos(la), np.cos(d) - np.sin(la) * np.sin(la2))
    return float(np.degrees(la2)), float(np.degrees(lo2) % 360)


def bearing(lat1, lon1, lat2, lon2):
    la1, la2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
    return float(np.degrees(np.arctan2(np.sin(dl) * np.cos(la2), np.cos(la1) * np.sin(la2) - np.sin(la1) * np.cos(la2) * np.cos(dl))))


def verify_pos(T, alat, alon, mlat, mlon, km_=300.0):
    """analysed low within km_ of the alternative and not within km_ of the main low"""
    if not len(T):
        return False
    da = rks.km(alat, alon, T[:, 0], T[:, 1])
    dm = rks.km(mlat, mlon, T[:, 0], T[:, 1])
    return bool(((da <= km_) & (dm > km_)).any())


def alt_verify(r, T):
    """(verified, placebo rate) of one alternative against the analysed lows T (k, 3). Position alternatives: the
    literal rule; placebo = the same rule at the same distance from the main low and 7 other bearings (45 degree
    steps from the alternative's own). Depth alternatives (within 300 km of the main low): verified when an
    analysed low within 300 km of it is closer in depth to the alternative than to the main low; no placebo."""
    if r.kind == "depth":
        if not len(T):
            return False, np.nan
        da = rks.km(r.alat, r.alon, T[:, 0], T[:, 1])
        n = da <= 300.0
        return bool(n.any() and (np.abs(T[n, 2] - r.ahpa) < np.abs(T[n, 2] - r.mhpa)).any()), np.nan
    v = verify_pos(T, r.alat, r.alon, r.mlat, r.mlon)
    b0 = bearing(r.mlat, r.mlon, r.alat, r.alon)
    pl = [verify_pos(T, *dest(r.mlat, r.mlon, b0 + 45 * j, r.adist_km), r.mlat, r.mlon) for j in range(1, 8)]
    return v, float(np.mean(pl))


if __name__ == "__main__":
    main()
