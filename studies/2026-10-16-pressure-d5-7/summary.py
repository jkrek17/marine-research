"""Tables from evaluate.py records. Run: python3 summary.py TAG [held|tune|all] [deep]"""
import os, sys, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

OUT = lib.RECORDS


def load(tag):
    with open(os.path.join(OUT, "records_%s.pkl" % tag), "rb") as f:
        return pickle.load(f)["recs"]


def common(recs):
    """keep only cases where every system is present (same cases for all)"""
    from collections import defaultdict
    by = defaultdict(set)
    for r in recs:
        by[(r["ymd"], r["dom"], r["step"])].add(r["sys"])
    allsys = set().union(*by.values()) if by else set()
    ok = {k for k, v in by.items() if v == allsys}
    return [r for r in recs if (r["ymd"], r["dom"], r["step"]) in ok]


def stats(rs, deep=False):
    rows = [r["rows"] for r in rs if len(r["rows"])]
    R = np.concatenate(rows) if rows else np.zeros((0, 4))
    if deep:
        R = R[R[:, 3] < 980]
    nc = len(rs)
    return {"cases": nc, "lows": len(R), "pos": R[:, 0].mean() if len(R) else np.nan,
            "hit": R[:, 2].mean() if len(R) else np.nan, "bias": np.nanmean(R[:, 1]) if len(R) else np.nan,
            "mae": np.nanmean(np.abs(R[:, 1])) if len(R) else np.nan,
            "fa": sum(r["fa"] for r in rs) / max(nc, 1), "nf": sum(r["nf"] for r in rs) / max(nc, 1)}


def table(recs, subset="tune", deep=False, systems=None):
    recs = common(recs)
    if subset == "held":
        recs = [r for r in recs if r["held"]]
    elif subset == "tune":
        recs = [r for r in recs if r["tune"]]
    systems = systems or sorted({r["sys"] for r in recs})
    lines = ["%-14s %-4s %4s %5s %5s | %6s %5s %6s %5s | %5s %5s" % ("system", "dom", "lead", "cases", "lows", "pos", "hit", "bias", "mae", "FA/c", "n<1000")]
    for dom in ("natl", "npac", "both"):
        for step in lib.STEPS:
            for s in systems:
                rs = [r for r in recs if r["sys"] == s and r["step"] == step and (dom == "both" or r["dom"] == dom)]
                if not rs:
                    continue
                t = stats(rs, deep)
                lines.append("%-14s %-4s %4d %5d %5d | %6.0f %5.2f %+6.1f %5.1f | %5.2f %5.2f" % (
                    s, dom, step, t["cases"], t["lows"], t["pos"], t["hit"], t["bias"], t["mae"], t["fa"], t["nf"]))
            lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    tag = sys.argv[1]
    sub = sys.argv[2] if len(sys.argv) > 2 else "tune"
    print(table(load(tag), sub, deep="deep" in sys.argv))
