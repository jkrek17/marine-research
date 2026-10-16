"""Does a linear depth calibration by lead (fitted leave-one-month-out on tuning hits) cut depth error?"""
import pickle, sys, numpy as np
import tune, summary as S, lib
tag = sys.argv[1] if len(sys.argv) > 1 else "base"
R = [r for r in pickle.load(open(lib.RECORDS + "/records_%s.pkl" % tag, "rb"))["recs"] if r["tune"]]
base = pickle.load(open(lib.RECORDS + "/records_base.pkl", "rb"))["recs"]
base = [r for r in base if r["tune"]]


def pairs(rs, T=0.25):
    X = []
    for r in rs:
        L = r["lows"]
        L = L[L[:, 3] >= T] if len(L) else L
        for la, lo, p in r["truth"]:
            if len(L):
                d = lib.km(la, lo, L[:, 0], L[:, 1]); j = d.argmin()
                if d[j] <= 300:
                    X.append((r["step"], L[j, 2], p, r["ymd"][:6]))
    return X


X = pairs([r for r in R if r["sys"] == "vote"])
months = sorted({x[3] for x in X})
fits = {}
for m in months:
    for st in (120, 144, 168):
        A = np.array([(x[1], x[2]) for x in X if x[0] == st and x[3] != m], float)
        b, a = np.polyfit(A[:, 0] - 1000, A[:, 1], 1)
        fits[(m, st)] = (a, b)
print("fit all-month slope/intercept:", {st: np.round(np.polyfit(np.array([x[1] for x in X if x[0]==st])-1000, np.array([x[2] for x in X if x[0]==st]), 1), 2).tolist() for st in (120,144,168)})
cal = {}
def calib_for(r):
    a, b = fits[(r["ymd"][:6], r["step"])]
    return lambda p, step: a + b * (p - 1000)
# report with per-record calibration
for st in (120, 144, 168):
    for name, use in (("raw", False), ("calibrated", True)):
        line = "%d %-11s" % (st, name)
        rs = [r for r in R if r["sys"] == "vote" and r["step"] == st]
        for m in ("gfs", "ifs", "aifs"):
            t = S.stats([r for r in base if r["sys"] == m and r["step"] == st])
            out = []
            for T in tune.TS:
                Rw, F = [], 0
                for r in rs:
                    rows, fa = tune.rescore(r, T, calib_for(r) if use else None)
                    Rw.append(rows); F += fa
                Rw = np.concatenate(Rw)
                out.append((T, Rw[:, 0].mean(), np.nanmean(np.abs(Rw[:, 1])), np.nanmean(Rw[:, 1]), F / len(rs), 0))
            v = tune.at_fa(np.array(out), t["fa"])
            line += " %s %+4.0f/%+4.1f bias %+4.1f" % (m[0].upper(), v[1] - t["pos"], v[2] - t["mae"], v[3])
        print(line, flush=True)
