"""Agent vs TFP vs persistence on the 50 test cases: drill score, matched / type / position / extras, and paired
differences with a storm-block bootstrap (cases of the same low within 48 h and 1000 nm resampled together).
  python3 compare.py   -> compare.csv (one row per method and basin), fronts.csv (one row per analysed front and method)
"""
import csv
import json

import numpy as np

import common
import deck

HERE = common.HERE
METHODS = {"agent": "agent_answers.json", "tfp": "tfp_test_drawn.json", "persist": "persist_test_drawn.json"}


def load(name):
    d = json.loads((HERE / METHODS[name]).read_text())
    return {k: (v["fronts"] if isinstance(v, dict) else v) for k, v in d.items()}


def storms(ids, man, vt):
    by = {c["id"]: c for c in man["cases"]}
    lab = {}
    for i in sorted(ids, key=lambda x: vt[x]):
        for j in list(lab):
            if abs((vt[i] - vt[j]).total_seconds()) <= 48 * 3600 and deck._nm(by[i]["low"]["lat"], by[i]["low"]["lon"], by[j]["low"]["lat"], by[j]["low"]["lon"]) <= 1000:
                lab[i] = lab[j]
                break
        else:
            lab[i] = i
    return lab


def boot(diff, lab, n=10000, seed=1):
    groups = {}
    for k, g in enumerate(lab):
        groups.setdefault(g, []).append(k)
    G = list(groups.values())
    rng = np.random.default_rng(seed)
    m = []
    for _ in range(n):
        pick = rng.integers(0, len(G), len(G))
        idx = [k for p in pick for k in G[p]]
        m.append(diff[idx].mean())
    return np.percentile(m, [5, 95])


def main():
    ids = deck.test_ids()
    man = deck.manifest()
    vt = deck.valid_times()
    basin = {c["id"]: c["basin"] for c in man["cases"]}
    sc = {m: common.score({i: [{"type": f["type"], "pts": f["pts"]} for f in load(m)[i]] for i in ids}) for m in METHODS}
    pct = {m: np.array([sc[m][i]["pct"] for i in ids]) for m in METHODS}
    lab = storms(ids, man, vt)
    labs = [lab[i] for i in ids]
    rows, frows = [], []
    for m in METHODS:
        for b in ("all", "natl", "npac"):
            sel = [k for k, i in enumerate(ids) if b == "all" or basin[i] == b]
            R = [r for k in sel for r in sc[m][ids[k]]["rows"]]
            mt = [r for r in R if r["matched"]]
            rows.append({"method": m, "basin": b, "cases": len(sel), "mean_pct": round(float(pct[m][sel].mean()), 1),
                         "analysed_fronts": len(R), "matched": len(mt), "type_right": sum(r["drawnType"] == r["type"] for r in mt),
                         "median_dist_nm": round(float(np.median([r["dist"] for r in mt])), 0) if mt else None,
                         "extras": sum(sc[m][ids[k]]["extras"] for k in sel), "zero_score_cases": int((pct[m][sel] == 0).sum())})
        for i in ids:
            for r in sc[m][i]["rows"]:
                frows.append({"method": m, "id": i, "basin": basin[i], "type": r["type"], "len_nm": round(r["len"]), "matched": r["matched"],
                              "drawn_type": r["drawnType"], "dist_nm": None if r["dist"] is None else round(r["dist"])})
    for a, b in (("agent", "tfp"), ("agent", "persist"), ("persist", "tfp")):
        d = pct[a] - pct[b]
        lo, hi = boot(d, labs)
        rows.append({"method": f"{a} - {b}", "basin": "all", "cases": len(ids), "mean_pct": round(float(d.mean()), 1),
                     "analysed_fronts": None, "matched": f"90% {lo:.1f} to {hi:.1f}", "type_right": f"wins {int((d > 0).sum())} losses {int((d < 0).sum())}",
                     "median_dist_nm": None, "extras": None, "zero_score_cases": f"{len(set(labs))} storms"})
    for name, R in (("compare.csv", rows), ("fronts.csv", frows)):
        with open(HERE / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(R[0]))
            w.writeheader()
            w.writerows(R)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
