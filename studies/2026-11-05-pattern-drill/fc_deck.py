"""Pattern drill, "beat the model" (Jason 2026-11-06): each model's full +24 h forecast maps for every case.

<id>_fc_<model>.bin = one snapshot in the deck's .bin layout (build_deck.FIELDS from the model's +24 h
forecast valid at T + 24 h, then the model's 10 m wind speed in kt and direction / 2 where the ASCAT layers
sit in an analysis snapshot, then land), so the page reads it with the same parser. The model's scene peak
(3rd-highest 0.25 deg 10 m wind over open water in the box, the ASCAT answer's rule) goes to
fc_<model>.json with its category. Models: gfs (all cases), ifs (ECMWF open data on AWS: 00/12Z runs from
March 2025 only; land and ice from the GFS run's +24 h).

    python3 fc_deck.py --model gfs|ifs [--deck page/deck] [--workers 4]     (resumable)
    python3 fc_deck.py --manifest      (after build_deck / score_ingredients: case["fc"] into the manifest)
"""
import argparse
import csv
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from rk import KT, fetch  # noqa: E402
from rk.basins import crop, grid  # noqa: E402
import build_deck as B  # noqa: E402
from scene import in_box  # noqa: E402

EC_START = dt.datetime(2025, 3, 1)
GFS_WANT = dict(fetch.DRILL, **{"UGRD:10 m above ground": "u10", "VGRD:10 m above ground": "v10"})
EC_SELECT = {("sfc", "msl", None): "msl", ("sfc", "10u", None): "u10", ("sfc", "10v", None): "v10",
             ("sfc", "skt", None): "tsfc", ("sfc", "2t", None): "t2"}
for lev in ("1000", "925", "850", "500", "250"):
    for p, n in (("gh", "z"), ("t", "t"), ("u", "u"), ("v", "v")):
        EC_SELECT[("pl", p, lev)] = n + lev
EC_SELECT[("pl", "vo", "500")] = "vo500"
OMEGA = 7.292e-5


def model_global(model, t0):
    if model == "gfs":
        return fetch.gfs_global(t0, 24, GFS_WANT)
    if t0 < EC_START or t0.hour % 12:
        return None
    from rk.fetch import nwp
    fetch.wait_for_quiet()
    raw = None
    for k in range(4):            # the ECMWF bucket drops requests now and then
        try:
            raw = nwp.fields("ifs", t0.strftime("%Y%m%d%H"), 24, EC_SELECT)
            break
        except RuntimeError:
            if k == 3:
                raise
            time.sleep(5 * 2 ** k)
    if raw is None or any(n not in raw for n in EC_SELECT.values()):
        return None
    mask = fetch.gfs_global(t0, 24, {"LAND:surface": "land", "ICEC:surface": "ice"})
    if mask is None:
        return None
    lat = np.linspace(90, -90, 721)[:, None]
    raw["vort500"] = raw.pop("vo500") + 2 * OMEGA * np.sin(np.radians(lat))   # relative -> absolute, as GFS ABSV
    raw.update(mask)
    return raw


def third(v):
    v = np.sort(v[np.isfinite(v)])[::-1]
    return round(float(v[2]), 1) if len(v) >= 3 else None


def one(row, deck, model):
    out = deck / ("%s_fc_%s.bin" % (row["id"], model))
    t0 = dt.datetime.strptime(row["t0"], "%Y%m%d%H")
    g = model_global(model, t0)
    if g is None:
        return None
    lat_n, lon_w = B.box_for(row)
    m, land = B.maps(g, lat_n, lon_w)
    rows, cols = B.box_index(lat_n, lon_w)
    sl = (slice(B.MARGIN, -B.MARGIN), slice(B.MARGIN, -B.MARGIN))
    u = g["u10"][np.ix_(rows, cols)][sl][::2, ::2]
    v = g["v10"][np.ix_(rows, cols)][sl][::2, ::2]
    spd = np.hypot(u, v) * KT
    dirn = (np.degrees(np.arctan2(-u, -v)) % 360) / 2          # meteorological, from
    parts = [B.quant(m[k], off, sc) for k, _, _, off, sc in B.FIELDS]
    parts += [B.quant(spd, 0.0, 1.0), B.quant(dirn, 0.0, 1.0), land.astype(np.uint8)]
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(b"".join(a.tobytes() for a in parts))
    tmp.replace(out)
    b = row["basin"]
    iy, ix = crop(b)
    s = np.hypot(g["u10"][iy][:, ix], g["v10"][iy][:, ix]) * KT
    water = (g["land"][iy][:, ix] < 0.01) & (g["ice"][iy][:, ix] <= 0.15)
    lats, lons = grid(b)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    pk = third(np.where(in_box(la, lo, lat_n, lon_w) & water, s, np.nan))
    return {"peak": pk, "cat": None if pk is None else int(0 if pk < 34 else 1 if pk < 48 else 2 if pk < 64 else 3)}


def to_manifest(deck):
    """Merge fc_<model>.json into deck/manifest.json as case["fc"][model] = {peak, cat} (cases with the file)."""
    p = deck / "manifest.json"
    m = json.loads(p.read_text())
    got = {k: json.loads((HERE / ("fc_%s.json" % k)).read_text()) for k in ("gfs", "ifs") if (HERE / ("fc_%s.json" % k)).exists()}
    for c in m["cases"]:
        c["fc"] = {k: v[c["id"]] for k, v in got.items()
                   if c["id"] in v and (deck / ("%s_fc_%s.bin" % (c["id"], k))).exists()}
    p.write_text(json.dumps(m, separators=(",", ":")))
    print("manifest:", {k: sum(k in c["fc"] for c in m["cases"]) for k in got}, "of", len(m["cases"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["gfs", "ifs"])
    ap.add_argument("--manifest", action="store_true", help="only merge the forecast peaks into the manifest")
    ap.add_argument("--deck", default=str(HERE / "page" / "deck"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    deck = Path(a.deck)
    if a.manifest or not a.model:
        return to_manifest(deck)
    p = HERE / ("fc_%s.json" % a.model)
    done = json.loads(p.read_text()) if p.exists() else {}
    ids = {c["id"] for c in json.loads((deck / "manifest.json").read_text())["cases"]}
    rows = [r for r in csv.DictReader(open(B.ROOT / "key.csv")) if r["id"] in ids
            and not (r["id"] in done and (deck / ("%s_fc_%s.bin" % (r["id"], a.model))).exists())]

    def safe(r):
        try:
            return one(r, deck, a.model)
        except Exception as e:
            print(r["id"], "error", e, flush=True)
            return None
    with ThreadPoolExecutor(a.workers) as ex:
        for r, res in zip(rows, ex.map(safe, rows)):
            if res is not None:
                done[r["id"]] = res
    p.write_text(json.dumps(done, indent=0, sort_keys=True))
    print(len(done), "cases with a", a.model, "+24 h forecast")


if __name__ == "__main__":
    main()
