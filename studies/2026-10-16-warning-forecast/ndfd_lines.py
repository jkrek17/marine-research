"""Warning lines against references that are not shaped by the text format (Jason, 2026-10-17 04:54Z).

The HSF text has to draw areas as boxes and quadrants, so its area is not a fair bar. This re-scores the
strongest-model lines beside three other references, all with the fair scores of fair_lines.py:
  desk    the issued HSF text (as before); hours where some blocks did not parse are kept as a lower bound
          (complete = 0), since dropping them dropped 35% of storm events and 39% of HF lows (audit 2026-10-17)
  ndfd    the desk's own gridded wind (NDFD oceanic, the full update made from the same 00/12Z runs,
          rk.desk.issue_for), drawn at the level, with offsets 0..+8 kt
  mean2   the plain GFS/ECMWF average, with offsets
  max3    strongest of GFS, ECMWF and AIFS, with offsets
  blend, corelift  the page's blend and Core Lifted (+5 kt where core likelihood >= 35%), built with awips-tools
          storm.py as page_lines.py does (core without its 850 mb inputs); only when asked for on the command line
Two scopes: "all" is the OPC water as before; "ndfd" is the OPC water where the NDFD grid has a value, and
every rule, the text included, is scored there so the four compare on the same cells and events.
Gale and storm truth (column truth): ASCAT where it passed (+-90 min), and the GFS and ECMWF analyses (step 0)
over all the water; HF truth is the archive (truth = archive). Area against the truth needs no extra field: cells (seen warned cells) / obs_cells (ASCAT cells at the level).

usage: python3 ndfd_lines.py OUT.csv [RULES] ; RULES = comma list, default desk,ndfd,mean2,max3
       (blend,corelift need awips-tools: env AWIPS_TOOLS, default a clone beside this repo); env NPROC (default 3)
"""
import csv
import datetime as dt
import glob
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

import score_warnings as W  # noqa: E402
from rk import desk, score, store, truth  # noqa: E402
from rk.basins import grid  # noqa: E402

OFFSETS = {34: range(-2, 13), 48: range(0, 17), 64: range(0, 23, 2)}
NDFD_OFFSETS = {34: range(0, 9), 48: range(0, 9), 64: range(0, 9, 2)}
RULES = ("desk", "ndfd", "mean2", "max3")


def page_fields(z, step, lats, ocean):
    """The page's blend and Core Lifted wind for one case, as page_lines.py builds them."""
    import warnings
    from page_lines import MODEL, storm
    pr, mem = W.products(z, step)
    n81 = int(z["nsrc"][0] + z["nsrc"][1])
    nan = np.full(pr["blend"].shape, np.nan, np.float32)
    low = {"u925": z["u925"].astype(np.float32), "v925": z["v925"].astype(np.float32),
           "t925": z["t925"].astype(np.float32), "t2": z["t2"].astype(np.float32),
           "skt": z["skt"].astype(np.float32), "u850": nan, "v850": nan, "t850": nan}
    members, aens = mem[:n81], mem[n81:]
    speeds = np.array([pr["gfs"], pr["ifs"], pr["aifs"]])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        feats = storm.core_features(np.abs(lats), pr["blend"], pr["blend"] - W.support_base(speeds, members),
                                    speeds, members, aens, low)
        core = storm.core_grid(feats, ocean, MODEL)
    windcore, _ = storm.products(pr["blend"], core, members)
    return {"blend": pr["blend"], "corelift": windcore.astype(np.float32)}
RING = np.ones((2 * W.NBR + 1, 2 * W.NBR + 1), bool)


def text_masks(basin, valid, hour):
    """Issued HSF masks at every hour the text exists, complete or not -> ({L: mask}, complete) or (None, 0)."""
    iss = valid - dt.timedelta(hours=hour) + dt.timedelta(hours=4, minutes=30)
    p = W.EXTRA / "desk" / basin / ("%s_h%02d.npz" % (iss.strftime("%Y%m%d%H%M"), hour))
    if not p.exists():
        return None, 0
    with np.load(p) as z:
        return {L: z["w%d" % L].astype(bool) for L in (34, 48, 64)}, int(z["complete"])


def ndfd_at(basin, run, valid):
    """The desk's gridded wind valid at `valid` from the full update made from `run`, if cached."""
    d = desk._read(desk.issue_for(basin, run))
    if d is None or valid not in d[basin]["valid"]:
        return None
    return d[basin]["speed"][d[basin]["valid"].index(valid)].astype(np.float32)


def _case(args):
    basin, f, rules = args if len(args) == 3 else (*args, RULES)
    run, step = os.path.basename(f)[:-4].split("_")
    run, step = dt.datetime.strptime(run, "%Y%m%d%H"), int(step)
    valid = run + dt.timedelta(hours=step)
    an = store.analysis(basin, valid)
    if an is None:
        return []
    tm, complete = text_masks(basin, valid, step)
    nd = ndfd_at(basin, run, valid)
    sea = W.opc_area(basin) & an["mask"].astype(bool)
    seen_a, spd_a = truth.ascat_grid(basin, valid)
    if seen_a is None:
        seen_a, spd_a = np.zeros(sea.shape, bool), np.zeros(sea.shape, np.float32)
    # gale and storm truth: ASCAT where it passed, and each analysis (model step 0) over all the water
    truths = {"ascat": (seen_a, spd_a), "anl_gfs": (sea, an["gfs"]["speed"]), "anl_ifs": (sea, an["ifs"]["speed"])}
    hf = truth.hf_fixes(basin, valid)
    lats, lons = grid(basin)
    if hf is None or not len(hf):
        iy = ix = np.zeros(0, int)
    else:
        iy = np.clip(np.rint((lats[0] - hf["lat"].values) / 0.25).astype(int), 0, lats.size - 1)
        ix = np.clip(np.rint((hf["lon"].values - lons[0]) / 0.25).astype(int), 0, lons.size - 1)
    with np.load(f) as z:
        s = {m: z["s10_" + m].astype(np.float32) for m in ("gfs", "ifs", "aifs")}
        fields = {"max3": np.maximum(np.maximum(s["gfs"], s["ifs"]), s["aifs"]), "mean2": 0.5 * (s["gfs"] + s["ifs"])}
        if {"blend", "corelift"} & set(rules):
            fields.update(page_fields(z, step, lats, an["mask"].astype(bool)))
    fields = {k: v for k, v in fields.items() if k in rules}
    cosl = 225 * np.cos(np.radians(lats))[:, None]
    rows = []

    def score_scope(scope, area, tname):
        seen0, spd = truths[tname]
        seen = seen0 & area
        keep = area[iy, ix]
        hla, hlo = (hf["lat"].values[keep], hf["lon"].values[keep]) if len(iy) else ([], [])
        base = dict(dom=basin, run=run.strftime("%Y%m%d%H"), step=step, valid=valid.strftime("%Y%m%d%H"),
                    scope=scope, truth="archive" if tname == "ascat" else tname, has_text=int(tm is not None), complete=complete, has_ndfd=int(nd is not None))

        def add(rule, setting, L, w):
            if L == 64 and tname != "ascat":
                return   # HF truth is the archive whatever the gale/storm truth; scored once
            w = w & area
            r = dict(base, rule=rule, setting=setting, L=L, area_nm2=float((cosl * w).sum()),
                     reach_nm2=float((cosl * (ndimage.binary_dilation(w, RING) & area)).sum()) if w.any() else 0.0)
            if L == 64:
                for k in (150, 300, 500):
                    q = score.warning_points(w, basin, hla, hlo, k, mask=area)
                    r.update({"events": q["events"], "areas": q["areas"], "hits%d" % k: q["hits"],
                              "false%d" % k: q["false"]})
            else:
                r.update(score.warning_events(w, spd, seen, L, mask=area))
            if L != 64:
                r["truth"] = tname
            rows.append(r)

        for L in (34, 48, 64):
            if tm is not None and "desk" in rules:
                add("desk", 0, L, tm[L])
            if nd is not None and "ndfd" in rules:
                for d in NDFD_OFFSETS[L]:
                    add("ndfd", d, L, np.nan_to_num(nd, nan=-99) + d >= L)
            for name, field in fields.items():
                for d in OFFSETS[L]:
                    add(name, d, L, field + d >= L)

    for tname in truths:
        score_scope("all", sea, tname)
        if nd is not None:
            score_scope("ndfd", sea & np.isfinite(nd), tname)
    return rows


def run_case(args):
    for i in range(4):
        try:
            return _case(args)
        except OSError:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


if __name__ == "__main__":
    from multiprocessing import get_context
    out = sys.argv[1]
    rules = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else RULES
    jobs = [(b, f, rules) for b in ("natl", "npac") for f in sorted(glob.glob(str(W.EXTRA / "cases" / b / "*.npz")))]
    print(len(jobs), "cases", flush=True)
    rows = []
    with get_context("spawn").Pool(int(os.environ.get("NPROC", "3"))) as p:
        for i, r in enumerate(p.imap_unordered(run_case, jobs, chunksize=2)):
            rows += r
            if i % 100 == 0:
                print(i, flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), flush=True)
