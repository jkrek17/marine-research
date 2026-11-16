"""POST HOC: does the warp help once the filled ensemble means are out of the field? Paired raw-threshold
differences (km, mean analysis, all winter weeks) of the aligned blend minus the plain mean of the same runs:
al_gi - m_gi, al_det - m_gif (and the depth-fix versions against their plain bowls are in the main tables).
Writes results/warp_effect.csv. Needs rescore.py's output."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1])); sys.path.insert(0, str(HERE))
import numpy as np, pandas as pd
import analyze as A
import analyze_eq as Q

d = Q.rescore_dir()
C, Lw = Q.read(d, "case"), Q.read(d, "low")
CT = Q.case_long(C, Lw)
EA = Q.entries_frame(CT, pd.read_csv(Q.RES / "tuning_choices.csv"))
E = Q.finish(EA[(EA.k == 0) & EA.entry.isin(["al_gi", "m_gi", "al_det", "m_gif"])])
rows = []
for a, b in (("al_gi", "m_gi"), ("al_det", "m_gif")):
    for lead in A.LEADS:
        for water in (False, True):
            Em = E[(E.lead == lead) & (E.truth == "mean")]
            j = Em[Em.entry == a].set_index(A.KEYS).join(Em[Em.entry == b].set_index(A.KEYS), how="inner", lsuffix="_c", rsuffix="_r").reset_index()
            ps, pr, n = ("pos_sum_w_c", "pos_sum_w_r", "n_w_c") if water else ("pos_sum_c", "pos_sum_r", "n_lows_c")
            # pos_sum_w exists for both (same lows): difference pooled over lows
            st = np.c_[j[ps] - j[pr], j[n]]
            v, lo, hi, p = A.boot(A.week_codes(j.week_c), st, lambda s: s[..., 0] / s[..., 1], 2000)
            rows.append(dict(method=a, reference=b, lead=lead, over_water_only=water, n_cases=len(j), dpos_km=v, lo=lo, hi=hi, p=p,
                             dfalse=float((j.false_n_c - j.false_n_r).mean()), drmse=float((j.rmse_c - j.rmse_r).mean())))
pd.DataFrame(rows).to_csv(Q.RES / "warp_effect.csv", index=False)
print(pd.DataFrame(rows).query("not over_water_only").round(2).to_string())
