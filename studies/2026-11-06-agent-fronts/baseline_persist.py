"""Reference baseline: the analysed fronts from 6 h earlier, moved with the low (persistence). Not a first guess the
agent could use at a forecast hour, but it says how much of the answer the previous analysis already holds.
Needs rk.fronts (front drill, PR #75). Writes persist_test.csv.
  python3 baseline_persist.py
"""
import csv
import json
import datetime as dt

import numpy as np

import common
import deck
try:
    from rk import fronts as rkf
except ImportError:     # front drill not merged yet: load rk/fronts.py from its branch checkout (RK_FRONTS_PY)
    import importlib.util
    import os
    import sys
    spec = importlib.util.spec_from_file_location("rk.fronts", os.environ["RK_FRONTS_PY"])
    rkf = importlib.util.module_from_spec(spec)
    sys.modules["rk.fronts"] = rkf
    spec.loader.exec_module(rkf)

HERE = common.HERE


def km(la1, lo1, la2, lo2):
    return deck._nm(la1, lo1, la2, lo2) * 1.852


def persist(case, valid):
    a = rkf.analysis(valid - dt.timedelta(hours=6))
    if a is None:
        return None
    low = case["low"]
    best = None
    for p, la, lo in a["lows"]:
        d = km(la, lo, low["lat"], low["lon"])
        if d < 800 and (best is None or d + 20 * abs(p - low["hpa"]) < best[0]):
            best = (d + 20 * abs(p - low["hpa"]), la, lo)
    if best is None:
        return []
    _, la0, lo0 = best
    dla, dlo = low["lat"] - la0, ((low["lon"] - lo0 + 180) % 360) - 180
    fr = [f for f in a["fronts"] if f["type"] in ("cold", "warm", "occluded", "stationary")]
    ends = lambda f: [(f["lat"][0], f["lon"][0]), (f["lat"][-1], f["lon"][-1])]
    sys_ = [f for f in fr if min(km(y, x, la0, lo0) for y, x in ends(f)) <= 300]
    for f in fr:     # one pass of attachment: an end within 60 nm of a system front point
        if any(f is s for s in sys_):
            continue
        if any(min(deck._nm(y, x, a2, b2) for a2, b2 in zip(s["lat"], s["lon"])) <= 60 for s in sys_ for y, x in ends(f)):
            sys_.append(f)
    out = []
    for f in sys_:
        if f["type"] == "stationary":
            continue
        out.append({"type": f["type"], "pts": [[float(y) + dla, (float(x) + dlo) % 360] for y, x in zip(f["lat"], f["lon"])]})
    return out


def main():
    man = deck.manifest()
    vt = deck.valid_times()
    byid = {c["id"]: c for c in man["cases"]}
    ids = deck.test_ids()
    drawn = {i: (persist(byid[i], vt[i]) or []) for i in ids}
    (HERE / "persist_test_drawn.json").write_text(json.dumps(drawn))
    sc = common.score(drawn)
    with open(HERE / "persist_test.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "basin", "pct", "n_truth", "n_matched", "n_type_right", "extras"])
        for i in ids:
            r = sc[i]
            w.writerow([i, byid[i]["basin"], round(r["pct"], 1), len(r["rows"]), sum(x["matched"] for x in r["rows"]),
                        sum(x["matched"] and x["drawnType"] == x["type"] for x in r["rows"]), r["extras"]])
    print("persistence test mean", round(float(np.mean([sc[i]["pct"] for i in ids])), 1))


if __name__ == "__main__":
    main()
