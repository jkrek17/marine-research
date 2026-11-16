"""Tune, score and rank the candidates (design.md; BUILD.md "analyze.py"). Reads run.py's parts, writes results/*.csv
and params.json.

    python3 analyze.py [--scores DIR] [--n-boot 2000]

1. Tuning (leave-one-month-out, tune weeks only). For each tuned family (cap for al/ald, X for od, offset for off,
   weight preset for wb; per lead, weights also per basin) and each fold month: the training cases are the
   split == "tune" cases whose cycle AND valid time are outside held-out weeks and whose cycle is not inside the
   fold month nor within 7 days of its edges. Objective: pooled mean position error against the mean analysis
   (headline truth), among settings whose RMSE is at most 0.15 hPa worse than IFS and false lows at most 0.15
   per map more than IFS on the same training cases; if none qualifies the untuned setting stands. The
   setting chosen with every tune case is the final one (params.json) and is what the held-out weeks see.
2. Scoring. Untuned candidates on every winter week; tuned ones ("<name>_t") on the out-of-fold forecasts of the
   tune weeks; the held-out weeks (final setting for tuned ones) are a sign check only. Differences from IFS
   are matched case by case, position pooled over analysed lows; 95% interval and p from resampling whole ISO
   weeks (rk.compare.boot_sums, 2000 draws); Benjamini-Hochberg q = 0.10 over candidates x leads (headline truth).
3. The win rule of design.md, applied mechanically (RULE below), winners per lead for "best possible" and "AWIPS
   inputs", a separate best-on-RMSE list, the outlier-drop risk table and the strong-low depth tables.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
from rk import paths, compare

RES = HERE / "results"
LEADS = tuple(range(24, 169, 24))
KEYS = ["basin", "cycle", "lead", "truth"]
TRUTHS = ("gfs", "ifs", "mean")
MONTHS = ("202511", "202512", "202601", "202602", "202603")
PURGE = pd.Timedelta(days=7)
RULE = dict(min_km=10.0, min_frac=0.05, rmse_slack=0.15, false_slack=0.15, depth_slack=0.5, q=0.10)
# tuned family -> grid key; untuned label of the setting column
FAMILY = {"al": "cap", "ald": "cap", "al_gfe": "cap", "ald_gfe": "cap", "al_gfe2": "cap", "ald_gfe2": "cap",
          "od": "X", "od_gfe": "X", "od_gfe2": "X", "off": "off", "wb": "w", "wb_gfe": "w", "wb_gfe2": "w"}
UNTUNED = {"al": "cap=450", "ald": "cap=450", "al_gfe": "cap=450", "ald_gfe": "cap=450", "al_gfe2": "cap=450",
           "ald_gfe2": "cap=450", "od": "X=300", "od_gfe": "X=300", "od_gfe2": "X=300", "wb": "w=eq",
           "wb_gfe": "w=eq", "wb_gfe2": "w=eq"}
FALLBACK = dict(UNTUNED, off="off=0")
PER_BASIN = {"wb", "wb_gfe", "wb_gfe2"}
# simplicity ranks for ties (design.md: simpler first, then the one GFE can use)
RANK = {"gfs": 1, "ifs": 1, "aifs": 1, "aigfs": 1, "m_gi": 2, "m_gia": 2, "m_gif": 2, "gefs": 3, "ens": 3,
        "aifsens": 3, "grand": 3, "wb": 4, "wb_gfe": 4, "wb_gfe2": 4, "od": 5, "od_gfe": 5, "od_gfe2": 5,
        "al": 6, "al_gfe": 6, "al_gfe2": 6, "bowl": 7, "bowl_gfe": 7, "bowl_gfe2": 7, "off": 7, "ald": 8,
        "ald_gfe": 8, "ald_gfe2": 8, "al_gi": 6, "ald_gi": 8, "al_det": 6, "ald_det": 8}
GFE_OK = {"gfs", "ifs", "aigfs", "m_gi", "m_gia", "gefs", "wb_gfe", "wb_gfe2", "al_gfe", "al_gfe2", "ald_gfe",
          "ald_gfe2", "bowl_gfe", "bowl_gfe2", "od_gfe", "od_gfe2"}
NOT_FIELDS = {"vote", "an_gfs", "an_ifs"}


def scores_dir(a):
    return Path(a) if a else Path(__import__("os").environ.get("MSLP_BLEND_SCORES") or
                                  paths.cache("extra", "mslp-blend-d7", "scores"))


def read(d, name, cols=None):
    ps = sorted((d / "parts").glob("*/%s_*.parquet" % name))
    if not ps:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p, columns=cols) for p in ps], ignore_index=True)
    for c in ("basin", "truth", "cand", "setting", "split", "week", "month"):
        if c in df:
            df[c] = df[c].astype("category")
    return df


def base_label(cand, setting):
    return setting in ("base", UNTUNED.get(cand))


# ------------------------------------------------------------------------------------------------ case table
def case_table(F, L):
    g = L.assign(strong=L.an_hpa < 980).groupby(KEYS + ["cand", "setting"], observed=True)
    a = g.agg(pos_sum=("pos_km", "sum"), n_lows=("pos_km", "size"), posh_sum=("pos_h", "sum"),
              hit_sum=("hit", "sum")).reset_index()
    s = L[L.an_hpa < 980].groupby(KEYS + ["cand", "setting"], observed=True).agg(
        sd_n=("depth_err_hpa", lambda x: int(x.notna().sum())), sd_bias_sum=("depth_err_hpa", "sum"),
        sd_abs_sum=("depth_err_hpa", lambda x: float(np.abs(x).sum()))).reset_index()
    C = F.merge(a, on=KEYS + ["cand", "setting"], how="left").merge(s, on=KEYS + ["cand", "setting"], how="left")
    for c in ("pos_sum", "n_lows", "posh_sum", "hit_sum", "sd_n", "sd_bias_sum", "sd_abs_sum"):
        C[c] = C[c].fillna(0.0)
    C["cycle"] = pd.to_datetime(C["cycle"])
    C["valid"] = pd.to_datetime(C["valid"])
    return C


# ------------------------------------------------------------------------------------------------ tuning
def tuning(C, fams_present, grid_w):
    """Returns (choices DataFrame [cand, lead, basin, fold, setting], final dict for params.json)."""
    ref = C[(C.cand == "ifs") & (C.setting == "base") & (C.truth == "mean")][
        ["basin", "cycle", "lead", "rmse", "false_n"]].rename(columns={"rmse": "rmse_r", "false_n": "false_r"})
    fam = C[C.cand.isin(fams_present) & (C.truth == "mean") & (C.split == "tune") & (~C.valid_held)]
    M = fam.merge(ref, on=["basin", "cycle", "lead"], how="inner")
    M["month"] = M["month"].astype(str)
    M["d_rmse"] = M.rmse - M.rmse_r
    M["d_false"] = M.false_n - M.false_r
    out = []
    folds = list(MONTHS) + ["final"]
    for fold in folds:
        if fold == "final":
            T = M
        else:
            y, m = int(fold[:4]), int(fold[4:])
            start = pd.Timestamp(y, m, 1)
            end = start + pd.offsets.MonthBegin(1)
            T = M[(M.cycle < start - PURGE) | (M.cycle >= end + PURGE)]
        for cand, key in FAMILY.items():
            if cand not in fams_present:
                continue
            Tc = T[T.cand == cand]
            by = ["lead", "basin"] if cand in PER_BASIN else ["lead"]
            agg = Tc.groupby(by + ["setting"], observed=True).agg(
                ps=("pos_sum", "sum"), nl=("n_lows", "sum"), dr=("d_rmse", "mean"), df=("d_false", "mean"),
                n=("rmse", "size")).reset_index()
            agg["obj"] = agg.ps / agg.nl.clip(lower=1)
            agg["ok"] = (agg.dr <= RULE["rmse_slack"]) & (agg.df <= RULE["false_slack"])
            for lead in LEADS:
                for basin in ("natl", "npac"):
                    sel = agg[(agg.lead == lead) & ((agg.basin == basin) if cand in PER_BASIN else True)]
                    sel = sel[sel.setting.isin([s for s in sel.setting.unique() if s.split("=")[0] == key])]
                    ok = sel[sel.ok]
                    if len(ok):
                        pick = ok.sort_values("obj").setting.iloc[0]
                        why = "guards ok"
                    else:
                        pick, why = FALLBACK[cand], "no setting passes the guards: untuned stands"
                    out.append((cand, lead, basin, fold, pick, why, int(sel.n.max()) if len(sel) else 0))
    ch = pd.DataFrame(out, columns=["cand", "lead", "basin", "fold", "setting", "note", "n_cases"])
    fin = ch[ch.fold == "final"]
    params = {"cap": {}, "X": {}, "off": {}, "w": {"natl": {}, "npac": {}}, "note": (
        "final settings chosen on all tune-week cases (no held-out, valid time outside held-out weeks); "
        "cap/X/off pooled over both basins and listed per candidate family; w per basin")}
    for cand, key in FAMILY.items():
        if cand not in fams_present:
            continue
        for lead in LEADS:
            if key == "w":
                for basin in ("natl", "npac"):
                    s = fin[(fin.cand == cand) & (fin.lead == lead) & (fin.basin == basin)].setting.iloc[0]
                    params["w"][basin].setdefault(cand, {})[str(lead)] = {"preset": s[2:], "weights": grid_w.get(s[2:])}
            else:
                s = fin[(fin.cand == cand) & (fin.lead == lead) & (fin.basin == "natl")].setting.iloc[0]
                params[key].setdefault(cand, {})[str(lead)] = float(s.split("=")[1])
    return ch, params


def select_tuned(df, ch):
    """Rows of df (columns cand, lead, basin, split, month, setting) that are the tuned setting, relabelled
    cand + '_t': out-of-fold month for tune-week cycles, the final setting for held-out ones."""
    d = df[df.cand.isin(list(FAMILY))].copy()
    d["fold"] = np.where(d.split.astype(str) == "tune", d.month.astype(str), "final")
    d["cand"] = d.cand.astype(str)
    d["basin"] = d.basin.astype(str)
    chm = ch.assign(cand=ch.cand.astype(str))
    chm = chm[["cand", "lead", "basin", "fold", "setting"]].rename(columns={"setting": "chosen"})
    d = d.merge(chm, on=["cand", "lead", "basin", "fold"], how="inner")
    d["setting"] = d.setting.astype(str)
    d = d[d.setting == d.chosen].drop(columns=["chosen", "fold"])
    d["cand"] = d.cand + "_t"
    return d


def untuned_rows(df):
    c = df.cand.astype(str)
    s = df.setting.astype(str)
    keep = (s == "base") | ((s == c.map(UNTUNED)) & c.isin(list(UNTUNED))) | (s == "default")
    # tuned families' untuned value is labelled both "cap=450" and "default": keep one
    keep &= ~((s == c.map(UNTUNED)) & c.isin(list(UNTUNED)))
    d = df[keep & ~c.isin(["off"])].copy()
    d["cand"] = d.cand.astype(str)
    return d


# ------------------------------------------------------------------------------------------------ stats
def week_codes(w):
    return pd.factorize(pd.Series(w).astype(str), sort=True)[0]


def boot(wk, stats, f, n_boot, seed=0):
    """f maps column sums (k,) or (n, k) to the statistic; returns (value, lo, hi, p two-sided)."""
    tot, dr = compare.boot_sums(wk, stats, n_boot=n_boot, seed=seed)
    v = float(f(tot))
    d = np.asarray(f(dr))
    lo, hi = np.percentile(d, [2.5, 97.5])
    p = 2 * min((np.sum(d >= 0) + 1) / (n_boot + 1), (np.sum(d <= 0) + 1) / (n_boot + 1))
    return v, float(lo), float(hi), float(min(p, 1.0))


def pair(E, a, b):
    """Case-matched merge of entry a (candidate) with entry b (reference) from the entries frame E."""
    A = E[E.entry == a].set_index(KEYS)
    B = E[E.entry == b].set_index(KEYS)
    j = A.join(B, how="inner", lsuffix="_c", rsuffix="_r").reset_index()
    return j


def diffs(j, n_boot, full=True):
    """Position (km, pooled over lows), RMSE, false lows per map, strong-low |bias| change for a joined frame."""
    out = {"n_cases": len(j), "n_lows": int(j.n_lows_c.sum()), "n_weeks": int(j.week_c.nunique())}
    if not len(j) or j.n_lows_c.sum() == 0:
        return dict(out, **{k: np.nan for k in ("dpos", "dpos_lo", "dpos_hi", "p_pos", "pos_ref", "drmse", "drmse_lo",
                                               "drmse_hi", "p_rmse", "dfalse", "ddepth")})
    wk = week_codes(j.week_c)
    out["pos_ref"] = float(j.pos_sum_r.sum() / j.n_lows_c.sum())
    out["pos_c"] = float(j.pos_sum_c.sum() / j.n_lows_c.sum())
    st = np.c_[j.pos_sum_c - j.pos_sum_r, j.n_lows_c]
    if full:
        v, lo, hi, p = boot(wk, st, lambda s: s[..., 0] / s[..., 1], n_boot)
        out.update(dpos=v, dpos_lo=lo, dpos_hi=hi, p_pos=p)
        r = j.rmse_c - j.rmse_r
        ok = r.notna().to_numpy()
        if ok.any():
            v, lo, hi, p = boot(wk[ok], np.c_[r[ok], np.ones(ok.sum())], lambda s: s[..., 0] / s[..., 1], n_boot)
            out.update(drmse=v, drmse_lo=lo, drmse_hi=hi, p_rmse=p)
        else:
            out.update(drmse=np.nan, drmse_lo=np.nan, drmse_hi=np.nan, p_rmse=np.nan)
    else:
        out.update(dpos=float(st[:, 0].sum() / st[:, 1].sum()), drmse=float((j.rmse_c - j.rmse_r).mean()))
    out["dfalse"] = float((j.false_n_c - j.false_n_r).mean())
    sn = j.sd_n_c.sum()
    out["strong_n"] = int(sn)
    if sn >= 5:
        out["ddepth"] = float(abs(j.sd_bias_sum_c.sum() / sn) - abs(j.sd_bias_sum_r.sum() / max(j.sd_n_r.sum(), 1)))
    else:
        out["ddepth"] = np.nan
    return out


def bh(p, q):
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.full(len(p), np.nan)
    if not ok.any():
        return out
    pp = p[ok]
    o = np.argsort(pp)
    m = len(pp)
    adj = np.minimum.accumulate((pp[o] * m / (np.arange(m) + 1))[::-1])[::-1]
    r = np.empty(m)
    r[o] = np.minimum(adj, 1.0)
    out[ok] = r
    return out


# ------------------------------------------------------------------------------------------------ tables
def by_lead_table(E, Lsel, Dsel):
    rows = []
    E = E.copy()
    for (entry, lead, truth), g in E.groupby(["entry", "lead", "truth"], observed=True):
        for basin, gg in [("all", g)] + [(b, g[g.basin == b]) for b in ("natl", "npac")]:
            if not len(gg):
                continue
            n = gg.n_lows.sum()
            rows.append(dict(entry=entry, lead=lead, truth=truth, basin=basin, n_cases=len(gg), n_lows=int(n),
                             pos_km=gg.pos_sum.sum() / n if n else np.nan,
                             pos_hung_km=gg.posh_sum.sum() / n if n else np.nan,
                             hit300=gg.hit_sum.sum() / n if n else np.nan, rmse=gg.rmse.mean(), bias=gg.bias.mean(),
                             rmse_ls=gg.rmse_ls.mean(), sharp=gg.sharp.mean(), false_per_map=gg.false_n.mean(),
                             fc_lows_per_map=gg.n_fc.mean(),
                             strong_n=int(gg.sd_n.sum()),
                             strong_bias=gg.sd_bias_sum.sum() / gg.sd_n.sum() if gg.sd_n.sum() else np.nan,
                             strong_mae=gg.sd_abs_sum.sum() / gg.sd_n.sum() if gg.sd_n.sum() else np.nan))
    T = pd.DataFrame(rows)
    T.loc[T.entry == "vote", "pos_hung_km"] = np.nan      # the vote's lows are not matched one-to-one (not computed)
    # medians and track split from the low rows
    if len(Lsel):
        g = Lsel.groupby(["entry", "lead", "truth"], observed=True)
        m = g.agg(pos_median_km=("pos_km", "median"), along_km=("along_km", "mean"),
                  cross_abs_km=("cross_km", lambda x: float(np.nanmean(np.abs(x))) if x.notna().any() else np.nan),
                  cross_km=("cross_km", "mean")).reset_index()
        T = T.merge(m.assign(basin="all"), on=["entry", "lead", "truth", "basin"], how="left")
    if len(Dsel):
        g = Dsel.groupby(["entry", "lead", "truth"], observed=True).agg(
            fdeep_n=("err_hpa", "size"), fdeep_bias=("err_hpa", "mean"),
            fdeep_mae=("err_hpa", lambda x: float(np.abs(x).mean()))).reset_index()
        T = T.merge(g.assign(basin="all"), on=["entry", "lead", "truth", "basin"], how="left")
    return T


def risk_table(R):
    if not len(R):
        return pd.DataFrame()
    R = R[(R.truth == "mean") & R.drop_err_km.notna()]
    g = R.groupby(["cand", "setting", "lead", "basin", "model"], observed=True)
    t = g.agg(n_dropped=("closest", "size"), share_closest=("closest", "mean"),
              drop_err_km=("drop_err_km", "mean"), best_other_km=("best_other_km", "mean"),
              dist_to_consensus_km=("dist_km", "mean"), n_weeks=("week", "nunique")).reset_index()
    a = R.groupby(["cand", "setting", "lead"], observed=True).agg(
        n_dropped=("closest", "size"), share_closest=("closest", "mean"), drop_err_km=("drop_err_km", "mean"),
        best_other_km=("best_other_km", "mean"), dist_to_consensus_km=("dist_km", "mean"),
        n_weeks=("week", "nunique")).reset_index().assign(basin="all", model="all")
    return pd.concat([t, a], ignore_index=True).sort_values(["cand", "setting", "lead", "basin", "model"])


def downstream(E, n_boot, tag=""):
    """Paired differences from IFS, the win rule and the winners for an entries frame E (columns as built in
    main). Writes diffs_vs_ifs{tag}.csv, win_rule{tag}.csv, winners{tag}.csv; returns (Dif, Win)."""
    entries = sorted(set(E.entry) - {"ifs"})
    # ---- paired differences vs IFS
    rows = []
    Eg = {k: g for k, g in E.groupby(["lead", "truth"])}
    for entry in entries:
        for lead in LEADS:
            for truth in TRUTHS:
                for basin in ("all", "natl", "npac"):
                    for sub in ("main", "held"):
                        Em = Eg.get((lead, truth))
                        if Em is None:
                            continue
                        Em = Em[Em[sub]]
                        if basin != "all":
                            Em = Em[Em.basin == basin]
                        Ec = Em[Em.entry == entry]
                        Er = Em[(Em.entry == "ifs")]
                        if entry.endswith("_t") and sub == "main":
                            Er = Er[Er.split.astype(str) == "tune"]
                        if not len(Ec):
                            continue
                        j = Ec.set_index(KEYS).join(Er.set_index(KEYS), how="inner", lsuffix="_c",
                                                      rsuffix="_r").reset_index()
                        full = basin == "all" and sub == "main"
                        r = diffs(j, n_boot, full=full)
                        rows.append(dict(entry=entry, lead=lead, truth=truth, basin=basin, subset=sub, **r))
        print("diffs", tag, entry, flush=True)
    Dif = pd.DataFrame(rows)
    # BH over entries x leads on the headline truth, all-weeks/out-of-fold, both basins pooled
    m = (Dif.truth == "mean") & (Dif.basin == "all") & (Dif.subset == "main") & Dif.entry.isin(
        [e for e in entries if e not in NOT_FIELDS or e == "vote"])
    Dif.loc[m, "q_pos"] = bh(Dif.loc[m, "p_pos"].to_numpy(), RULE["q"])
    Dif.loc[m, "q_rmse"] = bh(Dif.loc[m, "p_rmse"].to_numpy(), RULE["q"])
    Dif.to_csv(RES / ("diffs_vs_ifs%s.csv" % tag), index=False)

    # ---- win rule
    W = []
    for (entry, lead), g in Dif.groupby(["entry", "lead"]):
        h = g[(g.truth == "mean") & (g.basin == "all") & (g.subset == "main")]
        if not len(h):
            continue
        h = h.iloc[0]
        sign = lambda t, b="all", s="main": g[(g.truth == t) & (g.basin == b) & (g.subset == s)].dpos
        neg = lambda x: bool(len(x) and x.iloc[0] < 0)
        c = {}
        c["pos_size"] = bool(h.dpos <= -max(RULE["min_km"], RULE["min_frac"] * h.pos_ref)) if np.isfinite(h.dpos) else False
        c["pos_interval"] = bool(h.dpos_hi < 0) if np.isfinite(h.dpos_hi) else False
        c["pos_bh"] = bool(h.q_pos <= RULE["q"]) if np.isfinite(h.q_pos) else False
        c["rmse"] = bool(h.drmse_hi <= RULE["rmse_slack"]) if np.isfinite(h.drmse_hi) else False
        c["false"] = bool(h.dfalse <= RULE["false_slack"]) if np.isfinite(h.dfalse) else False
        c["depth"] = bool(h.ddepth <= RULE["depth_slack"]) if np.isfinite(h.ddepth) else True   # NaN: too few strong lows
        c["sign_gfs_ifs"] = neg(sign("gfs")) and neg(sign("ifs"))
        c["sign_basins"] = neg(sign("mean", "natl")) and neg(sign("mean", "npac"))
        c["sign_held"] = neg(sign("mean", "all", "held"))
        win = all(c.values()) and entry not in NOT_FIELDS
        # mirror: best field on RMSE
        mr = (bool(h.drmse_hi < 0) if np.isfinite(h.drmse_hi) else False) and bool(h.q_rmse <= RULE["q"]) \
            if np.isfinite(h.q_rmse) else False
        mr = mr and bool(h.dpos <= RULE["min_km"]) and c["false"] and c["depth"]
        for t in ("gfs", "ifs"):
            x = g[(g.truth == t) & (g.basin == "all") & (g.subset == "main")].drmse
            mr = mr and bool(len(x) and x.iloc[0] < 0)
        W.append(dict(entry=entry, lead=lead, win=win, win_rmse=bool(mr) and entry not in NOT_FIELDS,
                      dpos=h.dpos, dpos_lo=h.dpos_lo, dpos_hi=h.dpos_hi, pos_ref=h.pos_ref, drmse=h.drmse,
                      drmse_hi=h.drmse_hi, dfalse=h.dfalse, ddepth=h.ddepth, q_pos=h.q_pos, **c))
    Win = pd.DataFrame(W)
    Win.to_csv(RES / ("win_rule%s.csv" % tag), index=False)

    # ---- winners per lead: best position among passers; ties (interval of difference contains 0) go to the simpler
    def base_of(e):
        return e[:-2] if e.endswith("_t") else e

    def rank(e):
        return RANK.get(base_of(e), 9) * 2 + (1 if e.endswith("_t") else 0)

    def pick(pool, lead, col):
        P = Win[(Win.lead == lead) & (Win[col]) & Win.entry.isin(pool)]
        if not len(P):
            return None, []
        key = "dpos" if col == "win" else "drmse"
        best = P.sort_values(key).iloc[0]
        tied = [best.entry]
        for e in P.entry:
            if e == best.entry:
                continue
            Eb = E[(E.lead == lead) & (E.truth == "mean") & (E.entry.isin([e, best.entry])) & E.main]
            jj = pair(Eb, e, best.entry)
            jj = jj.rename(columns={})
            if not len(jj):
                continue
            wk = week_codes(jj.week_c)
            if key == "dpos":
                st = np.c_[jj.pos_sum_c - jj.pos_sum_r, jj.n_lows_c]
                v, lo, hi, _ = boot(wk, st, lambda s: s[..., 0] / s[..., 1], n_boot)
            else:
                x = (jj.rmse_c - jj.rmse_r)
                v, lo, hi, _ = boot(wk, np.c_[x, np.ones(len(x))], lambda s: s[..., 0] / s[..., 1], n_boot)
            if lo <= 0 <= hi:
                tied.append(e)
        tied = sorted(tied, key=lambda e: (rank(e), 0 if base_of(e) in GFE_OK else 1))
        return tied[0], tied

    allp = sorted(set(Win.entry))
    gfe = [e for e in allp if base_of(e) in GFE_OK]
    gfe_noaig = [e for e in gfe if not (base_of(e) in ("aigfs", "m_gia") or (base_of(e).endswith("_gfe") and "gfe2" not in base_of(e)))]
    wins = []
    for lead in LEADS:
        for label, pool, col in (("best possible", allp, "win"), ("AWIPS inputs", gfe, "win"),
                                 ("AWIPS inputs without AI-GFS", gfe_noaig, "win"),
                                 ("best field on RMSE", allp, "win_rmse")):
            w, tied = pick(pool, lead, col)
            wins.append(dict(lead=lead, answer=label, winner=w or "none passes (IFS stays)", tied="|".join(tied),
                             n_pass=int(Win[(Win.lead == lead) & Win[col] & Win.entry.isin(pool)].shape[0])))
    pd.DataFrame(wins).to_csv(RES / ("winners%s.csv" % tag), index=False)

    return Dif, Win


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores")
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()
    d = scores_dir(a.scores)
    RES.mkdir(exist_ok=True)
    F, L, D, R = read(d, "field"), read(d, "lows"), read(d, "fdeep"), read(d, "risk")
    print("rows: field %d lows %d fdeep %d risk %d" % (len(F), len(L), len(D), len(R)), flush=True)
    C = case_table(F, L)
    import candidates
    grid_w = candidates.grid_values()["w"]
    fams = sorted(set(C.cand.astype(str)) & set(FAMILY))

    # ---- tuning
    ch, params = tuning(C, fams, grid_w)
    ch.to_csv(RES / "tuning_choices.csv", index=False)
    with open(RES / "params.json", "w") as f:
        json.dump(params, f, indent=1)
    print("tuned families:", fams, flush=True)

    # ---- entries
    Cu, Ct = untuned_rows(C), select_tuned(C, ch)
    Cu["entry"], Ct["entry"] = Cu.cand, Ct.cand
    E = pd.concat([Cu, Ct], ignore_index=True)
    E["basin"] = E.basin.astype(str)
    E["truth"] = E.truth.astype(str)
    Lu, Lt = untuned_rows(L), select_tuned(L, ch)
    Lu["entry"], Lt["entry"] = Lu.cand, Lt.cand
    Ls = pd.concat([Lu, Lt], ignore_index=True)
    Du, Dt = untuned_rows(D), select_tuned(D, ch)
    Du["entry"], Dt["entry"] = Du.cand, Dt.cand
    Ds = pd.concat([Du, Dt], ignore_index=True)
    is_tuned = E.entry.str.endswith("_t")
    # evaluation sets: untuned = every winter week, tuned = out-of-fold (tune weeks); held-out separately
    E["main"] = np.where(is_tuned, E.split.astype(str) == "tune", True)
    E["held"] = E.split.astype(str) == "held_out"
    Ls["main"] = np.where(Ls.entry.str.endswith("_t"), Ls.split.astype(str) == "tune", True)
    Ds["main"] = np.where(Ds.entry.str.endswith("_t"), Ds.split.astype(str) == "tune", True)

    # tuned entries need tune-week cases: the AI-GFS runs sit almost entirely in held-out weeks (20 tune cases),
    # so their tuned versions are dropped (not scored on a handful of cases); their untuned versions stay.
    cnt = E[E.main & (E.truth == "mean") & (E.lead == 48)].groupby("entry").size()
    small = [e for e in cnt.index if e.endswith("_t") and cnt[e] < 60]
    if small:
        print("dropped tuned entries with fewer than 60 tune-week cases:", small, flush=True)
        E, Ls, Ds = E[~E.entry.isin(small)], Ls[~Ls.entry.isin(small)], Ds[~Ds.entry.isin(small)]
        pd.Series(small, name="dropped_entry").to_csv(RES / "dropped_tuned_entries.csv", index=False)

    # ---- by-lead descriptive table (main sets)
    T = by_lead_table(E[E.main], Ls[Ls.main], Ds[Ds.main])
    T.to_csv(RES / "by_lead.csv", index=False)
    print("by_lead", len(T), flush=True)

    Dif, Win = downstream(E, a.n_boot)

    # ---- outlier risk, strong low depth, noise floor, vote
    rt = risk_table(R)
    rt.to_csv(RES / "outlier_risk.csv", index=False)
    sd = T[(T.truth == "mean") & (T.basin == "all")][["entry", "lead", "strong_n", "strong_bias", "strong_mae",
                                                      "fdeep_n", "fdeep_bias", "fdeep_mae"]]
    sd.to_csv(RES / "strong_depth.csv", index=False)
    nf = T[T.entry.isin(["an_gfs", "an_ifs"]) & (T.basin == "all")][["entry", "lead", "truth", "n_cases", "rmse", "bias",
                                                                       "rmse_ls", "pos_km", "pos_median_km"]]
    nf.to_csv(RES / "noise_floor.csv", index=False)
    print("done; tables in", RES)


if __name__ == "__main__":
    main()
