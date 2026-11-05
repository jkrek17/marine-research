"""Pattern drill, step 2a (version 2, Jason 2026-11-05): the scene's answer, not one low's.

The answer for a snapshot is the strongest wind ASCAT saw anywhere in the map box (3rd highest 0.25 deg cell,
so one noisy cell does not set it), and the circled low is the deepest low in the box. A candidate (pick.py)
is kept only when the low it follows is the deepest in the box at both T and T + 24 h, so the circle and the
track stay on one low. The guard that ASCAT actually passed over that low's circulation is pick.good() on
its own pressure basin (find_cases.py, version 2).

    python3 scene.py [--find find2]  -> scene.json beside key.csv: {key: {...}} for every candidate

key = basin|t0|lat0|lon0. Per snapshot s (0, 24): deep_s (the followed low is the deepest in the box),
peak_s (kt), plat_s, plon_s (where the 3rd-highest cell is), n_s (ASCAT cells in the box).
Resumable: keys already in scene.json are skipped.
"""
import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from rk import truth  # noqa: E402
from rk.basins import grid  # noqa: E402
import pick  # noqa: E402
from build_deck import NX, NY, RES, box_for  # noqa: E402


def key(x):
    return "%s|%s|%.2f|%.2f" % (x["basin"], x["t0"].strftime("%Y%m%d%H"), x["r0"]["lat"], x["r0"]["lon"])


def in_box(lat, lon, lat_n, lon_w):
    """Inside the map box (cell-edge extent), lon any convention."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    return ((lat <= lat_n + RES / 2) & (lat >= lat_n - (NY - 1) * RES - RES / 2)
            & (((lon - lon_w + RES / 2) % 360) <= (NX - 1) * RES + RES))


def scene_peak(g, lats, lons, lat_n, lon_w):
    """3rd highest gridded ASCAT cell inside the box -> (kt, lat, lon, n) or (None, None, None, n)."""
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    m = np.isfinite(g) & in_box(la, lo, lat_n, lon_w)
    n = int(m.sum())
    if n < 3:
        return None, None, None, n
    v, a, b = g[m], la[m], lo[m]
    k = np.argsort(v)[::-1][2]
    return round(float(v[k]), 1), float(a[k]), float(b[k]), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", default="find2")
    a = ap.parse_args()
    rec = pick.load(a.find)
    cands = pick.candidates(rec)
    out_p = pick.ROOT / "scene.json"
    done = json.loads(out_p.read_text()) if out_p.exists() else {}
    todo = defaultdict(list)          # (basin, valid) -> [(cand, snap)]
    for x in cands:
        if key(x) in done:
            continue
        for s, t in (("0", x["t0"]), ("24", x["t1"])):
            todo[(x["basin"], t)].append((x, s))
    print(len(cands), "candidates,", len(cands) - len({key(x) for x in cands} - set(done)), "done,",
          len(todo), "ASCAT times to read", flush=True)
    res = defaultdict(dict)
    for i, ((basin, t), items) in enumerate(sorted(todo.items(), key=lambda kv: kv[0][1])):
        asc = truth.ascat(basin, t)
        lats, lons = grid(basin)
        g = truth.ascat_to_grid(basin, asc["lat"], asc["lon"], asc["spd_kt"])[0] if asc is not None else None
        lows = rec[t][basin]["lows"]
        for x, s in items:
            row = {"lat0": x["r0"]["lat"], "lon0": x["r0"]["lon"], "lat24": x["r1"]["lat"], "lon24": x["r1"]["lon"]}
            lat_n, lon_w = box_for(row)
            me = x["r0"] if s == "0" else x["r1"]
            inside = [r for r in lows if in_box(r["lat"], r["lon"], lat_n, lon_w)]
            deep = min(inside, key=lambda r: r["hpa"]) if inside else None
            d = res[key(x)]
            d["deep_" + s] = bool(deep is not None and abs(deep["lat"] - me["lat"]) < 0.01 and abs(deep["lon"] - me["lon"]) < 0.01)
            pk, pla, plo, n = scene_peak(g, lats, lons, lat_n, lon_w) if g is not None else (None, None, None, 0)
            d.update({"peak_" + s: pk, "plat_" + s: pla, "plon_" + s: plo, "n_" + s: n})
        if i % 100 == 0:
            print(i, len(todo), t, flush=True)
    done.update({k: v for k, v in res.items() if len(v) == 10})
    tmp = out_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(done))
    tmp.replace(out_p)
    keep = [v for v in done.values() if v["deep_0"] and v["deep_24"] and v["peak_0"] is not None and v["peak_24"] is not None]
    print("scene.json", len(done), "| deepest low in the box at both times:", len(keep))


if __name__ == "__main__":
    main()
