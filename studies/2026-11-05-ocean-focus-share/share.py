"""Share of OPC-box water inside each hazard layer, per cycle and lead, from the forecast records."""
import sys, os, json, glob, shutil, numpy as np
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))
from rk import paths as _paths
AWIPS = os.environ.get("AWIPS_TOOLS") or str(_REPO.parent / "awips-tools")
WORK = str(_paths.cache("ocean-focus"))
os.makedirs(WORK, exist_ok=True)
sys.path.insert(0, AWIPS + "/marine_wind/pipeline")
import record
OUT = WORK + "/rows_recent.csv"
LI = np.load(WORK + "/landice_20261105.npz")   # GFS LAND/ICEC, 5 Nov 00Z +24 h (fetch.gfs_low, glob domain)
water = (LI["land"] < 0.5) & ~(LI["ice"] >= 0.5)
lat = 90 - np.arange(721) / 4.0
lon = -180 + np.arange(1440) / 4.0
cosw = np.cos(np.radians(lat))[:, None] * np.ones((1, 1440))
def box(s, n, w, e):
    lo = (lon - w) % 360 <= (e - w)
    return ((lat >= s) & (lat <= n))[:, None] & lo[None, :]
BOX = {"natl": box(18, 67, -95, 10) & water, "npac": box(18, 67, 135, 245) & water,
       "natl_core": box(30, 67, -75, 0) & water, "npac_core": box(30, 67, 160, 245) & water}
def layers(z):
    warn, core, focus, boost = z["warn"], z["core"], z["focus"], z["boost"]
    if core.max() > 1.5: core = core / 100.0
    L = {"gale_line": (warn & 1) > 0, "storm_line": (warn & 2) > 0, "hf_line": (warn & 4) > 0,
         "core35": core >= 0.35, "models_split": focus >= 2, "split_48_64": focus >= 3,
         "spread_2kt": boost >= 2.0, "members_agree": z["hazard"] > 0,
         "blend34": z["windcore"] >= 34}
    L["any_warning"] = warn > 0
    L["focus_union"] = L["any_warning"] | L["core35"] | L["models_split"] | L["spread_2kt"]
    L["storm_up_union"] = L["storm_line"] | L["hf_line"] | L["core35"] | L["split_48_64"]
    return L
def run(cycles, steps=(24, 48, 72, 96, 120)):
    new = not os.path.exists(OUT)
    f = open(OUT, "a")
    if new: f.write("cycle,step,basin,layer,share,area_nm2\n")
    done = set()
    if not new:
        for line in open(OUT).read().splitlines()[1:]:
            c, s = line.split(",")[:2]; done.add((c, int(s)))
    for c in cycles:
        for s in steps:
            if (c, s) in done: continue
            tmp = WORK + "/dl-%s" % c
            try:
                if not record._artifact(tmp, c, s): print("missing", c, s, flush=True); continue
                z = np.load("%s/%s-f%03d.npz" % (tmp, c, s))
                L = layers(z)
                for b, m in BOX.items():
                    tot = (cosw * m).sum()
                    cell_nm2 = (15 * 15)   # 0.25 deg lat = 15 nm
                    for k, v in L.items():
                        a = (cosw * (m & v)).sum()
                        f.write("%s,%d,%s,%s,%.5f,%.0f\n" % (c, s, b, k, a / tot, a * cell_nm2))
                    f.write("%s,%d,%s,%s,%.5f,%.0f\n" % (c, s, b, "water", 1.0, tot * cell_nm2))
                f.flush(); print("ok", c, s, flush=True)
            except Exception as e:
                print("err", c, s, e, flush=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
if __name__ == "__main__":
    run(sys.argv[1:])
