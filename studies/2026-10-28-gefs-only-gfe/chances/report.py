"""Fit GEFS-only chance curves on tune weeks, score held-out weeks once, apply the preset win line.

    python3 report.py

Reads the counts from accumulate.py (rk.paths.data("extra","gefs-only-gfe","chances")). Writes results.csv,
curves.json, verdict.md and cases.csv next to this file (small).

Fit method = the 10-16 study's final one (refit.py, approved 10-17): rk.calibrate.fit_pooled per basin and lead
group, thin bins shrunk toward rk.calibrate.fit_logistic of both basins' tune table. 34 and 48 kt only; 64 kt is
raw and labelled not calibrated. Fitted separately for 0.25 deg and 0.5 deg inputs (half_deg before binning).
Pacific: fit on the 00 UTC valid times (tune weeks); the held-out score is the 00 UTC cells plus the 06/18 UTC
valid cells (design card), both also shown alone.

Win line (design card, section 1, preset): on held-out weeks, in both basins and at each lead group, the remapped
chance has (a) a lower reliability error than raw GEFS and (b) a Brier skill not lower than raw by more than 0.01.

Pooled comparison (reported beside it, not part of the verdict): the page's pooled GEFS+ENS+AIFS ENS member share
from the 10-16 counts (chance-calibration/pooled, pooled_npac0618), raw and through the page's tables, on the same
held-out cycles and steps."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from rk import calibrate as C, paths  # noqa: E402

DATA = paths.data("extra", "gefs-only-gfe", "chances", "x").parent
POOL = paths.DATA.parent / "chance-calibration"
GROUPS = list(C.LEAD_GROUPS)
GLABEL = {"le48": "+24/48", "72": "+72", "ge96": "+96/120"}
BASINS = ("natl", "npac")
RESOLUTIONS = ("025", "050")
RLABEL = {"025": "0.25 deg", "050": "0.5 deg"}
BNAME = {"natl": "Atlantic", "npac": "Pacific"}
WIN_BSS_TOL = 0.01
GROUP_0618 = {30: "le48", 54: "le48", 78: "72", 102: "ge96", 126: "ge96"}


# ---- counts -> weighted (p, event, w) ----

def load_counts():
    with np.load(DATA / "counts.npz") as z:
        return {k: z[k] for k in z.files}


def pool(counts, basin, kinds, res, thr, group, split):
    """Sum the quantised counts of the kinds ('main', '0618') -> (p, e, w) or None."""
    tot = None
    for k, v in counts.items():
        b, kind, r, t, g, s = k.split("|")
        if (b, r, int(t), g, s) == (basin, res, thr, group, split) and kind in kinds:
            tot = v if tot is None else tot + v
    if tot is None:
        return None
    return expand(tot, np.arange(tot.shape[1]) / 1e4)


def expand(cnt, pv):
    n, ev = cnt[0], cnt[1]
    return np.r_[pv, pv], np.r_[np.ones(len(pv)), np.zeros(len(pv))], np.r_[ev, n - ev]


def load_pooled():
    """The 10-16 pooled-share counts (k of 133 members) as {(basin, kind, thr, group, split): (p, e, w)} summed over steps."""
    out = {}
    for folder, kind in (("pooled", "main"), ("pooled_npac0618", "0618")):
        raw = json.load(open(POOL / folder / "counts.json"))
        for key, v in raw.items():
            b, tn, th, st, sp, nm = key.split("|")
            if tn != "box":
                continue
            st, nm, v = int(st), int(nm), np.array(v)
            g = GROUP_0618[st] if kind == "0618" else C.lead_group(st)
            k = (b, kind, int(th), g, sp, nm)
            out[k] = out.get(k, 0) + v
    return out


def pooled_pool(pc, basin, kinds, thr, group, split):
    parts = []
    for (b, kind, th, g, sp, nm), v in pc.items():
        if (b, th, g, sp) == (basin, thr, group, split) and kind in kinds:
            parts.append(expand(v, np.arange(nm + 1) / nm))
    if not parts:
        return None
    return tuple(np.concatenate([x[i] for x in parts]) for i in range(3))


# ---- scores ----

def metrics(x, raw_k=None, cal_k=None):
    """x = (p, e, w) -> dict of scores for the raw chance, and the remapped chance if knots are given."""
    p, e, w = x
    clim = (w * e).sum() / w.sum()
    out = dict(cells=int(w.sum()), events=int((w * e).sum()), base_rate=clim,
               bss_raw=C.brier_skill(p, e, clim, w), relerr_raw=C.reliability_error(C.table(p, e, w=w)))
    if raw_k is not None:
        q = C.apply(p, raw_k, cal_k)
        out.update(bss_remap=C.brier_skill(q, e, clim, w), relerr_remap=C.reliability_error(C.table(q, e, w=w)))
    return out


def true_at_raw(x, centre=0.30, half=0.05):
    """Held-out observed frequency among cells whose raw chance is within centre +- half (%, NaN when thin), and the cell count."""
    p, e, w = x
    m = (p >= centre - half) & (p < centre + half + 1e-9)
    n = w[m].sum()
    return (float((w[m] * e[m]).sum() / n) if n >= 30 else float("nan")), int(n)


def cycles_with_event(rows, basin, kinds, thr, group, split):
    r = rows[(rows.basin == basin) & rows.kind.isin(kinds) & (rows.thr == thr) & (rows.group == group) & (rows.split == split)]
    g = r.groupby(["kind", "cycle"])
    return int(g.ngroups), int((g.events.sum() > 0).sum())


def main():
    counts = load_counts()
    rows = pd.read_csv(DATA / "cycle_rows.csv", dtype={"cycle": str})
    pc = load_pooled()
    refit = json.load(open(POOL / "pooled" / "calibration_refit.json"))["thresholds"]
    pagecur = json.load(open(POOL / "pooled" / "calibration_page_current.json"))["thresholds"]

    def knots(tab, thr, basin, g):
        if str(thr) not in tab:
            return [0, 100], [0, 100]                     # not calibrated on the page: raw share
        c = tab[str(thr)][basin][g]
        return c["raw"], c["cal"]

    res_rows, curves, cases_rows = [], {r: {} for r in RESOLUTIONS}, []
    for res in RESOLUTIONS:
        for thr in (34, 48):
            for g in GROUPS:
                tunes = {b: pool(counts, b, ("main",), res, thr, g, "tune") for b in BASINS}
                prior = C.fit_logistic(C.table(*[np.concatenate([tunes[b][i] for b in BASINS]) for i in range(2)],
                                               w=np.concatenate([tunes[b][2] for b in BASINS])))
                for basin in BASINS:
                    t = tunes[basin]
                    raw_k, cal_k = C.fit_pooled(C.table(t[0], t[1], w=t[2]), prior=prior)
                    curves[res][(thr, basin, g)] = (raw_k, cal_k)
                    sets = {"all": ("main", "0618") if basin == "npac" else ("main",), "main": ("main",)}
                    if basin == "npac":
                        sets["0618"] = ("0618",)
                    for sname, kinds in sets.items():
                        h = pool(counts, basin, kinds, res, thr, g, "held_out")
                        if h is None:
                            continue
                        m = metrics(h, raw_k, cal_k)
                        tr, trn = true_at_raw(h)
                        nc, ne = cycles_with_event(rows, basin, kinds, thr, g, "held_out")
                        r = dict(res=RLABEL[res], thr=thr, basin=basin, lead=GLABEL[g], cells_set=sname,
                                 tune_cells=int(t[2].sum()), tune_events=int((t[2] * t[1]).sum()),
                                 held_cycles_steps=nc, held_cycles_with_event=ne, **m,
                                 true_at_raw30=tr, raw30_cells=trn, cal_at_30=float(C.cal_at(30, raw_k, cal_k)),
                                 cal_at_10=float(C.cal_at(10, raw_k, cal_k)), raw_for_30=C.raw_for(30, raw_k, cal_k))
                        # pooled page chance on the same held-out cells (10-16 counts)
                        pk = pooled_pool(pc, basin, kinds, thr, g, "held_out")
                        if pk is not None:
                            pm = metrics(pk, *knots(refit, thr, basin, g))
                            pp = metrics(pk, *knots(pagecur, thr, basin, g))
                            r.update(pooled_cells=pm["cells"], pooled_events=pm["events"], pooled_bss_raw=pm["bss_raw"],
                                     pooled_relerr_raw=pm["relerr_raw"], pooled_bss_page=pp["bss_remap"],
                                     pooled_relerr_page=pp["relerr_remap"], pooled_bss_refit=pm["bss_remap"],
                                     pooled_relerr_refit=pm["relerr_remap"])
                        res_rows.append(r)
                if res == "025":
                    pass
            # nothing else per threshold
        # 64 kt: raw only
        for g in GROUPS:
            for basin in BASINS:
                for sname, kinds in {"all": ("main", "0618") if basin == "npac" else ("main",), "main": ("main",)}.items():
                    h = pool(counts, basin, kinds, res, 64, g, "held_out")
                    if h is None:
                        continue
                    nc, ne = cycles_with_event(rows, basin, kinds, 64, g, "held_out")
                    tr, trn = true_at_raw(h)
                    res_rows.append(dict(res=RLABEL[res], thr=64, basin=basin, lead=GLABEL[g], cells_set=sname,
                                         held_cycles_steps=nc, held_cycles_with_event=ne, **metrics(h),
                                         true_at_raw30=tr, raw30_cells=trn))
    df = pd.DataFrame(res_rows)
    df["relerr_better"] = df.relerr_remap < df.relerr_raw
    df["bss_ok"] = df.bss_remap >= df.bss_raw - WIN_BSS_TOL
    df["win"] = df.relerr_better & df.bss_ok
    for c in ("relerr_better", "bss_ok", "win"):
        df[c] = df[c].astype(object).where(df.thr != 64, None)
    df.to_csv(HERE / "results.csv", index=False, float_format="%.5g")

    # curves.json: page layout, both resolutions
    out = {"note": ("GEFS-only chance calibration vs the ASCAT 3x3 box, fitted on tune weeks of winter 2025-26 "
                    "(rk.calibrate.fit_pooled, prior = both-basin logistic). NOT for the page (the page pools GEFS + "
                    "ECMWF ENS + AIFS ENS): for a GFE that has only GEFS. 34 and 48 kt; 64 kt stays raw, not calibrated. "
                    "Pacific fitted on 00 UTC valid times. Knots in percent; 0.5 deg = half_deg of the 0.25 deg share grid."),
           "resolutions": {RLABEL[r]: C.to_page_json(curves[r])["thresholds"] for r in RESOLUTIONS}}
    json.dump(out, open(HERE / "curves.json", "w"), indent=1)

    verdict(df, curves)


def verdict(df, curves):
    d = df[(df.thr != 64) & (df.cells_set == "all")]
    L = ["# GEFS-only chances: verdict", "",
         "*Win line (design card, preset): on held-out weeks, in both basins and at each lead group, the remapped chance has "
         "a lower reliability error than raw GEFS and a Brier skill not lower than raw by more than 0.01. The 0.5 deg result decides. "
         "Truth: ASCAT 3x3 box. Fit: tune weeks, `rk.calibrate.fit_pooled` per basin, prior = both-basin logistic (the 10-16 refit method). "
         "Held-out weeks scored once. Pacific held-out = 00 UTC plus 06/18 UTC valid times; Pacific fit = 00 UTC valid times.*", ""]
    L += ["## Verdict", "", "| Resolution | Chance | Basin x lead cells passing | Verdict | Failing cells |", "|---|---|---|---|---|"]
    verd = {}
    for res in ("0.25 deg", "0.5 deg"):
        for thr in (34, 48):
            x = d[(d.res == res) & (d.thr == thr)]
            ok = bool(x.win.all())
            verd[(res, thr)] = ok
            fail = ", ".join("%s %s (%s)" % (BNAME[r.basin], r.lead, ("rel err" if not r.relerr_better else "") +
                                             (" + " if not r.relerr_better and not r.bss_ok else "") + ("skill" if not r.bss_ok else ""))
                             for r in x.itertuples() if not r.win) or "none"
            L.append("| %s | %s kt | %d of %d | %s | %s |" % (res, "gale 34" if thr == 34 else "storm 48", int(x.win.sum()), len(x),
                                                            "WIN" if ok else "NOT MET", fail))
    L += ["", "64 kt: raw GEFS p64 only, **not calibrated** (too few events); see the table below.", ""]
    for res in ("0.5 deg", "0.25 deg"):
        L += ["## Held-out scores, %s" % res, "",
              "| Chance | Basin | Lead | Held-out cycles with event | Brier skill raw | remapped | Rel. error raw | remapped | Win | Raw 30% = true | Remapped says at raw 30% | Pooled page: Brier skill raw | page table | refit table | Pooled rel. error raw | page | refit |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in d[d.res == res].sort_values(["thr", "basin", "lead"]).itertuples():
            f = lambda v, n=3: ("%.*f" % (n, v)) if v == v else "n/a"  # noqa: E731
            pct = lambda v: ("%.0f%%" % (100 * v)) if v == v else "n/a"  # noqa: E731
            L.append("| %s | %s | %s | %d of %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                "gale 34" if r.thr == 34 else "storm 48", BNAME[r.basin], r.lead, r.held_cycles_with_event, r.held_cycles_steps,
                f(r.bss_raw, 2), f(r.bss_remap, 2), f(r.relerr_raw), f(r.relerr_remap), "yes" if r.win else "NO",
                pct(r.true_at_raw30), "%.0f%%" % r.cal_at_30, f(r.pooled_bss_raw, 2), f(r.pooled_bss_page, 2), f(r.pooled_bss_refit, 2),
                f(r.pooled_relerr_raw), f(r.pooled_relerr_page), f(r.pooled_relerr_refit)))
        L.append("")
    L += ["## 64 kt, raw GEFS p64, NOT calibrated", "",
          "| Resolution | Basin | Lead | Held-out cycles with event | Brier skill raw | Reliability error raw | Observed at raw 25-35% |", "|---|---|---|---|---|---|---|"]
    for r in df[(df.thr == 64) & (df.cells_set == "all")].sort_values(["res", "basin", "lead"]).itertuples():
        L.append("| %s | %s | %s | %d of %d | %.2f | %.3f | %s (%d cells) |" % (
            r.res, BNAME[r.basin], r.lead, r.held_cycles_with_event, r.held_cycles_steps, r.bss_raw, r.relerr_raw,
            ("%.0f%%" % (100 * r.true_at_raw30)) if r.true_at_raw30 == r.true_at_raw30 else "n/a", r.raw30_cells))
    L += ["", "## Notes", "",
          "- Pooled page columns are for comparison only (the 10-16 counts of GEFS+ENS+AIFS ENS share, 133 members, same held-out cycles and steps where all three ensembles exist; `page table` = `calibration_page_current.json` (34 kt raw), `refit table` = `calibration_refit.json`, approved 10-17).",
          "- Cell counts overstate the evidence: weeks are the independent sample, and no intervals are computed.",
          "- One winter; the fit and the held-out weeks are both winter 2025-26.",
          "- Truth is the ASCAT box mean, not an analysis; analyses read storm force lower (10-16)."]
    (HERE / "verdict.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:20]))


if __name__ == "__main__":
    main()
