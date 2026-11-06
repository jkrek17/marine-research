#!/usr/bin/env python3
"""925 mix-down study (design.md): what ASCAT saw in gap cells, then the grid lift and warning trigger.

  python3 analyze.py            # reads build.py's cases from RK_CACHE, writes CSVs + RESULTS.json here

Gap cell: GFS 925 >= 35 kt, GFS 10 m < 25 kt, GFS skin - 2 m >= 5 C (rk.features.mixdown_gap).
Split: by cycle (rk.cases.held_out); tune rows whose valid time is also a held-out valid time are dropped.
"""
import datetime as dt, glob, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rk import cases, compare, features, paths  # noqa: E402
from rk.basins import grid  # noqa: E402

GALE = 34.0
WARM = {"natl": (33, 44, 285, 315), "npac": (30, 42, 160, 185)}   # Gulf Stream / Kuroshio Extension boxes
CACHE = Path(os.environ.get("MIX_CACHE", paths.cache("extra", "925-mixdown")))


def load():
    p = CACHE / "cells.parquet"
    if p.exists():
        return pd.read_parquet(p)
    frames = []
    for basin in ("natl", "npac"):
        lats, lons = grid(basin)
        for f in sorted(glob.glob(str(CACHE / basin / "*.npz"))):
            stem = Path(f).stem
            cyc = dt.datetime.strptime(stem.split("_f")[0], "%Y%m%d%H")
            step = int(stem.split("_f")[1])
            with np.load(f) as z:
                d = {k: z[k] for k in z.files}
            if d["iy"].size == 0:
                continue
            df = pd.DataFrame({k: d[k].astype(np.float32) for k in ("asc", "gfs", "ifs", "det", "s925", "sa")})
            df["iy"], df["ix"] = d["iy"], d["ix"]
            df["lat"], df["lon"] = lats[d["iy"]].astype(np.float32), lons[d["ix"]].astype(np.float32)
            df["basin"], df["cycle"], df["step"] = basin, cyc, step
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["valid"] = df["cycle"] + pd.to_timedelta(df["step"], unit="h")
    df["split"] = split_of(df["cycle"])
    hv = set(df.loc[df.split == "held_out", "valid"].unique())
    df = df[~((df.split == "tune") & df["valid"].isin(hv))].reset_index(drop=True)
    df = df.dropna(subset=["asc", "gfs", "s925", "sa"]).reset_index(drop=True)
    lo = df["lon"] % 360
    warm = np.zeros(len(df), bool)
    for b, (s, n, w, e) in WARM.items():
        warm |= (df.basin == b).to_numpy() & (df.lat >= s).to_numpy() & (df.lat <= n).to_numpy() & (lo >= w).to_numpy() & (lo <= e).to_numpy()
    df["warm"] = warm
    df.to_parquet(p)
    return df


def split_of(cyc):
    u = pd.Series(pd.unique(cyc))
    m = {c: ("held_out" if cases.held_out(c.to_pydatetime()) else "tune") for c in u}
    return cyc.map(m).to_numpy()


def gap(df, s925=35.0, ten=25.0, sa=5.0):
    return features.mixdown_gap(df["s925"].to_numpy(), df["gfs"].to_numpy(), df["sa"].to_numpy(), s925, ten, sa)


def describe(g, label):
    asc, s9 = g["asc"].to_numpy(float), g["s925"].to_numpy(float)
    r = asc / s9
    ct = g.drop_duplicates(["basin", "valid", "iy", "ix"])
    return dict(group=label, cells=len(g), cell_times=len(ct), cases=g.groupby(["basin", "cycle", "step"]).ngroups,
                gale_frac=float((asc >= GALE).mean()) if len(g) else np.nan,
                gale_frac_celltimes=float((ct["asc"] >= GALE).mean()) if len(ct) else np.nan,
                storm_frac=float((asc >= 48).mean()) if len(g) else np.nan,
                asc_median=float(np.median(asc)) if len(g) else np.nan,
                s925_median=float(np.median(s9)) if len(g) else np.nan,
                gfs_median=float(g["gfs"].median()), det_median=float(g["det"].median()),
                det_bias=float((g["det"] - g["asc"]).mean()),
                ratio_p10=float(np.percentile(r, 10)) if len(g) else np.nan,
                ratio_p50=float(np.median(r)) if len(g) else np.nan,
                ratio_p90=float(np.percentile(r, 90)) if len(g) else np.nan,
                need_ratio_for_gale=float(np.median(GALE / s9)) if len(g) else np.nan)


def physics(df):
    rows = []
    for lead, d in (("+24/+30", df[df.step <= 30]), ("all leads", df)):
        base = (d.s925 >= 35) & (d.gfs < 25)
        for lab, m in (("gap: sa >= 5", base & (d.sa >= 5)), ("sa 5-8", base & (d.sa >= 5) & (d.sa < 8)),
                       ("sa 8+", base & (d.sa >= 8)), ("sa >= 5, warm current", base & (d.sa >= 5) & d.warm),
                       ("sa >= 5, elsewhere", base & (d.sa >= 5) & ~d.warm),
                       ("control sa 2-5", base & (d.sa >= 2) & (d.sa < 5)), ("control sa < 2", base & (d.sa < 2)),
                       ("925 >= 30 (sa >= 5)", (d.s925 >= 30) & (d.gfs < 25) & (d.sa >= 5)),
                       ("925 >= 40 (sa >= 5)", (d.s925 >= 40) & (d.gfs < 25) & (d.sa >= 5)),
                       ("925 35-40", base & (d.sa >= 5) & (d.s925 < 40)),
                       ("925 40-45", base & (d.sa >= 5) & (d.s925 >= 40) & (d.s925 < 45)),
                       ("925 45+", base & (d.sa >= 5) & (d.s925 >= 45)),
                       ("10 m < 20 (gap)", base & (d.sa >= 5) & (d.gfs < 20))):
            for b in ("natl", "npac", "both"):
                g = d[m & ((d.basin == b) if b != "both" else True)]
                rows.append(dict(lead=lead, basin=b, **describe(g, lab)))
    return pd.DataFrame(rows)


# ---- products ---------------------------------------------------------------------------------------------
def tune_factors(df):
    t = df[(df.split == "tune") & gap(df)]
    return {"5-8": float(np.median(t.asc[t.sa < 8] / t.s925[t.sa < 8])), "8+": float(np.median(t.asc[t.sa >= 8] / t.s925[t.sa >= 8]))}


def grid_products(df, f):
    det = df["det"].to_numpy(float)
    g = gap(df)
    fac = np.where(df.sa.to_numpy() >= 8, f["8+"], f["5-8"])
    return {"blend": det,
            "gap -> 34": np.where(g, np.maximum(det, GALE), det),
            "gap -> 925 x f": np.where(g, np.maximum(det, df.s925.to_numpy() * fac), det)}


def warn_products(df):
    strong = np.fmax(df["gfs"].to_numpy(float), df["ifs"].to_numpy(float))
    return strong, gap(df)


def counts(df, fc_event, ob_event):
    """Per-case cell counts and tile counts (5 deg tiles, >= 150 seen cells)."""
    k = df[["basin", "cycle", "step"]].copy()
    k["h"], k["f"], k["m"] = fc_event & ob_event, fc_event & ~ob_event, ~fc_event & ob_event
    k["ob"] = ob_event
    k["tile"] = (np.floor(df.lat / 5).astype(int) * 1000 + np.floor((df.lon % 360) / 5).astype(int)).to_numpy()
    k["fe"], k["oe"] = fc_event, ob_event
    tg = k.groupby(["basin", "cycle", "step", "tile"]).agg(n=("ob", "size"), fe=("fe", "any"), oe=("oe", "any"))
    tg = tg[tg.n >= 150]
    tg["th"], tg["tf"], tg["tm"] = tg.fe & tg.oe, tg.fe & ~tg.oe, ~tg.fe & tg.oe
    cc = k.groupby(["basin", "cycle", "step"])[["h", "f", "m", "ob"]].sum()
    tc = tg.groupby(["basin", "cycle", "step"])[["th", "tf", "tm"]].sum()
    return cc.join(tc, how="left").fillna(0).reset_index()


def summarise(c):
    s = c[["h", "f", "m", "ob", "th", "tf", "tm"]].sum()
    return dict(pod=s.h / (s.h + s.m), far=s.f / max(s.h + s.f, 1), csi=s.h / (s.h + s.f + s.m),
                area=(s.h + s.f) / max(s.ob, 1), tile_catch=s.th / max(s.th + s.tm, 1),
                tile_csi=s.th / max(s.th + s.tf + s.tm, 1), false_tiles=int(s.tf), gale_cells=int(s.ob), gale_tiles=int(s.th + s.tm))


def area_match(df, mask, target_cells, base, lo=20.0, hi=34.0):
    """Threshold T on `base` so cells with base >= T match `target_cells` (count) in mask rows."""
    v = np.sort(base[mask])[::-1]
    if target_cells <= 0 or len(v) == 0:
        return hi
    return float(np.clip(v[min(int(target_cells), len(v)) - 1], lo, hi))


def main():
    df = load()
    print("cells", len(df), df.groupby(["basin", "split"]).size().to_dict(), flush=True)
    phys = physics(df)
    phys.to_csv(HERE / "gap_cells.csv", index=False, float_format="%.3f")
    df = df.dropna(subset=["det", "ifs"]).reset_index(drop=True)   # products need the #95 blend and ECMWF
    print("cells with blend", len(df), flush=True)
    f = tune_factors(df)
    ob = (df.asc >= GALE).to_numpy()
    tune = (df.split == "tune").to_numpy()
    res = {"factors_tune": f, "grid": {}, "warn": {}}
    long_rows = []
    # ---- grid: equal-area control = the blend's gale threshold lowered to T (tune), applied everywhere
    gp = grid_products(df, f)
    for name in ("gap -> 34", "gap -> 925 x f"):
        for b in ("natl", "npac"):
            mb = (df.basin == b).to_numpy()
            T = area_match(df, mb & tune, (gp[name][mb & tune] >= GALE).sum(), gp["blend"])
            res["grid"].setdefault(name, {})[b + "_control_T"] = T
            gp_ctrl = np.where(mb, gp["blend"] >= T, False)
            gp.setdefault("ctrl " + name, np.zeros(len(df), bool))
            gp["ctrl " + name] |= gp_ctrl
    events = {k: (v >= GALE) if v.dtype != bool else v for k, v in gp.items()}
    for k, ev in events.items():
        c = counts(df, ev, ob)
        c["method"] = k
        long_rows.append(c.assign(kind="grid"))
    # ---- warning: today's line strongest >= 30; trigger = line | gap; control = strongest >= T at equal area
    strong, g = warn_products(df)
    wev = {"line 30": strong >= 30, "line 30 + gap": (strong >= 30) | g}
    for b in ("natl", "npac"):
        mb = (df.basin == b).to_numpy()
        T = area_match(df, mb & tune, wev["line 30 + gap"][mb & tune].sum(), strong, lo=20, hi=30)
        res["warn"][b + "_control_T"] = T
        wev.setdefault("line T (equal area)", np.zeros(len(df), bool))
        wev["line T (equal area)"] |= mb & (strong >= T)
    for k, ev in wev.items():
        c = counts(df, ev, ob)
        c["method"] = k
        long_rows.append(c.assign(kind="warn"))
    L = pd.concat(long_rows, ignore_index=True)
    L["split"] = split_of(L["cycle"])
    L.to_csv(HERE / "case_counts.csv.gz", index=False)
    summ = []
    for (kind, meth, b, sp), g_ in L.groupby(["kind", "method", "basin", "split"]):
        summ.append(dict(kind=kind, method=meth, basin=b, split=sp, **summarise(g_)))
    summ = pd.DataFrame(summ)
    summ.to_csv(HERE / "summary.csv", index=False, float_format="%.4f")
    # ---- paired, held-out
    pr = []
    cnt = ["h", "f", "m", "ob", "th", "tf", "tm"]
    metrics = {"pod": lambda c: c["h"] / (c["h"] + c["m"]), "csi": lambda c: c["h"] / (c["h"] + c["f"] + c["m"]),
               "area": lambda c: (c["h"] + c["f"]) / c["ob"], "tile_catch": lambda c: c["th"] / (c["th"] + c["tm"]),
               "tile_csi": lambda c: c["th"] / (c["th"] + c["tf"] + c["tm"])}
    H = L[L.split == "held_out"].drop(columns=["split", "kind"])
    for m_, base in (("gap -> 34", "blend"), ("gap -> 34", "ctrl gap -> 34"), ("gap -> 925 x f", "blend"),
                     ("gap -> 925 x f", "ctrl gap -> 925 x f"), ("line 30 + gap", "line 30"),
                     ("line 30 + gap", "line T (equal area)")):
        for mn, fn in metrics.items():
            p = compare.paired_counts(H, m_, base, fn, cnt, by="basin", case_cols=["basin", "cycle", "step"], n_boot=2000)
            p["method_name"], p["baseline_name"], p["metric"] = m_, base, mn
            pr.append(p)
    pd.concat(pr).to_csv(HERE / "heldout_paired.csv", index=False, float_format="%.4f")
    json.dump(res, open(HERE / "RESULTS.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
