"""Front drill, step 2: the deck (format in design.md, "Deck format") for every case in picked.csv.

    python3 build_deck.py [--out <deck folder>] [--workers 4] [--limit N] [--manifest-only]

Per case, a 25 x 40 deg box at 0.5 deg centred on the analysed low: GFS f000 maps through rk.fetch.gfs_global
(our own `want`, the pattern drill's DRILL plus 700 hPa and 10 m), 3 h MSLP change against the previous cycle's f003,
ASCAT (the drill's ascat_box, +-90 min; "ascat" true when it covers >= 15% of the box water), GOES air-mass RGB (GOES-East in the Atlantic, GOES-West in the Pacific; IR from GridSat-B1 where that has no usable picture), the analysed fronts and lows (rk.fronts, merged, curved (rk.fronts.smooth)
to 25 nm, clipped to the box minus 1 deg, pieces under 150 nm dropped), each flagged "sys" when it belongs to the case
low's system (FL.mark_system) with the ring radius "sys_r_nm", and one hint line per system non-trough front type from
the case's own fields. Cases with under 250 nm of system front are dropped from the manifest, and so are cases before
FL.COVERAGE_FULL_FROM whose system has a front ending at WPC's old map edge; cases whose system has a front ending at the edge of the coded analysis (180 in the Pacific, 1W in the Atlantic, FL.basin_edge_clipped) or no cold, warm or occluded front are left out too. Ids g0001... (the first deck's f* files stay on disk). Truth fronts are curves (rk.fronts.smooth). Air-mass RGB only for
lows at or south of 55N, GridSat IR otherwise. Resumable: a case whose work/<id>.json exists for the same time and position is skipped (delete it to redo). The deck
(<out>/manifest.json, <id>.bin, <id>_am.jpg or <id>_ir.jpg) and key.csv (never published) go under
rk.paths.data("extra", "front-drill"); the deck is never committed.
"""
import argparse
import csv
import datetime as dt
import importlib.util
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import frontlib as FL  # noqa: E402
from rk import KT, diag, fetch, fronts, paths  # noqa: E402


def _load_drill():
    p = HERE.parent / "2026-11-05-pattern-drill" / "build_deck.py"
    spec = importlib.util.spec_from_file_location("pattern_drill_build_deck", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


D = _load_drill()      # box_index, quant, ascat_box, _sat_grid, _sample, GREY, RES, NY, NX, MARGIN
RES, NY, NX, MARGIN = D.RES, D.NY, D.NX, D.MARGIN
ROOT = paths.data("extra", "front-drill")
WORK = ROOT / "work"
EDGE_FRAC = 0.15            # ASCAT must cover this share of the box water
ID_PREFIX = "g"             # the second deck (both basins); the first deck's f0001... files stay on disk, out of the manifest

WANT = {"PRMSL:mean sea level": "msl", "HGT:1000 mb": "z1000", "HGT:500 mb": "z500",
        "TMP:850 mb": "t850", "RH:850 mb": "rh850", "TMP:700 mb": "t700", "RH:700 mb": "rh700",
        "UGRD:10 m above ground": "u10", "VGRD:10 m above ground": "v10",
        "UGRD:250 mb": "u250", "VGRD:250 mb": "v250", "LAND:surface": "land", "ICEC:surface": "ice"}
WANT_P = {"PRMSL:mean sea level": "msl"}

# key, name, units, offset, scale (value = offset + scale x byte, byte 0..254, 255 missing)
FIELDS = [
    ("msl", "Sea level pressure", "hPa", 930.0, 0.5),
    ("thk", "1000-500 hPa thickness", "dam", 470.0, 0.5),
    ("u10", "10 m wind, east component", "m/s", -40.0, 0.32),
    ("v10", "10 m wind, north component", "m/s", -40.0, 0.32),
    ("te850", "850 hPa equivalent potential temperature", "K", 240.0, 0.5),
    ("te700", "700 hPa equivalent potential temperature", "K", 240.0, 0.5),
    ("dp3", "3 h MSLP change", "hPa", -12.7, 0.1),
    ("wspd250", "250 hPa wind speed", "kt", 0.0, 1.0),
    ("ascat_spd", "ASCAT wind speed (255 unseen)", "kt", 0.0, 1.0),
    ("ascat_dir", "ASCAT wind direction from (255 unseen)", "deg", 0.0, 2.0),
    ("land", "Land or sea ice", "0/1", 0.0, 1.0),
]
BIN_SIZE = len(FIELDS) * NY * NX
_lock = threading.Lock()
_bytes = {"gfs": 0, "abi": 0}


def box_for(lat, lon):
    """North-west cell centre of the box centred on the low (lat_n, lon_w 0-360, multiples of 0.5)."""
    lat_n = round((lat + (NY - 1) * RES / 2) * 2) / 2
    lon_w = round(((lon - (NX - 1) * RES / 2) % 360) * 2) / 2
    return lat_n, lon_w


def gfs_bytes(valid, step, want):
    import nwp
    idx = nwp.ncep_index(fetch.gfs_url(valid, step))
    n = 0
    for k in want:
        s, e = (idx or {}).get(k, (0, -1))
        n += (e - s + 1) if e is not None else 0
    return n


def maps(g, gp, lat_n, lon_w):
    """GFS dicts (T f000, previous cycle f003 or None) -> ({key: [NY, NX] float, NaN missing}, land bool).
    Smoothed on the 0.25 deg grid with the margin, then every second cell, like the drill."""
    rows, cols = D.box_index(lat_n, lon_w)
    c = {k: v[np.ix_(rows, cols)].astype(float) for k, v in g.items()}
    msl = diag.smooth(c["msl"] / 100.0, 1.0)
    z1000, z500 = diag.smooth(c["z1000"], 2.0), diag.smooth(c["z500"], 2.0)
    te850 = diag.smooth(diag.theta_e(c["t850"], c["rh850"], 850.0), 1.0)
    te700 = diag.smooth(diag.theta_e(c["t700"], c["rh700"], 700.0), 1.0)
    out = {"msl": msl, "thk": (z500 - z1000) / 10.0,
           "u10": diag.smooth(c["u10"], 1.0), "v10": diag.smooth(c["v10"], 1.0),
           "te850": te850, "te700": te700,
           "wspd250": np.hypot(diag.smooth(c["u250"], 2.0), diag.smooth(c["v250"], 2.0)) * KT}
    if gp is not None:
        mp = diag.smooth(gp["msl"][np.ix_(rows, cols)].astype(float) / 100.0, 1.0)
        out["dp3"] = msl - mp
    else:
        out["dp3"] = np.full_like(msl, np.nan)
    water = (c["land"] < 0.5) & (c["ice"] < 0.15)
    sl = (slice(MARGIN, -MARGIN), slice(MARGIN, -MARGIN))
    return {k: diag.subsample(v[sl], 2) for k, v in out.items()}, diag.subsample((~water)[sl], 2)


AM_MAX_LAT = 55.0         # the air-mass RGB turns false purple near the disk edge: only for lows at or south of this


def imagery(valid, lat_n, lon_w, lon_c, stem, out, low_lat, basin):
    """Air-mass RGB (GOES-East in the Atlantic, GOES-West in the Pacific) where the case low is at or south of AM_MAX_LAT,
    the Atlantic box centre is inside the GOES-East disk and the picture covers the box, else GridSat IR -> "am" | "ir" |
    None; writes <stem>_am.jpg or <stem>_ir.jpg."""
    from PIL import Image
    from rk import satellite
    lat, lon = D._sat_grid(lat_n, lon_w)
    if (basin == "npac" or lon_c <= 335.0) and low_lat <= AM_MAX_LAT:    # east of 25W is outside the GOES-East disk
        a = satellite.airmass_box(basin, valid)
        if a is not None:
            s = D._sample(a, lat, lon, ["b08", "b10", "b12", "b13"])
            ok = np.all([np.isfinite(s[k]) for k in s], axis=0)
            if ok.mean() > 0.3:
                rgb = satellite.airmass_rgb(s["b08"], s["b10"], s["b12"], s["b13"])
                img = np.where(ok[..., None], np.nan_to_num(rgb) * 255, D.GREY).astype(np.uint8)
                Image.fromarray(img, "RGB").save(out / (stem + "_am.jpg"), quality=80)
                return "am"
    b = satellite.box(basin, valid)
    if b is not None:
        tb = D._sample(b, lat, lon, ["tb"])["tb"]
        if np.isfinite(tb).mean() > 0.2:
            v = np.clip((300.0 - tb) / 100.0, 0, 1) ** 0.8 * 255
            img = np.where(np.isfinite(tb), v, D.GREY).astype(np.uint8)
            Image.fromarray(img, "L").save(out / (stem + "_ir.jpg"), quality=80)
            return "ir"
    return None


def _patch_abi_bytes():
    from rk import satellite
    orig = satellite.abi_airmass

    def wrapped(basin, valid):
        m = orig(basin, valid)
        if m is not None:
            with _lock:
                _bytes["abi"] += int(m.get("bytes", 0))
        return m
    satellite.abi_airmass = wrapped


def _dropped():
    p = WORK / "dropped.json"
    return json.loads(p.read_text()) if p.exists() else {}


def one(row, out):
    cid = row["id"]
    src = "%s %s %s" % (row["valid"], row["lat"], row["lon"])
    pj = WORK / (cid + ".json")
    if _dropped().get(cid) == src:           # built before, and left out of the deck (system too short or at the old edge)
        return "skip"
    if pj.exists() and (out / (cid + ".bin")).exists():
        old = json.loads(pj.read_text())
        # files from the first run carry no "src": same low position and pressure is the same case
        same = old.get("src") == src or ("src" not in old and old["low"] == {
            "lat": float(row["lat"]), "lon": float(row["lon"]), "hpa": float(row["hpa"])})
        if same:
            if old.get("img") == "am" and old["low"]["lat"] > AM_MAX_LAT:     # imagery rule changed: only the picture is redone
                valid = dt.datetime.strptime(row["valid"], "%Y%m%d%H")
                lat_n, lon_w = old["lat0"], old["lon0"]
                lon_c = (lon_w + (NX - 1) * RES / 2) % 360
                old["img"] = imagery(valid, lat_n, lon_w, lon_c, cid, out, old["low"]["lat"], old.get("basin", row["basin"]))
                tmp = WORK / (cid + ".tmp")
                tmp.write_text(json.dumps(old))
                tmp.replace(pj)
                return "imagery"
            return "skip"
    valid = dt.datetime.strptime(row["valid"], "%Y%m%d%H")
    basin = row["basin"]
    lat, lon, hpa = float(row["lat"]), float(row["lon"]), float(row["hpa"])
    lat_n, lon_w = box_for(lat, lon)
    lon_c = (lon_w + (NX - 1) * RES / 2) % 360
    g = fetch.gfs_global(valid, 0, WANT)
    if g is None:
        return "no gfs"
    gp = fetch.gfs_global(valid - dt.timedelta(hours=6), 3, WANT_P)
    with _lock:
        _bytes["gfs"] += gfs_bytes(valid, 0, WANT) + (gfs_bytes(valid - dt.timedelta(hours=6), 3, WANT_P) if gp else 0)
    m, land = maps(g, gp, lat_n, lon_w)
    del g
    spd, dirn = D.ascat_box(basin, valid, lat_n, lon_w)
    water = ~land
    cover = float(((spd != 255) & water).sum() / max(1, water.sum()))
    ascat = cover >= EDGE_FRAC
    if not ascat:
        spd[:], dirn[:] = 255, 255
    img = imagery(valid, lat_n, lon_w, lon_c, cid, out, lat, basin)

    a = fronts.analysis(valid)
    if a is None:
        return "no analysis"
    fr = FL.clip_fronts(FL.merged(a), lat_n, lon_w, NY, NX, RES)
    lows = FL.lows_in_box(a["lows"], lat_n, lon_w, NY, NX, RES)
    rec = {"id": cid, "basin": basin, "lat0": lat_n, "lon0": lon_w, "low": {"lat": lat, "lon": lon, "hpa": hpa}, "lows": lows,
           "fronts": fr, "img": img, "ascat": ascat, "ascat_cover": round(cover, 3), "src": src}

    parts = []
    for k, _, _, off, sc in FIELDS:
        if k == "ascat_spd":
            parts.append(spd)
        elif k == "ascat_dir":
            parts.append(dirn)
        elif k == "land":
            parts.append(land.astype(np.uint8))
        else:
            parts.append(D.quant(m[k], off, sc))
    tmp = out / (cid + ".tmp")
    tmp.write_bytes(b"".join(p.tobytes() for p in parts))
    tmp.replace(out / (cid + ".bin"))
    WORK.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(WORK / (cid + ".npz"), **{k: v.astype(np.float32) for k, v in m.items()})
    tmp = WORK / (cid + ".tmp")
    tmp.write_text(json.dumps(rec))
    tmp.replace(WORK / (cid + ".json"))
    return "ok"


def _safe(r, out):
    try:
        return one(r, out)
    except Exception as e:
        return "error %r" % e


def finish(rec):
    """Work record -> manifest case: mark the case low's system fronts ("sys"), the ring radius ("sys_r_nm") and
    the hints of the system's non-trough front types (from the case's saved maps). The fronts are cut again from the
    coded analysis (curved through the coded points, FL.clip_fronts), so a change of the truth needs no new fields.
    Returns (record, None), or (None, reason) when the system has under FL.SYS_MIN_NM of non-trough front ("short") or,
    for an analysis before FL.COVERAGE_FULL_FROM, a system front ends at WPC's old map edge ("edge")."""
    valid = dt.datetime.strptime(rec["src"].split()[0], "%Y%m%d%H")
    a = fronts.analysis(valid)
    if a is not None:
        rec["fronts"] = FL.clip_fronts(FL.merged(a), rec["lat0"], rec["lon0"], NY, NX, RES)
    rec["sys_r_nm"] = FL.mark_system(rec["fronts"], rec["low"]["lat"], rec["low"]["lon"])
    if FL.sys_length_nm(rec["fronts"]) < FL.SYS_MIN_NM:
        return None, "short"
    if valid < FL.COVERAGE_FULL_FROM and FL.edge_clipped(rec["fronts"]):
        return None, "edge"
    if FL.basin_edge_clipped(rec["fronts"], rec["basin"]):      # a system front ends at 180 or 1W, where the coded analysis stops
        return None, "edge"
    if not any(f["sys"] and f["type"] in FL.DRAWN for f in rec["fronts"]):
        return None, "short"                                    # only a stationary front left: nothing for the trainee to draw
    with np.load(WORK / (rec["id"] + ".npz")) as z:
        m = {k: z[k].astype(float) for k in z.files}
    pts_by_type = {}
    for f in rec["fronts"]:
        if f["sys"] and f["type"] in FL.NON_TROUGH:
            pts_by_type.setdefault(f["type"], []).append(f["pts"])
    rec["hints"] = {}
    for typ in FL.NON_TROUGH:
        if typ in pts_by_type:
            h = FL.hint(typ, pts_by_type[typ], m, rec["lat0"], rec["lon0"])
            if h:
                rec["hints"][typ] = h
    return rec, None


def manifest(rows, out):
    cases, dropped, edge = [], [], []
    gone = _dropped()
    for r in rows:
        p = WORK / (r["id"] + ".json")
        if not p.exists() or not (out / (r["id"] + ".bin")).exists():
            continue
        rec, why = finish(json.loads(p.read_text()))
        if rec is None:
            (edge if why == "edge" else dropped).append(r["id"])
            gone[r["id"]] = "%s %s %s" % (r["valid"], r["lat"], r["lon"])
            continue
        gone.pop(r["id"], None)
        rec.pop("ascat_cover", None)
        rec.pop("src", None)
        for k in ("am", "ir"):                       # a picture the case no longer uses
            if rec["img"] != k and (out / ("%s_%s.jpg" % (r["id"], k))).exists():
                (out / ("%s_%s.jpg" % (r["id"], k))).unlink()
        cases.append(rec)
    m = {"version": 1, "res": RES, "ny": NY, "nx": NX,
         "fields": [{"key": k, "name": n, "units": u, "offset": o, "scale": s} for k, n, u, o, s in FIELDS],
         "cases": cases}
    (out / "manifest.json").write_text(json.dumps(m, separators=(",", ":")))
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "dropped.json").write_text(json.dumps(gone))
    keep = {c["id"] for c in cases}
    for f in list(out.glob(ID_PREFIX + "*")):        # files of cases dropped from the deck
        if f.name.split(".")[0].split("_")[0] not in keep:
            f.unlink()
    with open(ROOT / "key.csv", "w", newline="") as f:      # never published
        w = csv.writer(f)
        w.writerow(["id", "valid", "basin", "lat", "lon", "hpa", "types", "lengths_nm"])
        for r in rows:
            if r["id"] in keep:
                w.writerow([r["id"], r["valid"], r["basin"], r["lat"], r["lon"], r["hpa"], r["types"], r["lengths_nm"]])
    return len(cases), dropped, edge


def rehint(out):
    """Rewrite hints in out/manifest.json from each case's own .bin (FL.hint: weak signals are not quoted). Reads local
    files only; fronts, fields and imagery are not touched. Prints how many hints changed."""
    p = out / "manifest.json"
    m = json.loads(p.read_text())
    ix = {f["key"]: (k, f) for k, f in enumerate(m["fields"])}
    ny, nx, n, changed = m["ny"], m["nx"], 0, 0
    for c in m["cases"]:
        if not c.get("hints"):
            continue
        raw = np.frombuffer((out / (c["id"] + ".bin")).read_bytes(), np.uint8)
        fld = {}
        for key in ("msl", "te850", "u10", "v10"):
            k, f = ix[key]
            b = raw[k * ny * nx:(k + 1) * ny * nx].reshape(ny, nx)
            fld[key] = np.where(b == 255, np.nan, f["offset"] + f["scale"] * b)
        for typ in list(c["hints"]):
            pts = [f["pts"] for f in c["fronts"] if f.get("sys", True) and f["type"] == typ]
            h = FL.hint(typ, pts, fld, c["lat0"], c["lon0"]) if pts else None
            n += 1
            if h != c["hints"][typ]:
                changed += 1
            if h:
                c["hints"][typ] = h
            else:
                del c["hints"][typ]
    p.write_text(json.dumps(m, separators=(",", ":")))
    print("rehinted %d hints in %s: %d changed" % (n, p, changed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "deck"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rehint", action="store_true", help="no downloads, no rebuild: rewrite the hints of the deck's manifest from the cases' own .bin (weak signals not quoted)")
    ap.add_argument("--manifest-only", action="store_true", help="no downloads: write the manifest from the cases already built")
    a = ap.parse_args()
    out = Path(a.out)
    if a.rehint:
        return rehint(out)
    out.mkdir(parents=True, exist_ok=True)
    _patch_abi_bytes()
    for name in ("key.csv",):                        # the first deck's key stays as key_v1.csv
        if (out / "manifest.json").exists() and (ROOT / name).exists() and not (ROOT / "key_v1.csv").exists():
            (ROOT / "key_v1.csv").write_bytes((ROOT / name).read_bytes())
            (out / "manifest_v1.json").write_bytes((out / "manifest.json").read_bytes())
    rows = list(csv.DictReader(open(ROOT / "picked.csv")))
    todo = rows[:a.limit] if a.limit else rows
    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for r, res in zip([] if a.manifest_only else todo, [] if a.manifest_only else ex.map(lambda r: _safe(r, out), todo)):
            n += 1
            if res != "skip":
                print(n, len(todo), r["id"], res, "gfs %.2f GB abi %.2f GB" % (_bytes["gfs"] / 1e9, _bytes["abi"] / 1e9), flush=True)
    ids = {r["id"] for r in rows}
    for f in list(out.glob(ID_PREFIX + "*")):        # files of cases no longer picked
        if f.name.split(".")[0].split("_")[0] not in ids:
            f.unlink()
    k, dropped, edge = manifest(todo, out)
    print("manifest", k, "cases; dropped (system under %d nm of non-trough front):" % FL.SYS_MIN_NM, dropped)
    print("dropped, a system front ends at the edge of the coded analysis (180, 1W): %d" % len(edge), edge)
    print("streamed this run: GFS %.2f GB, GOES ABI %.2f GB" % (_bytes["gfs"] / 1e9, _bytes["abi"] / 1e9))


if __name__ == "__main__":
    main()
