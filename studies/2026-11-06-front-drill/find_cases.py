"""Front drill, step 1: find and pick the cases (design.md, "Cases").

    python3 find_cases.py [--estimate] [--workers 6] [--n 200]

Atlantic only; 00/06/12/18 UTC, November-March of the winters 2024-25 and 2025-26 plus 13 Aug-4 Nov 2026 (full WPC coverage, lows to 10W). For every analysed low
(rk.fronts, the Unified Surface Analysis as coded by WPC) over open water (GFS land mask) between 25W and
100W and 25-67N with a non-trough front end within 300 km (after merge_segments):
  second_low   no second analysed low within 500 km (kept when none)
  types_match  the low's non-trough front types are the same in the analyses 6 h before and after
  gfs          a GFS f000 MSLP minimum within 150 km of the low and within 4 hPa of its analysed pressure
  day          at most one case per low (tracked across 6 h steps, nearest within 600 km) per UTC day
Writes under rk.paths.data("extra", "front-drill"): candidates.csv (every candidate with the flag of each
filter), picked.csv (about --n cases balanced on front types, winters and months), msl/<YYYYMMDDHH>.npz (small GFS
f000 MSLP crops, the cache that makes the run resumable) and landmask.npy. GFS MSLP is fetched only for lows that
passed the cheaper filters; --estimate prints the bytes that would stream (from the .idx files) and stops.
"""
import argparse
import csv
import datetime as dt
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import frontlib as FL  # noqa: E402
from rk import fetch, fronts, paths  # noqa: E402

OUT = paths.data("extra", "front-drill")
# Periods: two winters in WPC's old (clipped) domain, then the full-coverage months. The new period starts one
# analysis after FL.COVERAGE_FULL_FROM so the 6 h neighbour used by the type filter is also full coverage.
WINTERS = {"2024-25": (dt.datetime(2024, 11, 1), dt.datetime(2025, 3, 31, 18)),
           "2025-26": (dt.datetime(2025, 11, 1), dt.datetime(2026, 3, 31, 18)),
           "2026-fall": (FL.COVERAGE_FULL_FROM + dt.timedelta(hours=6), dt.datetime(2026, 11, 4, 18))}
LAT_MIN, LAT_MAX = 25.0, 67.0
LON_MIN = 260.0                          # 100W
LON_MAX_OF = {"2024-25": 335.0, "2025-26": 335.0, "2026-fall": 350.0}     # 25W; 10W once the coverage is full
GFS_KM, GFS_DP = 150.0, 4.0
CROP = {"lat_n": 70.0, "lon_w": 240.0, "ny": 241, "nx": 480}   # 0.25 deg: 70N-10N, 240-359.75E (the first runs cached 240-345E)
MSL_KEY = {"PRMSL:mean sea level": "msl"}


def synoptic_times(t0, t1):
    out = []
    while t0 <= t1:
        out.append(t0)
        t0 += dt.timedelta(hours=6)
    return out


def crop_of(g):
    r0, c0 = int(round((90 - CROP["lat_n"]) / 0.25)), int(round(CROP["lon_w"] / 0.25))
    return g[r0:r0 + CROP["ny"], c0:c0 + CROP["nx"]]


# ---------------------------------------------------------------- inputs
def load_analyses(days, workers):
    """{valid: analysis} for the synoptic times of the UTC days (text cached by rk.fronts)."""
    def one(d):
        try:
            return [a for a in fronts.day(d) if fronts.synoptic(a["valid"])]
        except Exception as e:  # the day is simply missing from the sample
            print("fronts", d, "error", e, flush=True)
            return []
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, days))
    return {a["valid"]: a for r in res for a in r}


def landmask(valid):
    p = OUT / "landmask480.npy"
    if p.exists():
        return np.load(p)
    g = fetch.gfs_global(valid, 0, {"LAND:surface": "land"})
    if g is None:
        raise RuntimeError("no GFS LAND")
    m = crop_of(g["land"]).astype(np.float32)
    np.save(p, m)
    return m


def _widen(a, fill):
    """A crop cached before the crop grew from 421 to 480 columns, padded east with `fill`."""
    return a if a.shape[1] >= CROP["nx"] else np.pad(a, ((0, 0), (0, CROP["nx"] - a.shape[1])), constant_values=fill)


def ocean_mask(land):
    """Water cells connected to the open Atlantic (drops the Great Lakes and other inland water)."""
    from scipy.ndimage import label
    lab, _ = label(land < 0.5, structure=np.ones((3, 3)))
    y, x = int(round((CROP["lat_n"] - 45.0) / 0.25)), int(round((330.0 - CROP["lon_w"]) / 0.25))
    return lab == lab[y, x]


def is_water(ocean, lat, lon, ice=None):
    """Over open water: GFS land mask (ocean-connected cells only), no sea ice (ICEC < 0.15 when given), and
    not Hudson or James Bay (inside the ocean mask through Hudson Strait, but ice-covered or enclosed)."""
    y = int(round((CROP["lat_n"] - lat) / 0.25))
    x = int(round((lon - CROP["lon_w"]) / 0.25))
    if not (0 <= y < ocean.shape[0] and 0 <= x < ocean.shape[1]) or not ocean[y, x]:
        return False
    if lat >= 51.0 and lon <= 284.0:
        return False
    return ice is None or not ice[y, x] >= 0.15


def ice_file(valid):
    return OUT / "ice" / (valid.strftime("%Y%m%d%H") + ".npz")


def fetch_ice(valid):
    """GFS f000 ICEC crop (fraction) for a valid time, cached -> array or None."""
    p = ice_file(valid)
    if p.exists():
        with np.load(p) as z:
            return _widen(z["ice"], 0.0)
    g = fetch.gfs_global(valid, 0, {"ICEC:surface": "ice"})
    if g is None:
        return None
    m = np.nan_to_num(crop_of(g["ice"]), nan=0.0).astype(np.float16)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".tmp.npz")
    np.savez_compressed(tmp, ice=m)
    tmp.replace(p)
    return m


def msl_file(valid):
    return OUT / "msl" / (valid.strftime("%Y%m%d%H") + ".npz")


def fetch_msl(valid):
    """GFS f000 MSLP (hPa) crop for a valid time -> array or None (cached; a missing time is retried next run)."""
    p = msl_file(valid)
    if p.exists():
        with np.load(p) as z:
            return _widen(z["msl"], 1100.0)
    g = fetch.gfs_global(valid, 0, MSL_KEY)
    if g is None:
        return None
    m = (crop_of(g["msl"]) / 100.0).astype(np.float32)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".tmp.npz")
    np.savez_compressed(tmp, msl=m)
    tmp.replace(p)
    return m


def gfs_check(msl, lat, lon, hpa):
    """Deepest local minimum (13 x 13 window) of the crop within GFS_KM of the low -> (distance km, GFS hPa
    minus analysed hPa), or (None, None) when there is none."""
    from scipy.ndimage import minimum_filter
    la = CROP["lat_n"] - np.arange(msl.shape[0]) * 0.25
    lo = CROP["lon_w"] + np.arange(msl.shape[1]) * 0.25
    LA, LO = np.meshgrid(la, lo, indexing="ij")
    d = FL.km(lat, lon, LA, LO)
    is_min = msl == minimum_filter(msl, size=13, mode="nearest")
    k = is_min & (d <= GFS_KM)
    if not k.any():
        return None, None
    f = np.where(k, msl, np.inf)
    j = np.unravel_index(np.argmin(f), f.shape)
    return float(d[j]), float(msl[j] - hpa)


# ---------------------------------------------------------------- stages
def stage_a(an, ocean, times, winter_of, ice_of=None):
    """Candidates: analysed lows over open water in the region with an attached non-trough front."""
    rows = []
    mem = {}
    for t in times:
        a = an.get(t)
        if a is None:
            continue
        mf = mem.setdefault(t, FL.merged(a))
        for i, (hpa, lat, lon) in enumerate(a["lows"]):
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX_OF[winter_of[t]]) or not is_water(ocean, lat, lon, ice_of(t) if ice_of else None):
                continue
            att = FL.attached(mf, lat, lon)
            if not att:
                continue
            rows.append({"valid": t, "idx": i, "lat": lat, "lon": lon, "hpa": hpa,
                         "types": tuple(sorted({f["type"] for f in att})),
                         "lengths": "|".join("%s:%d" % (f["type"], round(FL.length_nm(f["lat"], f["lon"]))) for f in att),
                         "total_nm": sum(FL.length_nm(f["lat"], f["lon"]) for f in att)})
    return rows


def neighbours(an, t, mem):
    def get(tt):
        a = an.get(tt)
        if a is None:
            return None
        if tt not in mem:
            mem[tt] = FL.merged(a)
        return a["lows"], mem[tt]
    return get(t - dt.timedelta(hours=6)), get(t + dt.timedelta(hours=6))


def estimate(times, n=12):
    """Bytes the MSLP records of `times` would stream, from a sample of .idx files."""
    import nwp
    step = max(1, len(times) // n)
    sizes = []
    for t in times[::step][:n]:
        idx = nwp.ncep_index(fetch.gfs_url(t, 0))
        if idx and "PRMSL:mean sea level" in idx:
            s, e = idx["PRMSL:mean sea level"]
            sizes.append((e - s + 1) if e is not None else 1_000_000)
    return float(np.mean(sizes)) * len(times) if sizes else float("nan"), sizes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--n", type=int, default=200, help="cases to pick when there is no picked.csv yet")
    ap.add_argument("--n-new", type=int, default=60, help="cases to pick from the full-coverage period (old picks are kept)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    times, winter_of = [], {}
    for w, (t0, t1) in WINTERS.items():
        ts = synoptic_times(t0, t1)
        times += ts
        winter_of.update({t: w for t in ts})
    days = sorted({(t + dt.timedelta(hours=h)).date() for t in times for h in (-6, 0, 6)})
    an = load_analyses(days, a.workers)
    print("analyses loaded: %d of %d synoptic times (+neighbours)" % (sum(t in an for t in times), len(times)), flush=True)
    ocean = ocean_mask(landmask(times[0]))

    # sea ice (GFS ICEC, small records) is needed only at times with a low over water and a front end near it
    pre = stage_a(an, ocean, times, winter_of)
    ice_times = sorted({c["valid"] for c in pre})
    ice = {}

    def getice(t):
        try:
            return t, fetch_ice(t)
        except Exception as e:
            print("ice", t, "error", e, flush=True)
            return t, None
    with ThreadPoolExecutor(a.workers) as ex:
        ice.update(dict(ex.map(getice, ice_times)))
    cand = stage_a(an, ocean, times, winter_of, lambda t: ice.get(t))
    print("before the sea-ice and Hudson Bay cut: %d candidates; ice missing at %d of %d times" % (
        len(pre), sum(v is None for v in ice.values()), len(ice_times)))
    n_lows = sum(len(an[t]["lows"]) for t in times if t in an)
    print("analysed lows %d; candidates (open water, 100W to 25W (10W in the full-coverage period), 25-67N, non-trough front end within 300 km): %d" % (n_lows, len(cand)))

    mem = {}
    for c in cand:
        t = c["valid"]
        c["second"] = FL.has_second_low(an[t]["lows"], c["lat"], c["lon"])
        prev, nxt = neighbours(an, t, mem)
        c["match"] = FL.types_match(prev, nxt, c["types"], c["lat"], c["lon"])
        c["gfs_dist"] = c["gfs_dp"] = None
        c["gfs_ok"] = None
    s1 = [c for c in cand if not c["second"]]
    s2 = [c for c in s1 if c["match"]]
    print("no second low within 500 km: %d (of %d); types match +-6 h: %d (cumulative), %d alone" % (
        len(s1), len(cand), len(s2), sum(c["match"] for c in cand)))

    need = sorted({c["valid"] for c in s2})
    todo = [t for t in need if not msl_file(t).exists()]
    est, sizes = estimate(todo) if todo else (0.0, [])
    print("GFS MSLP: %d times needed, %d not cached; estimated %.0f MB to stream (sample %d records, mean %.0f kB)" % (
        len(need), len(todo), est / 1e6, len(sizes), np.mean(sizes) / 1e3 if sizes else 0), flush=True)
    if a.estimate:
        return
    if est > 50e9:
        raise SystemExit("estimate over 50 GB: stop and report")

    def getmsl(t):
        try:
            return t, fetch_msl(t)
        except Exception as e:
            print("msl", t, "error", e, flush=True)
            return t, None
    msl = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for k, (t, m) in enumerate(ex.map(getmsl, need)):
            msl[t] = m
            if (k + 1) % 50 == 0:
                print("msl", k + 1, len(need), flush=True)
    for c in s2:
        m = msl.get(c["valid"])
        if m is None:
            continue
        c["gfs_dist"], c["gfs_dp"] = gfs_check(m, c["lat"], c["lon"], c["hpa"])
        c["gfs_ok"] = c["gfs_dist"] is not None and abs(c["gfs_dp"]) <= GFS_DP
    s3 = [c for c in s2 if c["gfs_ok"]]
    print("GFS minimum within 150 km and 4 hPa: %d of %d (no MSLP for %d)" % (
        len(s3), len(s2), sum(msl.get(c["valid"]) is None for c in s2)))

    # tracks per winter, then one case per track per UTC day
    for w in WINTERS:
        by_t = {}
        for t in times:
            if winter_of[t] == w and t in an:
                by_t[t] = an[t]["lows"]
        ids = FL.link_tracks(by_t)
        for c in cand:
            if winter_of[c["valid"]] == w:
                c["track"] = "%s-%d" % (w, ids[(c["valid"], c["idx"])])
    best = {}
    for c in s3:
        k = (c["track"], c["valid"].date())
        score = (len(c["types"]), c["total_nm"], -c["valid"].hour)
        if k not in best or score > best[k][0]:
            best[k] = (score, c)
    keep = [v[1] for v in best.values()]
    for c in cand:
        c["keep"] = any(c is k for k in keep)
    print("one per low per day: %d kept (from %d)" % (len(keep), len(s3)))
    by_type = Counter(t for c in keep for t in c["types"])
    print("kept cases with each type present: " + ", ".join("%s %d" % (t, by_type[t]) for t in FL.NON_TROUGH))
    print("kept by type set: " + str(Counter(c["types"] for c in keep).most_common(8)))

    with open(OUT / "candidates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["valid", "lat", "lon", "hpa", "types", "lengths_nm", "second_low", "types_match", "gfs_dist_km",
                    "gfs_dp_hpa", "gfs_ok", "track", "keep"])
        for c in cand:
            w.writerow([c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"], "%.0f" % c["hpa"],
                        "|".join(c["types"]), c["lengths"], int(c["second"]), int(c["match"]),
                        "" if c["gfs_dist"] is None else "%.0f" % c["gfs_dist"],
                        "" if c["gfs_dp"] is None else "%.1f" % c["gfs_dp"],
                        "" if c["gfs_ok"] is None else int(c["gfs_ok"]), c["track"], int(c["keep"])])

    picked = pick_all(keep, winter_of, a.n, a.n_new)
    ids = assign_ids(picked)
    with open(OUT / "picked.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "valid", "lat", "lon", "hpa", "types", "lengths_nm", "winter", "track"])
        for cid, c in sorted(zip(ids, picked), key=lambda x: x[0]):
            w.writerow([cid, c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"],
                        "%.0f" % c["hpa"], "|".join(c["types"]), c["lengths"], winter_of[c["valid"]], c["track"]])
    pt = Counter(t for c in picked for t in c["types"])
    print("picked %d: with " % len(picked) + ", ".join("%s %d" % (t, pt[t]) for t in FL.NON_TROUGH))
    print("picked by winter/month: " + str(sorted(Counter((winter_of[c["valid"]], c["valid"].month) for c in picked).items())))
    print("picked by hour: " + str(sorted(Counter(c["valid"].hour for c in picked).items())))


def pick_all(keep, winter_of, n, n_new):
    """The picks of an earlier run stay (same time and position, read from picked.csv); the full-coverage period adds
    n_new more balanced the same way. With no picked.csv, the two winters are picked first (n cases)."""
    p = OUT / "picked.csv"
    old_rows = [r for r in csv.DictReader(open(p))] if p.exists() else []
    old_rows = [r for r in old_rows if r["winter"] != "2026-fall"]
    new_pool = [c for c in keep if winter_of[c["valid"]] == "2026-fall"]
    if not old_rows:
        old = pick([c for c in keep if winter_of[c["valid"]] != "2026-fall"], winter_of, n)
    else:
        by = {(c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"]): c for c in keep}
        old = [by[(r["valid"], r["lat"], r["lon"])] for r in old_rows if (r["valid"], r["lat"], r["lon"]) in by]
        print("earlier picks kept: %d of %d" % (len(old), len(old_rows)))
    return old + pick(new_pool, winter_of, n_new)


def assign_ids(picked):
    """Ids f0001...: a case already in picked.csv (same time and position) keeps its id so a deck built from
    an earlier list is not rebuilt; new cases take the unused ids in random order (the order carries no meaning)."""
    old = {}
    p = OUT / "picked.csv"
    if p.exists():
        for r in csv.DictReader(open(p)):
            old[(r["valid"], r["lat"], r["lon"])] = r["id"]
    ids = [old.get((c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"])) for c in picked]
    used = {i for i in ids if i}
    free = ["f%04d" % k for k in range(1, len(picked) + 1) if "f%04d" % k not in used]
    random.Random(1106).shuffle(free)
    return [i or free.pop() for i in ids]


def pick(keep, winter_of, n, seed=20261106):
    """About n cases: spread over the ten (winter, month) strata (equal quotas), and each step takes the case
    whose types are least represented so far (weight 1 / (count + 1), cold and warm counted alike, troughs
    never), with a small penalty for a second case from a low already picked. Returned in random order."""
    rng = random.Random(seed)
    strata = sorted({(winter_of[c["valid"]], c["valid"].month) for c in keep})
    quota = int(np.ceil(n / len(strata)))
    left = list(keep)
    got, tcount, scount, track_n = [], Counter(), Counter(), Counter()
    while left and len(got) < n:
        pool = [c for c in left if scount[(winter_of[c["valid"]], c["valid"].month)] < quota] or left
        best = max(pool, key=lambda c: sum(1.0 / (tcount[t] + 1) for t in c["types"])
                   - 0.3 * track_n[c["track"]] + 0.001 * rng.random())
        left.remove(best)
        got.append(best)
        tcount.update(best["types"])
        scount[(winter_of[best["valid"]], best["valid"].month)] += 1
        track_n[best["track"]] += 1
    rng.shuffle(got)
    return got


if __name__ == "__main__":
    main()
