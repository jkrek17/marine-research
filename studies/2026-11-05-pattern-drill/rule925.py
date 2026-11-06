"""Pattern drill: the forecaster's shortcut, "strongest 925 mb wind on the map x a mixing factor" (Jason 2026-11-06).

Per snapshot (the deck's analysis maps, and the GFS +24 h forecast maps of fc_deck.py): the 20 strongest 925 mb
cells over water in the map box; w = the 3rd highest (as the ASCAT answer uses its 3rd highest cell); d = the
largest sea minus 2 m air among those 20 cells. Factor = median ASCAT answer / w within each d class
(< 2 C, 2-5 C, 5 C+). Fitted on the winters 2024-25 and 2025-26 (the first 174 cases) and tested on the three
earlier winters, which were added after the factors were first quoted, so that test is out of sample.
Then refitted on all winters and written to the deck manifest as "rule925" (the page reads it).

    python3 rule925.py [--deck page/deck] [--no-write]
"""
import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CUTS = [2.0, 5.0]
TOP = 20


def cat(k):
    return 0 if k < 34 else 1 if k < 48 else 2 if k < 64 else 3


def snap_fields(u, s, m):
    F, n = m["fields"], m["ny"] * m["nx"]
    nf = len(F)
    base = s * (nf + 3) * n

    def field(key):
        i = [f["key"] for f in F].index(key)
        f = F[i]
        q = u[base + i * n: base + (i + 1) * n].astype(float)
        return np.where(q == 255, np.nan, f["offset"] + f["scale"] * q)
    land = u[base + (nf + 2) * n: base + (nf + 3) * n] > 0
    return field("wspd925"), field("sst_air"), land


def predictor(u, s, m):
    w, d, land = snap_fields(u, s, m)
    ok = ~land & np.isfinite(w) & np.isfinite(d)
    if ok.sum() < 3:
        return None
    idx = np.argsort(np.where(ok, w, -1.0))[::-1][:TOP]
    return float(w[idx[2]]), float(np.nanmax(d[idx]))


def klass(d):
    return 0 if d < CUTS[0] else 1 if d < CUTS[1] else 2


def fit(rows):
    return [round(float(np.median([r["obs"] / r["w"] for r in rows if klass(r["d"]) == k])), 2) for k in range(3)]


def score(rows, f, label):
    rc = np.array([cat(r["w"] * f[klass(r["d"])]) for r in rows])
    oc = np.array([r["cat"] for r in rows])
    st = oc >= 2
    out = {"n": len(rows), "exact": round(100 * float((rc == oc).mean())),
           "storm_plus_exact": round(100 * float((rc[st] == oc[st]).mean())) if st.any() else None,
           "hf_caught": int(((rc == 3) & (oc == 3)).sum()), "hf": int((oc == 3).sum()),
           "hf_over": int(((rc == 3) & (oc == 2)).sum()), "storm": int((oc == 2).sum())}
    if all("gfs" in r for r in rows):
        gc = np.array([r["gfs"] for r in rows])
        out.update(gfs_exact=round(100 * float((gc == oc).mean())),
                   gfs_storm_plus_exact=round(100 * float((gc[st] == oc[st]).mean())) if st.any() else None,
                   gfs_hf_caught=int(((gc == 3) & (oc == 3)).sum()))
    print(label, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default=str(HERE / "page" / "deck"))
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    deck = Path(a.deck)
    m = json.loads((deck / "manifest.json").read_text())
    rows = {"now": [], "fc": []}
    for c in m["cases"]:
        early = int(c["id"][1:]) >= 315   # ids from 315 on are the three winters added 2026-11-06
        u = np.fromfile(deck / (c["id"] + ".bin"), np.uint8)
        for s, k in ((0, "t0"), (1, "t24")):
            p = predictor(u, s, m)
            if p:
                rows["now"].append({"w": p[0], "d": p[1], "obs": c[k]["peak"], "cat": c[k]["cat"], "early": early})
        g = c.get("fc", {}).get("gfs")
        if g and (deck / (c["id"] + "_fc_gfs.bin")).exists():
            p = predictor(np.fromfile(deck / (c["id"] + "_fc_gfs.bin"), np.uint8), 0, m)
            if p:
                rows["fc"].append({"w": p[0], "d": p[1], "obs": c["t24"]["peak"], "cat": c["t24"]["cat"],
                                   "gfs": g["cat"], "early": early})
    f_train = fit([r for r in rows["now"] if not r["early"]])
    print("factors fitted on 2024-26 analysis snapshots:", f_train)
    res = {"fit_2024_26": f_train}
    for g in ("now", "fc"):
        res[g + "_in_sample"] = score([r for r in rows[g] if not r["early"]], f_train, g + " 2024-26 (in sample)")
        test = [r for r in rows[g] if r["early"]]
        if test:
            res[g + "_held_out"] = score(test, f_train, g + " 2021-24 (held out)")
    f_all = fit(rows["now"])
    print("factors refitted on all winters:", f_all)
    res["f"] = f_all
    (HERE / "rule925.json").write_text(json.dumps(res, indent=1))
    if not a.no_write:
        m["rule925"] = {"cuts": CUTS, "f": f_all, "top": TOP}
        (deck / "manifest.json").write_text(json.dumps(m, separators=(",", ":")))
        print("manifest: rule925", m["rule925"])


if __name__ == "__main__":
    main()
