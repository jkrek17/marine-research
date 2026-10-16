"""Issued OPC High Seas Forecast warnings -> gridded "warned" masks on the scoring grids.

Winter 2025-26 issuances (2025-10-31 .. 2026-03-31), both basins:
  primary   1630 UTC (synopsis 12Z) and 0430 UTC (synopsis 00Z)
  secondary 2230 UTC (18Z) and 1030 UTC (06Z)
Atlantic (HSFAT1) -> natl, Pacific (HSFEP1) -> npac; grids from wind-focus/basins/code/bfetch.py
(0.25 deg, north-first rows, lon 0-360).

Warned area at level L (34, 48, 64 kt) = union of the block areas at that hour whose wind range
tops out at L or more -- the rule in hsf/code/score_compare.py score_case(). Cells are grid cell
centres tested with shapely.contains_xy. 'area' is the forecast-area polygon (hsf_parse AREAS).
complete = every block at that hour with wind hi >= 34 was fully parsed (same as score_case).

Parser: hsf_parse_wx.py (a copy of hsf/code/hsf_parse.py with fixes marked "WX:").

Writes desk/<dom>/<issuedYYYYMMDDHHMM>_h<HH>.npz (w34 w48 w64 area bool; lows float32 rows
lat, lon 0-360, mb, headline code 0 none 1 gale 2 storm 3 hurricane force 4 tropical; complete;
valid) and desk/index.csv.

usage: python3 desk_masks.py [primary|all]
"""
import csv
import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from rk.paths import DATA  # noqa: E402
ROOT = str(DATA / "extra" / "warning-experiment")       # desk/<dom>/*.npz and desk/index.csv
PF = os.environ.get("PROJECT_FILES", "/mnt/project-files")   # hsf archive and parser, basins study grids
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(PF, "hsf", "code"))
sys.path.insert(2, os.path.join(PF, "wind-focus", "basins", "code"))
import bfetch  # noqa: E402
from hsf_parse_wx import AREAS, RASTER, parse  # noqa: E402
from split_archive import products  # noqa: E402

LEVELS = (34, 48, 64)
HOURS = (0, 24, 48)
BASINS = {"atl": ("HSFAT1", "natl"), "pac": ("HSFEP1", "npac")}
PRIMARY = ("1630", "0430")
SECONDARY = ("2230", "1030")
START, END = datetime(2025, 10, 31), datetime(2026, 4, 1)
CODE = {"NONE": 0, "GALE": 1, "STORM": 2, "HURRICANE FORCE": 3, "TROPICAL": 4}


def headline(w):
    w = (w or "").upper()
    if "HURRICANE FORCE" in w or "FORCE 12" in w:
        return "HURRICANE FORCE"
    if re.search(r"HURRICANE|TROPICAL", w):
        return "TROPICAL"
    if "STORM" in w:
        return "STORM"
    if "GALE" in w:
        return "GALE"
    return "NONE" if w in ("", "NONE") else w


def issuances(basin, hhmm):
    """{issued datetime: product}; a later copy of the same issuance (correction) replaces an earlier one."""
    out = {}
    for p in products(os.path.join(PF, "hsf", "archive", BASINS[basin][0] + ".txt")):
        m = re.search(r"\n(\d{4}) UTC \w{3} (\w{3}) (\d+) (\d{4})", p)
        if not m or m.group(1) not in hhmm:
            continue
        t = datetime.strptime("%s %s %s %s" % (m.group(4), m.group(2), m.group(3), m.group(1)), "%Y %b %d %H%M")
        if START <= t < END:
            out[t] = p
    return out


def grid(dom):
    lats, lons = bfetch.LATS[dom], bfetch.LONS[dom]
    LON, LAT = np.meshgrid(lons, lats)
    return LAT, (LON if dom == "npac" else np.where(LON > 180, LON - 360, LON))


def run(sets):
    rows = []
    for basin, (_, dom) in BASINS.items():
        LAT, LONB = grid(dom)
        area = shapely.contains_xy(AREAS[basin], LONB, LAT)
        odir = os.path.join(ROOT, "desk", dom)
        os.makedirs(odir, exist_ok=True)
        for which, hhmm in sets:
            iss = issuances(basin, hhmm)
            print(basin, which, len(iss), "issuances", flush=True)
            for t, prod in sorted(iss.items()):
                try:
                    r = parse(prod, basin)
                except Exception as e:  # one bad product should not stop the run
                    print("parse fail", basin, t, e, flush=True)
                    continue
                syn = r["synopsis_valid"] or datetime(t.year, t.month, t.day, {4: 0, 10: 6, 16: 12, 22: 18}[t.hour])
                if syn != datetime(t.year, t.month, t.day, {4: 0, 10: 6, 16: 12, 22: 18}[t.hour]):
                    print("odd synopsis time", basin, t, syn, flush=True)
                for h in HOURS:
                    allb = [b for b in r["blocks"] if b["hour"] == h and b["wind"]]
                    b34 = [b for b in allb if (b["wind"][1] or 0) >= 34]
                    complete = all(b["parsed"] for b in b34)
                    masks = {}
                    for L in LEVELS:
                        m = np.zeros(LAT.shape, bool)
                        for b in allb:
                            if b["area"] is not None and b["wind"][1] and b["wind"][1] >= L:
                                m |= shapely.contains_xy(b["area"], LONB, LAT)
                        masks["w%d" % L] = m & area
                    lows, seen = [], set()
                    for s in r["systems"]:
                        if s["hour"] != h:
                            continue
                        hl = headline(s["warning"])
                        for la, lo, mb in s["lows"]:
                            lo360 = lo % 360
                            k = (la, lo360, mb)
                            if k in seen:
                                continue
                            seen.add(k)
                            lows.append((la, lo360, mb, CODE.get(hl, 0), hl))
                    valid = syn + timedelta(hours=h)
                    name = "%s_h%02d" % (t.strftime("%Y%m%d%H%M"), h)
                    np.savez_compressed(os.path.join(odir, name + ".npz"), area=area, complete=np.bool_(complete),
                                        valid=valid.strftime("%Y%m%d%H"),
                                        lows=np.array([x[:4] for x in lows], np.float32).reshape(-1, 4), **masks)
                    rows.append(dict(dom=dom, issued=t.strftime("%Y%m%d%H%M"), hour=h, valid=valid.strftime("%Y%m%d%H"),
                                     complete=int(complete), n_blocks=len(allb),
                                     w34_cells=int(masks["w34"].sum()), w48_cells=int(masks["w48"].sum()),
                                     w64_cells=int(masks["w64"].sum()),
                                     lows=";".join("%s %.1fN %.1fE %d" % (x[4], x[0], x[1], x[2]) for x in lows),
                                     set=which, n_blocks34=len(b34),
                                     n_unparsed34=sum(not b["parsed"] for b in b34)))
    with open(os.path.join(ROOT, "desk", "index.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), "rows; geometry backend:", "raster stand-in" if RASTER else "shapely", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    sets = [("primary", PRIMARY)] + ([("secondary", SECONDARY)] if mode == "all" else [])
    run(sets)
