"""Pick the fixed 20-case benchmark: deck/bench.json.

Version 2 (Jason 2026-11-06, "the benchmark test does growth/decay. that needs to change"): the benchmark is
20 Beat the model cases, so only cases with a GFS +24 h forecast and not in the Storm or HF? extras (pool=hf).

Stratified by the +24 h category (5 per category: none, gale, storm, HF) with the two basins mixed inside each
category; deterministic (cases ranked by an md5 of the id, no random numbers), so every run of this script and
every device get the same 20 cases in the same order.

    python3 make_bench.py
"""
import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
N_PER_CAT = 5


def rank(cid):
    return hashlib.md5(("bench-v2:" + cid).encode()).hexdigest()


def select(manifest):
    cases = [c for c in manifest["cases"] if c.get("t0") and c.get("t24") and (c.get("fc") or {}).get("gfs")
             and c.get("pool") != "hf"]
    chosen = []
    for cat in range(4):
        pool = sorted((c for c in cases if c["t24"]["cat"] == cat), key=lambda c: rank(c["id"]))
        by_basin = {}
        for c in pool:
            by_basin.setdefault(c["basin"], []).append(c)
        basins = sorted(by_basin, key=lambda b: -len(by_basin[b]))     # larger pool first
        picked = []
        while len(picked) < N_PER_CAT and any(by_basin[b] for b in basins):
            for b in basins:                                            # alternate basins while both have cases
                if by_basin[b] and len(picked) < N_PER_CAT:
                    picked.append(by_basin[b].pop(0))
        chosen += picked
    chosen.sort(key=lambda c: rank("order:" + c["id"]))                 # interleave the categories
    return chosen


if __name__ == "__main__":
    m = json.loads((here / "deck" / "manifest.json").read_text())
    ch = select(m)
    out = {"version": 2, "n": len(ch), "ids": [c["id"] for c in ch],
           "note": "20 Beat the model cases, 5 per +24 h category, basins mixed; excluded from practice and blitz."}
    (here / "deck" / "bench.json").write_text(json.dumps(out, separators=(",", ":")))
    cnt = {}
    for c in ch:
        cnt[(c["t24"]["cat"], c["basin"])] = cnt.get((c["t24"]["cat"], c["basin"]), 0) + 1
    print(len(ch), "bench cases", sorted(cnt.items()))
