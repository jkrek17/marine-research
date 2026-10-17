"""ASCAT referee for the label test (report only, nothing tuned on it): for HF and S fixes in winter 2025-26
(Nov-Mar, the winter the store's analyses cover), the largest real 10 m ASCAT wind (rk.truth.ascat, rain
dropped, Metop-B/C met halfway) within 500 km and 90 min of the fix. Does the IR model's probability rank those
peaks better than the pressure-and-latitude baseline? Reads results.csv (run.py --final); writes ascat.csv.

    python3 studies/2026-10-17-hf-satellite/ascat_check.py
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import HERE
from rk import score, truth

RADIUS_KM, MIN_CELLS = 500.0, 300        # about a third of the 500 km disc seen (25 km cells)


def main():
    r = pd.read_csv(HERE / "results.csv", parse_dates=["valid"])
    r = r[(r["valid"] >= "2025-11-01") & (r["valid"] < "2026-04-01")]
    rows = []
    for _, f in r.iterrows():
        a = truth.ascat(f["basin"], f["valid"].to_pydatetime())
        if a is None:
            rows.append({**f, "ascat": "missing"})
            continue
        d = score.km(f["lat"], f["lon"], a["lat"], a["lon"])
        k = d <= RADIUS_KM
        rows.append({**f, "ascat": "ok" if k.sum() >= MIN_CELLS else "thin", "n_cells": int(k.sum()),
                     "peak_kt": float(a["spd_kt"][k].max()) if k.any() else np.nan})
    o = pd.DataFrame(rows)
    o.to_csv(HERE / "ascat.csv", index=False, float_format="%.3f")
    print(o.groupby(["ascat", "category"]).size().unstack(fill_value=0))
    g = o[o["ascat"] == "ok"]
    print("seen fixes %d (HF %d, S %d), storms %d, held out %d" % (
        len(g), (g.category == "HF").sum(), (g.category == "S").sum(), g.event_id.nunique(),
        (g.split == "held_out").sum()))
    print("median ASCAT peak: HF %.1f kt, S %.1f kt; share >= 64 kt: HF %.2f, S %.2f" % (
        g[g.category == "HF"].peak_kt.median(), g[g.category == "S"].peak_kt.median(),
        (g[g.category == "HF"].peak_kt >= 64).mean(), (g[g.category == "S"].peak_kt >= 64).mean()))
    for m in ("p_base", "p_ir"):
        rho = spearmanr(g[m], g["peak_kt"]).statistic
        print("%s: Spearman with ASCAT peak %.3f; AUC for ASCAT >= 56 kt %.3f" % (
            m, rho, score.auc(g[m], g["peak_kt"] >= 56)))


if __name__ == "__main__":
    main()
