"""Turn work/day_results.pkl (compare.py) and work/obs_pairs.pkl (obs_pairs.py) into results/*.csv, numbers.md, peaks.png.
Intervals: 95% percentile intervals from resampling whole ISO weeks (2000 reps, seed 0)."""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare import WORK  # noqa: E402
sys.path.insert(0, str(HERE.parents[1]))
from rk import style  # noqa: E402

RES = HERE / "results"
B = 2000
BANDS_PEAK = [("40-48", 0, 48), ("48-56", 48, 56), ("56-64", 56, 64), ("64+", 64, 1e9)]
BANDS_CELL = [("25-34", 25, 34), ("34-48", 34, 48), ("48-56", 48, 56), ("56-64", 56, 64), ("64+", 64, 1e9)]


# ---- week-block bootstrap on per-week sums ----
def week_sums(wk, cols):
    """cols: [n, k] array of per-row additive stats -> (week ids, [nweeks, k] sums)."""
    uw, inv = np.unique(wk, return_inverse=True)
    out = np.zeros((len(uw), cols.shape[1]))
    np.add.at(out, inv, cols)
    return uw, out


def boot_stat(W, fn, seed=0):
    """W: [nweeks, k] per-week sums; fn maps summed [.., k] to the statistic(s). Returns point, lo, hi."""
    point = fn(W.sum(0, keepdims=True))
    if len(W) < 2:
        return point.ravel(), np.full(point.size, np.nan), np.full(point.size, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(W), size=(B, len(W)))
    tot = W[idx].sum(1)
    with np.errstate(all="ignore"):
        s = fn(tot)
    lo, hi = np.nanpercentile(s, [2.5, 97.5], axis=0)
    return point.ravel(), np.atleast_1d(lo), np.atleast_1d(hi)


def f_mean(S):          # cols: n, sum
    with np.errstate(all="ignore"):
        return (S[:, 1] / S[:, 0])[:, None]


def f_deming(S):        # cols: n, sx, sy, sxx, syy, sxy  -> slope, intercept
    n, sx, sy, sxx, syy, sxy = S.T
    mx, my = sx / n, sy / n
    vxx, vyy, vxy = sxx - n * mx ** 2, syy - n * my ** 2, sxy - n * mx * my
    with np.errstate(all="ignore"):
        b = (vyy - vxx + np.sqrt((vyy - vxx) ** 2 + 4 * vxy ** 2)) / (2 * vxy)
    return np.stack([b, my - b * mx], 1)


def f_ratio(S):
    with np.errstate(all="ignore"):
        return (S[:, 1] / S[:, 0])[:, None]


# ---- method 1 ----
def storm_summary(df):
    df = df.copy()
    df["mean_pk"] = 0.5 * (df.ascat40_peak + df.smap_peak)
    df["d"] = df.smap_peak - df.ascat40_peak
    df["gap_pk"] = (df.other_t - df.t_peak).abs()
    df["gapbin"] = np.where(df.gap_pk <= 90, "0-90", "90-180")
    df["split"] = np.where(df.held_out, "held_out", "tune")
    strata = [("all", "all", np.ones(len(df), bool))]
    for col in ("basin", "sat", "gapbin", "split"):
        for v in sorted(df[col].unique()):
            strata.append((col, str(v), (df[col] == v).to_numpy()))
    rows = []
    for direction in ("ascat", "smap"):
        dd = df if direction == "both" else df[df.direction == direction]
        sel_dir = np.ones(len(df), bool) if direction == "both" else (df.direction == direction).to_numpy()
        for col, val, m in strata:
            sub = df[m & sel_dir]
            for bname, lo_, hi_ in [("all", -1, 1e9)] + BANDS_PEAK:
                s = sub[(sub.mean_pk >= lo_) & (sub.mean_pk < hi_)]
                row = dict(direction=direction, stratum=col, value=val, band=bname, n_pairs=len(s),
                           n_weeks=s.week.nunique())
                if len(s):
                    uw, W = week_sums(s.week.to_numpy(), np.stack([np.ones(len(s)), s.d.to_numpy()], 1))
                    p, lo, hi = boot_stat(W, f_mean)
                    row.update(mean_ascat40=s.ascat40_peak.mean(), mean_smap=s.smap_peak.mean(),
                               diff=p[0], diff_lo=lo[0], diff_hi=hi[0])
                    if bname == "all" and len(s) >= 8:
                        x, y = s.ascat40_peak.to_numpy(), s.smap_peak.to_numpy()
                        cols = np.stack([np.ones(len(s)), x, y, x * x, y * y, x * y], 1)
                        uw, W = week_sums(s.week.to_numpy(), cols)
                        p, lo, hi = boot_stat(W, f_deming)
                        row.update(deming_slope=p[0], slope_lo=lo[0], slope_hi=hi[0],
                                   deming_icpt=p[1], icpt_lo=lo[1], icpt_hi=hi[1])
                rows.append(row)
            # check: 95th percentiles (ASCAT raw over the object or the 300 km disk, SMAP over the disk or the object)
            s = sub.dropna(subset=["ascat_p95", "smap_p95"])
            row = dict(direction=direction, stratum=col, value=val, band="p95", n_pairs=len(s), n_weeks=s.week.nunique())
            if len(s):
                dp = (s.smap_p95 - s.ascat_p95).to_numpy()
                uw, W = week_sums(s.week.to_numpy(), np.stack([np.ones(len(s)), dp], 1))
                p, lo, hi = boot_stat(W, f_mean)
                row.update(mean_ascat40=s.ascat_p95.mean(), mean_smap=s.smap_p95.mean(), diff=p[0], diff_lo=lo[0], diff_hi=hi[0])
            rows.append(row)
    return pd.DataFrame(rows), df


# ---- method 2 ----
def cell_tables(res):
    # week -> aggregate per key
    keys = {}
    for r in res:
        for k, e in r["cells"].items():
            keys.setdefault(k, {}).setdefault((r["week"], r["held_out"]), []).append(e)
    rows, qrows = [], []
    pcts = (90, 99, 99.9)
    edges = np.arange(0, 100.01, 0.1)
    centres = 0.5 * (edges[:-1] + edges[1:])

    def combine(sel):
        """sel: list of (win, basin, sat, week, held_out, entry) -> per-week additive arrays."""
        out = {}
        for wk, ho, e in sel:
            o = out.setdefault(wk, dict(n=0, sd=0, sx=0, sy=0, hx=0, hy=0, ho=ho))
            for f in ("n", "sd", "sx", "sy", "hx", "hy"):
                o[f] = o[f] + e[f]
        return out

    for win in (90, 180):
        for bsel in ("natl", "npac", "all"):
            for ssel in ("all", 2, 3):
                for split in ("all", "held_out", "tune"):
                    sel = []
                    for (w, bn, sat), wks in keys.items():
                        if w != win or (bsel != "all" and bn != bsel) or (ssel != "all" and sat != ssel):
                            continue
                        for (wk, ho), es in wks.items():
                            if split != "all" and (split == "held_out") != ho:
                                continue
                            for e in es:
                                sel.append((wk, ho, e))
                    if not sel:
                        continue
                    pw = combine(sel)
                    wk = np.array(sorted(pw))
                    for b, (bname, lo_, hi_) in enumerate(BANDS_CELL):
                        N = np.array([pw[k]["n"][b] for k in wk])
                        if N.sum() == 0:
                            continue
                        W = np.stack([N, [pw[k]["sd"][b] for k in wk]], 1)
                        keep = N > 0
                        p, lo, hi = boot_stat(W[keep], f_mean)
                        rows.append(dict(window_min=win, basin=bsel, sat=ssel, split=split, band=bname,
                                         n_cells=int(N.sum()), n_weeks=int(keep.sum()),
                                         mean_ascat40=sum(pw[k]["sx"][b] for k in wk) / N.sum(),
                                         mean_smap=sum(pw[k]["sy"][b] for k in wk) / N.sum(),
                                         diff=p[0], diff_lo=lo[0], diff_hi=hi[0]))
                    # all bands >= 25 kt
                    N = np.array([pw[k]["n"].sum() for k in wk])
                    W = np.stack([N, [pw[k]["sd"].sum() for k in wk]], 1)
                    if N.sum():
                        p, lo, hi = boot_stat(W[N > 0], f_mean)
                        rows.append(dict(window_min=win, basin=bsel, sat=ssel, split=split, band="25+",
                                         n_cells=int(N.sum()), n_weeks=int((N > 0).sum()),
                                         mean_ascat40=sum(pw[k]["sx"].sum() for k in wk) / N.sum(),
                                         mean_smap=sum(pw[k]["sy"].sum() for k in wk) / N.sum(),
                                         diff=p[0], diff_lo=lo[0], diff_hi=hi[0]))
                    if ssel == "all" and split == "all":
                        HX = np.array([pw[k]["hx"] for k in wk])
                        HY = np.array([pw[k]["hy"] for k in wk])
                        rng = np.random.default_rng(0)
                        idx = rng.integers(0, len(wk), size=(B, len(wk)))

                        def qs(H, tot=None):
                            c = np.cumsum(H, -1)
                            t = c[..., -1:]
                            out = []
                            for q in pcts:
                                i = (c < q / 100 * t).sum(-1)
                                out.append(centres[np.clip(i, 0, len(centres) - 1)])
                            return np.stack(out, -1)

                        px, py = qs(HX.sum(0)), qs(HY.sum(0))
                        bx = np.stack([qs(HX[i].sum(0)) for i in idx[:, :]]) if False else None
                        cx = np.cumsum(HX, 1)  # unused placeholder to keep memory small
                        # bootstrap in chunks
                        bxs, bys = [], []
                        for ch in np.array_split(idx, 20):
                            bxs.append(qs(HX[ch].sum(1)))
                            bys.append(qs(HY[ch].sum(1)))
                        bx, by = np.concatenate(bxs), np.concatenate(bys)
                        dq = by - bx
                        lo, hi = np.percentile(dq, [2.5, 97.5], axis=0)
                        n_all = int(HX.sum())
                        for j, q in enumerate(pcts):
                            qrows.append(dict(window_min=win, basin=bsel, percentile=q, n_cells=n_all,
                                              n_weeks=len(wk), ascat40_kt=px[j], smap_kt=py[j],
                                              diff=py[j] - px[j], diff_lo=lo[j], diff_hi=hi[j]))
    return pd.DataFrame(rows), pd.DataFrame(qrows)


# ---- method 4 ----
def rain_tables(res):
    parts = [r["rain"] for r in res if r["rain"] is not None]
    c = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    c["basin"] = np.where(c["basin"] == 1, "natl", "npac")
    df = pd.DataFrame(c)
    df["band"] = pd.cut(df.smap, [48, 56, 64, 1e9], right=False, labels=["48-56", "56-64", "64+"]).astype(str)
    rows = []
    for bsel in ("natl", "npac", "all"):
        for split in ("all", "held_out", "tune"):
            for band in ("all", "48-56", "56-64", "64+"):
                s = df
                if bsel != "all":
                    s = s[s.basin == bsel]
                if split != "all":
                    s = s[s.held_out == (split == "held_out")]
                if band != "all":
                    s = s[s.band == band]
                h = s[s.has]
                row = dict(table="share", basin=bsel, split=split, smap_band=band, n_smap48=len(s),
                           n_with_ascat180=len(h), n_no_ascat=len(s) - len(h), n_rain_flagged=int(h.arain.sum()))
                if len(h):
                    uw, W = week_sums(h.week.to_numpy(), np.stack([np.ones(len(h)), h.arain.to_numpy(float)], 1))
                    p, lo, hi = boot_stat(W, f_ratio)
                    row.update(share_rain=p[0], share_lo=lo[0], share_hi=hi[0], n_weeks=len(uw))
                    uw, W = week_sums(s.week.to_numpy(), np.stack([np.ones(len(s)), s.has.to_numpy(float)], 1))
                    p, lo, hi = boot_stat(W, f_ratio)
                    row.update(share_with_ascat=p[0])
                rows.append(row)
    h = df[df.has]
    for bsel in ("natl", "npac", "all"):
        for fl in (True, False):
            s = h[(h.arain == fl) & ((h.basin == bsel) | (bsel == "all"))]
            if not len(s):
                continue
            q = np.percentile(s.aspd, [10, 25, 50, 75, 90])
            rows.append(dict(table="ascat_speed", basin=bsel, rain_flagged=fl, n_with_ascat180=len(s),
                             n_weeks=s.week.nunique(), mean_ascat=s.aspd.mean(), mean_smap=s.smap.mean(),
                             mean_smap_minus_ascat=(s.smap - s.aspd).mean(),
                             ascat_p10=q[0], ascat_p25=q[1], ascat_p50=q[2], ascat_p75=q[3], ascat_p90=q[4],
                             frac_ascat_ge48=(s.aspd >= 48).mean(), frac_ascat_lt34=(s.aspd < 34).mean()))
    return pd.DataFrame(rows)


def fnum(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else ("%+.*f" % (d, x))


def ci(r, d=1):
    return "%s [%s, %s]" % (fnum(r["diff"], d), fnum(r["diff_lo"], d), fnum(r["diff_hi"], d))


def figure(df, ss):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style.use()
    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    lim = (38, 90)
    ax.plot(lim, lim, color=style.INK2, lw=1, label="1:1")
    for direction, mk, col, lab in (("ascat", "o", style.METHOD_COLORS["ascat"], "storm found in ASCAT40"),
                                    ("smap", "s", style.METHOD_COLORS["ens"], "storm found in SMAP")):
        s = df[df.direction == direction]
        ax.scatter(s.ascat40_peak, s.smap_peak, s=22, marker=mk, facecolors="none", edgecolors=col, alpha=0.7,
                   label="%s (n=%d)" % (lab, len(s)))
    # binned means by mean of the pair (ASCAT-selected pairs and all pairs pooled by direction ASCAT, the main one)
    for direction, col in (("ascat", style.METHOD_COLORS["ascat"]), ("smap", style.METHOD_COLORS["ens"])):
        for bname, lo_, hi_ in BANDS_PEAK[1:]:
            r = ss[(ss.direction == direction) & (ss.stratum == "all") & (ss.band == bname)].iloc[0]
            if r.n_pairs < 5:
                continue
            ax.errorbar(r.mean_ascat40, r.mean_ascat40 + r["diff"],
                        yerr=[[r["diff"] - r.diff_lo], [r.diff_hi - r["diff"]]], color=col, marker="D", ms=7,
                        capsize=3, lw=1.8, mec="white")
    r48 = ss[(ss.direction == "ascat") & (ss.stratum == "all") & (ss.band == "all")].iloc[0]
    s = df[(df.direction == "ascat")]
    m48 = s[0.5 * (s.ascat40_peak + s.smap_peak) >= 48]
    d = m48.smap_peak - m48.ascat40_peak
    uw, W = week_sums(m48.week.to_numpy(), np.stack([np.ones(len(m48)), d.to_numpy()], 1))
    p, lo, hi = boot_stat(W, f_mean)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("ASCAT40 storm peak (kt, equivalent-neutral)")
    ax.set_ylabel("SMAP peak within 300 km (kt, equivalent-neutral)")
    style.title(ax, "SMAP reads %.1f kt (%.1f to %.1f) %s ASCAT at storm-force peaks" % (
        abs(p[0]), lo[0], hi[0], "above" if p[0] > 0 else "below"),
        "ASCAT-selected pairs, mean peak 48+ kt, n=%d, %d weeks, winter 2025-26\n"
        "diamonds: band means (by mean of the two peaks), 95%% week-block intervals" % (len(m48), len(uw)))
    ax.set_title(ax.get_title(loc="left"), loc="left", fontsize=12, color=style.INK, pad=36)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_aspect("equal")
    return fig, (p[0], lo[0], hi[0], len(m48), len(uw))


def numbers_md(df, ss, cs, cq, rain, obs, fig_stat):
    L = ["# Storm-force truth: numbers", "",
         "SMAP minus ASCAT40 (equivalent-neutral 10 m wind, kt). Intervals: 95%, resampling whole ISO weeks (2000 reps). "
         "Bands are on the mean of the two peaks (method 1) or of the two cell values (method 2). Pairs found by both "
         "directions are listed in both. Winter 2025-26 (1 Nov - 31 Mar), 30-67N inside the natl and npac boxes.", ""]
    nb = df.groupby("direction").size().to_dict()
    both = int(df[df.direction == "ascat"].pair_id.isin(df[df.direction == "smap"].pair_id).sum())
    L += ["## Method 1: storm peaks per pass pair", "",
          "Pairs: %s; storm-passes found by both directions: %d" % (", ".join("%s-selected %d" % kv for kv in nb.items()), both),
          "Pairs by SMAP-ASCAT peak time gap: 0-90 min %d, 90-180 min %d" % (
              int((df.gap_pk <= 90).sum()), int((df.gap_pk > 90).sum())), "",
          "Figure title number (ASCAT-selected, mean peak 48+): diff %+.2f [%+.2f, %+.2f] kt, n=%d pairs, %d weeks" % fig_stat, ""]
    for direction in ("ascat", "smap"):
        L += ["### Direction: %s-selected" % direction, "",
              "| stratum | band | n pairs | n weeks | mean ASCAT40 | mean SMAP | SMAP - ASCAT40 [95%] | Deming slope [95%] | Deming intercept [95%] |",
              "|---|---|---|---|---|---|---|---|---|"]
        for _, r in ss[(ss.direction == direction)].iterrows():
            if r.n_pairs == 0:
                L.append("| %s=%s | %s | 0 | 0 | | | | | |" % (r.stratum, r.value, r.band))
                continue
            dem = ("%.2f [%.2f, %.2f]" % (r.deming_slope, r.slope_lo, r.slope_hi),
                   "%.1f [%.1f, %.1f]" % (r.deming_icpt, r.icpt_lo, r.icpt_hi)) if pd.notna(r.get("deming_slope")) else ("", "")
            L.append("| %s=%s | %s | %d | %d | %.1f | %.1f | %s | %s | %s |" % (
                r.stratum, r.value, r.band, r.n_pairs, r.n_weeks, r.mean_ascat40, r.mean_smap, ci(r), dem[0], dem[1]))
        L.append("")
    L += ["Band `p95`: SMAP p95 minus ASCAT raw p95 (the mean_ASCAT40 column holds the ASCAT p95); the instrument that "
          "selected the storm contributes its object, the other its 300 km disk.", ""]
    L += ["## Method 2: cell pairs (same grid cell, ASCAT40 vs SMAP)", "",
          "| window | basin | sat | split | band | n cells | mean ASCAT40 | mean SMAP | SMAP - ASCAT40 [95%] |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in cs[(cs.sat == "all")].iterrows():
        L.append("| %d | %s | %s | %s | %s | %d | %.1f | %.1f | %s |" % (
            r.window_min, r.basin, r.sat, r.split, r.band, r.n_cells, r.mean_ascat40, r.mean_smap, ci(r)))
    L += ["", "Per satellite (split=all):", "",
          "| window | basin | sat | band | n cells | SMAP - ASCAT40 [95%] |", "|---|---|---|---|---|---|"]
    for _, r in cs[(cs.sat != "all") & (cs.split == "all")].iterrows():
        L.append("| %d | %s | %s | %s | %d | %s |" % (r.window_min, r.basin, r.sat, r.band, r.n_cells, ci(r)))
    L += ["", "### Quantile-quantile of common cells", "",
          "| window | basin | percentile | n cells | n weeks | ASCAT40 kt | SMAP kt | SMAP - ASCAT40 [95%] |", "|---|---|---|---|---|---|---|---|"]
    for _, r in cq.iterrows():
        L.append("| %d | %s | %s | %d | %d | %.1f | %.1f | %s |" % (
            r.window_min, r.basin, r.percentile, r.n_cells, r.n_weeks, r.ascat40_kt, r.smap_kt, ci(r)))
    L += ["", "## Method 3: buoys and ships", ""]
    if obs is not None and len(obs):
        L += ["| instrument | platform | basin | band | n | n weeks | bias (instrument - obs) [95%] | SD | mean obs | mean instrument |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in obs.iterrows():
            L.append("| %s | %s | %s | %s | %d | %d | %s | %s | %s | %s |" % (
                r.instrument, r.platform, r.basin, r.band, r.n, r.n_weeks,
                ci(dict(diff=r["bias"], diff_lo=r.bias_lo, diff_hi=r.bias_hi)) if pd.notna(r.bias) else "n/a",
                "%.1f" % r.sd if pd.notna(r.sd) else "n/a", "%.1f" % r.mean_obs, "%.1f" % r.mean_inst))
    else:
        L.append("not available")
    L += ["", "## Method 4: rain", "",
          "SMAP cells >= 48 kt (domain, SMAP passes of each day) with an ASCAT cell (any rain flag) at the same cell within 180 min.", "",
          "| basin | split | SMAP band | n SMAP 48+ | n with ASCAT | n without | n rain-flagged | share rain-flagged [95%] | n weeks |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in rain[rain.table == "share"].iterrows():
        sh = "n/a" if pd.isna(r.get("share_rain")) else "%.1f%% [%.1f%%, %.1f%%]" % (100 * r.share_rain, 100 * r.share_lo, 100 * r.share_hi)
        L.append("| %s | %s | %s | %d | %d | %d | %d | %s | %s |" % (
            r.basin, r.split, r.smap_band, r.n_smap48, r.n_with_ascat180, r.n_no_ascat, r.n_rain_flagged, sh,
            "" if pd.isna(r.get("n_weeks")) else int(r.n_weeks)))
    L += ["", "ASCAT speed (kt, intercalibrated equivalent-neutral) in those cells:", "",
          "| basin | rain flagged | n | n weeks | mean ASCAT | mean SMAP | mean SMAP - ASCAT | p10 | p25 | p50 | p75 | p90 | share ASCAT >= 48 | share ASCAT < 34 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in rain[rain.table == "ascat_speed"].iterrows():
        L.append("| %s | %s | %d | %d | %.1f | %.1f | %+.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.2f | %.2f |" % (
            r.basin, r.rain_flagged, r.n_with_ascat180, r.n_weeks, r.mean_ascat, r.mean_smap, r.mean_smap_minus_ascat,
            r.ascat_p10, r.ascat_p25, r.ascat_p50, r.ascat_p75, r.ascat_p90, r.frac_ascat_ge48, r.frac_ascat_lt34))
    return "\n".join(L) + "\n"


def main():
    RES.mkdir(exist_ok=True)
    with open(WORK / "day_results.pkl", "rb") as f:
        res = pickle.load(f)
    df = pd.DataFrame([x for r in res for x in r["rows"]])
    # pair ids: a storm-pass found both ways (same date, ASCAT satellite pass and SMAP node; ASCAT peaks within 200 km)
    from compare import dist_km
    df = df.reset_index(drop=True)
    df["pair_id"] = np.arange(len(df))
    a = df[df.direction == "ascat"]
    for i, r in df[df.direction == "smap"].iterrows():
        c = a[(a.date == r.date) & (a.sat == r.sat) & (a.ptype == r.ptype) & (a.node == r.node)]
        if len(c):
            d = dist_km(r.other_lat, r.other_lon, c.lat.to_numpy(), c.lon.to_numpy())
            if d.min() <= 200:
                df.loc[i, "pair_id"] = c.pair_id.iloc[int(np.argmin(d))]
    ss, df = storm_summary(df)
    out = df.drop(columns=["mean_pk", "d", "gapbin", "split"]).copy()
    out["iso_week"] = out.week
    out = out.drop(columns=["week"]).round(3)
    out.to_csv(RES / "storm_pairs.csv", index=False)
    ss.round(3).to_csv(RES / "storm_summary.csv", index=False)
    cs, cq = cell_tables(res)
    cs.round(3).to_csv(RES / "cell_summary.csv", index=False)
    cq.round(3).to_csv(RES / "cell_qq.csv", index=False)
    rain = rain_tables(res)
    rain.round(4).to_csv(RES / "rain.csv", index=False)
    op = WORK / "obs_summary.csv"
    obs = pd.read_csv(op) if op.exists() else None
    if obs is not None:
        obs.round(3).to_csv(RES / "obs_summary.csv", index=False)
    fig, stat = figure(df, ss)
    png, svg = style.save(fig, RES / "peaks.png")
    svg.unlink()
    (RES / "numbers.md").write_text(numbers_md(df, ss, cs, cq, rain, obs, stat))
    print("written", [p.name for p in sorted(RES.iterdir())])


if __name__ == "__main__":
    main()
