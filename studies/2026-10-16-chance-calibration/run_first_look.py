"""Chance calibration, GEFS-only first look.

    python3 run_first_look.py accumulate   # read the store + truth, write counts.json and cycle_rows.csv
    python3 run_first_look.py report       # fit on tune weeks, score held-out, write results, curves, figures

GEFS member fractions (p34/p48/p64) are exact multiples of 1/n, so the accumulate stage keeps counts per
member count k (events and cells), per basin x truth x threshold x lead x split. Memory stays small and the
fit and the scores are exact. Nothing is downloaded except ASCAT/air-sea truth through rk.truth.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from rk import calibrate as C, cases, fetch, paths, store, truth  # noqa: E402

OUT = Path(os.environ.get("RK_CC_OUT", paths.DATA.parent / "chance-calibration" / "gefs_first_look"))
THRS = (34, 48, 64)
TRUTHS = ("box", "cell", "anl")
TRUTH_LABEL = {"box": "ASCAT 3x3 box", "cell": "ASCAT single cell", "anl": "analysis"}
BASINS = ("natl", "npac")
LABEL = "GEFS only, first look"
# Cycle hours (UTC) per basin. ASCAT covers the Atlantic box equally at 00 and 12 UTC; the Pacific is only
# in the store at 00 UTC. Adding Pacific 06/18 UTC later is a one-line change: "npac": [0, 6, 18].
HOURS = {"natl": [0, 12], "npac": [0]}
START, END = dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31)


def accumulate():
    OUT.mkdir(parents=True, exist_ok=True)
    counts, rows, log = {}, [], []
    for basin in BASINS:
        tcache = {}
        cyc = sorted(c for h in HOURS[basin] for c in cases.cycles(basin, START, END, hour=h)
                     if store.load_ens(basin, c, "gefs", 24) is not None)
        print(basin, "cycles with GEFS in the store:", len(cyc), flush=True)
        for c in cyc:
            fetch.wait_for_quiet()
            split = cases.split(c)
            for step in cases.STEPS:
                ens = store.load_ens(basin, c, "gefs", step)
                if ens is None:
                    continue
                valid = c + dt.timedelta(hours=step)
                if valid not in tcache:
                    have = store._analysis_path(basin, valid).exists()     # never trigger an analysis download
                    ag = truth.ascat_grid(basin, valid) if have else None
                    an = truth.analysis(basin, valid) if have else None
                    t = {}
                    if ag is not None:
                        t["box"], t["cell"] = ag["box"], ag["cells"]
                    if an is not None:
                        t["anl"] = np.where(an["mask"], an["mean_speed"], np.nan)
                    tcache[valid] = t
                    if len(tcache) > 12:
                        tcache.pop(next(iter(tcache)))
                    if ag is None or an is None:
                        log.append("%s %s: missing %s" % (basin, valid, [k for k in ("box", "anl") if k not in t]))
                nm = ens["n"]
                for thr in THRS:
                    p = ens["p%d" % thr]
                    for tn, tv in tcache[valid].items():
                        m = np.isfinite(tv)
                        if not m.any():
                            continue
                        k = np.rint(p[m] * nm).astype(int)
                        e = tv[m] >= thr
                        key = "|".join(map(str, (basin, tn, thr, step, split, nm)))
                        arr = counts.setdefault(key, np.zeros((2, nm + 1)))
                        arr[0] += np.bincount(k, minlength=nm + 1)
                        arr[1] += np.bincount(k[e], minlength=nm + 1)
                        rows.append((basin, tn, thr, step, c.strftime("%Y%m%d%H"), split, int(m.sum()), int(e.sum())))
        print(basin, "done", flush=True)
    json.dump({k: v.tolist() for k, v in counts.items()}, open(OUT / "counts.json", "w"))
    pd.DataFrame(rows, columns="basin truth thr step cycle split n events".split()).to_csv(OUT / "cycle_rows.csv", index=False)
    (OUT / "accumulate.log").write_text("\n".join(log) + "\n")
    print("wrote", OUT, "missing-truth notes:", len(log), flush=True)


def _expand(cnt, nm):
    """counts [2, nm+1] (cells, events) -> p, event, w arrays for rk.calibrate."""
    pv = np.arange(nm + 1) / nm
    n, ev = cnt[0], cnt[1]
    return np.r_[pv, pv], np.r_[np.ones(nm + 1), np.zeros(nm + 1)], np.r_[ev, n - ev]


def _pool(counts, basin, tn, thr, group, split):
    ps, es, ws = [], [], []
    for key, v in counts.items():
        b, t, th, st, sp, nm = key.split("|")
        if (b, t, int(th), sp) == (basin, tn, thr, split) and C.lead_group(int(st)) == group:
            p, e, w = _expand(np.array(v), int(nm))
            ps.append(p), es.append(e), ws.append(w)
    if not ps:
        return None
    return np.concatenate(ps), np.concatenate(es), np.concatenate(ws)


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from rk import style
    style.use()
    counts = {k: np.array(v) for k, v in json.load(open(OUT / "counts.json")).items()}
    rows = pd.read_csv(OUT / "cycle_rows.csv")
    rows["group"] = rows.step.map(C.lead_group)
    res, curves, allcurves, rel = [], {}, {}, []
    for basin in BASINS:
        for tn in TRUTHS:
            for thr in THRS:
                for g in C.LEAD_GROUPS:
                    tune, held = _pool(counts, basin, tn, thr, g, "tune"), _pool(counts, basin, tn, thr, g, "held_out")
                    if tune is None or held is None:
                        continue
                    tt = C.table(*tune[:2], w=tune[2])
                    raw, cal = C.fit(tt)
                    curves_key = (thr, basin, g)
                    allcurves.setdefault(tn, {})[curves_key] = (raw, cal)
                    if tn == "box":
                        curves[curves_key] = (raw, cal)
                    p, e, w = held
                    q = C.apply(p, raw, cal)
                    n = w.sum()
                    ev = (w * e).sum()
                    clim = ev / n
                    th_raw, th_cal = C.table(p, e, w=w), C.table(q, e, w=w)
                    r = rows[(rows.basin == basin) & (rows.truth == tn) & (rows.thr == thr) & (rows.group == g)]
                    rh, rt = r[r.split == "held_out"], r[r.split == "tune"]
                    anyev = lambda d: int((d.groupby("cycle").events.sum() > 0).sum())  # noqa: E731
                    res.append(dict(
                        basin=basin, truth=tn, thr=thr, lead=g, label=LABEL,
                        tune_cells=int(tune[2].sum()), tune_events=int((tune[2] * tune[1]).sum()),
                        tune_cycles=rt.cycle.nunique(), tune_cycles_with_event=anyev(rt),
                        held_cells=int(n), held_events=int(ev), held_cycles=rh.cycle.nunique(),
                        held_cycles_with_event=anyev(rh), held_base_rate=clim,
                        bss_raw=C.brier_skill(p, e, clim, w), bss_remap=C.brier_skill(q, e, clim, w),
                        brier_raw=C.brier(p, e, w), brier_remap=C.brier(q, e, w),
                        relerr_raw=C.reliability_error(th_raw), relerr_remap=C.reliability_error(th_cal),
                        raw_for_30=C.raw_for(30, raw, cal), raw_for_50=C.raw_for(50, raw, cal),
                        raw_for_90=C.raw_for(90, raw, cal), cal_at_30=float(C.cal_at(30, raw, cal)),
                        cal_at_10=float(C.cal_at(10, raw, cal)),
                        raw_knots=json.dumps(raw), cal_knots=json.dumps(cal)))
                    for kind, t in (("raw", th_raw), ("remap", th_cal)):
                        rr = C._rel(t)
                        for i in range(len(rr["n"])):
                            rel.append(dict(basin=basin, truth=tn, thr=thr, lead=g, kind=kind, bin_lo=C.EDGES[i],
                                            n=rr["n"][i], events=rr["events"][i], mean_fc=rr["mean_fc"][i],
                                            obs_freq=rr["obs_freq"][i]))
    df = pd.DataFrame(res)
    df.to_csv(OUT / "results.csv", index=False, float_format="%.5g")
    relf = pd.DataFrame(rel)
    relf.to_csv(OUT / "reliability_bins.csv", index=False, float_format="%.5g")
    C.to_page_json(curves, note="GEFS only, first look: GEFS member fraction vs ASCAT 3x3 box, fitted on tune weeks "
                   "of winter 2025-26 (Nov-Dec 2025 cycles in the store). NOT for the page: the page pools "
                   "GEFS + ECMWF ENS + AIFS ENS.", path=OUT / "curves.json")
    json.dump({tn: json.loads(json.dumps(C.to_page_json(c))) for tn, c in allcurves.items()},
              open(OUT / "curves_all_truths.json", "w"), indent=1)
    # figures: one per truth x threshold, one panel per lead group, held-out weeks
    for tn in TRUTHS:
        for thr in THRS:
            fig, axs = plt.subplots(1, 3, figsize=(11.5, 4.2))
            hi = 0.05
            for ax, g in zip(axs, C.LEAD_GROUPS):
                for basin in BASINS:
                    col = style.BASIN_COLORS[basin]
                    for kind in ("raw", "remap"):
                        d = relf[(relf.basin == basin) & (relf.truth == tn) & (relf.thr == thr) & (relf.lead == g)
                                 & (relf.kind == kind) & (relf.n >= 30)]
                        if not len(d):
                            continue
                        hi = max(hi, d.mean_fc.max(), d.obs_freq.max())
                        if kind == "raw":
                            ax.plot(d.mean_fc, d.obs_freq, "--", marker="o", mfc="white", mec=col, color=col, lw=1.3, ms=5)
                        else:
                            ax.plot(d.mean_fc, d.obs_freq, "-", marker="o", color=col, ms=5)
                ax.text(0.04, 0.94, {"le48": "+24 and +48 h", "72": "+72 h", "ge96": "+96 and +120 h"}[g], transform=ax.transAxes,
                        fontsize=10, color=style.INK, va="top")
            hi = min(1.0, hi * 1.1)
            for ax in axs:
                ax.plot([0, hi], [0, hi], color=style.SPINE, lw=1, zorder=0)
                ax.set_xlim(0, hi), ax.set_ylim(0, hi)
                ax.set_xlabel("GEFS chance of %d kt or more" % thr)
            axs[0].set_ylabel("how often it happened (%s)" % TRUTH_LABEL[tn])
            from matplotlib.lines import Line2D
            h = [Line2D([], [], color=style.BASIN_COLORS[b], lw=2, label=cases_name(b)) for b in BASINS]
            h += [Line2D([], [], color="#5f5e5a", ls="--", marker="o", mfc="white", label="raw"),
                  Line2D([], [], color="#5f5e5a", marker="o", label="remapped")]
            axs[2].legend(handles=h, loc="lower right")
            s = df[(df.truth == tn) & (df.thr == thr) & (df.lead == "le48")].set_index("basin")
            bit = ", ".join("%s %.2f to %.2f" % ({"natl": "Atl", "npac": "Pac"}[b], s.loc[b, "bss_raw"], s.loc[b, "bss_remap"])
                            for b in BASINS if b in s.index)
            style.title(axs[0], "%d kt chance runs %s; remap moves Brier skill %s (+24/48, held-out)" % (
                thr, "high" if _over(relf, tn, thr) else "low", bit),
                "%s. %s truth. Nov-Dec 2025 cycles in the store; fit on tune weeks, shown for held-out weeks; bins of 30+ cells." % (LABEL, TRUTH_LABEL[tn]))
            style.save(fig, OUT / ("reliability_%s_%d" % (tn, thr)))
            plt.close(fig)
    print("report written to", OUT)


def _over(relf, tn, thr):
    d = relf[(relf.truth == tn) & (relf.thr == thr) & (relf.kind == "raw") & (relf.n >= 30) & (relf.mean_fc > 0.05)]
    return (d.n * (d.mean_fc - d.obs_freq)).sum() > 0


def cases_name(b):
    from rk.basins import BASINS as B
    return B[b]["name"]


if __name__ == "__main__":
    {"accumulate": accumulate, "report": report}[sys.argv[1]]()
