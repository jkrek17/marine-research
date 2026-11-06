#!/usr/bin/env python3
"""Write a tiny synthetic test deck (manifest.json + 3 x <id>.bin + imagery JPEGs) in the deck format of
../design.md ("Deck format"), so the page can be tried without data. The fields are made up (an idealised low,
cold/warm/occluded/stationary fronts, a theta-e jump across each cold front, a tendency dipole, a jet); they are
for testing the page only.

Run: python3 make_test_deck.py [outdir]   (default: testdeck/ next to this file; NOT deck/, the real deck).
To try the page, serve a folder holding index.html, app.js, style.css and this output as deck/.

Cases:
  t0001  one cold front (+ a trough, which is never scored, + a warm front of ANOTHER system far outside the ring:
         "sys": false, greyed at the reveal, never scored), imagery "am", no ASCAT
  t0002  occluded + cold + warm meeting at a triple point, imagery "ir", no ASCAT
  t0003  stationary + cold, no imagery (img null), ASCAT barbs
  t0004  North Pacific (basin "npac"), the box straddles 180: occluded + cold + warm + a given stationary front, imagery "ir"
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ImportError:  # without Pillow the deck has no imagery (img null everywhere)
    Image = None

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "testdeck"
NY, NX, RES = 51, 81, 0.5
FIELDS = [  # key, name, units, offset, scale   (order is the contract)
    ("msl", "Mean sea level pressure", "hPa", 930.0, 0.5),
    ("thk", "1000-500 hPa thickness", "dam", 470.0, 0.5),
    ("u10", "10 m wind, u", "m/s", -40.0, 0.32),
    ("v10", "10 m wind, v", "m/s", -40.0, 0.32),
    ("te850", "850 hPa theta-e", "K", 240.0, 0.5),
    ("te700", "700 hPa theta-e", "K", 240.0, 0.5),
    ("dp3", "3 h MSLP change", "hPa", -12.7, 0.1),
    ("wspd250", "250 hPa wind speed", "kt", 0.0, 1.0),
    ("ascat_spd", "ASCAT wind speed", "kt", 0.0, 1.0),
    ("ascat_dir", "ASCAT wind direction (from)", "deg", 0.0, 2.0),
    ("land", "Land", "0/1", 0.0, 1.0),
]
STEP_NM = 25.0

CASES = [
    {"id": "t0001", "lat0": 62.0, "lon0": 300.0, "img": "am", "ascat": False,
     "lows": [(49.0, 318.0, 988)],
     "fronts": [("cold", [(47.5, 318.5), (44.0, 316.5), (40.5, 317.0), (38.5, 319.0)]),
                ("trough", [(52.0, 322.0), (55.0, 325.0), (58.0, 326.0)]),
                ("warm", [(61.0, 301.0), (60.5, 304.0), (60.0, 307.0)], False)]},
    {"id": "t0002", "lat0": 62.0, "lon0": 300.0, "img": "ir", "ascat": False,
     "lows": [(50.0, 320.0, 976)],
     "fronts": [("occluded", [(50.3, 320.3), (52.0, 322.5), (53.5, 325.0)]),
                ("cold", [(53.5, 325.0), (51.0, 327.0), (46.0, 325.0), (41.0, 322.5)]),
                ("warm", [(53.5, 325.0), (54.0, 329.0), (55.0, 333.0), (55.5, 337.0)])]},
    {"id": "t0003", "lat0": 62.0, "lon0": 300.0, "img": None, "ascat": True,
     "lows": [(46.0, 330.0, 1002)],
     "fronts": [("stationary", [(44.0, 322.0), (43.5, 328.0), (44.0, 334.0), (44.5, 338.0)]),
                ("cold", [(45.0, 330.5), (42.0, 329.0), (39.0, 330.0)])]},
    {"id": "t0004", "lat0": 62.0, "lon0": 170.0, "img": "ir", "ascat": False, "basin": "npac",
     "lows": [(50.0, 195.0, 984)],
     "fronts": [("occluded", [(50.3, 195.3), (52.0, 197.5), (53.5, 200.0)]),
                ("cold", [(53.5, 200.0), (51.0, 202.0), (46.0, 200.0), (41.0, 197.5)]),
                ("warm", [(53.5, 200.0), (54.0, 204.0), (55.0, 208.0)]),
                ("stationary", [(50.0, 193.0), (49.0, 188.0), (49.5, 183.0)])]},
]
HINTS = {
    "cold": "Winds veer across it and theta-e drops about 12 K behind it (test numbers).",
    "warm": "Winds back ahead of it; the cloud shield thickens toward the front (test numbers).",
    "occluded": "The 700 hPa theta-e ridge wraps from the warm sector into the low (test numbers).",
    "stationary": "Isobars run along the line and the wind is parallel to it (test numbers).",
    "trough": "A kink in the isobars with no thermal gradient (test numbers).",
}


def densify(pts, step=STEP_NM):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        d = math.hypot((b[0] - a[0]) * 60.0, (b[1] - a[1]) * 60.0 * math.cos(math.radians((a[0] + b[0]) / 2)))
        n = max(1, int(math.ceil(d / step)))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


def nm(la1, lo1, la2, lo2):
    """Great-circle distance, nm."""
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 3440.07 * math.asin(math.sqrt(a))


def q(v, off, sc):
    b = np.round((v - off) / sc)
    b = np.clip(b, 0, 254)
    b[~np.isfinite(v)] = 255
    return b.astype(np.uint8)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def build(case, rng):
    lat0, lon0 = case["lat0"], case["lon0"]
    lat = lat0 - np.arange(NY)[:, None] * RES + 0 * np.arange(NX)[None, :]
    lon = lon0 + np.arange(NX)[None, :] * RES + 0 * np.arange(NY)[:, None]
    ll, lo, hp = case["lows"][0]
    dy = (lat - ll) * 111.2
    dx = (lon - lo) * 111.2 * np.cos(np.radians(lat))
    r = np.hypot(dx, dy)
    depth = 1018 - hp
    g = np.exp(-(r / 650.0) ** 2)
    g2 = np.exp(-(r / 1100.0) ** 2)
    # longitude of the cold front as a function of latitude (low's own longitude if none)
    cold = [fr[1] for fr in case["fronts"] if fr[0] == "cold"]
    if cold:
        c = sorted(cold[0])
        clon = np.interp(lat, [p[0] for p in c], [p[1] for p in c])
    else:
        clon = np.full_like(lat, lo)
    warm = sigmoid((lon - clon) * 111.2 * np.cos(np.radians(lat)) / 70.0)   # 0 behind the cold front, 1 ahead
    f = {}
    f["msl"] = 1018 - 0.12 * (lat - 45) - depth * g
    f["thk"] = 540 - 1.4 * (lat - 45) + 6 * (warm - 0.5) - 3 * g2
    spd = 8 + 0.9 * depth * np.exp(-((r - 350) / 400.0) ** 2)            # m/s, peaks in a ring round the low
    rr = r + 1.0
    f["u10"] = np.clip(-spd * dy / rr * 0.92 + spd * (-dx / rr) * 0.38, -39, 40)   # cyclonic + some inflow
    f["v10"] = np.clip(spd * dx / rr * 0.92 + spd * (-dy / rr) * 0.38, -39, 40)
    f["te850"] = 281 - 0.8 * (lat - 45) + 13 * warm + 2.0 * rng.normal(0, 0.15, lat.shape)
    f["te700"] = 276 - 0.4 * (lat - 45) + 7 * sigmoid((lon - clon - 3.0) * 111.2 * 0.65 / 120.0) * np.exp(-((lat - ll - 2) / 9.0) ** 2)
    f["dp3"] = (-5.0 * np.exp(-(((dx - 300) ** 2 + dy ** 2) / 500.0 ** 2)) + 4.0 * np.exp(-(((dx + 400) ** 2 + dy ** 2) / 500.0 ** 2)))
    f["wspd250"] = 40 + (55 + 0.8 * depth) * np.exp(-((lat - (ll - 5)) / 6.0) ** 2) * (0.7 + 0.3 * np.cos(np.radians((lon - lo) * 6)))
    land = ((lon % 360) < (lon0 % 360) + 3 + 2.0 * np.sin(np.radians(lat * 14))).astype(np.uint8)
    land |= ((lat < 41) & ((lon % 360) > (lon0 % 360) + 34)).astype(np.uint8)
    # ASCAT: two diagonal swath bands where the case has ascat
    if case["ascat"]:
        seen = (np.abs((lon - lon0) * 0.9 - (lat0 - lat) * 0.6 - 24) < 9) | (np.abs((lon - lon0) * 0.9 - (lat0 - lat) * 0.6 - 52) < 9)
        seen &= land == 0
        u, v = f["u10"], f["v10"]
        sp_kt = 1.944 * np.hypot(u, v) * 1.08 + rng.normal(0, 1.0, lat.shape)
        frm = (np.degrees(np.arctan2(-u, -v)) % 360)
        a_spd = np.where(seen, np.round(np.clip(sp_kt, 0, 120)), 255).astype(np.uint8)
        a_dir = np.where(seen, np.round(frm / 2.0), 255).astype(np.uint8)
    else:
        a_spd = np.full(lat.shape, 255, np.uint8)
        a_dir = np.full(lat.shape, 255, np.uint8)
    blobs = []
    for k, _n, _u, off, sc in FIELDS:
        if k == "ascat_spd":
            blobs.append(a_spd)
        elif k == "ascat_dir":
            blobs.append(a_dir)
        elif k == "land":
            blobs.append(land.astype(np.uint8))
        else:
            blobs.append(q(f[k], off, sc))
    return b"".join(a.tobytes() for a in blobs), land


def sat_image(case, kind, rng):
    """Synthetic picture over the cell-edge extent, 250 x 400 px, row 0 north (0.1 deg per px)."""
    h, w = 250, 400
    lat0, lon0 = case["lat0"], case["lon0"]
    la = lat0 + RES / 2 - (np.arange(h)[:, None] + 0.5) * (NY * RES / h) + 0 * np.arange(w)[None, :]
    lo = lon0 - RES / 2 + (np.arange(w)[None, :] + 0.5) * (NX * RES / w) + 0 * np.arange(h)[:, None]
    ll, lol, hp = case["lows"][0]
    dy = (la - ll) * 111.2
    dx = (lo - lol) * 111.2 * np.cos(np.radians(la))
    rr = np.hypot(dx, dy) + 1
    th = np.arctan2(dy, dx)
    cloud = np.clip(0.5 + 0.5 * np.cos(2 * th - rr / 250.0), 0, 1) * np.exp(-(rr / (800 + 6 * (1018 - hp))) ** 2)
    cloud = np.clip(cloud + rng.normal(0, 0.04, cloud.shape), 0, 1)
    if kind == "ir":
        gr = np.clip(60 + 190 * cloud, 0, 255)
        arr = np.stack([gr, gr, gr], -1)
    else:
        dry = np.exp(-(((lo - lol) + 6) * 111 * 0.65 / 500) ** 2) * np.exp(-((la - ll + 2) / 5) ** 2)
        arr = np.stack([60 + 180 * dry + 60 * cloud, 150 - 80 * dry + 60 * cloud, 90 + 90 * (1 - dry) + 60 * cloud], -1)
        arr = np.clip(arr + 100 * (cloud[..., None] > 0.8), 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(11)
    cases = []
    for c in CASES:
        blob, _land = build(c, rng)
        (OUT / (c["id"] + ".bin")).write_bytes(blob)
        img = c["img"] if Image is not None else None
        if img:
            sat_image(c, img, rng).save(OUT / ("%s_%s.jpg" % (c["id"], img)), quality=80)
        types = []
        fr = []
        r = 0.0
        for t, pts, *rest in c["fronts"]:
            d = densify(pts)
            sysf = rest[0] if rest else True
            fr.append({"type": t, "pts": [[round(a, 3), round(b, 3)] for a, b in d], "sys": sysf})
            if sysf:
                r = max([r] + [nm(c["lows"][0][0], c["lows"][0][1], a, b) for a, b in d])
                if t not in types:
                    types.append(t)
        lows = [{"lat": a, "lon": b, "hpa": h} for a, b, h in c["lows"]]
        cases.append({"id": c["id"], "basin": c.get("basin", "natl"), "lat0": c["lat0"], "lon0": c["lon0"], "low": lows[0], "lows": lows,
                      "sys_r_nm": min(900, round(r + 60)),
                      "fronts": fr, "img": img, "ascat": bool(c["ascat"]),
                      "hints": {t: HINTS[t] for t in types}})
    man = {"version": 1, "res": RES, "ny": NY, "nx": NX,
           "fields": [{"key": k, "name": n, "units": u, "offset": o, "scale": s} for k, n, u, o, s in FIELDS],
           "cases": cases}
    (OUT / "manifest.json").write_text(json.dumps(man))
    print("wrote", len(cases), "cases to", OUT)


if __name__ == "__main__":
    main()
