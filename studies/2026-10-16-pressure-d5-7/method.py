"""Systems for the day 5-7 lows study.

Every system returns its forecast lows (k, 3+) lat, lon, hPa [, support, spread_km] for one case
(cycle, basin, lead), plus a field used only when no forecast low is within 1000 km of an analysed one.

consensus(): "member-vote lows". Each member and deterministic run votes for the lows it has; votes are
weighted so each ensemble counts as a block. A low is kept where the weighted share of voters with a low
within R km reaches T. Its position is the weighted mean of the voters' own low positions, and its depth a
weighted quantile of their own central pressures, then a linear depth calibration by lead. Because every
voter's low is taken at its own centre, the depth is not smeared the way an averaged field smears it.
"""
import os, datetime as dt
import numpy as np
from lib import CACHE, km, find_lows, dec, dedupe, STEPS

ENS = ("gefs", "ens", "aifsens")
DET = ("gfs", "ifs", "aifs")
_cache = {}


def load(src, ymd):
    k = (src, ymd)
    if k not in _cache:
        p = os.path.join(CACHE, "fc_%s_%s.npz" % (src, ymd))
        _cache[k] = dict(np.load(p)) if os.path.exists(p) else None
        if len(_cache) > 12:
            _cache.pop(next(iter(_cache)))
    return _cache[k]


def analysis(ymd, dom):
    out = []
    for src, name in (("noaa", "gfs"), ("ec", "ifs")):
        p = os.path.join(CACHE, "an_%s_%s.npz" % (src, ymd))
        if os.path.exists(p):
            z = np.load(p)
            k = "an_%s_%s" % (name, dom)
            if k in z.files:
                out.append(dec(z[k]))
    return None if len(out) < 2 else (out[0] + out[1]) / 2


def case(ymd, dom, step, lag=True):
    """All inputs for one case. Returns dict or None when a source is missing."""
    n, e = load("noaa", ymd), load("ec", ymd)
    if n is None or e is None:
        return None
    c = {"det": {}, "mem": {}, "mlows": {}, "lag": {}}
    for m in DET:
        z = n if m == "gfs" else e
        k = "det_%s_%s_%d" % (m, dom, step)
        if k not in z:
            return None
        c["det"][m] = dec(z[k])
    for en in ENS:
        z = n if en == "gefs" else e
        k = "mem_%s_%s_%d" % (en, dom, step)
        if k in z:
            c["mem"][en] = z[k]
            c["mlows"][en] = z["low_%s_%s_%d" % (en, dom, step)]
    if "gefs" not in c["mem"] or "ens" not in c["mem"]:
        return None
    if lag:
        prev = (dt.datetime.strptime(ymd, "%Y%m%d") - dt.timedelta(days=1)).strftime("%Y%m%d")
        pn, pe = load("noaa", prev), load("ec", prev)
        if pn is not None and pe is not None:
            for m in DET:
                z = pn if m == "gfs" else pe
                k = "det_%s_%s_%d" % (m, dom, step + 24)
                if k in z:
                    c["lag"]["det_" + m] = dec(z[k])
            if step + 24 in STEPS:
                for en in ENS:
                    z = pn if en == "gefs" else pe
                    k = "low_%s_%s_%d" % (en, dom, step + 24)
                    if k in z:
                        c["lag"]["mlows_" + en] = z[k]
    return c


def grand_mean(c, ens=ENS):
    """equal weight per ensemble, at 0.5 deg"""
    ms = [c["mem"][e].astype(np.float32).mean(0) / 10 + 1000 for e in ens if e in c["mem"]]
    return np.mean(ms, 0)


def det_lows(c, dom):
    return {m: find_lows(c["det"][m], dom, 1010.0) for m in DET}


def voters(c, dom, w, use_lag=True, lag_w=0.5):
    """list of (weight, lows (k,3)). w: dict ensemble/det name -> block weight."""
    V = []
    for en in ENS:
        if en not in c["mlows"] or w.get(en, 0) <= 0:
            continue
        L = c["mlows"][en]
        mem = np.unique(L[:, 0]) if len(L) else []
        nm = c["mem"][en].shape[0]
        for m in range(nm):
            V.append((w[en] / nm, dedupe(L[L[:, 0] == m][:, 1:4].astype(np.float64))))
    for m in DET:
        if w.get(m, 0) > 0:
            V.append((w[m], find_lows(c["det"][m], dom, 1012.0)))
    if use_lag and lag_w > 0:
        for en in ENS:
            k = "mlows_" + en
            if k in c["lag"] and w.get(en, 0) > 0:
                L = c["lag"][k]
                nm = int(L[:, 0].max()) + 1 if len(L) else 0
                for m in range(nm):
                    V.append((lag_w * w[en] / nm, dedupe(L[L[:, 0] == m][:, 1:4].astype(np.float64))))
        for m in DET:
            k = "det_" + m
            if k in c["lag"] and w.get(m, 0) > 0:
                V.append((lag_w * w[m], find_lows(c["lag"][k], dom, 1012.0)))
    tot = sum(v[0] for v in V)
    return [(a / tot, L) for a, L in V]


def wquant(x, wt, q):
    o = np.argsort(x)
    cw = np.cumsum(wt[o]) / wt.sum()
    return float(x[o][min(np.searchsorted(cw, q), len(x) - 1)])


def consensus(V, R=400.0, T=0.3, q=0.5, cand_p=1008.0, sep=600.0, calib=None, members=None):
    """member-vote lows. Returns (k, 5): lat, lon, hPa, support, spread_km.
    members: optional list, filled with each low's [(voter index, voter low lat, lon), ...]."""
    pts, own, wts = [], [], []
    for i, (a, L) in enumerate(V):
        L = L[L[:, 2] < cand_p] if len(L) else L
        for r in L:
            pts.append(r); own.append(i); wts.append(a)
    if not pts:
        return np.zeros((0, 5))
    P = np.array(pts); own = np.array(own); wts = np.array(wts)   # already grouped by voter
    starts = np.r_[0, np.where(np.diff(own))[0] + 1]
    vw = wts[starts]
    # D[i, j] distance between candidate points
    D = km(P[:, 0][:, None], P[:, 1][:, None], P[:, 0][None, :], P[:, 1][None, :])
    alive = np.ones(len(P), bool)
    out = []
    while alive.any():
        # support of each alive point: weight of distinct voters with an alive low within R
        near = (D <= R) & alive[None, :]
        sup = np.logical_or.reduceat(near, starts, axis=1) @ vw
        sup[~alive] = -1
        i = int(sup.argmax())
        if sup[i] < T:
            break
        # each voter's nearest alive low within R of the seed, then recentre once
        lat0, lon0 = P[i, 0], P[i, 1]
        for _ in range(2):
            d = km(lat0, lon0, P[:, 0], P[:, 1])
            sel = []
            for v in np.unique(own[(d <= R) & alive]):
                js = np.where((own == v) & (d <= R) & alive)[0]
                sel.append(js[d[js].argmin()])
            sel = np.array(sel)
            ww = wts[sel]
            lat0 = float(np.sum(ww * P[sel, 0]) / ww.sum())
            dl = (P[sel, 1] - lon0 + 180) % 360 - 180
            lon0 = float((lon0 + np.sum(ww * dl) / ww.sum()) % 360)
        p = wquant(P[sel, 2], ww, q)
        if calib is not None:
            p = calib[0] + calib[1] * (p - 1000.0)
        spread = float(np.median(km(lat0, lon0, P[sel, 0], P[sel, 1])))
        out.append((lat0, lon0, p, ww.sum(), spread))
        if members is not None:
            members.append([(int(own[k]), P[k, 0], P[k, 1]) for k in sel])
        alive[sel] = False
        alive &= km(lat0, lon0, P[:, 0], P[:, 1]) > sep
    return np.array(out).reshape(-1, 5)
