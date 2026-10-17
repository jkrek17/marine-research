"""Refit after the 2026-10-17 audit: rk.calibrate.fit_pooled (thin bins shrunk toward the both-basin curve,
adjacent bins pooled) against the page's current table (rk.calibrate.fit, shrunk toward raw, running maximum).

    python3 refit.py [OOT_DIR]

Fits on the tune weeks of the counts in chance-calibration/pooled/ (winter 2025-26, 1 Nov - 31 Mar, the data
the page table came from) and scores (1) the held-out weeks of those counts and (2), when OOT_DIR holds a
counts.json in the same format with cycles the fit never saw (e.g. Pacific 06/18 UTC, or a later season), every
cell in it that is not in the original counts (OOT counts minus the original, tune and held-out weeks alike). ASCAT 3x3 box truth, 34 and 48 kt; 64 kt is not
refitted (too few events). Writes refit_compare.csv, refit_highbins.csv and calibration_refit.json to
chance-calibration/pooled/ (the page's file is not touched)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from rk import calibrate as C, paths  # noqa: E402
import run_first_look as R  # noqa: E402

BASE = paths.DATA.parent / "chance-calibration" / "pooled"
PAGE = json.load(open(BASE / "calibration_recommended.json"))["thresholds"]
GROUPS = list(C.LEAD_GROUPS)


def load(d):
    return {k: np.array(v) for k, v in json.load(open(Path(d) / "counts.json")).items()}


def minus(a, b):
    out = {}
    for k, v in a.items():
        d = v - b.get(k, 0)
        if d[0].sum() > 0:
            out[k] = d
    return out


def table(counts, basin, thr, g, split):
    parts = [R._pool(counts, b, "box", thr, g, s) for b in ([basin] if basin != "both" else ["natl", "npac"])
             for s in ([split] if split != "any" else ["tune", "held_out"])]
    x = R._cat(parts)
    return None if x is None else C.table(*x[:2], w=x[2]), x


def scores(x, raw, cal):
    p, e, w = x
    q = C.apply(p, raw, cal)
    clim = (w * e).sum() / w.sum()
    hi = p >= 0.10
    t = C.table(q, e, w=w)
    th = C.table(q[hi], e[hi], w=w[hi]) if hi.any() else None
    return dict(bss=C.brier_skill(q, e, clim, w), relerr=C.reliability_error(t),
                relerr_hi=C.reliability_error(th) if th is not None else np.nan,
                cells=int(w.sum()), events=int((w * e).sum()), cells_hi=int(w[hi].sum()))


def main(oot_dir=None):
    old = load(BASE)
    sets = {"held_out": (old, "held_out")}
    if oot_dir:
        sets["unseen"] = (minus(load(oot_dir), old), "any")
    rows, hib, curves = [], [], {}
    for thr in (34, 48):
        for g in GROUPS:
            shared_tab, _ = table(old, "both", thr, g, "tune")
            prior = C.fit_logistic(shared_tab)
            for basin in ("natl", "npac"):
                tune, _ = table(old, basin, thr, g, "tune")
                cands = {"page": (PAGE[str(thr)][basin][g]["raw"], PAGE[str(thr)][basin][g]["cal"]),
                         "raw_member_share": ([0, 100], [0, 100]),
                         "refit": C.fit_pooled(tune, prior=prior)}
                curves[(thr, basin, g)] = cands["refit"]
                for sname, (counts, split) in sets.items():
                    tb = table(counts, basin, thr, g, split)
                    if tb[0] is None:
                        continue
                    x = tb[1]
                    for cn, (raw, cal) in cands.items():
                        rows.append(dict(thr=thr, basin=basin, lead=g, score_on=sname, curve=cn, **scores(x, raw, cal)))
                    r = C._rel(tb[0])
                    for i in range(len(r["n"])):
                        if r["n"][i] > 0 and r["mean_fc"][i] >= 0.10:
                            hib.append(dict(thr=thr, basin=basin, lead=g, score_on=sname,
                                            raw_pct=round(100 * r["mean_fc"][i], 1), cells=int(r["n"][i]),
                                            verified_pct=round(100 * r["obs_freq"][i], 1),
                                            page_pct=round(float(C.cal_at(100 * r["mean_fc"][i], *cands["page"])), 1),
                                            refit_pct=round(float(C.cal_at(100 * r["mean_fc"][i], *cands["refit"])), 1)))
    for g in GROUPS:                                   # 64 kt unchanged
        for basin in ("natl", "npac"):
            t = PAGE["64"][basin][g]
            curves[(64, basin, g)] = (t["raw"], t["cal"])
    pd.DataFrame(rows).to_csv(BASE / "refit_compare.csv", index=False, float_format="%.4g")
    pd.DataFrame(hib).to_csv(BASE / "refit_highbins.csv", index=False)
    C.to_page_json(curves, note=("Refit 2026-10-17 after the audit (rk.calibrate.fit_pooled: thin bins shrunk toward "
                                 "the both-basin curve, adjacent bins pooled). Winter 2025-26 tune weeks vs ASCAT 3x3 "
                                 "box, pooled GEFS+ENS+AIFS ENS share. 34 and 48 kt refitted per basin; 64 kt unchanged. "
                                 "Scores: chance-calibration/pooled/refit_compare.csv."),
                   path=BASE / "calibration_refit.json")
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
