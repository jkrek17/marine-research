"""Front drill, step 1: find and pick the cases (design.md, "Cases").

    python3 find_cases.py [--estimate] [--workers 6] [--end 2026110518] [--relax auto|yes|no]

Both basins; 00/06/12/18 UTC from the first full-coverage analysis (FL.COVERAGE_FULL_FROM + 6 h) to --end (the latest
complete UTC day). For every analysed low (rk.fronts, the Unified Surface Analysis as coded by WPC) over open water
(GFS land mask, per-basin crop; no sea ice; not the Gulf of Mexico, Gulf of St Lawrence, Hudson Bay, Gulf of California or
Puget Sound) in the North Atlantic (100W to 3W) or the North Pacific east of 180 (180 to 116W; the bulletin codes nothing west
of 180), 25-67N, with a cold, warm or occluded front end within 300 km (after merge_segments; what the trainee draws):
  second_low   no second analysed low within 500 km (kept when none)
  types_match  the low's non-trough front types are the same in the analyses 6 h before and after (strict), or
               (relaxed) the cold/warm/occluded types present now were also present 6 h before or after
  gfs          a GFS f000 MSLP minimum within 150 km of the low and within 4 hPa of its analysed pressure
  day          at most one case per low (tracked across 6 h steps, nearest within 600 km) per UTC day
All passing cases are taken (no cap). The relaxed match is used when the strict one leaves under 250 cases (--relax auto).
Writes under rk.paths.data("extra", "front-drill"): candidates.csv (every candidate with the flag of each
filter), picked.csv (every passing case), msl/<YYYYMMDDHH>.npz (small GFS
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
PERIOD_START = FL.COVERAGE_FULL_FROM + dt.timedelta(hours=6)
PERIOD_END = dt.datetime(2026, 11, 5, 18)       # last synoptic time of the latest complete UTC day (today is 2026-11-06)
PERIOD = "fall2026"
LAT_MIN, LAT_MAX = 25.0, 67.0
GFS_KM, GFS_DP = 150.0, 4.0
MIN_STRICT = 250                         # fewer strict-match cases than this -> the relaxed match
# Per-basin GFS crops (0.25 deg). The Atlantic one is the cache of the first runs (msl/, ice/, landmask480.npy);
# the Pacific has its own. seed: a point in the open ocean that the water mask must connect to.
BASINS = {
    "natl": {"lat_n": 70.0, "lon_w": 240.0, "ny": 241, "nx": 480, "seed": (45.0, 330.0), "lon": (255.0, 357.0),
             "msl": "msl", "ice": "ice", "land": "landmask480.npy"},
    "npac": {"lat_n": 70.0, "lon_w": 170.0, "ny": 241, "nx": 360, "seed": (45.0, 200.0), "lon": (180.0, 255.0),
             "msl": "msl_npac", "ice": "ice_npac", "land": "landmask_npac.npy"},
}
MSL_KEY = {"PRMSL:mean sea level": "msl"}


def basin_of(lon):
    """"natl" / "npac" for a low longitude (0-360), or None outside both."""
    for b, d in BASINS.items():
        if d["lon"][0] <= lon <= d["lon"][1]:
            return b
    return None


def excluded_water(basin, lat, lon):
    """Enclosed or coastal water that is not the open ocean (inside the GFS ocean mask, so it needs a box):
    Gulf of Mexico, Hudson and James Bay, Gulf of St Lawrence (natl); Gulf of California, Puget Sound and the
    Strait of Georgia (npac)."""
    if basin == "natl":
        return ((lat < 31.0 and 260.0 <= lon <= 279.0) or (lat >= 51.0 and lon <= 284.0)
                or (46.0 <= lat <= 52.0 and 289.0 <= lon <= 300.5))
    return (lat < 32.0 and lon >= 244.0) or (47.0 <= lat <= 50.5 and lon >= 236.0)


def synoptic_times(t0, t1):
    out = []
    while t0 <= t1:
        out.append(t0)
        t0 += dt.timedelta(hours=6)
    return out


def crop_of(g, basin="natl"):
    C = BASINS[basin]
    r0, c0 = int(round((90 - C["lat_n"]) / 0.25)), int(round(C["lon_w"] / 0.25))
    return g[r0:r0 + C["ny"], c0:c0 + C["nx"]]


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


def landmask(valid, basin="natl"):
    p = OUT / BASINS[basin]["land"]
    if p.exists():
        return np.load(p)
    g = fetch.gfs_global(valid, 0, {"LAND:surface": "land"})
    if g is None:
        raise RuntimeError("no GFS LAND")
    m = crop_of(g["land"], basin).astype(np.float32)
    np.save(p, m)
    return m


def _widen(a, fill, basin="natl"):
    """A crop cached before the crop grew from 421 to 480 columns, padded east with `fill`."""
    nx = BASINS[basin]["nx"]
    return a if a.shape[1] >= nx else np.pad(a, ((0, 0), (0, nx - a.shape[1])), constant_values=fill)


def ocean_mask(land, basin="natl"):
    """Water cells connected to the open ocean of the basin (drops the Great Lakes and other inland water)."""
    from scipy.ndimage import label
    C = BASINS[basin]
    lab, _ = label(land < 0.5, structure=np.ones((3, 3)))
    y, x = int(round((C["lat_n"] - C["seed"][0]) / 0.25)), int(round((C["seed"][1] - C["lon_w"]) / 0.25))
    return lab == lab[y, x]


def is_water(ocean, lat, lon, ice=None, basin="natl"):
    """Over open water: GFS land mask (ocean-connected cells only), no sea ice (ICEC < 0.15 when given), and
    not one of the enclosed or coastal waters of excluded_water()."""
    C = BASINS[basin]
    y = int(round((C["lat_n"] - lat) / 0.25))
    x = int(round((lon - C["lon_w"]) / 0.25))
    if not (0 <= y < ocean.shape[0] and 0 <= x < ocean.shape[1]) or not ocean[y, x]:
        return False
    if excluded_water(basin, lat, lon):
        return False
    return ice is None or not ice[y, x] >= 0.15


def ice_file(valid, basin="natl"):
    return OUT / BASINS[basin]["ice"] / (valid.strftime("%Y%m%d%H") + ".npz")


def fetch_ice(valid, basin="natl"):
    """GFS f000 ICEC crop (fraction) for a valid time, cached -> array or None."""
    p = ice_file(valid, basin)
    if p.exists():
        with np.load(p) as z:
            return _widen(z["ice"], 0.0, basin)
    g = fetch.gfs_global(valid, 0, {"ICEC:surface": "ice"})
    if g is None:
        return None
    m = np.nan_to_num(crop_of(g["ice"], basin), nan=0.0).astype(np.float16)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".tmp.npz")
    np.savez_compressed(tmp, ice=m)
    tmp.replace(p)
    return m


def msl_file(valid, basin="natl"):
    return OUT / BASINS[basin]["msl"] / (valid.strftime("%Y%m%d%H") + ".npz")


def fetch_msl(valid, basin="natl"):
    """GFS f000 MSLP (hPa) crop for a valid time -> array or None (cached; a missing time is retried next run)."""
    p = msl_file(valid, basin)
    if p.exists():
        with np.load(p) as z:
            return _widen(z["msl"], 1100.0, basin)
    g = fetch.gfs_global(valid, 0, MSL_KEY)
    if g is None:
        return None
    m = (crop_of(g["msl"], basin) / 100.0).astype(np.float32)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".tmp.npz")
    np.savez_compressed(tmp, msl=m)
    tmp.replace(p)
    return m


def gfs_check(msl, lat, lon, hpa, basin="natl"):
    """Deepest local minimum (13 x 13 window) of the crop within GFS_KM of the low -> (distance km, GFS hPa
    minus analysed hPa), or (None, None) when there is none."""
    from scipy.ndimage import minimum_filter
    C = BASINS[basin]
    la = C["lat_n"] - np.arange(msl.shape[0]) * 0.25
    lo = C["lon_w"] + np.arange(msl.shape[1]) * 0.25
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
def stage_a(an, oceans, times, ice_of=None):
    """Candidates: analysed lows over open water in either basin with an attached cold, warm or occluded front
    (what the trainee draws; the types column also lists a stationary front)."""
    rows = []
    mem = {}
    for t in times:
        a = an.get(t)
        if a is None:
            continue
        mf = mem.setdefault(t, FL.merged(a))
        seen = []
        for i, (hpa, lat, lon) in enumerate(a["lows"]):
            if any(abs(lat - la) < 0.05 and abs(lon - lo) < 0.05 for la, lo in seen):    # the bulletin lists some lows twice
                continue
            seen.append((lat, lon))
            basin = basin_of(lon)
            if basin is None or not (LAT_MIN <= lat <= LAT_MAX):
                continue
            ice = ice_of(t, basin) if ice_of else None
            if not is_water(oceans[basin], lat, lon, ice, basin):
                continue
            att = FL.attached(mf, lat, lon)
            if not att or not any(f["type"] in FL.DRAWN for f in att):
                continue
            rows.append({"valid": t, "idx": i, "lat": lat, "lon": lon, "hpa": hpa, "basin": basin,
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
    ap.add_argument("--end", default=PERIOD_END.strftime("%Y%m%d%H"), help="last synoptic time, YYYYMMDDHH")
    ap.add_argument("--relax", default="auto", choices=("auto", "yes", "no"),
                    help="relaxed 6 h type match: auto = only when the strict match leaves under %d cases" % MIN_STRICT)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    times = synoptic_times(PERIOD_START, dt.datetime.strptime(a.end, "%Y%m%d%H"))
    days = sorted({(t + dt.timedelta(hours=h)).date() for t in times for h in (-6, 0, 6)})
    an = load_analyses(days, a.workers)
    print("analyses loaded: %d of %d synoptic times (+neighbours)" % (sum(t in an for t in times), len(times)), flush=True)
    oceans = {b: ocean_mask(landmask(times[0], b), b) for b in BASINS}

    # sea ice (GFS ICEC, small records) is needed only at times with a low over water and a front end near it
    pre = stage_a(an, oceans, times)
    ice_jobs = sorted({(c["valid"], c["basin"]) for c in pre})
    ice = {}

    def getice(job):
        try:
            return job, fetch_ice(*job)
        except Exception as e:
            print("ice", job, "error", e, flush=True)
            return job, None
    with ThreadPoolExecutor(a.workers) as ex:
        ice.update(dict(ex.map(getice, ice_jobs)))
    cand = stage_a(an, oceans, times, lambda t, b: ice.get((t, b)))
    print("before the sea-ice cut: %d candidates; ice missing at %d of %d (time, basin)" % (
        len(pre), sum(v is None for v in ice.values()), len(ice_jobs)))
    n_lows = sum(len(an[t]["lows"]) for t in times if t in an)
    nb = Counter(c["basin"] for c in cand)
    print("analysed lows %d; candidates (open water, 25-67N, cold/warm/occluded front end within 300 km): %d (N Atlantic %d, N Pacific %d)" % (
        n_lows, len(cand), nb["natl"], nb["npac"]))

    mem = {}
    for c in cand:
        t = c["valid"]
        c["second"] = FL.has_second_low(an[t]["lows"], c["lat"], c["lon"])
        prev, nxt = neighbours(an, t, mem)
        c["match"] = FL.types_match(prev, nxt, c["types"], c["lat"], c["lon"])
        c["match_relaxed"] = FL.types_match_relaxed(prev, nxt, c["types"], c["lat"], c["lon"])
        c["gfs_dist"] = c["gfs_dp"] = None
        c["gfs_ok"] = None
    s1 = [c for c in cand if not c["second"]]
    s2 = [c for c in s1 if c["match_relaxed"]]          # the relaxed set contains the strict one
    print("no second low within 500 km: %d (of %d); type match +-6 h: strict %d, relaxed %d (cumulative with the second-low filter)" % (
        len(s1), len(cand), sum(c["match"] for c in s1), len(s2)))

    need = sorted({(c["valid"], c["basin"]) for c in s2})
    todo = [j for j in need if not msl_file(*j).exists()]
    est, sizes = estimate([t for t, _ in todo]) if todo else (0.0, [])
    print("GFS MSLP: %d (time, basin) crops needed, %d not cached; estimated %.0f MB to stream (sample %d records, mean %.0f kB)" % (
        len(need), len(todo), est / 1e6, len(sizes), np.mean(sizes) / 1e3 if sizes else 0), flush=True)
    if a.estimate:
        return
    if est > 50e9:
        raise SystemExit("estimate over 50 GB: stop and report")

    def getmsl(job):
        try:
            return job, fetch_msl(*job)
        except Exception as e:
            print("msl", job, "error", e, flush=True)
            return job, None
    msl = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for k, (job, m) in enumerate(ex.map(getmsl, need)):
            msl[job] = m
            if (k + 1) % 50 == 0:
                print("msl", k + 1, len(need), flush=True)
    for c in s2:
        m = msl.get((c["valid"], c["basin"]))
        if m is None:
            continue
        c["gfs_dist"], c["gfs_dp"] = gfs_check(m, c["lat"], c["lon"], c["hpa"], c["basin"])
        c["gfs_ok"] = c["gfs_dist"] is not None and abs(c["gfs_dp"]) <= GFS_DP
    print("GFS minimum within 150 km and 4 hPa: %d of %d relaxed-match, %d of %d strict-match (no MSLP for %d)" % (
        sum(bool(c["gfs_ok"]) for c in s2), len(s2), sum(bool(c["gfs_ok"]) for c in s2 if c["match"]),
        sum(c["match"] for c in s2), sum(msl.get((c["valid"], c["basin"])) is None for c in s2)))

    # tracks (all lows of a time, both basins), then one case per track per UTC day
    ids = FL.link_tracks({t: an[t]["lows"] for t in times if t in an})
    for c in cand:
        c["track"] = "%s-%d" % (PERIOD, ids[(c["valid"], c["idx"])])

    def one_per_day(pool):
        best = {}
        for c in pool:
            k = (c["track"], c["valid"].date())
            score = (len(c["types"]), c["total_nm"], -c["valid"].hour)
            if k not in best or score > best[k][0]:
                best[k] = (score, c)
        return [v[1] for v in best.values()]
    strict = one_per_day([c for c in s2 if c["gfs_ok"] and c["match"]])
    relaxed = one_per_day([c for c in s2 if c["gfs_ok"]])
    print("one per low per UTC day: strict match %d cases (N Atlantic %d, N Pacific %d); relaxed match %d cases (N Atlantic %d, N Pacific %d)" % (
        len(strict), sum(c["basin"] == "natl" for c in strict), sum(c["basin"] == "npac" for c in strict),
        len(relaxed), sum(c["basin"] == "natl" for c in relaxed), sum(c["basin"] == "npac" for c in relaxed)), flush=True)
    use_relaxed = a.relax == "yes" or (a.relax == "auto" and len(strict) < MIN_STRICT)
    keep = relaxed if use_relaxed else strict
    print("using the %s match: %d cases" % ("RELAXED" if use_relaxed else "strict", len(keep)))
    by_type = Counter(t for c in keep for t in c["types"])
    print("kept cases with each type present: " + ", ".join("%s %d" % (t, by_type[t]) for t in FL.NON_TROUGH))
    print("kept by type set: " + str(Counter(c["types"] for c in keep).most_common(8)))
    for c in cand:
        c["keep"] = any(c is k for k in keep)

    for name in ("candidates", "picked"):         # the first deck's lists stay beside the new ones
        p, q = OUT / (name + ".csv"), OUT / (name + "_v1.csv")
        if p.exists() and not q.exists() and "winter" in p.read_text().splitlines()[0]:
            p.replace(q) if name == "picked" else q.write_bytes(p.read_bytes())
    with open(OUT / "candidates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["valid", "basin", "lat", "lon", "hpa", "types", "lengths_nm", "second_low", "types_match",
                    "types_match_relaxed", "gfs_dist_km", "gfs_dp_hpa", "gfs_ok", "track", "keep"])
        for c in cand:
            w.writerow([c["valid"].strftime("%Y%m%d%H"), c["basin"], "%.1f" % c["lat"], "%.1f" % c["lon"], "%.0f" % c["hpa"],
                        "|".join(c["types"]), c["lengths"], int(c["second"]), int(c["match"]), int(c["match_relaxed"]),
                        "" if c["gfs_dist"] is None else "%.0f" % c["gfs_dist"],
                        "" if c["gfs_dp"] is None else "%.1f" % c["gfs_dp"],
                        "" if c["gfs_ok"] is None else int(c["gfs_ok"]), c["track"], int(c["keep"])])

    picked = sorted(keep, key=lambda c: c["valid"])
    ids = assign_ids(picked)
    with open(OUT / "picked.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "valid", "lat", "lon", "hpa", "types", "lengths_nm", "basin", "track"])
        for cid, c in sorted(zip(ids, picked), key=lambda x: x[0]):
            w.writerow([cid, c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"],
                        "%.0f" % c["hpa"], "|".join(c["types"]), c["lengths"], c["basin"], c["track"]])
    pt = Counter(t for c in picked for t in c["types"])
    print("picked %d: with " % len(picked) + ", ".join("%s %d" % (t, pt[t]) for t in FL.NON_TROUGH))
    print("picked by basin/month: " + str(sorted(Counter((c["basin"], c["valid"].month) for c in picked).items())))
    print("picked by hour: " + str(sorted(Counter(c["valid"].hour for c in picked).items())))


ID_PREFIX = "g"          # the second deck's ids (the first deck's f0001... files stay on disk, out of the manifest)


def assign_ids(picked):
    """Ids g0001...: a case already in picked.csv (same time and position) keeps its id so a deck built from
    an earlier list is not rebuilt; new cases take the unused ids in random order (the order carries no meaning)."""
    old = {}
    p = OUT / "picked.csv"
    if p.exists():
        for r in csv.DictReader(open(p)):
            if r["id"].startswith(ID_PREFIX):
                old[(r["valid"], r["lat"], r["lon"])] = r["id"]
    ids = [old.get((c["valid"].strftime("%Y%m%d%H"), "%.1f" % c["lat"], "%.1f" % c["lon"])) for c in picked]
    used = {i for i in ids if i}
    free = ["%s%04d" % (ID_PREFIX, k) for k in range(1, len(picked) + 1) if "%s%04d" % (ID_PREFIX, k) not in used]
    random.Random(1106).shuffle(free)
    return [i or free.pop() for i in ids]


if __name__ == "__main__":
    main()
