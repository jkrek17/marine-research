"""The single best-guess MSLP map: the grand ensemble mean everywhere, and around each member-vote low the
members' own fields averaged after shifting each one so its low sits on the vote position ("aligned
average"), blended in over 400-1000 km, then nudged with a smooth 250 km bowl so the map low reads the vote's
central pressure. Only lows with at least SHAPE_MIN weighted support are drawn in; weaker ones are
returned in the list (scored the same way) for the forecaster to see with their confidence. So the large-scale pattern is the mean's, and each low keeps the
depth and shape the members give it instead of the smeared mean low."""
import numpy as np
import lib, method as M

INNER, OUTER = 400.0, 1000.0
SHAPE_MIN = 0.30   # lows with less weighted member support are listed (with their confidence) but not drawn into the map


def voter_fields(c, w):
    """voter index -> (ensemble, member) in the same order method.voters builds them (ensembles first)"""
    idx = []
    for en in M.ENS:
        if en in c["mlows"] and w.get(en, 0) > 0:
            idx += [(en, m) for m in range(c["mem"][en].shape[0])]
    return idx


def best_guess(c, dom, P):
    V = M.voters(c, dom, P["w"], use_lag=False)
    mem = []
    lows = M.consensus(V, R=P["R"], T=P["T"], q=P["q"], members=mem)
    base = lib.to_quarter(M.grand_mean(c), dom)
    ids = voter_fields(c, P["w"])
    lat, lon = lib.LAT[dom], lib.LON[dom]
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    out = base.copy()
    for (la, lo, p, sup, spr), ms in zip(lows, mem):
        if sup < SHAPE_MIN:
            continue
        acc, n = np.zeros_like(base), 0
        for v, mla, mlo in ms:
            if v >= len(ids):
                continue          # deterministic voters carry no member field here
            en, m = ids[v]
            f = lib.to_quarter(c["mem"][en][m].astype(np.float32) / 10 + 1000, dom)
            dy = int(round((mla - la) / 0.25)); dx = int(round(((lo - mlo + 180) % 360 - 180) / 0.25))
            # shift so the member's low lands on the vote position (rows run north to south)
            g = np.roll(np.roll(f, dy, axis=0), dx, axis=1)
            acc += g; n += 1
        if n < 3:
            continue
        comp = acc / n
        d = lib.km(la, lo, LA, LO)
        wgt = np.clip((OUTER - d) / (OUTER - INNER), 0, 1)
        out = out * (1 - wgt) + comp * wgt
    # make each map low read the vote's central pressure: a smooth bowl (or lift) of 250 km scale
    for la, lo, p, sup, spr in lows:
        if sup < SHAPE_MIN:
            continue
        d = lib.km(la, lo, LA, LO)
        near = d < 300
        dp = p - out[near].min()
        out = out + dp * np.exp(-0.5 * (d / 250.0) ** 2)
    return out, lows
