"""Member-vote settings on tuning cases only, compared at EQUAL false lows.

The vote keeps lows in order of support, so one run at a low threshold holds every higher threshold too:
lows with support >= T are the same whatever lower T the run stopped at. Each setting is run once at
T=0.08 and re-scored at many T; position and depth error are then read off at the false-low rate of each
deterministic model (linear interpolation in T)."""
import sys, json, itertools
import numpy as np
import evaluate as E, summary as S, lib

TS = np.round(np.arange(0.08, 0.81, 0.02), 2)
DEP = {"gfs", "ifs", "aifs"}


def rescore(r, T, calib=None):
    L = r["lows"]
    L = L[L[:, 3] >= T] if len(L) else np.zeros((0, 5))
    L3 = L[:, :3].copy()
    if calib is not None and len(L3):
        L3[:, 2] = calib(L3[:, 2], r["step"])
    rows = lib.score_vals(r["truth"], L3, r["fvals"])
    fa, nf = lib.false_lows(r["truth_all"], L3)
    return rows, fa


def curve(recs, step, calib=None, deep=False, sel=lambda r: r["tune"]):
    rs = [r for r in recs if r["sys"] == "vote" and r["step"] == step and sel(r)]
    out = []
    for T in TS:
        R, F = [], 0
        for r in rs:
            rows, fa = rescore(r, T, calib)
            R.append(rows); F += fa
        R = np.concatenate(R)
        if deep:
            R = R[R[:, 3] < 980]
        out.append((T, R[:, 0].mean(), np.nanmean(np.abs(R[:, 1])), np.nanmean(R[:, 1]), F / len(rs), R[:, 2].mean()))
    return np.array(out)


def at_fa(c, fa):
    """interpolate the curve (sorted by FA) at a false-low rate"""
    o = np.argsort(c[:, 4])
    return [float(np.interp(fa, c[o, 4], c[o, k])) for k in range(6)]


def report(name, recs, base, calib=None, sel=lambda r: r["tune"]):
    line = "%-34s" % name
    for step in (120, 144, 168):
        c = curve(recs, step, calib, sel=sel)
        for m in ("gfs", "ifs", "aifs"):
            t = S.stats([r for r in base if r["sys"] == m and r["step"] == step and sel(r)])
            v = at_fa(c, t["fa"])
            line += " %s %+4.0f/%+4.1f" % (m[0].upper(), v[1] - t["pos"], v[2] - t["mae"])
        line += " |"
    print(line, flush=True)


if __name__ == "__main__":
    cyc = E.cycles()
    base = [r for r in E.main("base", dict(E.DEFAULT, T=0.08), only=cyc) if r["tune"]]
    print("vote minus model at that model's false-low rate: position km / depth MAE hPa; leads 120 | 144 | 168")
    report("default R400 q.5", base, base)
    grid = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    keys = list(grid)
    for vals in itertools.product(*[grid[k] for k in keys]):
        P = dict(E.DEFAULT, T=0.08); P.update(dict(zip(keys, vals)))
        r = E.main("tmp", P, base=False, only=cyc)
        report(" ".join("%s=%s" % (k, v) for k, v in zip(keys, vals))[:34], r, base)
