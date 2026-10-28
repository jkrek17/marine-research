"""Follow one named low through every model run and ensemble member (the "storm read", tools/storm_read.py).

Pure numpy on pulled MSLP and wind. Lows come from rk.bomb.find_lows; the low is tracked FORWARD from a parent
low (a time and position the forecaster gives), not found backward from the valid time, because models that
differ in timing put the same low up to 1,300 km apart at the valid time and a nearest-low search there can
pick another system (LESSONS.md, 1 Nov 2026 central Atlantic bomb). Interface: rk/CONTRACT.md.
"""
import datetime as dt

import numpy as np

from . import KT  # noqa: F401  (re-exported: m/s to kt)
from .bomb import find_lows
from .score import km

PARENT_KM, STEP_KM, WIND_KM, STEP_H = 700.0, 800.0, 600.0, 6
THRESH = (34, 48, 64)
FMT = "%Y-%m-%dT%HZ"
NAMES = {"gfs": "GFS", "ifs": "ECMWF", "aifs": "AIFS", "aigfs": "AI-GFS",
         "gefs": "GEFS", "ens": "ECMWF ENS", "aifs-ens": "AIFS ENS"}
ENS_PARENT = {"gefs": "gfs", "ens": "ifs", "aifs-ens": "aifs"}   # ensemble hue = parent model


def tstr(t):
    return t.strftime(FMT)


def tparse(s):
    return dt.datetime.strptime(s, FMT)


def wind_max(speed, lats, lons, lat, lon, radius_km=WIND_KM):
    """Highest `speed` (kt, [y, x]) within radius_km of (lat, lon); NaN if no cell is inside."""
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    inside = km(LA, LO, lat, lon) <= radius_km
    if not inside.any():
        return float("nan")
    return float(np.nanmax(np.where(inside, speed, np.nan)))


def follow(lows_by_t, t0, lat0, lon0):
    """Parent low at t0 (nearest to lat0, lon0 within PARENT_KM), then both ways in 6 h steps, each step the
    nearest low within STEP_KM of the previous point -> {valid: (lat, lon, hPa)} or None."""
    L = lows_by_t.get(t0)
    if L is None or not len(L):
        return None
    d = km(L[:, 0], L[:, 1], lat0, lon0)
    j = int(np.argmin(d))
    if d[j] > PARENT_KM:
        return None
    tr = {t0: tuple(L[j])}
    for sign in (-1, 1):
        t, cur = t0, L[j]
        while True:
            t = t + dt.timedelta(hours=STEP_H * sign)
            M = lows_by_t.get(t)
            if M is None or not len(M):
                break
            d = km(M[:, 0], M[:, 1], cur[0], cur[1])
            k = int(np.argmin(d))
            if d[k] > STEP_KM:
                break
            cur = M[k]
            tr[t] = tuple(cur)
    return tr


def track(msl_by_t, speed_by_t, lats, lons, t0, lat0, lon0):
    """{valid: hPa [y, x]} and {valid: kt [y, x]} (wind optional per time) -> time-sorted points
    [{t, lat, lon, p, wmax}] of the low followed from the parent, or None."""
    lows = {t: find_lows(np.asarray(m, np.float32), lats, lons) for t, m in msl_by_t.items()}
    tr = follow(lows, t0, lat0, lon0)
    if tr is None:
        return None
    out = []
    for t in sorted(tr):
        la, lo, p = tr[t]
        S = speed_by_t.get(t) if speed_by_t else None
        w = None if S is None else wind_max(S, lats, lons, la, lo)
        if w is not None and not np.isfinite(w):
            w = None
        out.append({"t": tstr(t), "lat": float(la), "lon": float(lo), "p": float(p), "wmax": w})
    return out


def at(points, t):
    """The point of a track at datetime t, or None."""
    s = tstr(t)
    for x in points or []:
        if x["t"] == s:
            return x
    return None


def bergeron(points, key):
    """Bergeron number of every 24 h window along the track -> (largest, the one ending at key); None where
    there is no pair. 1 = a bomb: 24 hPa in 24 h at 60N, scaled by sin60 / sin(mean latitude)."""
    T = {tparse(x["t"]): x for x in points or []}
    best = atkey = None
    for t, x in T.items():
        y = T.get(t - dt.timedelta(hours=24))
        if y is None:
            continue
        b = (y["p"] - x["p"]) * np.sin(np.radians(60.0)) / np.sin(np.radians(0.5 * (x["lat"] + y["lat"]))) / 24.0
        b = float(b)
        best = b if best is None else max(best, b)
        if t == key:
            atkey = b
    return best, atkey


def point_summary(points, key, wind_from, wind_to):
    """One run or member -> numbers at the key time and over the track (see CONTRACT)."""
    if not points:
        return {"tracked": False, "p": None, "lat": None, "lon": None, "wmax": None, "pmin": None, "tmin": None,
                "wlife": None, "berg": None, "berg_key": None, "bomb": False}
    k = at(points, key)
    low = min(points, key=lambda x: x["p"])
    wl = [x["wmax"] for x in points if x["wmax"] is not None and wind_from <= tparse(x["t"]) <= wind_to]
    b, bk = bergeron(points, key)
    return {"tracked": True, "p": k and k["p"], "lat": k and k["lat"], "lon": k and k["lon"],
            "wmax": k and k["wmax"], "pmin": low["p"], "tmin": low["t"], "wlife": max(wl) if wl else None,
            "berg": b, "berg_key": bk, "bomb": b is not None and b >= 1.0}


def _share(vals, k, n):
    return sum(1 for v in vals if v is not None and v >= k) / n if n else None


def ens_summary(rows):
    """point_summary rows of one ensemble's members -> shares over ALL members (untracked: no bomb, no wind)."""
    n = len(rows)
    atkey = [r for r in rows if r["tracked"] and r["p"] is not None]
    out = {"n": n, "tracked": sum(1 for r in rows if r["tracked"]), "at_key": len(atkey)}
    if atkey:
        out["p"] = [float(v) for v in np.percentile([r["p"] for r in atkey], [10, 50, 90])]
        out["lat"] = float(np.median([r["lat"] for r in atkey]))
        out["lon"] = float(np.median([r["lon"] for r in atkey]))
    else:
        out["p"] = out["lat"] = out["lon"] = None
    pm = [r["pmin"] for r in rows if r["tracked"]]
    out["pmin"] = float(np.median(pm)) if pm else None
    out["bomb"] = sum(1 for r in rows if r["bomb"])
    out["bomb_share"] = out["bomb"] / n if n else None
    out["key"] = {str(k): _share([r["wmax"] for r in rows], k, n) for k in THRESH}
    out["life"] = {str(k): _share([r["wlife"] for r in rows], k, n) for k in THRESH}
    return out


def pooled(rows_by_ens):
    """{ens: [point_summary rows]} -> shares over all members of all ensembles (member-weighted)."""
    rows = [r for v in rows_by_ens.values() for r in v]
    return ens_summary(rows)


def summarize(det_tracks, ens_tracks, key, wind_from, wind_to):
    """det_tracks {model: {cycle tag: points | None}}, ens_tracks {ens: [points | None per member]} ->
    the summary dict that summary.json holds (numbers only; tracks are kept elsewhere)."""
    det = {m: {c: point_summary(tr, key, wind_from, wind_to) for c, tr in sorted(cs.items())}
           for m, cs in det_tracks.items()}
    rows = {e: [point_summary(tr, key, wind_from, wind_to) for tr in ms] for e, ms in ens_tracks.items()}
    out = {"key": tstr(key), "wind_window": [tstr(wind_from), tstr(wind_to)], "det": det,
           "ens": {e: ens_summary(r) for e, r in rows.items()}}
    out["pooled"] = pooled(rows) if rows else None
    cycles = sorted({c for cs in det.values() for c in cs})
    out["latest"] = cycles[-1] if cycles else None
    return out


# ---------------------------------------------------------------- generated sentences

def _pct(x):
    return "%.0f%%" % (100 * x)


def _pos(lat, lon):
    return "%.1fN %.1f%s" % (lat, 360 - lon if lon > 180 else lon, "W" if lon > 180 else "E")


def _when(s):
    return tparse(s).strftime("%a %d %HZ")


def _units(summary):
    """Latest-cycle deterministic runs and ensemble middles that have the low at the key time."""
    u = []
    for m, cs in summary["det"].items():
        r = cs.get(summary["latest"])
        if r and r["tracked"] and r["p"] is not None:
            u.append((NAMES[m], r["p"], r["lat"], r["lon"], r["pmin"], r["tmin"]))
    for e, s in summary["ens"].items():
        if s["p"] is not None:
            u.append((NAMES[e], s["p"][1], s["lat"], s["lon"], s["pmin"], None))
    return u


def sentence_bomb(summary):
    latest, pl = summary["latest"], summary.get("pooled")
    yes = [NAMES[m] for m, cs in summary["det"].items() if cs.get(latest, {}).get("bomb")]
    no = [NAMES[m] for m, cs in summary["det"].items() if latest in cs and not cs[latest]["bomb"]]
    parts = []
    if pl and pl["n"]:
        parts.append("%s of all %d ensemble members deepen the low at bomb rate or faster over 24 h (by ensemble: %s)."
                     % (_pct(pl["bomb_share"]), pl["n"],
                        ", ".join("%s %s" % (NAMES[e], _pct(s["bomb_share"])) for e, s in summary["ens"].items())))
        lost = pl["n"] - pl["tracked"]
        if lost:
            parts.append("%d members never form a trackable low and count as no bomb." % lost)
    if yes or no:
        s = "%s bomb%s it" % (", ".join(yes), "s" if len(yes) == 1 else "") if yes else "No deterministic model bombs it"
        if no:
            s += "; %s %s short" % (", ".join(no), "falls" if len(no) == 1 else "fall")
        parts.append(s + ".")
    return " ".join(parts)


def sentence_depth(summary):
    u = _units(summary)
    if len(u) < 2:
        return ""
    key = _when(summary["key"])
    deep, shallow = min(u, key=lambda x: x[1]), max(u, key=lambda x: x[1])
    spread = shallow[1] - deep[1]
    pm = [x[4] for x in u if x[4] is not None]
    lowest = max(pm) - min(pm) if pm else 0.0
    far = max(km(a[2], a[3], b[2], b[3]) for a in u for b in u)
    s = ("At %s %s is deepest (%.0f hPa near %s) and %s shallowest (%.0f hPa near %s), a %.0f hPa spread; the lows sit up to "
         "%s km apart. " % (key, deep[0], deep[1], _pos(deep[2], deep[3]), shallow[0], shallow[1],
                            _pos(shallow[2], shallow[3]), spread, format(int(round(far, -1)), ",")))
    if pm and spread >= 2 * lowest and spread >= 6:
        s += ("The lowest pressures along the tracks differ by only %.0f hPa (%.0f-%.0f), so the split is mostly timing: "
              "the runs reach similar depth at different times." % (lowest, min(pm), max(pm)))
    elif pm and lowest >= 0.5 * spread:
        s += ("The lowest pressures along the tracks run %.0f-%.0f hPa, so the runs differ in depth as well as timing."
              % (min(pm), max(pm)))
    else:
        s += "The lowest pressures along the tracks run %.0f-%.0f hPa." % (min(pm), max(pm)) if pm else ""
    return s


def sentence_wind(summary):
    pl, parts = summary.get("pooled"), []
    key, (w0, w1) = _when(summary["key"]), [_when(x) for x in summary["wind_window"]]
    if pl and pl["n"]:
        parts.append("Pooled over %d members, the highest 10 m wind within %d km of the low at %s reaches 34 kt in %s, "
                     "48 kt in %s and 64 kt in %s; at some point from %s to %s it reaches 48 kt in %s and 64 kt in %s."
                     % (pl["n"], WIND_KM, key, _pct(pl["key"]["34"]), _pct(pl["key"]["48"]), _pct(pl["key"]["64"]),
                        w0, w1, _pct(pl["life"]["48"]), _pct(pl["life"]["64"])))
        parts.append("Members at 64 kt or more at %s: %s." % (key, ", ".join(
            "%s %s" % (NAMES[e], _pct(s["key"]["64"])) for e, s in summary["ens"].items())))
    d = [(NAMES[m], r["wmax"], r["wlife"]) for m, cs in summary["det"].items()
         for r in [cs.get(summary["latest"])] if r and r["wmax"] is not None]
    if d:
        parts.append("Deterministic runs at %s: %s." % (key, ", ".join("%s %.0f kt (peak %.0f)" % (n, w, wl) for n, w, wl in d)))
    return " ".join(parts)


def sentence_trend(summary):
    out = []
    for m, cs in summary["det"].items():
        seq = [(c, r["p"]) for c, r in sorted(cs.items()) if r["tracked"] and r["p"] is not None]
        if len(seq) < 3:
            continue
        p = [v for _, v in seq]
        runs = 0
        for a, b in zip(p[:-1][::-1], p[1:][::-1]):
            if b < a - 1:
                runs += 1
            else:
                break
        runs_up = 0
        for a, b in zip(p[:-1][::-1], p[1:][::-1]):
            if b > a + 1:
                runs_up += 1
            else:
                break
        if runs >= 2:
            out.append("%s has deepened the low on %d straight runs (%.0f to %.0f hPa at the key time)." % (NAMES[m], runs, p[-runs - 1], p[-1]))
        elif runs_up >= 2:
            out.append("%s has weakened the low on %d straight runs (%.0f to %.0f hPa)." % (NAMES[m], runs_up, p[-runs_up - 1], p[-1]))
        elif max(p) - min(p) <= 6:
            out.append("%s has held within %.0f hPa (%.0f-%.0f)." % (NAMES[m], max(p) - min(p), min(p), max(p)))
        else:
            out.append("%s has swung between %.0f and %.0f hPa from run to run." % (NAMES[m], min(p), max(p)))
    return " ".join(out)


CAVEATS = (
    "Models run 2-6 kt below ASCAT peaks, so verified winds could read higher than the model values here; ensemble "
    "wind is 0.25 degree output and understates peaks a little.",
    "Hurricane-force chances cannot be calibrated (too few cases, and the live blend is already under-confident at "
    "the top), so read the 64 kt shares as how many members reach it, not as probabilities.",
    "The bomb share is evidence, a single model's yes or no is not. In the day 5-7 bomb-watch test "
    "(studies/2026-10-19-bomb-d5-7/findings.md) the share of members that bomb a low within 500 km had held-out Brier "
    "skill +0.31 against climatology at day 5 and +0.22 and +0.14 at days 6 and 7, reliable up to about 35% and "
    "reading low above that at days 6-7, while GFS, ECMWF and AIFS yes/no scored below climatology. That test counted "
    "a bomb near any cell, not one named low, so this share is the same kind of evidence, not the same number.",
    "When the lows are apart in timing, the page's blend smooths the core away: read the members and the warning "
    "lines, not the blend.",
)


def narrative(summary):
    """Generated sentences from the summary numbers -> {bomb, depth, wind, trend, caveats: [..]}."""
    return {"bomb": sentence_bomb(summary), "depth": sentence_depth(summary), "wind": sentence_wind(summary),
            "trend": sentence_trend(summary), "caveats": list(CAVEATS)}
