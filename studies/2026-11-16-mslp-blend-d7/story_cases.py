"""Storyboards for the companion PDF: for four storms, where each source put the low at day 7 ... day 1 for the same valid time
(track map), each source's central pressure against the analysed value (lead-vs-depth lines), and one map row at day 4/5.

Storms: the deepest Atlantic (11 Dec 2025) and Pacific (8 Nov 2025) analysed lows with members, the Atlantic split (27 Jan 2026),
and one false-deep case chosen by rule (below). All 12Z cycles; fields from the MSLP-only extract files; vote lows from the Part B files.

False-deep rule (fixed here, before looking at the maps): over every winter 12Z cycle (1 Nov 2025 - 31 Mar 2026) at day 4 and day 5,
take each pair of a GFS low and an ECMWF low, both deeper than 990 hPa and within 450 km of each other. The pair's forecast depth is
the mean of the two lows; its analysed depth is the lowest pressure of the mean analysis within 500 km of the pair's mean position.
The case is the pair with the largest (analysed minus forecast) pressure, i.e. the deepest low both runs forecast that verified
weakest. Candidates are cached in results/story_false_deep_candidates.csv.
Writes results/story_tracks.csv, results/story_cases.csv and figs/story/c*_*.png.
"""
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
from rk import paths, score as rks
from rk.basins import grid
import make_story_figs as MS

RES = HERE / "results"
ROOT = paths.cache("extra", "mslp-blend-d7", "_root").parent
PKL = ROOT / "partb" / "cases"
CAND = RES / "story_false_deep_candidates.csv"
LEADS = MS.LEADS
SRC = ("ifs", "gfs", "m_gi", "vote")
SRCNAME = {"ifs": "ECMWF", "gfs": "GFS", "m_gi": "GFS+ECMWF mean", "vote": "Member vote"}
SRCSTY = {"ifs": dict(color=MS.NAVY, marker="o", ms=5.5), "gfs": dict(color=MS.MID, marker="^", ms=5.5),
          "m_gi": dict(color=MS.OX, marker="s", ms=5.0), "vote": dict(color=MS.GOLD, marker="D", ms=5.5)}


def km(a, b, c, d):
    return float(rks.km(a, b, c, d))


def scan_false():
    if CAND.exists():
        return pd.read_csv(CAND, parse_dates=["cycle"])
    rows = []
    for basin in ("natl", "npac"):
        lats, lons = grid(basin)
        LA, LO = np.meshgrid(lats, lons, indexing="ij")
        for p in sorted((ROOT / basin).glob("*12.npz")):
            cyc = datetime.strptime(p.stem, "%Y%m%d%H")
            z = np.load(p)
            for L in (96, 120):
                ks = [f"gfs_f{L:03d}", f"ifs_f{L:03d}", f"an_gfs_v{L:03d}", f"an_ifs_v{L:03d}"]
                if not all(k in z.files for k in ks):
                    continue
                Lg = rks.find_lows(z[ks[0]], basin, below=990.0)
                Li = rks.find_lows(z[ks[1]], basin, below=990.0)
                an = (z[ks[2]] + z[ks[3]]) / 2
                for _, g in Lg.iterrows():
                    for _, i in Li.iterrows():
                        if km(g.lat, g.lon, i.lat, i.lon) <= 450:
                            la, lo = (g.lat + i.lat) / 2, (g.lon + i.lon) / 2
                            amin = float(an[rks.km(la, lo, LA, LO) <= 500].min())
                            rows.append(dict(basin=basin, cycle=cyc, lead=L, lat=la, lon=lo, gfs=g.hpa, ifs=i.hpa,
                                             pair=(g.hpa + i.hpa) / 2, an_min500=amin))
    D = pd.DataFrame(rows)
    D["deficit"] = D.an_min500 - D.pair
    D = D.sort_values("deficit", ascending=False).reset_index(drop=True)
    D.to_csv(CAND, index=False)
    return D


# ------------------------------------------------------------------ track building
def load_fields(basin, cyc, L):
    p = ROOT / basin / f"{cyc:%Y%m%d%H}.npz"
    if not p.exists():
        return None
    z = np.load(p)
    if f"gfs_f{L:03d}" not in z.files or f"ifs_f{L:03d}" not in z.files:
        return None
    g, i = z[f"gfs_f{L:03d}"], z[f"ifs_f{L:03d}"]
    return {"gfs": g, "ifs": i, "m_gi": (g + i) / 2}


def nearest_low(f, basin, ref, within=1000.0):
    Lw = rks.find_lows(f, basin, below=1010.0)
    best = None
    for _, r in Lw.iterrows():
        d = km(ref[0], ref[1], r.lat, r.lon)
        if d <= within and (best is None or d < best[3]):
            best = (r.lat, r.lon, r.hpa, d)
    return best


def vote_low(basin, cyc, L, ref):
    import pickle
    p = PKL / basin / f"{cyc:%Y%m%d%H}.pkl"
    if L < 120 or not p.exists():
        return None
    r = pickle.load(open(p, "rb"))
    l = r["leads"].get(L) if r else None
    if not l:
        return None
    best = None
    for row in l["lows"]:
        d = km(ref[0], ref[1], row[0], row[1])
        if d <= 1000 and (best is None or row[3] > best[3]):
            best = (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
    return best


def analysed(basin, valid):
    z = np.load(ROOT / basin / f"{valid - timedelta(hours=24):%Y%m%d%H}.npz")
    return ((z["an_gfs_v024"] + z["an_ifs_v024"]) / 2).astype(np.float32), z["mask_v024"]


def track_case(cid, basin, valid, ref):
    """ref = (lat, lon) of the analysed low (or the pair position for the false-deep case)."""
    an, mask = analysed(basin, valid)
    lats, lons = grid(basin)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    near = rks.km(ref[0], ref[1], LA, LO) <= 500
    k = np.where(near, an, np.inf).argmin()
    iy, ix = np.unravel_index(k, an.shape)
    a_lat, a_lon, a_hpa = float(lats[iy]), float(lons[ix]), float(an[iy, ix])
    rows = [dict(case=cid, lead=0, source="analysis", lat=a_lat, lon=a_lon, hpa=a_hpa, dist_km=0.0)]
    for L in LEADS:
        cyc = valid - timedelta(hours=L)
        F = load_fields(basin, cyc, L)
        for s in SRC:
            if s == "vote":
                v = vote_low(basin, cyc, L, (a_lat, a_lon))
                if v:
                    rows.append(dict(case=cid, lead=L, source=s, lat=v[0], lon=v[1], hpa=v[2], dist_km=km(a_lat, a_lon, v[0], v[1])))
                continue
            if F is None:
                continue
            b = nearest_low(F[s], basin, (a_lat, a_lon))
            if b:
                rows.append(dict(case=cid, lead=L, source=s, lat=b[0], lon=b[1], hpa=b[2], dist_km=b[3]))
    return pd.DataFrame(rows), an, mask


# ------------------------------------------------------------------ figures
def fig_track(cid, T, an, mask, basin, title):
    lats, lons = grid(basin)
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.3, 3.2), dpi=200, gridspec_kw=dict(width_ratios=[1.1, 1]))
    fig.patch.set_facecolor(MS.CREAM)
    A = T[T.source == "analysis"].iloc[0]
    pts = T[T.source != "analysis"]
    la0, la1 = min(pts.lat.min(), A.lat) - 2.5, max(pts.lat.max(), A.lat) + 2.5
    lo0, lo1 = min(pts.lon.min(), A.lon) - 4, max(pts.lon.max(), A.lon) + 4
    a.set_facecolor("#FBF8EF")
    a.contourf(lons, lats, mask.astype(float), levels=[-0.5, 0.5], colors=[MS.SAND], zorder=1)
    lv = np.arange(900, 1060, 8)
    a.contour(lons, lats, an, levels=lv, colors=[MS.NAVY], linewidths=0.4, alpha=0.45, zorder=2)
    for s in SRC:
        P = T[T.source == s].sort_values("lead", ascending=False)
        if not len(P):
            continue
        a.plot(P.lon, P.lat, color=SRCSTY[s]["color"], lw=0.9, alpha=0.8, zorder=4)
        a.plot(P.lon, P.lat, ls="none", zorder=5, **SRCSTY[s], label=SRCNAME[s])
        for _, r in P.iterrows():
            d = int(r.lead / 24)
            if d in (7, 5, 3, 1) and s != "m_gi":
                a.annotate("%d: %d" % (d, round(r.hpa)), (r.lon, r.lat), textcoords="offset points",
                           xytext={"ifs": (4, 4), "gfs": (4, -8), "m_gi": (-4, -9), "vote": (4, 5)}[s], fontsize=5.3, color=SRCSTY[s]["color"], zorder=6)
    a.plot(A.lon, A.lat, marker="*", color="black", ms=12, ls="none", zorder=7, label="Analysis %d" % round(A.hpa))
    a.set_xlim(lo0, lo1)
    a.set_ylim(la0, la1)
    a.set_aspect(1.0 / np.cos(np.radians((la0 + la1) / 2)))
    a.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: "%d°W" % round(360 - v % 360) if v % 360 > 180 else "%d°E" % round(v % 360)))
    a.tick_params(labelsize=6, colors=MS.NAVY)
    a.set_title("Where each source put the low (day: hPa)", fontsize=8, loc="left", color=MS.NAVY, fontweight="bold")
    a.legend(frameon=False, fontsize=5.6, loc="best")
    for s in a.spines.values():
        s.set_color(MS.NAVY)
        s.set_linewidth(0.6)
    # depth lines
    MS.ax_style(b, xlab="days before the valid time")
    for s in SRC:
        P = T[T.source == s].sort_values("lead", ascending=False)
        if len(P):
            b.plot(P.lead / 24, P.hpa, **{k: v for k, v in SRCSTY[s].items() if k != "ms"}, markersize=SRCSTY[s]["ms"], lw=1.4, label=SRCNAME[s], ls="-" if s != "vote" else "none")
    b.axhline(A.hpa, color="black", lw=1.2)
    b.text(7.05, A.hpa, "analysed %d" % round(A.hpa), fontsize=6, va="bottom", ha="right")
    b.invert_xaxis()
    b.invert_yaxis()
    b.set_xticks(range(1, 8))
    b.set_ylabel("central pressure, hPa (deeper is up)")
    b.set_title("Depth, each run against the analysis", fontsize=8, loc="left", color=MS.NAVY, fontweight="bold")
    fig.tight_layout(w_pad=1.5)
    path = MS.OUTD / f"c_{cid}_track.png"
    fig.savefig(path, facecolor=MS.CREAM)
    plt.close(fig)
    assert path.stat().st_size < 1_000_000
    return path


def main():
    MS.setup()
    import make_figs as MF
    D = scan_false()
    top = D.iloc[0]
    print("false-deep case:", top.to_dict())
    det = pd.read_csv(RES / "worked_cases_detail.csv").set_index("case")
    cases = []
    for cid, basin in (("natl-deep-2025-12-11", "natl"), ("npac-deep-2025-11-08", "npac"), ("natl-split-2026-01-27", "natl")):
        r = det.loc[cid]
        cases.append(dict(case=cid, basin=basin, valid=pd.Timestamp(r.valid.replace("Z", ":00")), lat=r.an_lat, lon=r.an_lon, lead_map=120, kind="deep" if "deep" in cid else "split"))
    fcyc = pd.Timestamp(top.cycle)
    cases.append(dict(case="%s-falsedeep-%s" % (top.basin, f"{fcyc + timedelta(hours=int(top.lead)):%Y-%m-%d}"), basin=top.basin,
                      valid=fcyc + timedelta(hours=int(top.lead)), lat=top.lat, lon=top.lon, lead_map=int(top.lead), kind="false"))
    allT, meta = [], []
    for c in cases:
        T, an, mask = track_case(c["case"], c["basin"], c["valid"].to_pydatetime(), (c["lat"], c["lon"]))
        allT.append(T)
        fig_track(c["case"], T, an, mask, c["basin"], c["case"])
        # map row at the case's lead
        MF.LEAD = c["lead_map"]
        row = pd.Series(dict(basin=c["basin"], cycle5=c["valid"] - timedelta(hours=c["lead_map"]), valid=c["valid"], lat=c["lat"], lon=c["lon"],
                             kind="deep" if c["kind"] != "split" else "split", split_km=np.nan))
        fig, _ = MF.draw_case(row, "", compact=True)
        path = MS.OUTD / f"c_{c['case']}_maps.png"
        fig.savefig(path, dpi=240, facecolor=MS.CREAM)
        plt.close(fig)
        MF.LEAD = 120
        meta.append(dict(c, valid=f"{c['valid']:%Y-%m-%d %HZ}", maps=path.name))
    pd.concat(allT).to_csv(RES / "story_tracks.csv", index=False)
    pd.DataFrame(meta).to_csv(RES / "story_cases.csv", index=False)
    print(pd.concat(allT).round(1).to_string())


if __name__ == "__main__":
    main()
