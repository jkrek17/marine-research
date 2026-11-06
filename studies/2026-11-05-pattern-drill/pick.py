"""Pattern drill, step 2: pick the deck from the per-time low lists of find_cases.py.

A candidate = a low at T that ASCAT saw well (see good(): cover >= COVER, or COVER_STRONG at storm force;
at least MIN_SEEN cells) and that the
GFS-analysed lows follow (rk.storm_read.follow, 6 h steps) to T + 24 h, where ASCAT also saw it well.
With --scene (version 2, Jason 2026-11-05) the category is the strongest wind in the whole map box (scene.py)
and only lows that are the deepest in the box at both times are kept. Without it:
Category of each snapshot from peak3 (3rd highest ASCAT cell in the low's own pressure basin, up to 1000 km;
version 1 used 500 km nearest-low): 0 < 34 kt, 1 gale 34-47,
2 storm 48-63, 3 HF 64+. The deck is balanced on the +24 h category (N/4 each, as far as the class
allows; the rest goes to the other classes), the same low at most once in any 48 h, seeded.

    python3 pick.py [--n 200] [--seed 1] [--find find2] [--keep key.csv]
        -> key.csv beside the find folders (rk.paths.data extra/pattern-drill)

--keep re-keys an earlier deck instead of starting over: its cases that are still candidates keep their ids
(new categories from the new truth), and only the gaps are filled with new picks (ids after the highest).
The old key is first copied to key_v1.csv if that does not exist.

--strong N (Jason 2026-11-06, the "Storm or HF?" game) then adds up to N more lows that are storm force or
stronger at T or T + 24 h, HF first, same clash rule, marked pool=hf in key.csv: the page shows them only in
Storm or HF?, so the other games keep their balanced mix. An earlier key's pool column is kept.
"""
import argparse
import csv
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rk import paths, storm_read  # noqa: E402
from rk.storm_read import follow, km  # noqa: E402

storm_read.STEP_KM = 500.0   # stricter than the storm read's 800 km per 6 h, so a track never jumps lows

COVER, COVER_STRONG, MIN_SEEN = 0.5, 0.25, 30
LAND_HPA = 1000.0    # scene mode: a centre over land shallower than this is a heat or lee low and is dropped
ROOT = paths.data("extra", "pattern-drill")


def cat(kt):
    return 0 if kt < 34 else 1 if kt < 48 else 2 if kt < 64 else 3


def load(folder="find2"):
    out = {}
    for p in sorted((ROOT / folder).glob("*.json")):
        out[dt.datetime.strptime(p.stem, "%Y%m%d%H")] = json.loads(p.read_text())
    return out


def good(row):
    """ASCAT saw enough of the water around the low to trust the category: half of it, or a quarter when
    what it saw is already storm force (a partial pass can hide a stronger core, never a weaker one)."""
    if row.get("peak3") is None or row.get("n", 0) < MIN_SEEN:
        return False
    return row["cover"] >= (COVER_STRONG if row["peak3"] >= 48 else COVER)


def candidates(rec):
    out = []
    for basin in ("natl", "npac"):
        lows_by_t = {t: np.array([[r["lat"], r["lon"], r["hpa"]] for r in v[basin]["lows"]]).reshape(-1, 3)
                     for t, v in rec.items()}
        rows_by_t = {t: v[basin]["lows"] for t, v in rec.items()}
        for t0, rows in rows_by_t.items():
            t1 = t0 + dt.timedelta(hours=24)
            if t1 not in rows_by_t:
                continue
            for r0 in rows:
                if not good(r0):
                    continue
                tr = follow(lows_by_t, t0, r0["lat"], r0["lon"])
                if not tr or t1 not in tr:
                    continue
                la, lo, _ = tr[t1]
                r1 = min(rows_by_t[t1], key=lambda r: km(r["lat"], r["lon"], la, lo))
                if km(r1["lat"], r1["lon"], la, lo) > 1 or not good(r1):
                    continue
                out.append({"basin": basin, "t0": t0, "t1": t1, "r0": r0, "r1": r1,
                            "c0": cat(r0["peak3"]), "c1": cat(r1["peak3"]),
                            "track": {t: (p[0], p[1]) for t, p in tr.items()}})
    return out


def pick(cands, n, seed, kept=()):
    rng = random.Random(seed)
    rng.shuffle(cands)
    chosen = list(kept)
    have = {c: sum(x["c1"] == c for x in chosen) for c in range(4)}
    ids = {id(x) for x in chosen}
    by = {c: [x for x in cands if x["c1"] == c and id(x) not in ids] for c in range(4)}
    want = {c: max(0, min(len(by[c]) + have[c], n // 4) - have[c]) for c in range(4)}
    n = n - len(chosen)
    spare = n - sum(want.values())
    for c in sorted(range(4), key=lambda c: -len(by[c])):   # the short classes' places go to the others
        extra = min(spare, len(by[c]) - want[c])
        want[c] += extra
        spare -= extra

    def clash(x):
        """Same low (the tracks share a time within 300 km) with start times less than 48 h apart."""
        for y in chosen:
            if y["basin"] != x["basin"] or abs((y["t0"] - x["t0"]).total_seconds()) >= 48 * 3600:
                continue
            for t, (la, lo) in y["track"].items():
                p = x["track"].get(t)
                if p and km(la, lo, p[0], p[1]) < 300:
                    return True
        return False

    for c in (3, 2, 1, 0):          # rarest first, so their tracks win clashes
        got = 0
        for x in by[c]:
            if got >= want[c]:
                break
            if not clash(x):
                chosen.append(x)
                got += 1
    new = chosen[len(kept):]
    rng.shuffle(new)
    return list(kept) + new


def add_strong(cands, deck, n, seed):
    """Up to n more storm-force lows (category 2+ at T or T + 24 h), HF first, never clashing with the deck."""
    rng = random.Random(seed + 1)
    ids = {id(x) for x in deck}
    pool = [x for x in cands if id(x) not in ids and max(x["c0"], x["c1"]) >= 2]
    rng.shuffle(pool)
    pool.sort(key=lambda x: -max(x["c0"], x["c1"]))   # HF first (stable sort keeps the shuffle within a class)
    chosen = list(deck)

    def clash(x):
        for y in chosen:
            if y["basin"] != x["basin"] or abs((y["t0"] - x["t0"]).total_seconds()) >= 48 * 3600:
                continue
            for t, (la, lo) in y["track"].items():
                q = x["track"].get(t)
                if q and km(la, lo, q[0], q[1]) < 300:
                    return True
        return False

    got = 0
    for x in pool:
        if got >= n:
            break
        if not clash(x):
            x["pool"] = "hf"
            chosen.append(x)
            got += 1
    print("storm-force extras (pool=hf):", got, "| HF at either time:", sum(max(x["c0"], x["c1"]) == 3 for x in chosen[len(deck):]))
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--find", default="find2")
    ap.add_argument("--keep", default=None, help="earlier key.csv to re-key (keeps its ids)")
    ap.add_argument("--scene", action="store_true", help="scene answer from scene.json (version 2)")
    ap.add_argument("--strong", type=int, default=0, help="extra storm-force lows for Storm or HF? (pool=hf)")
    a = ap.parse_args()
    cands = candidates(load(a.find))
    if a.scene:
        # version 2: the answer is the scene's strongest wind, and the followed low must be the deepest in the box
        sc = json.loads((ROOT / "scene.json").read_text())
        from rk import fetch
        from rk.basins import grid
        mask = fetch.gfs_mask(dt.datetime(2025, 1, 1))   # land does not move; one analysis is enough

        def heat_low(basin, r):
            """Centre over land (3 x 3 cells of 0.25 deg, mostly land) and not deep: a heat or lee low, not a storm."""
            lats, lons = grid(basin)
            iy, ix = int(np.argmin(abs(lats - r["lat"]))), int(np.argmin(abs(lons - r["lon"])))
            land = mask[basin]["land"][max(0, iy - 1):iy + 2, max(0, ix - 1):ix + 2]
            return land.mean() > 0.5 and r["hpa"] > LAND_HPA

        keep = []
        for x in cands:
            if heat_low(x["basin"], x["r0"]) or heat_low(x["basin"], x["r1"]):
                continue
            v = sc.get("%s|%s|%.2f|%.2f" % (x["basin"], x["t0"].strftime("%Y%m%d%H"), x["r0"]["lat"], x["r0"]["lon"]))
            if not v or not (v["deep_0"] and v["deep_24"]) or v["peak_0"] is None or v["peak_24"] is None:
                continue
            x["scene"] = v
            x["c0"], x["c1"] = cat(v["peak_0"]), cat(v["peak_24"])
            keep.append(x)
        print("candidates", len(cands), "-> deepest low in the scene at both times, no heat lows:", len(keep))
        cands = keep
    kept, next_id = [], 1
    if a.keep:
        import shutil
        if not (ROOT / "key_v1.csv").exists():
            shutil.copy(ROOT / a.keep, ROOT / "key_v1.csv")
        old = list(csv.DictReader(open(ROOT / a.keep)))
        look = {(x["basin"], x["t0"].strftime("%Y%m%d%H"), round(x["r0"]["lat"], 2), round(x["r0"]["lon"], 2)): x
                for x in cands}
        lost = []
        for r in old:
            x = look.get((r["basin"], r["t0"], round(float(r["lat0"]), 2), round(float(r["lon0"]), 2)))
            if x is None:
                lost.append(r["id"])
                continue
            x["id"] = r["id"]
            x["pool"] = r.get("pool", "")
            kept.append(x)
        next_id = max(int(r["id"][1:]) for r in old) + 1
        moved = sum(int(r["cat0"]) != x["c0"] or int(r["cat24"]) != x["c1"]
                    for r in old for x in kept if x["id"] == r["id"])
        print("kept", len(kept), "of", len(old), "| categories changed in", moved, "| no longer candidates:", len(lost))
    tab = np.zeros((4, 4), int)
    for x in cands:
        tab[x["c0"], x["c1"]] += 1
    print("candidates", len(cands), "(rows category at T, columns at T+24)\n", tab)
    deck = pick(cands, a.n, a.seed, kept)
    if a.strong:
        deck = add_strong(cands, deck, a.strong, a.seed)
    for x in deck:
        if "id" not in x:
            x["id"] = "c%04d" % next_id
            next_id += 1
    tab = np.zeros((4, 4), int)
    for x in deck:
        tab[x["c0"], x["c1"]] += 1
    print("deck", len(deck), "natl", sum(x["basin"] == "natl" for x in deck), "\n", tab)
    with open(ROOT / "key.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "basin", "t0", "t24", "lat0", "lon0", "hpa0", "peak0", "cover0", "cat0",
                    "lat24", "lon24", "hpa24", "peak24", "cover24", "cat24", "plat0", "plon0", "plat24", "plon24", "pool"])
        for x in deck:
            r0, r1, v = x["r0"], x["r1"], x.get("scene", {})
            w.writerow([x["id"], x["basin"], x["t0"].strftime("%Y%m%d%H"), x["t1"].strftime("%Y%m%d%H"),
                        r0["lat"], r0["lon"], r0["hpa"], v.get("peak_0", r0["peak3"]), r0["cover"], x["c0"],
                        r1["lat"], r1["lon"], r1["hpa"], v.get("peak_24", r1["peak3"]), r1["cover"], x["c1"],
                        v.get("plat_0", ""), v.get("plon_0", ""), v.get("plat_24", ""), v.get("plon_24", ""), x.get("pool", "")])


if __name__ == "__main__":
    main()
