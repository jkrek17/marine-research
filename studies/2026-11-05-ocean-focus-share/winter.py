"""Winter 2025-26 held-out cycles: share of tested-box water in each hazard layer (same rules as the live page)."""
import os, sys, glob, numpy as np
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))
from rk import paths as _paths
AWIPS = os.environ.get("AWIPS_TOOLS") or str(_REPO.parent / "awips-tools")
WORK = str(_paths.cache("ocean-focus"))
os.makedirs(WORK, exist_ok=True)
from scipy import ndimage
sys.path.insert(0, AWIPS + "/marine_wind/pipeline")
import storm
storm.WRAP = False
HO = str(_paths.data("extra", "core-lift-retrain", "corelift-heldout"))
WE = str(_paths.data("extra", "warning-experiment"))
def focus_grid(speeds, TOL=2):   # copy of build.focus_grid (box grid, no wrap)
    cats = (34.0, 48.0, 64.0); mx = speeds.max(0)
    near = np.array([ndimage.maximum_filter(s, size=2 * TOL + 1, mode="reflect") for s in speeds])
    cmax, cmin = np.digitize(speeds, cats).max(0), np.digitize(near, cats).min(0)
    out = np.ones(mx.shape, np.uint8); out[mx < 30] = 0
    out[((cmax >= 1) & (cmin == 0)) | ((mx - near.min(0) >= 10) & (mx >= 30))] = 2
    out[(cmax >= 2) & (cmin < cmax)] = 3
    return out
lat = np.linspace(67, 30, 149)
cosw = np.cos(np.radians(lat))[:, None] * np.ones((1, 300))
f = open(WORK + "/rows_winter.csv", "a")
for b in sys.argv[1:]:
    for p in sorted(glob.glob("%s/%s/*_f*.npz" % (HO, b))):
        cyc, st = os.path.basename(p)[:10], int(os.path.basename(p)[12:15])
        if st not in (24, 48, 72, 96, 120): continue
        h = np.load(p); core, wc = h["core_likelihood"].astype(np.float32), h["corelift"].astype(np.float32)
        tr = "%s/truth/%s/%s.npz" % (WE, b, cyc)
        if not os.path.exists(tr): continue
        t = np.load(tr); ocean = (t["gfs_land"] < 0.5) & ~(t["gfs_ice"] >= 0.5)
        L = {"core35": core >= 0.35, "storm_line": wc >= 39}
        c = "%s/cases/%s/%s_%03d.npz" % (WE, b, cyc, st)
        if os.path.exists(c):
            z = np.load(c)
            sp = np.array([z["s10_gfs"], z["s10_ifs"], z["s10_aifs"]], np.float32)
            mem = z["mem"].astype(np.float32) / 2; n = z["nsrc"]
            w = storm.warning_areas(sp, wc, mem, ocean)
            k = 0.15 if st <= 24 else 0.25
            boost = np.minimum(k * mem[: n[0] + n[1]].std(0), 5)
            fg = focus_grid(sp)
            L.update({"gale_line": (w & 1) > 0, "storm_line": (w & 2) > 0, "hf_line": (w & 4) > 0,
                      "models_split": fg >= 2, "split_48_64": fg >= 3, "spread_2kt": boost >= 2,
                      "any_warning": w > 0})
            L["focus_union"] = L["any_warning"] | L["core35"] | L["models_split"] | L["spread_2kt"]
        L["storm_up_union"] = L["storm_line"] | L["core35"] | (L["hf_line"] | (L["split_48_64"]) if "hf_line" in L else False)
        cosw = np.cos(np.radians(lat))[:, None] * np.ones((1, ocean.shape[1]))
        tot = (cosw * ocean).sum()
        for kk, v in L.items():
            a = (cosw * (ocean & v)).sum()
            f.write("%s,%d,%s,%s,%.5f,%.0f\n" % (cyc, st, b, kk, a / tot, a * 225))
        f.write("%s,%d,%s,water,1,%.0f\n" % (cyc, st, b, tot * 225))
    print(b, "done", flush=True)
