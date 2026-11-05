#!/usr/bin/env python3
"""Fit and score the Core Lifted corrections from the cases build.py wrote (design.md).

  python3 fit_score.py                 TUNE weeks: 5-fold whole-week CV, selection by the design's win line
  python3 fit_score.py --final         HELD-OUT weeks, once: needs FINAL_CHOICE.json, refuses to rerun

Products (kt on the basin grid; CL = today's Core Lifted = gale_lift(r10 + 5 where P >= 0.35, Pg >= 0.6)):
  base        CL
  constL      r10 + L where P >= 0.35, then the gale floor; L = 0..10 (L = 5 is base)
  leadL       r10 + L(lead group) in cores; L per lead group picked on the tune weeks by the win line
  qmap        frequency matching: on candidate cells (ocean, CL >= 28) CL is mapped quantile-to-quantile onto
              ASCAT over seen candidate cells, one map per basin and lead group (d1 24-30 h, d2 48-54, d3 72-78,
              d45 96-126)
  qmap_core   qmap with separate maps in cores (P >= 0.35) and outside
  qmap_up     max(CL, qmap(CL)): the map may raise, never lower
  avgcorr     REFERENCE: mean ASCAT for each 2 kt CL bin (per basin and lead group) on candidate cells
Fitted products (qmap*, avgcorr) are fit on the other folds' tune weeks (out of fold) in tune mode and on all tune
weeks in --final mode.

Counts per case and product (case_counts.csv), thresholds 34/48/64:
  nt h m fa      5x5 deg tiles with >= 150 seen cells (as rk.score.tile_hits; tested against it)
  fc ob cau      seen cells with forecast >= thr / ASCAT >= thr / both (catch = cau/ob, area = fc/ob)
  afc aob acau   the same over all open water against the GFS+IFS analysis (00/12Z valid only)
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from rk import calibrate as calib, cases, compare, paths  # noqa: E402
from rk.basins import grid  # noqa: E402

LIFT_P, LIFT_KT, GALE_P, GALE_KT = 0.35, 5.0, 0.6, 34.0
CAND_KT = 28.0
THRS = (34, 48, 64)
LS = tuple(range(0, 11))
GROUPS = {"d1": (24, 30), "d2": (48, 54), "d3": (72, 78), "d45": (96, 102, 120, 126)}
STORM_AREA_CAP, GALE_AREA_CAP, GALE_CSI_TOL = 1.5, 1.3, 0.01
MIN_PAIRS = 2000
FOLDS = 5


def group_of(step):
    for g, s in GROUPS.items():
        if step in s:
            return g
    raise ValueError(step)


def folds(cycle):
    """Tune-week fold 0..4 (whole ISO weeks): hash the week so the 4 non-held-out residues spread over 5 folds."""
    y, w, _ = cycle.isocalendar()
    return (y * 53 + w) * 7 % 11 % FOLDS


def load_cases(basin, split):
    root = paths.cache("extra", "core-lift-bias", basin)
    out = []
    for p in sorted(root.glob("*.npz")):
        tag, step = p.stem.split("_f")
        cyc = cases.parse_tag(tag) if hasattr(cases, "parse_tag") else pd.Timestamp(
            "%s-%s-%s %s:00" % (tag[:4], tag[4:6], tag[6:8], tag[8:10])).to_pydatetime()
        if cases.split(cyc) != split:
            continue
        out.append((cyc, int(step), p))
    return out


def corelift(r10, P, Pg, L=LIFT_KT):
    w = np.where(P >= LIFT_P, r10 + L, r10)
    return np.where(Pg >= GALE_P, np.maximum(w, GALE_KT), w)


def read(p):
    z = np.load(p)
    d = {k: z[k] for k in z.files}
    for k in ("r10", "P", "Pg", "spd", "anl"):
        d[k] = d[k].astype(np.float32)
    d["CL"] = corelift(d["r10"], d["P"], d["Pg"])
    d["cand"] = d["ocean"] & (d["CL"] >= CAND_KT)
    return d


# ---- maps ----

def fit_qmap(x, y):
    return calib.quantile_map_fit(x, y, min_n=MIN_PAIRS)


def apply_qmap(m, x):
    return calib.quantile_map_apply(m, x)


def fit_avg(x, y):
    if len(x) < MIN_PAIRS:
        return None
    edges = np.arange(CAND_KT, 80, 2.0)
    b = np.digitize(x, edges)
    cx, cy = [], []
    for i in range(1, len(edges) + 1):
        s = b == i
        if s.sum() >= 30:
            cx.append(x[s].mean())
            cy.append(y[s].mean())
    return np.array(cx), np.array(cy)


def apply_avg(m, x):
    cx, cy = m
    out = np.interp(x, cx, cy)
    lo, hi = x < cx[0], x > cx[-1]
    out[lo] = x[lo] + (cy[0] - cx[0])
    out[hi] = x[hi] + (cy[-1] - cx[-1])
    return out


def fit_maps(pairs, train_mask):
    """pairs: DataFrame of seen candidate cells (group, core, CL, spd, fold). -> {kind: {key: map}}."""
    t = pairs[train_mask]
    maps = {"qmap": {}, "qmap_core": {}, "avgcorr": {}}
    for g, gg in t.groupby("group"):
        maps["qmap"][g] = fit_qmap(gg.CL.to_numpy(), gg.spd.to_numpy())
        maps["avgcorr"][g] = fit_avg(gg.CL.to_numpy(), gg.spd.to_numpy())
        for c in (0, 1):
            s = gg[gg.core == c]
            maps["qmap_core"][(g, c)] = fit_qmap(s.CL.to_numpy(), s.spd.to_numpy()) or maps["qmap"][g]
    return maps


def mapped(d, g, maps, kind):
    CL, cand = d["CL"], d["cand"]
    out = CL.copy()
    if kind in ("qmap", "qmap_up"):
        m = maps["qmap"].get(g)
        if m is None:
            return None
        out[cand] = apply_qmap(m, CL[cand])
        if kind == "qmap_up":
            out = np.maximum(out, CL)
    elif kind == "qmap_core":
        core = d["P"] >= LIFT_P
        for c in (0, 1):
            m = maps["qmap_core"].get((g, c))
            if m is None:
                return None
            s = cand & (core == bool(c))
            out[s] = apply_qmap(m, CL[s])
    elif kind == "avgcorr":
        m = maps["avgcorr"].get(g)
        if m is None:
            return None
        out[cand] = apply_avg(m, CL[cand])
    return out.astype(np.float32)


# ---- counts ----

class Tiles:
    """Precomputed tile layout for one case (as rk.score.tile_hits: 5x5 deg, >= 150 seen cells)."""

    def __init__(self, basin, seen):
        lats, lons = grid(basin)
        la, lo = np.meshgrid(lats, lons, indexing="ij")
        key = (np.floor(la / 5).astype(int) + 100) * 1000 + np.floor((lo % 360) / 5).astype(int)
        k = key[seen]
        self.ok = k.size > 0
        if self.ok:
            uk, self.inv = np.unique(k, return_inverse=True)
            self.keep = np.bincount(self.inv) >= 150
        self.seen = seen

    def counts(self, fc, ob, thr):
        if not self.ok:
            return 0, 0, 0, 0
        o = np.bincount(self.inv, weights=np.nan_to_num(ob[self.seen], nan=-1) >= thr)[self.keep] > 0
        f = np.bincount(self.inv, weights=np.nan_to_num(fc[self.seen], nan=-1) >= thr)[self.keep] > 0
        return int(self.keep.sum()), int((o & f).sum()), int((o & ~f).sum()), int((~o & f).sum())


def case_counts(d, tiles, fc):
    r = {}
    seen, spd, anl = d["seen"], d["spd"], d["anl"]
    aw = np.isfinite(anl)
    for t in THRS:
        nt, h, m, fa = tiles.counts(fc, spd, t)
        f, o = seen & (fc >= t), seen & (np.nan_to_num(spd, nan=-1) >= t)
        af, ao = aw & (fc >= t), aw & (np.nan_to_num(anl, nan=-1) >= t)
        r.update({"nt%d" % t: nt, "h%d" % t: h, "m%d" % t: m, "fa%d" % t: fa,
                  "fc%d" % t: int(f.sum()), "ob%d" % t: int(o.sum()), "cau%d" % t: int((f & o).sum()),
                  "afc%d" % t: int(af.sum()), "aob%d" % t: int(ao.sum()), "acau%d" % t: int((af & ao).sum())})
    r["anl_ok"] = int(aw.any())
    return r


def collect_pairs(basin, cs):
    rows = []
    for cyc, step, p in cs:
        d = read(p)
        s = d["seen"] & d["cand"]
        if not s.any():
            continue
        rows.append(pd.DataFrame({"group": group_of(step), "core": (d["P"][s] >= LIFT_P).astype(int),
                                  "CL": d["CL"][s], "spd": d["spd"][s], "fold": folds(cyc)}))
    return pd.concat(rows, ignore_index=True)


def score_cases(basin, cs, maps_for, lead_L=None):
    """maps_for(cyc) -> maps fitted without that cycle's fold (or on all tune weeks). lead_L: {group: L}."""
    out = []
    for cyc, step, p in cs:
        d = read(p)
        g = group_of(step)
        tiles = Tiles(basin, d["seen"])
        key = {"basin": basin, "cycle": cyc, "step": step, "group": g, "fold": folds(cyc)}
        prods = {"base": d["CL"]}
        for L in LS:
            prods["const%d" % L] = corelift(d["r10"], d["P"], d["Pg"], L)
        if lead_L:
            prods["leadL"] = corelift(d["r10"], d["P"], d["Pg"], lead_L[basin][g])
        maps = maps_for(cyc)
        for kind in ("qmap", "qmap_core", "qmap_up", "avgcorr"):
            f = mapped(d, g, maps, kind)
            if f is not None:
                prods[kind] = f
        for name, f in prods.items():
            out.append(dict(key, product=name, **case_counts(d, tiles, f)))
    return pd.DataFrame(out)


# ---- summaries ----

def pooled(df, by):
    s = df.groupby(by)[[c for c in df.columns if c[:2] in ("nt", "h3", "h4", "h6", "m3", "m4", "m6", "fa", "fc",
                                                              "ob", "ca", "af", "ao", "ac")]].sum()
    for t in THRS:
        s["pod%d" % t] = s["h%d" % t] / (s["h%d" % t] + s["m%d" % t])
        s["far%d" % t] = s["fa%d" % t] / (s["h%d" % t] + s["fa%d" % t])
        s["csi%d" % t] = s["h%d" % t] / (s["h%d" % t] + s["m%d" % t] + s["fa%d" % t])
        s["catch%d" % t] = s["cau%d" % t] / s["ob%d" % t]
        s["area%d" % t] = s["fc%d" % t] / s["ob%d" % t]
        s["acatch%d" % t] = s["acau%d" % t] / s["aob%d" % t]
        s["aarea%d" % t] = s["afc%d" % t] / s["aob%d" % t]
    return s.reset_index()


def passes(row, base):
    return (row.area48 <= STORM_AREA_CAP and row.area34 <= GALE_AREA_CAP
            and row.csi34 >= base.csi34 - GALE_CSI_TOL)


def pick_L(summ, by_group):
    """Per basin (and group if by_group): the constL with the highest storm-tile catch that passes the line."""
    out = {}
    keys = ["basin", "group"] if by_group else ["basin"]
    for k, g in summ.groupby(keys):
        k = k[0] if len(keys) == 1 else k
        base = g[g["product"] == "base"].iloc[0]
        best = None
        for L in LS:
            r = g[g["product"] == "const%d" % L].iloc[0]
            if passes(r, base) and (best is None or r.pod48 > best[1] + 1e-12):
                best = (L, r.pod48)
        out[k] = best[0] if best else int(LIFT_KT)
    return out


def paired(df, prods, baseline="base", by=("basin",), n_boot=2000):
    rows = []
    d = df.copy()
    d["cycle"] = pd.to_datetime(d["cycle"])
    metrics = {"pod48": (["h48", "m48"], lambda c: c["h48"] / (c["h48"] + c["m48"])),
               "catch48": (["cau48", "ob48"], lambda c: c["cau48"] / c["ob48"]),
               "area48": (["fc48", "ob48"], lambda c: c["fc48"] / c["ob48"]),
               "csi34": (["h34", "m34", "fa34"], lambda c: c["h34"] / (c["h34"] + c["m34"] + c["fa34"])),
               "area34": (["fc34", "ob34"], lambda c: c["fc34"] / c["ob34"]),
               "catch64": (["cau64", "ob64"], lambda c: c["cau64"] / c["ob64"])}
    for p in prods:
        for mname, (cnt, fn) in metrics.items():
            r = compare.paired_counts(d[d["product"].isin([p, baseline])], p, baseline, fn, cnt, by=list(by),
                                      n_boot=n_boot, method_col="product",
                                      case_cols=["basin", "cycle", "step"])
            r["metric"] = mname
            rows.append(r)
    return pd.concat(rows, ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--basins", default="natl,npac")
    ap.add_argument("--results", default=str(HERE))
    a = ap.parse_args()
    res = Path(a.results)
    basins = a.basins.split(",")
    if not a.final:
        allcounts = []
        for b in basins:
            cs = load_cases(b, "tune")
            pairs = collect_pairs(b, cs)
            print("%s: %d tune cases, %d seen candidate cells" % (b, len(cs), len(pairs)), flush=True)
            fm = {k: fit_maps(pairs, pairs.fold != k) for k in range(FOLDS)}
            allcounts.append(score_cases(b, cs, lambda cyc: fm[folds(cyc)]))
        df = pd.concat(allcounts, ignore_index=True)
        df.to_csv(res / "tune_case_counts.csv", index=False)
        summ = pooled(df, ["basin", "product"])
        summ_g = pooled(df, ["basin", "group", "product"])
        Lc = pick_L(summ, False)
        Lg = pick_L(summ_g, True)
        lead = {b: {g: Lg.get((b, g), 5) for g in GROUPS} for b in basins}
        # score leadL on the tune weeks with the picked sizes (in-sample pick; the held-out run is the test)
        lc = []
        for b in basins:
            cs = load_cases(b, "tune")
            lc.append(score_cases(b, cs, lambda cyc: {"qmap": {}, "qmap_core": {}, "avgcorr": {}}, lead_L=lead))
        lc = pd.concat(lc, ignore_index=True)
        df = pd.concat([df, lc[lc["product"] == "leadL"]], ignore_index=True)
        df.to_csv(res / "tune_case_counts.csv", index=False)
        summ = pooled(df, ["basin", "product"])
        summ_g = pooled(df, ["basin", "group", "product"])
        summ.to_csv(res / "tune_summary.csv", index=False)
        summ_g.to_csv(res / "tune_summary_by_lead.csv", index=False)
        json.dump({"constL": {k: v for k, v in Lc.items()}, "leadL": lead}, open(res / "tune_picks.json", "w"),
                  indent=1)
        cols = ["basin", "product", "pod48", "far48", "csi48", "catch48", "area48", "csi34", "catch34", "area34",
                "catch64", "area64", "acatch48", "aarea48"]
        print(summ[summ["product"].isin(["base", "const3", "const5", "const8", "const10", "leadL", "qmap",
                                         "qmap_core", "qmap_up", "avgcorr"])][cols].round(3).to_string())
        print("picks: constL", Lc, "leadL", lead)
        return
    # ---- final: held-out weeks, once ----
    choice = HERE / "FINAL_CHOICE.json"
    marker = HERE / "FINAL_RUN.json"
    if not choice.exists():
        sys.exit("FINAL_CHOICE.json missing: write it from the tune results first")
    if marker.exists() or (res / "final_case_counts.csv").exists():
        sys.exit("the held-out run has already been made; it is a one-time gate")
    ch = json.load(open(choice))
    allcounts = []
    for b in basins:
        tc = load_cases(b, "tune")
        pairs = collect_pairs(b, tc)
        maps = fit_maps(pairs, np.ones(len(pairs), bool))
        hc = load_cases(b, "held_out")
        print("%s: %d held-out cases" % (b, len(hc)), flush=True)
        c = score_cases(b, hc, lambda cyc: maps, lead_L=ch["leadL"])
        keep = ["base", "const%d" % ch["constL"][b], "leadL", "qmap", "qmap_core", "qmap_up", "avgcorr"]
        c = c[c["product"].isin(keep)].copy()
        c.loc[c["product"] == "const%d" % ch["constL"][b], "product"] = "constL"
        allcounts.append(c)
    df = pd.concat(allcounts, ignore_index=True)
    json.dump({"ran": pd.Timestamp.utcnow().isoformat(), "choice": ch}, open(marker, "w"))
    df.to_csv(res / "final_case_counts.csv", index=False)
    summ = pooled(df, ["basin", "product"])
    summ.to_csv(res / "final_summary.csv", index=False)
    pooled(df, ["basin", "group", "product"]).to_csv(res / "final_summary_by_lead.csv", index=False)
    prods = [p for p in df["product"].unique() if p != "base"]
    pr = paired(df, prods)
    pr.to_csv(res / "final_paired.csv", index=False)
    print(summ.round(3).to_string())
    print(pr.round(3).to_string())


if __name__ == "__main__":
    main()
