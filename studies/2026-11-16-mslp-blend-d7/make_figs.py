"""Worked-case map sets for the forecaster briefing (design.md "Worked cases"; selection in select_cases.py).

One PNG per case in figs/, three panels at +120 h (day 5):
  1 ECMWF ensemble mean (isobars) with every ensemble member's own low as a dot (12Z cycles only),
  2 GFS+ECMWF mean field (isobars) with the member-vote lows: depth label from the voters' own depths, 10-90% range,
    chance it exists, 50% / 80% position circles sized by member support, alternative scenario if >= 20% of members,
    G / E marks for the single-model lows,
  3 the analysis (mean of the GFS and IFS analyses) with its lows; hollow rings = the vote lows for comparison.
Also writes results/worked_cases_detail.csv (the numbers quoted for each case) and results/worked_cases.csv.

Inputs: the MSLP-only extract files and the Part B vote files (rk.paths.cache), members through rk.store.load (the
unpacked store files are cleaned afterwards with extract.clean), calibration in results/partb_params.json.
Plain lat/lon axes (cartopy is not installed); land is the analysis open-water mask.
Usage: python3 make_figs.py
"""
import json
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (str(REPO), str(HERE), str(REPO / "studies" / "2026-10-16-pressure-d5-7")):
    if p not in sys.path:
        sys.path.insert(0, p)
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from rk import paths, score as rks, store
from rk.basins import grid
import extract
import partb_analyze as PA

CREAM, NAVY, OX = "#F6F0E1", "#16294D", "#6B1D2A"
LAND, GREY = "#E3D9C0", "#8A8F9C"
ROOT = paths.cache("extra", "mslp-blend-d7", "_root").parent
CASES = ROOT / "partb" / "cases"
FIGS = HERE / "figs"
RES = HERE / "results"
PARAMS = {int(k): v for k, v in json.load(open(RES / "partb_params.json")).items()}
LEAD = 120
FS = 1.0          # font/marker scale: 1.0 for the full-size map set, 0.8 for the compact set used in the PDF


def lonlab(v, _=None):
    v = v % 360
    return "%d°W" % round(360 - v) if v > 180 else "%d°E" % round(v)


def ring(lat, lon, r_km, n=90):
    a = np.linspace(0, 2 * np.pi, n)
    dlat = r_km / 111.2 * np.sin(a)
    dlon = r_km / (111.2 * np.cos(np.radians(lat))) * np.cos(a)
    return np.c_[lon + dlon, lat + dlat]


def km(a, b, c, d):
    return float(rks.km(a, b, c, d))


# ------------------------------------------------------------------ data for one case

def get_fields(basin, cyc, lead=LEAD):
    """GFS, IFS (ECMWF), ensemble mean at +lead, hPa on the basin grid (extract file, else the store)."""
    out = {}
    p = ROOT / basin / f"{cyc:%Y%m%d%H}.npz"
    if p.exists():
        z = np.load(p)
        for k, nk in (("gfs", "gfs"), ("ifs", "ifs"), ("ens_mean", "ens")):
            key = f"{k}_f{lead:03d}"
            if key in z.files:
                out[nk] = z[key]
    for m in ("gfs", "ifs"):
        if m not in out:
            r = store.load_det(basin, cyc, m, lead)
            if r is not None:
                out[m] = r["msl"].astype(np.float32)
            extract.clean(basin, cyc)
    return out


def get_analysis(basin, valid):
    """mean of the GFS and IFS analyses at `valid` and the open-water mask (from the cycle 24 h earlier)."""
    p = ROOT / basin / f"{valid - timedelta(hours=24):%Y%m%d%H}.npz"
    z = np.load(p)
    return (z["an_gfs_v024"] + z["an_ifs_v024"]) / 2, z["mask_v024"]


def get_members(basin, cyc, lead=LEAD):
    """ECMWF ensemble member fields (0.5 deg, hPa) and member lows [member, lat, lon, hpa]; None if not stored."""
    tag = f"{cyc:%Y%m%d%H}"
    z = store.load(basin, tag, "mslpd57_ec")
    extract.clean(basin, cyc)
    if not z or f"mem_ens_{basin}_{lead}" not in z:
        return None
    mem = z[f"mem_ens_{basin}_{lead}"].astype(np.float32) / 10 + 1000
    return mem, z[f"low_ens_{basin}_{lead}"]


def vote_products(basin, cyc, lead=LEAD):
    """vote lows with label products: depth, 10-90% range, chance, 50/80% circles, alternatives."""
    p = CASES / basin / f"{cyc:%Y%m%d%H}.pkl"
    if not p.exists():
        return []
    r = pickle.load(open(p, "rb"))
    l = r["leads"].get(lead) if r else None
    if not l:
        return []
    pr = PARAMS[lead]
    xk, yk = pr["iso_knots"]
    out = []
    for i, row in enumerate(l["lows"]):
        lat, lon, hpa, sup = (float(v) for v in row[:4])
        chance = float(np.interp(sup, xk, yk))
        W, X = l["vd"][i]
        F = PA.cdf_grid(np.array([hpa]), np.asarray(X, float)[None], np.asarray(W, float)[None], pr["f"])
        q10, q90 = float(PA.quantile_from_cdf(F, 0.1)[0]), float(PA.quantile_from_cdf(F, 0.9)[0])
        tc = int(np.searchsorted(pr["terc"], sup, side="right"))
        r50, r80 = pr["rt"][tc]
        out.append(dict(lat=lat, lon=lon, hpa=hpa, support=sup, chance=chance, q10=q10, q90=q90, r50=r50, r80=r80,
                        alts=l["alts"][i]))
    return out


# ------------------------------------------------------------------ drawing

def base(ax, f, lats, lons, mask, ext, title, thick=True):
    la0, la1, lo0, lo1 = ext
    ax.set_facecolor("#FBF8EF")
    ax.contourf(lons, lats, mask.astype(float), levels=[-0.5, 0.5], colors=[LAND], zorder=1)
    ax.contour(lons, lats, mask.astype(float), levels=[0.5], colors=[GREY], linewidths=0.4, zorder=2)
    lv = np.arange(900, 1060, 4)
    cs = ax.contour(lons, lats, f, levels=lv, colors=[NAVY], linewidths=[1.0 if l % 20 == 0 else 0.45 for l in lv], zorder=3)
    lab = [l for l in lv if l % 20 == 0]
    ax.clabel(cs, levels=lab, fontsize=5.5 * FS, fmt="%d", inline=True, inline_spacing=2)
    ax.set_xlim(lo0, lo1)
    ax.set_ylim(la0, la1)
    ax.set_aspect(1.0 / np.cos(np.radians((la0 + la1) / 2)))
    ax.set_title(title, fontsize=8.5 * FS, color=NAVY, loc="left", fontweight="bold")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lonlab))
    ax.tick_params(labelsize=6 * FS, colors=NAVY, length=2)
    for s in ax.spines.values():
        s.set_color(NAVY)
        s.set_linewidth(0.6)


def inside(L, ext, lat_i=0, lon_i=1):
    la0, la1, lo0, lo1 = ext
    return la0 <= L[lat_i] <= la1 and lo0 <= L[lon_i] <= lo1


def draw_case(row, tag, compact=False, single=False):
    global FS
    FS = 0.78 if compact else (1.0 if single else 1.0)
    basin, cyc = row.basin, pd.Timestamp(row.cycle5).to_pydatetime()
    valid = cyc + timedelta(hours=LEAD)
    lats, lons = grid(basin)
    an, mask = get_analysis(basin, valid)
    fl = get_fields(basin, cyc)
    mm = get_members(basin, cyc) if cyc.hour == 12 else None
    votes = vote_products(basin, cyc) if cyc.hour == 12 else []
    gi = (fl["gfs"] + fl["ifs"]) / 2 if "gfs" in fl and "ifs" in fl else None
    if gi is None:
        return None
    # centre of the map: the analysed low (deep cases) or the middle of the two runs' lows (split cases)
    La = rks.find_lows(an.astype(np.float32), basin, below=1000.0, inset_deg=3.0)
    clat, clon = float(row.lat), float(row.lon)
    b = {"natl": (30, 67, 285, 359.75), "npac": (30, 67, 160, 245)}[basin]
    h = 12.5 if row.kind == "deep" else 14.0
    la0, la1 = max(b[0], clat - h), min(b[1], clat + h)
    lo0, lo1 = max(b[2], clon - 31), min(b[3], clon + 31)
    ext = (la0, la1, lo0, lo1)
    if single:     # the proposed display (middle panel) alone, large
        fig = plt.figure(figsize=(7.3, 3.7), dpi=100)
        axs = [fig.add_axes([0, 0, 0.01, 0.01]), fig.add_axes([0.07, 0.10, 0.90, 0.82]), fig.add_axes([0, 0, 0.01, 0.01])]
    else:
        fig, axs = plt.subplots(1, 3, figsize=(7.3, 1.7) if compact else (13.2, 3.2), dpi=100)
    fig.patch.set_facecolor(CREAM)
    # ---- panel 1
    ens = None
    if mm is not None:
        mem, mlow = mm
        la2, lo2 = lats[::2][:mem.shape[1]], lons[::2][:mem.shape[2]]
        ens = mem.mean(0)
        base(axs[0], ens, la2, lo2, mask[::2, ::2][:len(la2), :len(lo2)], ext,
             "ECMWF ens. mean; dots = %d member lows" % mem.shape[0])
        sel = mlow[(mlow[:, 3] < 985) & (mlow[:, 1] >= la0) & (mlow[:, 1] <= la1) & (mlow[:, 2] >= lo0) & (mlow[:, 2] <= lo1)]
        axs[0].scatter(sel[:, 2], sel[:, 1], s=9 * FS * FS, c=OX, alpha=0.55, linewidths=0, zorder=5)
    elif "ens" in fl:
        base(axs[0], fl["ens"], lats, lons, mask, ext, "ECMWF ens. mean (00Z, no members)")
    else:
        axs[0].axis("off")
    # ---- panel 2
    base(axs[1], gi, lats, lons, mask, ext, "GFS+ECMWF mean, most likely lows")
    for m, ch in (("gfs", "G"), ("ifs", "E")):
        Lm = rks.find_lows(fl[m], basin, below=992.0)
        for _, r in Lm.iterrows():
            if inside((r.lat, r.lon), ext) and mask[np.abs(lats - r.lat).argmin(), np.abs(lons - r.lon).argmin()]:
                axs[1].text(r.lon, r.lat, ch, fontsize=7.5 * FS, color=NAVY, ha="center", va="center", fontweight="bold",
                            zorder=6, bbox=dict(boxstyle="circle,pad=0.12", fc=CREAM, ec=NAVY, lw=0.6))
    shown = []
    for v in votes:
        if v["chance"] < 0.30 or v["hpa"] > 1000 or not inside((v["lat"], v["lon"]), ext):
            continue
        shown.append(v)
        for rr, ls, a in ((v["r80"], (0, (3, 2)), 0.5), (v["r50"], "-", 0.9)):
            axs[1].add_patch(Polygon(ring(v["lat"], v["lon"], rr), closed=True, fill=False, ec=OX, lw=0.9, ls=ls, alpha=a, zorder=4))
        axs[1].plot(v["lon"], v["lat"], marker="x", color=OX, ms=6 * FS, mew=1.6, zorder=7)
        axs[1].text(v["lon"] + 0.8, v["lat"] + 1.0, "L %d\n(%d–%d) %d%%" % (round(v["hpa"]), round(v["q10"]), round(v["q90"]),
                    round(100 * v["chance"])), fontsize=6.4 * FS, color=OX, fontweight="bold", zorder=8, va="bottom",
                    bbox=dict(boxstyle="round,pad=0.15", fc=CREAM, ec="none", alpha=0.8))
        for a in v["alts"]:
            if inside((a["lat"], a["lon"]), ext):
                axs[1].plot(a["lon"], a["lat"], marker="D", mfc="none", mec=OX, ms=6 * FS, mew=1.0, zorder=7)
                axs[1].text(a["lon"] + 0.8, a["lat"] - 0.5, "alt %d (%d%%)" % (round(a["hpa"]), round(100 * a["share"])),
                            fontsize=5.8 * FS, color=OX, va="top", zorder=8)
    if not votes:
        # 00Z: no members stored; depth from the two runs' own lows
        Lg, Le = (rks.find_lows(fl[m], basin, below=990.0) for m in ("gfs", "ifs"))
        for _, g in Lg.iterrows():
            if not inside((g.lat, g.lon), ext) or not len(Le):
                continue
            d = np.array([km(g.lat, g.lon, e.lat, e.lon) for _, e in Le.iterrows()])
            if d.min() <= 450:
                e = Le.iloc[int(d.argmin())]
                axs[1].text((g.lon + e.lon) / 2 + 0.8, (g.lat + e.lat) / 2 + 1.0, "L %d\n(G %d, E %d)" % (round((g.hpa + e.hpa) / 2), round(g.hpa), round(e.hpa)),
                            fontsize=6.4 * FS, color=OX, fontweight="bold", zorder=8, bbox=dict(boxstyle="round,pad=0.15", fc=CREAM, ec="none", alpha=0.8))
    # ---- panel 3
    base(axs[2], an, lats, lons, mask, ext, "Analysis valid %s" % f"{valid:%d %b %Y %HZ}")
    for _, r in La.iterrows():
        if inside((r.lat, r.lon), ext) and r.hpa < 995:
            axs[2].plot(r.lon, r.lat, marker="o", color=NAVY, ms=4 * FS, zorder=6)
            axs[2].text(r.lon + 0.8, r.lat + 0.8, "L %d" % round(r.hpa), fontsize=6.6 * FS, color=NAVY, fontweight="bold", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.12", fc=CREAM, ec="none", alpha=0.8))
    for v in shown:
        axs[2].plot(v["lon"], v["lat"], marker="o", mfc="none", mec=OX, ms=9 * FS, mew=1.3, zorder=7)
    if single:
        for _, r in La.iterrows():
            if inside((r.lat, r.lon), ext) and r.hpa < 995:
                axs[1].plot(r.lon, r.lat, marker="*", color=NAVY, ms=11, zorder=9)
                axs[1].text(r.lon + 0.8, r.lat + 0.6, "analysis L %d" % round(r.hpa), fontsize=7.5, color=NAVY, fontweight="bold", zorder=9,
                            bbox=dict(boxstyle="round,pad=0.15", fc=CREAM, ec="none", alpha=0.85))
        axs[0].set_visible(False)
        axs[2].set_visible(False)
        return fig, dict(an=an, mask=mask, fl=fl, gi=gi, ens=ens, votes=votes, La=La, mm=mm)
    fig.subplots_adjust(left=0.035, right=0.995, top=0.9 if compact else 0.915, bottom=0.11 if compact else 0.095, wspace=0.10)
    return fig, dict(an=an, mask=mask, fl=fl, gi=gi, ens=ens, votes=votes, La=La, mm=mm)


def detail(row, d, cid):
    """numbers for the case text: analysed deepest low (open water, in the map), what each product said near it"""
    basin = row.basin
    lats, lons = grid(basin)
    La = d["La"]
    wet = [r for _, r in La.iterrows() if d["mask"][np.abs(lats - r.lat).argmin(), np.abs(lons - r.lon).argmin()]]
    out = dict(case=cid, kind=row.kind, basin=basin, cycle=f"{pd.Timestamp(row.cycle5):%Y-%m-%d %HZ}", valid=f"{pd.Timestamp(row.valid):%Y-%m-%d %HZ}",
               members=bool(d["mm"] is not None), split_km=row.split_km)
    if not wet:
        return out
    a = min(wet, key=lambda r: km(r.lat, r.lon, row.lat, row.lon))
    out.update(an_lat=a.lat, an_lon=a.lon, an_hpa=a.hpa)

    def near(f, rad=500):
        yy, xx = np.meshgrid(np.arange(len(lats)), np.arange(len(lons)), indexing="ij")
        dist = rks.km(a.lat, a.lon, lats[yy], lons[xx])
        w = dist <= rad
        k = np.where(w, f, np.inf).argmin()
        iy, ix = np.unravel_index(k, f.shape)
        return float(f[iy, ix]), km(a.lat, a.lon, lats[iy], lons[ix])
    for nm, f in (("gfs", d["fl"].get("gfs")), ("ifs", d["fl"].get("ifs")), ("gi", d["gi"])):
        if f is not None:
            h, dk = near(f)
            out[nm + "_hpa"], out[nm + "_dist_km"] = h, dk
    if d["fl"].get("ens") is not None:
        out["ens_hpa"], out["ens_dist_km"] = near(d["fl"]["ens"])
    best = None     # the vote low with the most member support within 1000 km of the analysed low
    for v in d["votes"]:
        dk = km(a.lat, a.lon, v["lat"], v["lon"])
        if dk <= 1000 and (best is None or v["support"] > best[1]["support"]):
            best = (dk, v)
    if best:
        dk, v = best
        out.update(vote_hpa=v["hpa"], vote_dist_km=dk, vote_chance=v["chance"], vote_q10=v["q10"], vote_q90=v["q90"],
                   vote_support=v["support"], in50=dk <= v["r50"], in80=dk <= v["r80"], an_in_range=v["q10"] <= a.hpa <= v["q90"],
                   alt_shown=len(v["alts"]))
    return out


def main():
    R = pd.read_csv(RES / "worked_cases.csv", parse_dates=["valid", "cycle5"])
    rows = []
    FIGS.mkdir(exist_ok=True)
    (FIGS / "brief").mkdir(exist_ok=True)
    for i, r in R.iterrows():
        cid = "%s-%s-%s" % (r.basin, r.kind, f"{r.valid:%Y-%m-%d}")
        bn = "North Atlantic" if r.basin == "natl" else "North Pacific"
        kind = "deepest analysed low of the month" if r.kind == "deep" else "largest GFS-ECMWF split at day 5"
        tag = "%s, %s: day 5 forecast from %s, valid %s" % (bn, kind, f"{r.cycle5:%d %b %Y %HZ}", f"{r.valid:%d %b %Y %HZ}")
        try:
            res = draw_case(r, tag)
        except Exception as ex:
            print("FAILED", cid, repr(ex))
            continue
        if res is None:
            print("no fields", cid)
            continue
        fig, d = res
        fig.savefig(FIGS / f"{cid}.png", dpi=100, facecolor=CREAM)
        plt.close(fig)
        if cid == "natl-deep-2025-12-11":
            figs_, _ = draw_case(r, tag, single=True)
            figs_.savefig(FIGS / "brief" / f"{cid}_display.png", dpi=220, facecolor=CREAM)
            plt.close(figs_)
        figc, _ = draw_case(r, tag, compact=True)
        figc.savefig(FIGS / "brief" / f"{cid}.png", dpi=240, facecolor=CREAM)
        plt.close(figc)
        rows.append(detail(r, d, cid))
        print("ok", cid)
    pd.DataFrame(rows).to_csv(RES / "worked_cases_detail.csv", index=False)
    print(pd.DataFrame(rows).round(1).to_string())


if __name__ == "__main__":
    main()
