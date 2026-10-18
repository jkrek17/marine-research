#!/usr/bin/env python3
"""Tables from cases.csv: how much stronger ASCAT's core is than each product near the archive's lows.

  python3 summary.py            -> summary.csv, printed table

Per archive category (HF, S; the desk's own call, so not a selection on ASCAT) and lead:
  n cases, n storms, n weeks; mean ASCAT peak and mean product peak over the same seen cells within 500 km;
  mean gap (ASCAT minus product, kt) with a whole-week 95% interval (rk.compare.boot_sums);
  share of cases where ASCAT / the product reaches 48 and 64 kt somewhere in the seen circle;
  area ratio: product cells >= 48 (>= 64) over ASCAT cells >= 48 (>= 64), pooled, among seen cells.
Status counts (cases skipped for no forecast, no ASCAT or too few seen cells) go to status.csv.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import compare  # noqa: E402

PRODUCTS = ("gfs", "ifs", "aifs", "blend", "corelift")


def main():
    d = pd.read_csv(HERE / "cases.csv", parse_dates=["valid"])
    d = d.drop_duplicates(["basin", "event_id", "valid", "lead"])
    d.groupby(["category", "basin", "lead", "status"]).size().rename("n").reset_index().to_csv(
        HERE / "status.csv", index=False)
    ok = d[d.status == "ok"].copy()
    iso = ok.valid.dt.isocalendar()
    ok["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    rows = []
    for (cat, lead), g in ok.groupby(["category", "lead"]):
        for basin in ("both", "natl", "npac"):
            h = g if basin == "both" else g[g.basin == basin]
            if len(h) < 5:
                continue
            for p in PRODUCTS:
                gap = h.ascat_peak - h[p + "_peak"]
                gap5 = h.ascat_k5 - h[p + "_k5"]
                stats = np.column_stack([gap, np.ones(len(h)), h[p + "_n48"], h.ascat_n48,
                                         h[p + "_n64"], h.ascat_n64, gap5])
                tot, dr = compare.boot_sums(h.week.to_numpy(), stats, n_boot=2000, seed=0)
                mg = dr[:, 0] / dr[:, 1]
                mg5 = dr[:, 6] / dr[:, 1]
                rows.append(dict(
                    category=cat, lead=lead, basin=basin, product=p, n=len(h), storms=h.event_id.nunique(),
                    weeks=h.week.nunique(), ascat_peak=h.ascat_peak.mean(), product_peak=h[p + "_peak"].mean(),
                    gap=tot[0] / tot[1], gap_lo=np.percentile(mg, 2.5), gap_hi=np.percentile(mg, 97.5),
                    gap_median=gap.median(),
                    gap_k5=tot[6] / tot[1], gap_k5_lo=np.percentile(mg5, 2.5), gap_k5_hi=np.percentile(mg5, 97.5),
                    ascat_reach48=(h.ascat_peak >= 48).mean(), product_reach48=(h[p + "_peak"] >= 48).mean(),
                    ascat_reach64=(h.ascat_peak >= 64).mean(), product_reach64=(h[p + "_peak"] >= 64).mean(),
                    area48=tot[2] / tot[3] if tot[3] else np.nan,
                    area64=tot[4] / tot[5] if tot[5] else np.nan))
    s = pd.DataFrame(rows)
    # momentum test: of ASCAT's >= thr cells, the share where each model carries >= thr at 925 / 850 mb
    mom = []
    for (cat, lead), g in ok.groupby(["category", "lead"]):
        for basin in ("both", "natl", "npac"):
            h = g if basin == "both" else g[g.basin == basin]
            for m in ("gfs", "ifs", "aifs"):
                for lev in ("925", "850"):
                    for thr in (48, 64):
                        col = "%s_s%s_ge%d" % (m, lev, thr)
                        if col + "_nb" not in h or h[col + "_nb"].isna().all():
                            continue
                        hh = h[h[col + "_nb"].notna()]
                        n_ob = hh["ascat_n%d" % thr].sum()
                        mom.append(dict(category=cat, lead=lead, basin=basin, model=m, level=lev, thr=thr,
                                        n=len(hh), ascat_cells=int(n_ob),
                                        share_cell=hh[col + "_cell"].sum() / n_ob if n_ob else np.nan,
                                        share_50km=hh[col + "_nb"].sum() / n_ob if n_ob else np.nan,
                                        peak_aloft=hh["%s_s%s_peak" % (m, lev)].mean()))
    if mom:
        mm = pd.DataFrame(mom)
        mm.to_csv(HERE / "momentum.csv", index=False, float_format="%.3f")
        print(mm[(mm.basin == "both") & (mm.category == "HF")].to_string(index=False, float_format=lambda x: "%.2f" % x))
    s.to_csv(HERE / "summary.csv", index=False, float_format="%.3f")
    show = s[s.basin == "both"][["category", "lead", "product", "n", "storms", "weeks", "ascat_peak",
                                  "product_peak", "gap", "gap_lo", "gap_hi", "gap_k5", "ascat_reach64",
                                  "product_reach64", "area48", "area64"]]
    print(show.to_string(index=False, float_format=lambda x: "%.2f" % x))


if __name__ == "__main__":
    main()
