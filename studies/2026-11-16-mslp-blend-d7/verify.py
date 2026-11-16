"""Independent check of the mslp-blend-d7 headline numbers (own code, rk.score low_case + extract files)."""
import os, sys, glob, datetime
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from rk import paths, basins
from rk.score import low_case, find_lows, pressure_drop

LEADS = list(range(24, 169, 24))
ENTRIES = ["ifs", "gfs", "m_gi"]
rng = np.random.default_rng(1)

def fld(d, ent, L):
    if ent == "m_gi":
        return 0.5 * (d["gfs_f%03d" % L] + d["ifs_f%03d" % L])
    return d["%s_f%03d" % (ent, L)]

pos = {}; rm = {}; fa = {}; nf = {}; dep = {}; depm = {}; noise = {}; ncase = {}
per24 = {e: {} for e in ENTRIES}   # cycle -> list of pos
for basin in ("natl", "npac"):
    lat, _ = basins.grid(basin)
    w = np.cos(np.radians(lat))[:, None] * np.ones((1, basins.grid(basin)[1].size))
    for f in sorted(glob.glob(str(paths.cache("extra", "mslp-blend-d7", basin, "*.npz")))):
        cyc = os.path.basename(f)[:10]
        d = np.load(f)
        for L in LEADS:
            need = ["gfs_f%03d" % L, "ifs_f%03d" % L, "an_gfs_v%03d" % L, "an_ifs_v%03d" % L, "mask_v%03d" % L]
            if any(k not in d.files for k in need):
                continue
            an = 0.5 * (d[need[2]] + d[need[3]]); m = d[need[4]].astype(bool)
            ncase[L] = ncase.get(L, 0) + 1
            ok = m & np.isfinite(d[need[2]]) & np.isfinite(d[need[3]])
            noise.setdefault(L, []).append(np.sqrt((w[ok] * (d[need[2]][ok] - d[need[3]][ok]) ** 2).sum() / w[ok].sum()))
            for e in ENTRIES:
                fc = fld(d, e, L)
                rows, fl, nfc = low_case(an, fc, basin)
                pos.setdefault((e, L), []).extend(rows.pos_km.tolist())
                fa.setdefault((e, L), []).append(fl); nf.setdefault((e, L), []).append(nfc)
                ok2 = m & np.isfinite(fc) & np.isfinite(an)
                rm.setdefault((e, L), []).append(np.sqrt((w[ok2] * (fc[ok2] - an[ok2]) ** 2).sum() / w[ok2].sum()))
                s = rows[rows.an_hpa < 980]
                dep.setdefault((e, L), []).extend(s[s.hit].depth_err_hpa.tolist())
                depm.setdefault((e, L), []).extend(s.depth_err_hpa.tolist())
                if L == 24:
                    per24[e].setdefault((basin, cyc), []).extend(rows.pos_km.tolist())
out = []
for e in ENTRIES:
    for L in LEADS:
        p = np.array(pos[(e, L)])
        out.append(dict(entry=e, lead=L, n_cases=ncase[L], n_lows=len(p), pos_km=p.mean(), pos_median_km=np.median(p),
                        hit300=(p <= 300).mean(), false_per_map=np.mean(fa[(e, L)]), fc_lows_per_map=np.mean(nf[(e, L)]),
                        rmse=np.mean(rm[(e, L)]), strong_bias=np.mean(dep[(e, L)]), strong_n=len(dep[(e, L)]),
                        strong_bias_all1000=np.mean(depm[(e, L)]), noise_rmse=np.mean(noise[L])))
V = pd.DataFrame(out)
V.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "verify.csv"), index=False)

# +24 paired difference, week-block bootstrap (pooled lows)
keys = sorted(per24["ifs"])
wk = {k: datetime.datetime.strptime(k[1], "%Y%m%d%H").isocalendar()[:2] for k in keys}
weeks = sorted(set(wk.values()))
S = {wkk: [0.0, 0] for wkk in weeks}; T = {wkk: [0.0, 0] for wkk in weeks}
for k in keys:
    a, b = per24["m_gi"][k], per24["ifs"][k]
    S[wk[k]][0] += sum(a); S[wk[k]][1] += len(a); T[wk[k]][0] += sum(b); T[wk[k]][1] += len(b)
sa = np.array([S[x] for x in weeks]); sb = np.array([T[x] for x in weeks])
diff = sa[:, 0].sum() / sa[:, 1].sum() - sb[:, 0].sum() / sb[:, 1].sum()
bs = []
for _ in range(2000):
    i = rng.integers(0, len(weeks), len(weeks))
    bs.append(sa[i, 0].sum() / sa[i, 1].sum() - sb[i, 0].sum() / sb[i, 1].sum())
print("m_gi - ifs pos @24: %.2f km, 95%% CI [%.2f, %.2f], %d weeks" % (diff, *np.percentile(bs, [2.5, 97.5]), len(weeks)))

R = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "by_lead.csv"))
R = R[(R.truth == "mean") & (R.basin == "all")]
print("cases per lead:", ncase)
tol = dict(pos_km=1, rmse=.01, false_per_map=.01, strong_bias=.1)
cols = ["pos_km", "pos_median_km", "hit300", "false_per_map", "fc_lows_per_map", "rmse", "strong_bias"]
M = V.merge(R, left_on=["entry", "lead"], right_on=["entry", "lead"], suffixes=("", "_s"))
pd.set_option("display.width", 250)
for c in cols:
    M["d_" + c] = M[c] - M[c + "_s"]
print(M[["entry", "lead"] + ["d_" + c for c in cols]].round(3).to_string())
flag = [(r.entry, r.lead, c) for r in M.itertuples() for c in tol if abs(getattr(r, "d_" + c)) > tol[c]]
print("FLAGS:", flag)
print(V.round(3).to_string())
