#!/usr/bin/env python3
"""Learn the core stretch on tune weeks and score it (design.md).

  python3 fit.py            tune weeks: the mapping tables (tables.csv) and in-sample scores (tune_results.md)
  python3 fit.py --final    held-out weeks, once: scores vs Core Lifted -> final_results.md / .json (refuses to rerun)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import cases, compare, paths  # noqa: E402

LIFT_KT, LIFT_P = 5.0, 0.35          # live Core Lifted (awips-tools marine_wind/pipeline/storm.py)
CAP = 0.8                            # x geostrophic speed
LEVELS = np.r_[np.arange(1, 100), 99.5] / 100.0
BINS = (-np.inf, 20.0, 30.0, np.inf)
MIN_CELLS, MIN_64 = 2000, 30
NB = 5
KEYS = ["basin", "event_id", "valid", "lead"]


def load():
    t = pd.read_parquet(paths.cache("extra", "hf-stretch", "cells.parquet"))
    t["valid"] = pd.to_datetime(t["valid"])
    t["bin"] = np.digitize(t["drop"].fillna(0), BINS[1:-1])
    case_split = {v: cases.split(v.to_pydatetime()) for v in t.valid.unique()}
    t["split"] = t.valid.map(case_split)
    t["lifted"] = np.where(t.P >= LIFT_P, t.r10 + LIFT_KT, t.r10)
    return t


def tables(tu):
    """Quantile tables per (bin, lead), pooling leads where a bin is thin. -> {(bin, lead): (qs, qa)}"""
    core = tu[(tu.P >= LIFT_P) & tu.seen]
    out, rows = {}, []
    for b in range(len(BINS) - 1):
        cb = core[core.bin == b]
        if not len(cb):
            continue                                  # no seen core cells in this bin: Core Lifted stays
        pooled = None
        for lead in (24, 48, 72):
            g = cb[cb.lead == lead]
            if len(g) < MIN_CELLS or (g.ascat >= 64).sum() < MIN_64:
                if pooled is None:
                    pooled = (np.quantile(cb.r10, LEVELS), np.quantile(cb.ascat, LEVELS))
                out[(b, lead)] = pooled
                src = "pooled leads"
                n, n64 = len(cb), int((cb.ascat >= 64).sum())
            else:
                out[(b, lead)] = (np.quantile(g.r10, LEVELS), np.quantile(g.ascat, LEVELS))
                src = "own lead"
                n, n64 = len(g), int((g.ascat >= 64).sum())
            qs, qa = out[(b, lead)]
            rows.append(dict(bin=b, lead=lead, source=src, cells=n, cells64=n64,
                             r10_p90=qs[89], ascat_p90=qa[89], r10_p99=qs[98], ascat_p99=qa[98],
                             r10_p995=qs[-1], ascat_p995=qa[-1]))
    return out, pd.DataFrame(rows)


def mapped(x, qs, qa):
    qs, idx = np.unique(qs, return_index=True)
    qa = qa[idx]
    y = np.interp(x, qs, qa)
    y = np.where(x < qs[0], x + qa[0] - qs[0], y)
    return np.where(x > qs[-1], x + qa[-1] - qs[-1], y)


def stretch(t, tab):
    out = t.lifted.to_numpy().copy()
    core = (t.P >= LIFT_P).to_numpy()
    for (b, lead), (qs, qa) in tab.items():
        m = core & (t.bin == b).to_numpy() & (t.lead == lead).to_numpy()
        if m.any():
            out[m] = np.maximum(out[m], mapped(t.r10.to_numpy()[m], qs, qa))
    cap = CAP * t.vg.to_numpy()
    capped = out > np.maximum(cap, t.lifted.to_numpy())
    out = np.where(capped, np.maximum(cap, t.lifted.to_numpy()), out)
    return out, capped


def case_counts(g, col):
    """Neighbourhood counts for one case: dict per threshold."""
    iy, ix = g.iy.to_numpy() - g.iy.min(), g.ix.to_numpy() - g.ix.min()
    shape = (iy.max() + 1, ix.max() + 1)
    seen = np.zeros(shape, bool)
    seen[iy, ix] = g.seen.to_numpy()
    fc = np.full(shape, -1.0)
    fc[iy, ix] = g[col].to_numpy()
    ob = np.full(shape, -1.0)
    ob[iy, ix] = np.nan_to_num(g.ascat.to_numpy(), nan=-1.0)
    r = {}
    for thr in (48, 64):
        f_ = fc >= thr
        o_ = seen & (ob >= thr)
        fn = ndimage.maximum_filter(f_, size=NB, mode="constant")
        on = ndimage.maximum_filter(o_, size=NB, mode="constant")
        r.update({"o%d" % thr: int(o_.sum()), "o_hit%d" % thr: int((o_ & fn).sum()),
                  "f%d" % thr: int((f_ & seen).sum()), "f_hit%d" % thr: int((f_ & seen & on).sum())})
    return r


def score_table(t, cols):
    rows = []
    for k, g in t.groupby(KEYS, sort=False):
        r = dict(zip(KEYS, k))
        for c in cols:
            r.update({"%s_%s" % (c, n): v for n, v in case_counts(g, c).items()})
        rows.append(r)
    s = pd.DataFrame(rows)
    iso = pd.to_datetime(s.valid).dt.isocalendar()
    s["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    return s


def metrics(tot, c, thr, names):
    o, oh, f, fh = (tot[..., names.index("%s_%s%d" % (c, n, thr))] for n in ("o", "o_hit", "f", "f_hit"))
    with np.errstate(invalid="ignore", divide="ignore"):
        pod, sr = oh / o, fh / f
        csi = 1 / (1 / pod + 1 / sr - 1)
        return pod, sr, csi, f / o


def report(s, cols, title, lines, out=None):
    for lead in ("all", 24, 48, 72):
        h = s if lead == "all" else s[s.lead == lead]
        names = [n for n in s.columns if n.split("_")[0] in cols]
        tot, dr = compare.boot_sums(h.week.to_numpy(), h[names].to_numpy(float), n_boot=2000, seed=0)
        lines += ["", "### %s, lead %s (%d cases, %d weeks, %d storms)" % (
            title, lead, len(h), h.week.nunique(), h.groupby(["basin", "event_id"]).ngroups), "",
            "| Product | POD 64 | Success 64 | CSI 64 | Area ratio 64 | POD 48 | Success 48 | CSI 48 | Area ratio 48 |",
            "|---|---|---|---|---|---|---|---|---|"]
        for c in cols:
            m64, m48 = metrics(tot, c, 64, names), metrics(tot, c, 48, names)
            lines.append("| %s | %.3f | %.3f | %.3f | %.2f | %.3f | %.3f | %.3f | %.2f |" % ((c,) + m64 + m48))
        if "stretch" in cols:
            d64 = metrics(dr, "stretch", 64, names)[2] - metrics(dr, "lifted", 64, names)[2]
            d48 = metrics(dr, "stretch", 48, names)[2] - metrics(dr, "lifted", 48, names)[2]
            c64 = metrics(tot, "stretch", 64, names)[2] - metrics(tot, "lifted", 64, names)[2]
            c48 = metrics(tot, "stretch", 48, names)[2] - metrics(tot, "lifted", 48, names)[2]
            lo64, hi64 = np.nanpercentile(d64, [2.5, 97.5])
            lo48, hi48 = np.nanpercentile(d48, [2.5, 97.5])
            lines += ["", "CSI 64 stretch minus Core Lifted: %+.3f [%+.3f, %+.3f]; CSI 48: %+.3f [%+.3f, %+.3f]" % (
                c64, lo64, hi64, c48, lo48, hi48)]
            if out is not None and lead == "all":
                ar = metrics(tot, "stretch", 64, names)[3]
                out.update(csi64_diff=[c64, lo64, hi64], csi48_diff=[c48, lo48, hi48], area64=float(ar),
                           counts=dict(cases=len(h), weeks=int(h.week.nunique()),
                                       storms=int(h.groupby(["basin", "event_id"]).ngroups),
                                       ascat64_cells=int(h["stretch_o64"].sum())))


def main(final):
    t = load()
    tu = t[t.split == "tune"]
    tab, tdf = tables(tu)
    if not final:
        tdf.to_csv(HERE / "tables.csv", index=False, float_format="%.2f")
    part = t[t.split == ("held_out" if final else "tune")].copy()
    part["stretch"], capped = stretch(part, tab)
    core = (part.P >= LIFT_P).to_numpy()
    lines = ["# %s" % ("Held-out weeks (scored once)" if final else "Tune weeks (in-sample)"), "",
             "Core cells: %d; cap binds in %.1f%% of them." % (core.sum(), 100 * capped[core].mean())]
    s = score_table(part, ["lifted", "stretch", "r10"])
    res = {}
    report(s, ["r10", "lifted", "stretch"], "Scores", lines, res if final else None)
    if final:
        oj, om = HERE / "final_results.json", HERE / "final_results.md"
        if oj.exists() or om.exists():
            raise SystemExit("final results exist: the held-out score runs once")
        res["passed"] = bool(res["csi64_diff"][1] > 0 and res["area64"] <= 1.5 and res["csi48_diff"][0] >= -0.02)
        res["cap_binds_core"] = float(capped[core].mean())
        oj.write_text(json.dumps(res, indent=1, default=float) + "\n")
        lines += ["", "Pass (CSI 64 interval above 0, area ratio 64 <= 1.5, CSI 48 >= Core Lifted - 0.02): %s"
                  % res["passed"]]
        om.write_text("\n".join(lines) + "\n")
    else:
        (HERE / "tune_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    main(ap.parse_args().final)
