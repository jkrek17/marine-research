#!/usr/bin/env python3
"""Write a synthetic test deck (manifest + 12 .bin) into page/deck/ in the format of ../design.md.
Fields are made up (a low with circular isobars, a jet, a trough); they are for testing the page only.
Run: python3 make_test_deck.py [outdir]   (default: testdeck/ next to this file; NOT deck/, which is the real deck).
To try the page, serve a copy of it whose deck/ is this folder."""
import json
from pathlib import Path
import numpy as np
try:
    from PIL import Image
except ImportError:  # no Pillow: the deck has no satellite images (flags false)
    Image = None

HERE = Path(__file__).resolve().parent
import sys
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "testdeck"   # never page/deck/ (the real deck)
NY, NX, RES = 51, 81, 0.5
FIELDS = [  # key, name, units, offset, scale
    ("msl", "Mean sea level pressure", "hPa", 940.0, 0.5),
    ("thk", "1000-500 hPa thickness", "dam", 460.0, 1.0),
    ("z500", "500 hPa height", "dam", 440.0, 0.5),
    ("vort500", "500 hPa absolute vorticity", "1e-5 /s", 0.0, 0.25),
    ("z250", "250 hPa height", "dam", 900.0, 1.0),
    ("wspd250", "250 hPa wind speed", "kt", 0.0, 1.0),
    ("eady", "Eady growth rate 850-500 hPa", "/day", 0.0, 0.02),
    ("z850", "850 hPa height", "dam", 80.0, 0.25),
    ("t850", "850 hPa temperature", "C", -50.0, 0.25),
    ("tadv850", "850 hPa temperature advection", "K/day", -40.0, 0.5),
    ("sst_air", "Sea minus 2 m air temperature", "K", -20.0, 0.25),
]


def q(v, off, sc):
    b = np.round((v - off) / sc)
    b = np.clip(b, 0, 254)
    b[~np.isfinite(v)] = 255
    return b.astype(np.uint8)


def snapshot(lat0, lon0, low, peak, depth, rng, land):
    lat = lat0 - np.arange(NY)[:, None] * RES + 0 * np.arange(NX)[None, :]
    lon = lon0 + np.arange(NX)[None, :] * RES + 0 * np.arange(NY)[:, None]
    dy = (lat - low[0]) * 111.2
    dx = (lon - low[1]) * 111.2 * np.cos(np.radians(lat))
    r = np.hypot(dx, dy)
    g = np.exp(-(r / 600.0) ** 2)
    g2 = np.exp(-(r / 1000.0) ** 2)
    f = {}
    f["msl"] = 1018 - 0.15 * (lat - 45) - depth * g
    f["thk"] = 556 - 1.5 * (lat - 40) - 6 * g2 + 4 * np.exp(-(((lon - low[1]) - 12) * 111 * 0.65 / 700) ** 2) * 0
    f["z500"] = 580 - 1.9 * (lat - 40) - 0.45 * depth * g2 + 2 * np.sin(np.radians(lon * 9))
    f["vort500"] = 12 + 5 * np.sin(np.radians(lat * 6)) + 0.9 * depth * g2 * 0.6 + rng.normal(0, 0.3, lat.shape)
    f["z250"] = 1010 - 3.0 * (lat - 40) - 0.6 * depth * g2
    jetlat = low[0] - 6
    f["wspd250"] = 35 + (60 + 1.2 * depth) * np.exp(-((lat - jetlat) / 6.0) ** 2) * (0.7 + 0.3 * np.cos(np.radians((lon - low[1]) * 6)))
    f["eady"] = 0.35 + 1.0 * np.exp(-((lat - low[0] + 3) / 7.0) ** 2) * (0.6 + 0.01 * depth)
    f["z850"] = 128 - 0.6 * (lat - 45) - 0.18 * depth * g
    f["t850"] = 12 - 0.75 * (lat - 40) - 3 * np.cos(np.radians((lon - low[1]) * 12)) * g2
    f["tadv850"] = 9 * np.sin(np.radians((lon - low[1]) * 11)) * np.exp(-(r / 900.0) ** 2) * (0.5 + depth / 40)
    f["sst_air"] = 4 - 0.25 * (lat - 45) + 3 * np.sin(np.radians(lon * 4)) * 0.5 + rng.normal(0, 0.2, lat.shape)
    out = []
    for k, _n, _u, off, sc in FIELDS:
        v = f[k].copy()
        v[land == 1] = np.nan if k in ("sst_air",) else v[land == 1]
        out.append(q(v, off, sc))
    # ASCAT: two diagonal swath bands, wind peaks near the low
    seen = (np.abs((lon - lon0) * 0.9 - (lat0 - lat) * 0.6 - 18) < 8) | (np.abs((lon - lon0) * 0.9 - (lat0 - lat) * 0.6 - 50) < 9)
    seen &= land == 0
    base = 11 + (peak - 11) * np.exp(-(r / 380.0) ** 2) + rng.normal(0, 1.2, lat.shape)
    spd = np.where(seen, np.clip(base, 0, 100), np.nan)
    # cyclonic flow, some inflow (wind blows toward tangent CCW rotated inward)
    tx, ty = -dy, dx            # CCW tangent (east, north)
    ix, iy = -dx, -dy           # inward
    n = np.hypot(tx, ty) + 1e-6
    ux = (tx / n) * 0.9 + (ix / (np.hypot(ix, iy) + 1e-6)) * 0.35
    uy = (ty / n) * 0.9 + (iy / (np.hypot(ix, iy) + 1e-6)) * 0.35
    to = np.degrees(np.arctan2(ux, uy)) % 360
    frm = (to + 180) % 360
    dirb = np.where(seen, np.round(frm / 2), 255).astype(np.uint8)
    spdb = np.where(seen, np.round(spd), 255).astype(np.uint8)
    return b"".join(a.tobytes() for a in out) + spdb.tobytes() + dirb.tobytes() + land.astype(np.uint8).tobytes()


def sat_images(la0, lo0, low, depth, rng, kind):
    """Synthetic satellite picture over the cell-edge extent (2x2 px per 0.5 deg cell), rows north to south."""
    h, w = NY * 2, NX * 2
    lat = la0 + RES / 2 - (np.arange(h)[:, None] + 0.5) * RES / 2 + 0 * np.arange(w)[None, :]
    lon = lo0 - RES / 2 + (np.arange(w)[None, :] + 0.5) * RES / 2 + 0 * np.arange(h)[:, None]
    dy = (lat - low[0]) * 111.2
    dx = (lon - low[1]) * 111.2 * np.cos(np.radians(lat))
    r = np.hypot(dx, dy) + 1
    th = np.arctan2(dy, dx)
    cloud = np.clip(0.5 + 0.5 * np.cos(2 * th - r / 250.0), 0, 1) * np.exp(-(r / (700 + 8 * depth)) ** 2)
    cloud = np.clip(cloud + rng.normal(0, 0.04, cloud.shape), 0, 1)
    if kind == "ir":
        g = np.clip(60 + 190 * cloud, 0, 255)
        arr = np.stack([g, g, g], -1)
    else:
        dry = np.exp(-(((lon - low[1]) + 6) * 111 * 0.65 / 500) ** 2) * np.exp(-((lat - low[0] + 2) / 5) ** 2)
        arr = np.stack([60 + 180 * dry + 20 * cloud * 255 / 255, 150 - 80 * dry + 60 * cloud, 90 + 120 * (1 - dry) * (lat < low[0] - 6) + 60 * cloud], -1)
        arr = np.clip(arr + 120 * cloud[..., None] * np.array([1, 1, 1]) * (cloud[..., None] > 0.8), 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


ING = [  # key, name, units, cuts, favour, signal, verdict
    ("eady", "Eady growth", "per day", [0.8, 1.2], 1, 18.2, "strong"),
    ("jet", "250 mb jet", "kt", [80, 110], 1, 12.0, "weak"),
    ("pva", "Vorticity advection", "1e-9 /s2", [-2, 4], 1, 16.5, "strong"),
    ("tilt", "Tilt to 500 mb low", "km", [150, 400], -1, 9.0, "weak"),
    ("warm_adv", "Warm advection 850", "K/day", [1.5, 4], 1, 3.0, "none"),
    ("thk_grad", "Thickness gradient", "dam/1000 km", [6, 10], 1, 14.1, "weak"),
    ("sea_air", "Sea minus air", "K", [1, 4], 1, 17.0, "strong"),
    ("dry", "Dry air-mass signal", "index", [0.2, 0.5], 1, 6.0, "none"),
    ("peak0", "Peak wind now", "kt", [30, 45], -1, 20.0, "strong"),
]


def fake_ing(rng):
    out = {"jet_pos": str(rng.choice(["left exit", "right entrance", "other", "weak jet"]))}
    for k, _n, _u, cuts, _f, _s, _v in ING:
        if k == "dry" and rng.random() < 0.3:
            continue
        t = int(rng.integers(0, 3))
        v = [cuts[0] * 0.6, (cuts[0] + cuts[1]) / 2, cuts[1] * 1.4][t]
        out[k] = [round(float(v), 2), t]
    return out


def fake_ingredients():
    items = []
    for k, n, u, cuts, fav, sig, ver in ING:
        g = [28 - fav * sig / 2, 31, 28 + fav * sig / 2]
        items.append({"key": k, "name": n, "units": u, "n": 1004, "cuts": cuts,
                      "grow": [round(x, 1) for x in g], "decay": [round(55 - x, 1) for x in g],
                      "dp": [round(-1 - fav * x / 10, 1) for x in (-1, 0, 1)],
                      "signal": sig, "lo": sig - 8, "hi": sig + 8, "verdict": ver, "favour": fav})
    jp = {n: {"n": 100 + 20 * i, "grow": 25 + 8 * i, "decay": 40 - 6 * i, "dp": -1.0 - i} for i, n in enumerate(["left exit", "right entrance", "other", "weak jet"])}
    return {"n": 1004, "days": 300, "base_grow": 30.1, "base_decay": 25.0, "ingredients": items, "jet_pos": jp}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    cases = []
    spec = [  # basin, lat0, lon0, low0(lat,lon), peak0, low24, peak24, hpa0, hpa24
        ("natl", 62, 300, (48, 318), 52, (53, 326), 66, 1002, 984),
        ("natl", 62, 300, (45, 322), 38, (50, 330), 44, 1000, 996),
        ("natl", 62, 300, (50, 315), 30, (54, 324), 36, 1008, 1004),
        ("natl", 62, 300, (47, 320), 66, (52, 328), 55, 980, 988),
        ("natl", 62, 300, (49, 316), 45, (55, 326), 70, 996, 972),
        ("natl", 62, 300, (46, 324), 28, (50, 331), 30, 1010, 1006),
        ("npac", 58, 150, (42, 165), 58, (46, 175), 50, 990, 978),
        ("npac", 58, 150, (44, 168), 36, (49, 176), 52, 1000, 990),
        ("npac", 58, 150, (40, 163), 70, (45, 172), 68, 972, 966),
        ("natl", 60, 340, (45, 356), 40, (49, 366), 33, 998, 1002),
        ("npac", 58, 170, (43, 186), 25, (47, 195), 41, 1004, 998),
        ("natl", 62, 300, (51, 318), 50, (55, 327), 49, 994, 992),
    ]
    cat = lambda p: 3 if p >= 64 else 2 if p >= 48 else 1 if p >= 34 else 0
    for i, (b, la0, lo0, p0, k0, p24, k24, h0, h24) in enumerate(spec):
        lat = la0 - np.arange(NY)[:, None] * RES + 0 * np.arange(NX)[None, :]
        lon = lo0 + np.arange(NX)[None, :] * RES + 0 * np.arange(NY)[:, None]
        land = ((lon % 360) < (lo0 % 360) + 4 + 2.5 * np.sin(np.radians(lat * 14))).astype(np.uint8)
        land |= ((lat > la0 - 4) & ((lon % 360) < (lo0 % 360) + 14)).astype(np.uint8)
        cid = "c%04d" % (i + 1)
        blob = snapshot(la0, lo0, p0, k0, 1018 - h0, rng, land) + snapshot(la0, lo0, p24, k24, 1018 - h24, rng, land)
        (OUT / (cid + ".bin")).write_bytes(blob)
        flags = {}
        for snap, lowpos, hp in (("t0", p0, h0), ("t24", p24, h24)):
            fl = {}
            for kind in ("ir", "am"):
                ok = Image is not None and not (kind == "am" and i == 2) and not (kind == "ir" and i == 4 and snap == "t24")
                if ok:
                    sat_images(la0, lo0, lowpos, 1018 - hp, rng, kind).save(OUT / ("%s_%s_%s.jpg" % (cid, snap, kind)), quality=80)
                fl[kind] = bool(ok)
            flags[snap] = fl
        ing = fake_ing(rng) if i != 5 else None   # case 6 has no ing
        cases.append({"id": cid, "basin": b, "lat0": float(la0), "lon0": float(lo0),
                      "t0": {"lat": p0[0], "lon": p0[1], "hpa": h0, "cat": cat(k0), "peak": float(k0), "cover": 0.7, **flags["t0"]},
                      "t24": {"lat": p24[0], "lon": p24[1], "hpa": h24, "cat": cat(k24), "peak": float(k24), "cover": 0.6, **flags["t24"]}, **({"ing": ing} if ing else {})})
    man = {"version": 1, "res": RES, "ny": NY, "nx": NX,
           "fields": [{"key": k, "name": n, "units": u, "offset": o, "scale": s} for k, n, u, o, s in FIELDS],
           "ingredients": fake_ingredients(),
           "cases": cases}
    (OUT / "manifest.json").write_text(json.dumps(man))
    print("wrote", len(cases), "cases to", OUT)


if __name__ == "__main__":
    main()
