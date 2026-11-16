#!/usr/bin/env python3
"""Case 3, "The coastal jet every model missed": Gulf of Alaska, 06Z 9 Nov 2026 (North Pacific), run 00Z 8 Nov +30 h.

  python3 case3_goa_jet.py

Panels: coastal ASCAT (NOAA STAR ultra-high-resolution, Metop-B/C passes starting 04:30-07:30Z, peak per 0.25 deg cell)
| GFS | ECMWF | Best Wind rebuilt without ENS and without the gale-core floor (the live cycles in the store hold no ENS
or low-level files; see the caption). Models from the store release (rk.store, one 18 MB cycle). Writes
case3_goa_jet.png/.pdf/.md to RK_SUMMARY_OUT.
"""
import datetime as dt
import shutil

import numpy as np
from scipy import ndimage

import cases_common as C
from rk import basins, features, paths, store, style, truth

BASIN, CYC, STEP = "npac", dt.datetime(2026, 11, 8, 0), 30
VALID = CYC + dt.timedelta(hours=STEP)
JET = (53.0, 57.5, 360 - 146.0, 360 - 139.0)     # lat lo/hi, lon lo/hi: the barrier-jet strip north of the low
BOXLL = (48.0, 62.0, 205.0, 232.0)


def ascat_cells():
    t0, t1 = dt.datetime(2026, 11, 9, 4, 30), dt.datetime(2026, 11, 9, 7, 30)
    d = truth.star("uhr", BOXLL[:2], BOXLL[2:], t0, t1)
    d = {k: v for k, v in d.items()}
    # passes whose START lies in the window (the pass bracket is only known to 100 min)
    start = d["day_min"] + d["t_min"]
    ok = (start >= 0) & (start <= 180) & (d["q"] == 0)
    return {k: v[ok] for k, v in d.items()}, ok.sum()


def peak_grid(lat, lon, spd):
    lats, lons = basins.grid(BASIN)
    ny, nx = len(lats), len(lons)
    iy = np.floor((lats[0] - lat) / 0.25 + 0.5).astype(int)
    ix = np.floor((lon % 360 - lons[0]) / 0.25 + 0.5).astype(int)
    k = (iy >= 0) & (iy < ny) & (ix >= 0) & (ix < nx)
    g = np.full(ny * nx, -1.0)
    np.maximum.at(g, iy[k] * nx + ix[k], spd[k])
    g = g.reshape(ny, nx)
    return np.where(g >= 0, g, np.nan)


def main():
    style.use()
    lats, lons = basins.grid(BASIN)
    dets = {m: store.load_det(BASIN, CYC, m, STEP) for m in ("gfs", "ifs", "aifs")}
    g = store.load_ens(BASIN, CYC, "gefs", STEP)
    sp = np.array([dets[m]["speed"] for m in ("gfs", "ifs", "aifs")], np.float32)
    k = features._weights(("gfs", "ifs", "aifs"), {"aifs": 0.5})
    blend = features.support_closed_form(sp, [g], weights=k) + np.minimum(features.k_for(STEP) * features.pool([g])["sd"], features.CAP_KT)
    M = C.mlw_score()
    strong = np.nan_to_num(np.fmax(sp[0], sp[1]), nan=-1.0)
    p48 = ndimage.maximum_filter(np.nan_to_num(g["p48"], nan=0.0), size=features.NB, mode="nearest")
    add = sum(M.ramp(strong, kt, st) for kt, st in M.RAMPS) + np.where(p48 >= M.HF_P, M.ramp(strong, M.HF[0], M.HF[1]), 0.0)
    wm = truth.water_mask(BASIN, VALID)
    water = np.ones(blend.shape, bool) if wm is None else wm
    lift_on = water & (np.abs(lats)[:, None] >= M.MIN_LAT)
    best = np.where(lift_on, blend + add, blend)
    models = {"GFS": dets["gfs"]["speed"], "ECMWF": dets["ifs"]["speed"], "Best Wind (rebuilt after the event)": best}
    shutil.rmtree(store._cache_dir(BASIN, CYC), ignore_errors=True)

    cells, n = ascat_cells()
    asc = peak_grid(cells["lat"], cells["lon"], cells["spd_kt"])
    asc = np.where(water, asc, np.nan)            # drop land / ice cells
    seen = np.isfinite(asc)
    iy_, ix_ = np.where(np.nan_to_num(asc, nan=0) >= 64)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    jet = (LA >= JET[0]) & (LA <= JET[1]) & (LO >= JET[2]) & (LO <= JET[3])
    area = C.cell_area_nm2(BASIN)
    pk = np.nanargmax(np.where(jet, asc, -1))
    pyx = np.unravel_index(pk, asc.shape)
    out = {"ASCAT": dict(peak=float(np.nanmax(asc)), jet=float(np.nanmax(np.where(jet, asc, np.nan))),
                         c64=int((np.nan_to_num(asc, nan=0) >= 64).sum()), c48=int((np.nan_to_num(asc, nan=0) >= 48).sum()),
                         a64=C.area_k(np.nan_to_num(asc, nan=0) >= 64, area), at=(float(lats[pyx[0]]), float(lons[pyx[1]] - 360)))}
    for name, f in models.items():
        fj = np.where(jet, f, np.nan)
        on64 = seen & (np.nan_to_num(asc, nan=0) >= 64)
        out[name] = dict(peak=float(np.nanmax(np.where(water, f, np.nan))), jet=float(np.nanmax(fj)),
                         on_asc64=float(np.nanmax(np.where(on64, f, np.nan))), mean_on_asc64=float(np.nanmean(np.where(on64, f, np.nan))),
                         c64=int((np.nan_to_num(np.where(seen, f, np.nan), nan=0) >= 64).sum()),
                         c48_seen=int((np.nan_to_num(np.where(seen, f, np.nan), nan=0) >= 48).sum()))
    # raw (not gridded) ASCAT peak
    raw = float(cells["spd_kt"].max())
    box = (BOXLL[2], BOXLL[3], BOXLL[0], BOXLL[1])
    fig, axes = C.plt.subplots(1, 4, figsize=(17.5, 4.8))
    fig.subplots_adjust(wspace=0.12, top=0.74, bottom=0.2)
    items = [("Coastal ASCAT (seen cells)", asc, None)] + [(k_, v, water) for k_, v in models.items()]
    for ax, (name, f, faint) in zip(axes, items):
        C.base_map(BASIN, ax, box)
        m = C.draw_wind(ax, BASIN, np.where(water, f, np.nan), seen=None, contours=True)
        s = out["ASCAT" if faint is None else name]
        ax.set_title(name, fontsize=11, color=style.INK, loc="left", pad=22)
        ax.text(0, 1.015, "jet strip peak %.0f kt   domain peak %.0f kt" % (s["jet"], s["peak"]), transform=ax.transAxes,
                fontsize=8.5, color=style.INK2, va="bottom")
        ax.plot([JET[2] - 360 + 360, JET[3]], [JET[0], JET[0]], color=style.INK, lw=0.7, ls=":", zorder=6)
        ax.plot([JET[2], JET[3]], [JET[1], JET[1]], color=style.INK, lw=0.7, ls=":", zorder=6)
        ax.plot([JET[2], JET[2]], [JET[0], JET[1]], color=style.INK, lw=0.7, ls=":", zorder=6)
        ax.plot([JET[3], JET[3]], [JET[0], JET[1]], color=style.INK, lw=0.7, ls=":", zorder=6)
    C.wind_legend(fig, m, list(axes))
    a, gf, ec, bw = out["ASCAT"], out["GFS"], out["ECMWF"], out["Best Wind (rebuilt after the event)"]
    fig.suptitle("The coastal jet every model missed: ASCAT %.0f kt in the jet strip, GFS %.0f, ECMWF %.0f, Best Wind (rebuilt after the event) %.0f"
                 % (a["jet"], gf["jet"], ec["jet"], bw["jet"]), x=0.01, ha="left", fontsize=13.5, y=1.0, color=style.INK)
    fig.text(0.01, 0.915, "Gulf of Alaska, 06Z 9 Nov 2026; models +30 h from the 00Z 8 Nov run. Truth: NOAA STAR coastal ASCAT, passes starting "
             "04:56-06:58Z, peak per 0.25° cell (calibration unconfirmed). Dotted box: jet strip.", fontsize=8.6, color=style.INK2, ha="left")
    C.contour_note(fig, y=0.0)
    C.save_all(fig, "case3_goa_jet")
    cap = f"""# Case 3: The coastal jet every model missed

**Valid:** 06Z 9 Nov 2026 (ASCAT passes started 04:56, 05:18, 06:37 and 06:58Z; the two strongest at 06:37 and 06:58Z).  **Run:** 00Z 8 Nov 2026, +30 h (the 12Z run has no +18 h in the store).  **Basin:** North Pacific, Gulf of Alaska.
**Truth:** NOAA STAR coastal ultra-high-resolution ASCAT (Metop-B and -C, `rk.truth.star("uhr")`), quality flag 0, land and ice cells removed, peak per 0.25 deg cell ({n} raw points in the box). Equivalent-neutral vs real 10 m wind is not confirmed for this product, and RSS ASCAT for 9 Nov was not posted. The passes span about two hours either side of the model time; the jet strengthened across them (peak 57.6 kt at 04:56Z, 64.9 at 05:18Z, 71.1 at 06:37Z, 71.6 at 06:58Z).
**How picked:** not picked from a table; it is the event named in `LESSONS.md` (Gulf of Alaska low, 2026-11-11).
**Models:** GFS, ECMWF IFS and the AIFS (not drawn; peaks below) from the store release; **Best Wind is a rebuild, not the page's number**: the store's live cycles hold no ENS or lower-level files, so the blend uses GEFS spread only, the storm-core floor is missing, and the 34 kt line is not reliable. The strong-model ramps and the GEFS 48 kt HF core are as built. On a winter case where both exist, this rebuild gave a 78.7 kt peak against 78.8 kt and 742 against 732 cells at 48 kt (119 against 98 at 64 kt).

## Numbers (kt)
Jet strip = 53.0-57.5N, 139-146W. Domain = 48-62N, 155-128W water.
| Panel | Jet strip peak | Domain peak | Peak on cells where ASCAT is 64+ | Seen cells at 64+ / 48+ |
|---|---|---|---|---|
| ASCAT (cell peak) | {a['jet']:.1f} (at {a['at'][0]:.2f}N {-a['at'][1]:.2f}W) | {a['peak']:.1f} (raw point {raw:.1f}) | {a['peak']:.1f} | {a['c64']} / {a['c48']} |
| GFS | {gf['jet']:.1f} | {gf['peak']:.1f} | {gf['on_asc64']:.1f} (mean {gf['mean_on_asc64']:.1f}) | {gf['c64']} / {gf['c48_seen']} |
| ECMWF | {ec['jet']:.1f} | {ec['peak']:.1f} | {ec['on_asc64']:.1f} (mean {ec['mean_on_asc64']:.1f}) | {ec['c64']} / {ec['c48_seen']} |
| Best Wind (rebuilt after the event) | {bw['jet']:.1f} | {bw['peak']:.1f} | {bw['on_asc64']:.1f} (mean {bw['mean_on_asc64']:.1f}) | {bw['c64']} / {bw['c48_seen']} |
AIFS jet strip peak: {float(np.nanmax(np.where(jet, dets['aifs']['speed'], np.nan))):.1f} kt.

## Caveats
- The ASCAT here is a peak per 0.25 degree cell from ultra-high-resolution points, which reads higher than a grid-box mean; model grids are box means. Compare the ratio to the models with that in mind.
- One event, one run. The models' +30 h peaks differ from the 45-48 kt quoted in the notes if those came from the earlier or later runs; the numbers above are this run only.
- SMAP (about 16Z, 63-64 kt) and OSCAT-3 (19Z, 62 kt) in the existing figure were not redrawn; they are quoted from `/mnt/project-files/goa-low-nov9/scatterometer-check.png` and the notes and were not re-verified here.
**Code:** `studies/2026-11-16-research-summary/cases/case3_goa_jet.py`.
"""
    C.write_caption("case3_goa_jet", cap)
    print(out, raw)


if __name__ == "__main__":
    main()
