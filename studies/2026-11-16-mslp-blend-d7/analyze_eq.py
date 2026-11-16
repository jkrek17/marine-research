"""POST HOC analysis at equal false lows (lead's request 2026-11-16). Needs rescore.py's output.

    python3 analyze_eq.py [--n-boot 2000]

Reads rescore.py (prominence-thinned scores, T index k over TS) and the first analysis's tuning choices
(results/tuning_choices.csv, for the weighted-blend presets). Writes results/*_eq*.csv, *_raw2*.csv, *_water*.csv:
  1. Raw threshold (T = 0) for every re-scored candidate, so the first analysis and the post hoc candidates sit in
     one table (tag _raw2) and again restricted to analysed lows over open water (_raw_water).
  2. Equal false lows (tag _eq, _eq_water): the target R per lead and basin is the raw false-low rate of `al` (the
     least-false main candidate) on the same cases; each entry gets the prominence threshold T whose false rate is
     closest to R without exceeding it, chosen by leave-one-month-out on tune weeks (7-day purge, cases whose
     valid time is in a held-out week left out) and applied out of fold; the held-out weeks use the threshold chosen
     on all tune weeks. IFS is thinned the same way. If no T reaches R, the largest T (10 hPa) is used.
     Tuned weighted blends (wb_t, wb_gfe2_t) take their preset from the first analysis' out-of-fold choice
     and then their T from the folds of the other months (a nested approximation).
  3. Position-vs-false-rate curves (curves_eq.csv).
  4. Vote against IFS thinned to the vote's false rate (vote_eq.csv).
All post hoc: the design's raw-threshold results stay in the files without a tag.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
from rk import cases as rkc
import analyze as A
from analyze import KEYS, MONTHS, PURGE, RES

TS = (0, 1, 2, 3, 4, 5, 6, 8, 10)
NK = len(TS)
CASE = ["basin", "cycle", "lead"]
CURVE = ["ifs", "gfs", "m_gi", "m_gif", "wb_gfe2_t", "al", "ald", "al_gfe2", "od", "od_gfe2", "grand"]
EXPLORE = ["al_gi", "ald_gi", "al_det", "ald_det"]
REF = "al"


def rescore_dir():
    import os
    from rk import paths
    return Path(os.environ.get("MSLP_BLEND_RESCORE") or paths.cache("extra", "mslp-blend-d7", "rescore"))


def read(d, name):
    ps = sorted((d / "parts").glob("*/%s_*.parquet" % name))
    df = pd.concat([pd.read_parquet(p) for p in ps], ignore_index=True)
    for c in ("basin", "truth", "cand", "setting"):
        df[c] = df[c].astype("category")
    return df


def meta(df):
    u = df[["cycle", "lead"]].drop_duplicates().copy()
    cyc = pd.to_datetime(u.cycle)
    iso = cyc.dt.isocalendar()
    u["week"] = [("%d-W%02d" % (y, w)) for y, w in zip(iso.year, iso.week)]
    u["split"] = [rkc.split(c.to_pydatetime()) for c in cyc]
    u["month"] = cyc.dt.strftime("%Y%m")
    v = cyc + pd.to_timedelta(u.lead, unit="h")
    u["valid_held"] = [bool(rkc.held_out(x.to_pydatetime())) for x in v]
    return df.merge(u, on=["cycle", "lead"], how="left")


def case_long(C, Lw):
    """One row per case x candidate x setting x truth x T index k with the additive pieces."""
    g = ["basin", "cycle", "lead", "truth", "cand", "setting"]
    L = Lw.copy()
    strong = (L.an_hpa < 980).to_numpy()
    water = L.water.to_numpy()
    cols = {}
    for k in range(NK):
        cols["pos_%d" % k] = L["pos_%d" % k].to_numpy(np.float64)
        cols["hung_%d" % k] = L["hung_%d" % k].to_numpy(np.float64)
        cols["hit_%d" % k] = L["hit_%d" % k].to_numpy(np.float64)
        cols["posw_%d" % k] = cols["pos_%d" % k] * water
        d = L["dep_%d" % k].to_numpy(np.float64)
        cols["sdb_%d" % k] = d * strong
        cols["sda_%d" % k] = np.abs(d) * strong
    cols["n_lows"] = np.ones(len(L))
    cols["n_w"] = water.astype(float)
    cols["sd_n"] = strong.astype(float)
    S = pd.DataFrame(cols)
    for c in g:
        S[c] = L[c].to_numpy()
    S = S.groupby(g, observed=True).sum().reset_index()
    X = C.merge(S, on=g, how="left")
    for c in S.columns:
        if c not in g:
            X[c] = X[c].fillna(0.0)
    out = []
    keep = g + ["rmse", "bias", "n_lows", "n_w", "sd_n"]
    for k in range(NK):
        d = X[keep].copy()
        d["k"], d["T"] = k, TS[k]
        d["pos_sum"], d["posh_sum"], d["hit_sum"] = X["pos_%d" % k], X["hung_%d" % k], X["hit_%d" % k]
        d["pos_sum_w"] = X["posw_%d" % k]
        d["sd_bias_sum"], d["sd_abs_sum"] = X["sdb_%d" % k], X["sda_%d" % k]
        d["false_n"], d["n_fc"] = X["false_%d" % k], X["nfc_%d" % k]
        out.append(d)
    CT = pd.concat(out, ignore_index=True)
    CT["cycle"] = pd.to_datetime(CT.cycle)
    CT = meta(CT)
    for c in ("basin", "truth", "cand", "setting", "week", "split", "month"):
        CT[c] = CT[c].astype(str)
    return CT


def entries_frame(CT, ch):
    """Untuned entries and the tuned weighted blends (preset from the first analysis' out-of-fold choice)."""
    Cu = A.untuned_rows(CT.assign(cand=CT.cand.astype(str)))
    Cu = Cu[~Cu.cand.isin(["wb", "wb_gfe2"]) | (Cu.setting == "default")]
    Cu["entry"] = Cu.cand
    wbrows = CT[CT.cand.isin(["wb", "wb_gfe2"]) & CT.setting.str.startswith("w=")]
    Ct = A.select_tuned(wbrows, ch[ch.cand.isin(["wb", "wb_gfe2"])])
    Ct["entry"] = Ct.cand
    return pd.concat([Cu, Ct], ignore_index=True)


def choose_T(M, ref):
    """M: entry rows (truth mean) with columns entry, basin, cycle, lead, k, false_n, split, valid_held, month;
    ref: frame [basin, cycle, lead, false_ref]. Returns [entry, lead, basin, fold, k]."""
    M = M[(M.truth == "mean")].merge(ref, on=CASE, how="inner")
    tr = M[(M.split == "tune") & (~M.valid_held)]
    rows = []
    for fold in list(MONTHS) + ["final"]:
        if fold == "final":
            T = tr
        else:
            y, m = int(fold[:4]), int(fold[4:])
            start = pd.Timestamp(y, m, 1)
            end = start + pd.offsets.MonthBegin(1)
            T = tr[(tr.cycle < start - PURGE) | (tr.cycle >= end + PURGE)]
        a = T.groupby(["entry", "lead", "basin", "k"]).agg(rate=("false_n", "mean"), R=("false_ref", "mean"),
                                                            n=("false_n", "size")).reset_index()
        for (e, lead, basin), g in a.groupby(["entry", "lead", "basin"]):
            ok = g[g.rate <= g.R + 1e-12]
            if len(ok):
                k = int(ok.sort_values(["rate", "k"], ascending=[False, True]).k.iloc[0])
            else:
                k = NK - 1
            rows.append((e, lead, basin, fold, k, float(g.R.iloc[0]), float(g[g.k == k].rate.iloc[0]), int(g.n.iloc[0])))
    return pd.DataFrame(rows, columns=["entry", "lead", "basin", "fold", "k", "R_target", "rate_at_k", "n_cases"])


def apply_T(rows, tch):
    """Keep, per row, the k chosen for its fold (out-of-fold month for tune cycles, final for held-out ones)."""
    d = rows.copy()
    d["fold"] = np.where(d.split == "tune", d.month, "final")
    d = d.merge(tch[["entry", "lead", "basin", "fold", "k"]].rename(columns={"k": "kc"}), on=["entry", "lead", "basin", "fold"])
    return d[d.k == d.kc].drop(columns=["kc", "fold"])


def finish(E):
    """Columns downstream() and the tables expect."""
    E = E.copy()
    for c in ("rmse_ls", "sharp"):
        E[c] = np.nan
    is_t = E.entry.str.endswith("_t")
    E["main"] = np.where(is_t, E.split == "tune", True)
    E["held"] = E.split == "held_out"
    return E


def water_version(E):
    W = E.copy()
    W["pos_sum"], W["n_lows"] = W.pos_sum_w, W.n_w
    return W


def table(E, Lsel):
    rows = []
    for (entry, lead, truth), g in E[E.main].groupby(["entry", "lead", "truth"]):
        for basin, gg in [("all", g)] + [(b, g[g.basin == b]) for b in ("natl", "npac")]:
            n = gg.n_lows.sum()
            if not len(gg):
                continue
            rows.append(dict(entry=entry, lead=lead, truth=truth, basin=basin, n_cases=len(gg), n_lows=int(n),
                             T_mean=gg["T"].mean(), pos_km=gg.pos_sum.sum() / n if n else np.nan,
                             pos_water_km=gg.pos_sum_w.sum() / gg.n_w.sum() if gg.n_w.sum() else np.nan,
                             pos_hung_km=gg.posh_sum.sum() / n if n else np.nan,
                             hit300=gg.hit_sum.sum() / n if n else np.nan, rmse=gg.rmse.mean(), bias=gg.bias.mean(),
                             false_per_map=gg.false_n.mean(), fc_lows_per_map=gg.n_fc.mean(),
                             strong_n=int(gg.sd_n.sum()),
                             strong_bias=gg.sd_bias_sum.sum() / gg.sd_n.sum() if gg.sd_n.sum() else np.nan,
                             strong_mae=gg.sd_abs_sum.sum() / gg.sd_n.sum() if gg.sd_n.sum() else np.nan))
    T = pd.DataFrame(rows)
    if len(Lsel):
        m = Lsel.groupby(["entry", "lead", "truth"]).agg(pos_median_km=("pos", "median")).reset_index().assign(basin="all")
        T = T.merge(m, on=["entry", "lead", "truth", "basin"], how="left")
    return T


def low_selection(Lw, ch, tch):
    """Low rows of the entries at the chosen T (position per low as column pos), main sets only."""
    L = meta(Lw)
    for c in ("basin", "truth", "cand", "setting", "week", "split", "month"):
        L[c] = L[c].astype(str)
    Lu = A.untuned_rows(L.assign(cand=L.cand.astype(str)))
    Lu = Lu[~Lu.cand.isin(["wb", "wb_gfe2"]) | (Lu.setting == "default")]
    Lu["entry"] = Lu.cand
    wb = L[L.cand.isin(["wb", "wb_gfe2"]) & L.setting.str.startswith("w=")]
    Lt = A.select_tuned(wb, ch[ch.cand.isin(["wb", "wb_gfe2"])])
    Lt["entry"] = Lt.cand
    Lall = pd.concat([Lu, Lt], ignore_index=True)
    Lall["main"] = np.where(Lall.entry.str.endswith("_t"), Lall.split == "tune", True)
    Lall = Lall[Lall.main]
    return Lall


def pick_pos(L, tch):
    d = L.copy()
    d["fold"] = np.where(d.split == "tune", d.month, "final")
    d = d.merge(tch[["entry", "lead", "basin", "fold", "k"]].rename(columns={"k": "kc"}), on=["entry", "lead", "basin", "fold"])
    P = d[["pos_%d" % k for k in range(NK)]].to_numpy()
    d["pos"] = P[np.arange(len(d)), d.kc.to_numpy()]
    return d


def curves(EA, Lall):
    """Position vs false rate per T for the listed entries (truth mean; main sets)."""
    rows = []
    Em = EA[EA.truth == "mean"]
    Lm = Lall[Lall.truth == "mean"]
    for entry in CURVE:
        g0 = Em[Em.entry == entry]
        g0 = g0[g0.split == "tune"] if entry.endswith("_t") else g0
        l0 = Lm[Lm.entry == entry]
        for lead in A.LEADS:
            for basin in ("all", "natl", "npac"):
                g = g0[(g0.lead == lead) & ((g0.basin == basin) if basin != "all" else True)]
                ll = l0[(l0.lead == lead) & ((l0.basin == basin) if basin != "all" else True)]
                for k in range(NK):
                    h = g[g.k == k]
                    if not len(h):
                        continue
                    n = h.n_lows.sum()
                    rows.append(dict(entry=entry, lead=lead, basin=basin, T=TS[k], n_cases=len(h),
                                     false_per_map=h.false_n.mean(), fc_lows_per_map=h.n_fc.mean(),
                                     pos_km=h.pos_sum.sum() / n, pos_median_km=float(np.median(ll["pos_%d" % k])) if len(ll) else np.nan,
                                     pos_hung_km=h.posh_sum.sum() / n, hit300=h.hit_sum.sum() / n))
    return pd.DataFrame(rows)


def label_post_hoc():
    """Add post_hoc = True to the rows of the exploratory candidates in every post hoc table."""
    for p in sorted(RES.glob("*.csv")):
        if not any(t in p.name for t in ("_eq", "_raw2", "_raw_water", "curves", "warp_effect", "vote_eq")):
            continue
        df = pd.read_csv(p)
        col = "entry" if "entry" in df else ("method" if "method" in df else None)
        if col:
            df["post_hoc"] = df[col].isin(EXPLORE)
            df.to_csv(p, index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()
    d = rescore_dir()
    C, Lw = read(d, "case"), read(d, "low")
    print("rescore rows: case %d low %d" % (len(C), len(Lw)), flush=True)
    ch = pd.read_csv(RES / "tuning_choices.csv")
    ch["basin"] = ch.basin.astype(str)
    CT = case_long(C, Lw)
    print("long", len(CT), flush=True)
    EA = entries_frame(CT, ch)                           # entries x all k
    EA["main"] = np.where(EA.entry.str.endswith("_t"), EA.split == "tune", True)

    # ---- raw threshold (k = 0)
    E_raw = finish(EA[EA.k == 0])
    A_raw = {"": E_raw}
    # ---- equal false lows
    ref = EA[(EA.entry == REF) & (EA.k == 0) & (EA.truth == "mean")][CASE + ["false_n"]].rename(columns={"false_n": "false_ref"})
    tch = choose_T(EA, ref)
    tch.to_csv(RES / "eq_thresholds.csv", index=False)
    E_eq = finish(apply_T(EA, tch))
    print("eq rows", len(E_eq), flush=True)

    # ---- low-level tables (medians)
    Lall = low_selection(Lw, ch, tch)
    Lraw = Lall.assign(pos=Lall.pos_0)
    Leq = pick_pos(Lall, tch)
    T_raw = table(E_raw, Lraw[Lraw.main])
    T_eq = table(E_eq, Leq[Leq.main])
    T_raw.to_csv(RES / "by_lead_raw2.csv", index=False)
    T_eq.to_csv(RES / "by_lead_eq.csv", index=False)
    tch.to_csv(RES / "eq_thresholds.csv", index=False)
    cv = curves(EA, Lall)
    cv.to_csv(RES / "curves_eq.csv", index=False)

    # ---- downstream: raw (re-scored, includes the post hoc candidates), raw water, equal false, equal water
    # second target (post hoc): R = the raw false-low rate of m_gi (GFS+IFS equal mean), a middle rate that IFS can reach
    refB = EA[(EA.entry == "m_gi") & (EA.k == 0) & (EA.truth == "mean")][CASE + ["false_n"]].rename(columns={"false_n": "false_ref"})
    tchB = choose_T(EA, refB)
    tchB.to_csv(RES / "eq_thresholds_B.csv", index=False)
    E_eqB = finish(apply_T(EA, tchB))
    LeqB = pick_pos(Lall, tchB)
    table(E_eqB, LeqB[LeqB.main]).to_csv(RES / "by_lead_eq_B.csv", index=False)
    for tag, E in (("_raw2", E_raw), ("_raw_water", water_version(E_raw)), ("_eq", E_eq),
                   ("_eq_water", water_version(E_eq)), ("_eq_B", E_eqB)):
        Dif, Win = A.downstream(E, a.n_boot, tag=tag)
        Dif.assign(post_hoc=Dif.entry.isin(EXPLORE)).to_csv(RES / ("diffs_vs_ifs%s.csv" % tag), index=False)

    # ---- vote vs IFS thinned to the vote's false rate (12 UTC, day 5-7)
    F = A.read(A.scores_dir(None), "field")
    Lo = A.read(A.scores_dir(None), "lows")
    vF = F[(F.cand == "vote")]
    vL = Lo[Lo.cand == "vote"]
    Cv = A.case_table(vF, vL)
    Cv = Cv.assign(cand=Cv.cand.astype(str), basin=Cv.basin.astype(str), truth=Cv.truth.astype(str), split=Cv.split.astype(str),
                   month=Cv.month.astype(str), week=Cv.week.astype(str), entry="vote", k=0, T=0)
    Cv["pos_sum_w"] = np.nan
    Cv["n_w"] = np.nan
    refv = Cv[Cv.truth == "mean"][CASE + ["false_n"]].rename(columns={"false_n": "false_ref"})
    ifsA = EA[(EA.entry == "ifs")].merge(refv[CASE].drop_duplicates(), on=CASE)
    tv = choose_T(ifsA, refv)
    ifsT = apply_T(ifsA, tv).assign(entry="ifs")
    vote_all = finish(pd.concat([Cv, ifsT], ignore_index=True))
    vote_all["main"] = True
    ifs_raw = finish(ifsA[ifsA.k == 0]).assign(entry="ifs_raw")
    Dv, _ = A.downstream(pd.concat([vote_all, ifs_raw], ignore_index=True), a.n_boot, tag="_vote_eq")
    tv.to_csv(RES / "vote_eq_thresholds.csv", index=False)
    Tv = table(pd.concat([vote_all, ifs_raw], ignore_index=True), pd.DataFrame())
    Tv.to_csv(RES / "vote_eq.csv", index=False)
    label_post_hoc()
    print("done", flush=True)


if __name__ == "__main__":
    main()
