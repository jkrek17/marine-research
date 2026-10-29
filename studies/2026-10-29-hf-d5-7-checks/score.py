"""Score the three day 5-7 HF checks (design.md) on held-out weeks.

Reads CACHE/extra/hf-d5-7-checks/cells.parquet + members.npy (build.py), results/storms.csv (confirm.py) and, for
check 3, CACHE/extra/hf-d5-7-checks/desk.parquet (desk_join.py). Writes results/*.csv and prints the tables.
Truths: T1 = archive HF storm within 500 km (+-12 h); T2 = the same with ASCAT-confirmed storms only, rows near only
unconfirmed storms left out. Climatology, the depth line P*, and every fit use training weeks only (rows sharing a valid
time with a held-out row dropped, LESSONS). Intervals: 95%, 2,000 resamples of whole ISO weeks of the run.
Run: python3 score.py
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from rk import paths, score  # noqa: E402
import build  # noqa: E402

_spec = importlib.util.spec_from_file_location("bomb_score", ROOT / "studies" / "2026-10-19-bomb-d5-7" / "score.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)          # climatology, whole-week BSS intervals and reliability slope of the bomb study

RES = HERE / "results"
P_GRID = np.arange(940, 991, 5)
SIZES = (8, 16, 32, 64)
DRAWS = 50
N_BOOT = 2000
TRUTHS = ("t1", "t2")


def load():
    t = pd.read_parquet(paths.cache("extra", "hf-d5-7-checks", "cells.parquet"))
    mem = np.load(paths.cache("extra", "hf-d5-7-checks", "members.npy"))
    st = pd.read_csv(RES / "storms.csv", dtype={"event_id": str})
    conf = set(st.loc[st.status == "confirmed", "event_id"])
    ids = t.storms.str.split(";")
    t["t1"] = t.storms != ""
    t["t2"] = [bool(s) and any(i in conf for i in x) for s, x in zip(t.storms, ids)]
    t["t2_ok"] = ~t.t1 | t.t2                        # rows near only unconfirmed storms are out of T2
    held_valid = set(t.loc[t.split == "held_out", "valid"])
    t["train"] = (t.split == "tune") & ~t.valid.isin(held_valid)
    t["held"] = t.split == "held_out"
    t["n_mem"] = (mem != build.ABSENT).sum(1)
    return t, mem


def share(mem, p_star, cols=None):
    """Share of present members with a low at or below p_star within 500 km (cols: member slots to use)."""
    m = mem if cols is None else mem[:, cols]
    present = m != build.ABSENT
    k = (present & (m != build.NO_LOW) & (m <= p_star - 900)).sum(1)
    return k / np.maximum(present.sum(1), 1), k, present.sum(1)


def climatology(t, ev):
    d = t[["basin", "cell", "valid", "split"]].assign(event=t[ev].values)
    d["valid_held"] = ~t.train & (t.split == "tune")
    return B.add_climatology(d)["clim"].values


def bss(d, col, ev, seed=0):
    return B.boot_bss(d.assign(event=d[ev].values), col, "clim", seed=seed)


def pick_pstar(t, mem):
    """P* per basin and lead: the line with the lowest training Brier of the raw share against T1."""
    out = {}
    for (b, L), g in t[t.train].groupby(["basin", "lead"]):
        y = g.t1.values
        br = {p: np.mean((share(mem[g.index], p)[0] - y) ** 2) for p in P_GRID}
        out[(b, L)] = int(min(br, key=br.get))
    return out


def ens_slots():
    j, out = 0, {}
    for ens, _, n in build.ENS:
        out[ens] = np.arange(j, j + n)
        j += n
    return out


def check1(t, mem, pstar, rng):
    """Ensemble size: random member subsets vs all 133 vs the fair (unlimited-ensemble) Brier, held-out weeks."""
    slots = ens_slots()
    rows = []
    for ev in TRUTHS:
        for (b, L), g in t[t.held & (t.n_mem == build.SLOTS) & (t.t2_ok if ev == "t2" else True)].groupby(["basin", "lead"]):
            g = g.assign(clim=g["clim_" + ev])
            m = mem[g.index]
            ps = pstar[(b, L)]
            p_all, k, n = share(m, ps)
            g["p_all"] = p_all
            y = g[ev].values.astype(float)
            g["fair"] = score.fair_brier(k, n, y)
            row = {"truth": ev, "basin": b, "lead": L, "p_star": ps, "cells": len(g), "event_cells": int(y.sum()),
                   "storms": len(set(";".join(g.storms[g[ev]]).split(";")) - {""}), "cycles": g.cycle.nunique()}
            for size in SIZES:
                draws = []
                for _ in range(DRAWS):
                    cols = np.concatenate([rng.choice(s, max(1, round(size * len(s) / build.SLOTS)), replace=False)
                                           for s in slots.values()])
                    draws.append(share(m, ps, cols)[0])
                g["p%d" % size] = np.mean([(p - y) ** 2 for p in draws], axis=0)   # mean Brier over draws, per case
            clim_bs = (g.clim.values - y) ** 2
            for col, se in [("n%d" % s, g["p%d" % s].values) for s in SIZES] + \
                           [("n133", (g.p_all.values - y) ** 2), ("unlimited", g.fair.values)]:
                row["bss_" + col] = 1 - se.sum() / clim_bs.sum()
            # unlimited minus 133 members: BSS difference with a whole-week interval
            w = B.week(g.cycle)
            u, inv = np.unique(w, return_inverse=True)
            a1, a2, c = (np.bincount(inv, x) for x in (g.fair.values, (g.p_all.values - y) ** 2, clim_bs))
            idx = np.random.default_rng(0).integers(0, len(u), (N_BOOT, len(u)))
            dr = (a2[idx].sum(1) - a1[idx].sum(1)) / c[idx].sum(1)
            row.update(gain_unlimited=(a2.sum() - a1.sum()) / c.sum(), gain_lo=np.percentile(dr, 2.5),
                       gain_hi=np.percentile(dr, 97.5), weeks=len(u))
            row["more_members_help"] = bool(L >= 144 and row["gain_unlimited"] >= 0.02 and row["gain_lo"] > 0)
            rows.append(row)
    return pd.DataFrame(rows)


def features(t, mem, pstar):
    """Raw share now and the share of the run 24 h earlier at the same valid time (NaN when not stored)."""
    t = t.copy()
    t["share"] = np.nan
    for (b, L), g in t.groupby(["basin", "lead"]):
        t.loc[g.index, "share"] = share(mem[g.index], pstar[(b, L)])[0]
    # the earlier run uses its own lead's line, so each run's share means the same thing at its lead
    prev = t[["basin", "cell", "valid", "cycle", "lead", "share"]].copy()
    prev["cycle"] = prev.cycle + pd.Timedelta(hours=24)
    prev["lead"] = prev["lead"] - 24
    t = t.merge(prev.rename(columns={"share": "share_prev"}), on=["basin", "cell", "valid", "cycle", "lead"], how="left")
    return t


def fit_predict(tr, te, cols, ev):
    X = lambda d: np.column_stack([d[c].values for c in cols])    # noqa: E731
    m = LogisticRegression(C=1e3, max_iter=1000).fit(X(tr), tr[ev].values)
    return m.predict_proba(X(te))[:, 1], m.coef_.ravel().tolist()


def top_end(p, y, lo=0.3):
    k = p >= lo
    return int(k.sum()), float(p[k].mean()) if k.any() else np.nan, float(y[k].mean()) if k.any() else np.nan


def check2(t):
    """Run-to-run trend: logistic(share) vs logistic(share, share - share_prev), day 5 and 6."""
    rows = []
    for ev in TRUTHS:
        ok = t.t2_ok if ev == "t2" else pd.Series(True, index=t.index)
        for (b, L), g in t[ok & t.share_prev.notna() & t.lead.isin([120, 144])].groupby(["basin", "lead"]):
            g = g.assign(trend=g.share - g.share_prev, clim=g["clim_" + ev])
            tr, te = g[g.train], g[g.held].copy()
            te["pa"], ca = fit_predict(tr, te, ["share"], ev)
            te["pb"], cb = fit_predict(tr, te, ["share", "trend"], ev)
            y = te[ev].values.astype(float)
            a, alo, ahi, nw = bss(te, "pa", ev)
            bb, blo, bhi, _ = bss(te, "pb", ev)
            dif, dlo, dhi = B.boot_diff(te.assign(event=te[ev].values), "pa", "pb")              # Brier(share) - Brier(share + trend)
            ref = np.mean((te.clim.values - y) ** 2)
            na, ma, fa = top_end(te.pa.values, y)
            nb, mb, fb = top_end(te.pb.values, y)
            rows.append({"truth": ev, "basin": b, "lead": L, "cells": len(te), "event_cells": int(y.sum()),
                         "weeks": nw, "bss_share": a, "bss_share_lo": alo, "bss_share_hi": ahi,
                         "bss_trend": bb, "bss_trend_lo": blo, "bss_trend_hi": bhi,
                         "gain": dif / ref, "gain_lo": dlo / ref, "gain_hi": dhi / ref,
                         "coef_share": ca, "coef_trend": cb,
                         "top_n_share": na, "top_stated_share": ma, "top_verified_share": fa,
                         "top_n_trend": nb, "top_stated_trend": mb, "top_verified_trend": fb,
                         "trend_earns_place": bool(dlo > 0)})
    return pd.DataFrame(rows)


def check3(t):
    """Desk baseline: NDFD day 5-7 wind >= 64 (and >= 48) kt within 500 km, beside the calibrated member share."""
    p = paths.cache("extra", "hf-d5-7-checks", "desk.parquet")
    if not p.exists():
        print("check 3: no desk table yet (desk_join.py)")
        return None
    d = pd.read_parquet(p)
    t = t.merge(d, on=["basin", "cycle", "lead", "cell"], how="left")
    rows = []
    for ev in TRUTHS:
        ok = t.t2_ok if ev == "t2" else pd.Series(True, index=t.index)
        for (b, L), g in t[ok & t.desk_max.notna()].groupby(["basin", "lead"]):
            g = g.assign(clim=g["clim_" + ev])
            tr, te = g[g.train], g[g.held].copy()
            te["pa"], _ = fit_predict(tr, te, ["share"], ev)
            y = te[ev].values.astype(bool)
            row = {"truth": ev, "basin": b, "lead": L, "cells": len(te), "event_cells": int(y.sum()),
                   "desk_cycles": te.cycle.nunique()}
            row["bss_share"], row["bss_share_lo"], row["bss_share_hi"], row["weeks"] = bss(te, "pa", ev)
            for thr in (64, 48):
                yes = te.desk_max.values >= thr
                te["desk%d" % thr] = yes.astype(float)
                row["bss_desk%d" % thr], row["bss_desk%d_lo" % thr], row["bss_desk%d_hi" % thr], _ = \
                    bss(te, "desk%d" % thr, ev)
                h, f = int((yes & y).sum()), int((yes & ~y).sum())
                row["desk%d_yes" % thr] = int(yes.sum())
                row["desk%d_pod" % thr] = h / max(int(y.sum()), 1)
                row["desk%d_far" % thr] = f / max(h + f, 1)
            row["share_minus_desk48"], row["lo"], row["hi"] = B.boot_diff(te.assign(event=te[ev].values), "pa", "desk48")
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    t, mem = load()
    RES.mkdir(exist_ok=True)
    t["clim_t1"] = climatology(t, "t1")
    t.loc[t.t2_ok, "clim_t2"] = climatology(t[t.t2_ok], "t2")
    pstar = pick_pstar(t, mem)
    print("P* (hPa):", pstar)
    out = {"check1": check1(t, mem, pstar, np.random.default_rng(7))}
    t = features(t, mem, pstar)
    out["check2"] = check2(t)
    out["check3"] = check3(t)
    for k, v in out.items():
        if v is not None:
            v.to_csv(RES / (k + ".csv"), index=False, float_format="%.4f")
            with pd.option_context("display.width", 250, "display.max_columns", 40):
                print(k)
                print(v.round(3))


if __name__ == "__main__":
    main()
