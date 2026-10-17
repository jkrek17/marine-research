"""Motion-relative IR crops at every pilot fix -> the seven IR features (features.csv) and the mean crops per
basin and category, tuning weeks only (composites.npz under RK_CACHE/extra/hf-satellite, not in git).

    python3 studies/2026-10-17-hf-satellite/features.py

Crops: rk.satellite.crop, 1200 km half-width, 10 km pixels, storm motion up (north up for one-fix events).
A fix is kept for the features when at least 90% of its crop within 1000 km has IR.
"""
import numpy as np
import pandas as pd

from common import HERE, fixes
from rk import paths, satellite

HALF, RES = 1200.0, 10.0
COLD, WARM = 233.0, 260.0          # -40 C cloud top; > -13 C mostly cloud free or low cloud
MIN_VALID = 0.9

X, Y = satellite.grid_offsets(HALF, RES)
R = np.hypot(X, Y)
REL = np.degrees(np.arctan2(X, Y)) % 360          # 0 ahead, 90 right of track, 180 behind
SECTOR = (REL // 30).astype(int)


def feats(c):
    """Seven IR features of one crop (K) -> dict, plus valid share within 1000 km."""
    ok = np.isfinite(c)
    d = {"valid1000": ok[R <= 1000].mean()}

    def m(sel):
        v = c[sel & ok]
        return v

    r500, r1000 = R <= 500, R <= 1000
    d["cold500"] = np.mean(m(r500) < COLD)
    d["cold1000"] = np.mean(m(r1000) < COLD)
    d["p05_500"] = np.percentile(m(r500), 5)
    d["centre_minus_ring"] = m(R < 150).mean() - m((R >= 150) & (R < 500)).mean()
    ring = (R >= 200) & (R <= 800)
    d["dryslot"] = np.mean(m(ring & (REL >= 90) & (REL < 180)) > WARM)
    d["cloudhead"] = np.mean(m(ring & (REL >= 180)) < COLD)
    band = (R >= 300) & (R <= 700)
    d["asym"] = np.std([m(band & (SECTOR == k)).mean() for k in range(12)])
    return d


FEATURES = ["cold500", "cold1000", "p05_500", "centre_minus_ring", "dryslot", "cloudhead", "asym"]


def main():
    d = fixes()
    rows, sums = [], {}
    boxes = {}
    for i, f in d.iterrows():
        t = f["valid"].to_pydatetime()
        key = (f["basin"], t)
        if key not in boxes:
            boxes.clear()
            boxes[key] = satellite.box(f["basin"], t, download=False)
        b = boxes[key]
        row = {k: f[k] for k in ("basin", "event_id", "valid", "lat", "lon", "hpa", "category", "head", "split")}
        if b is None:
            row["status"] = "no imagery"
            rows.append(row)
            continue
        head = None if np.isnan(f["head"]) else float(f["head"])
        c = satellite.crop(b, f["lat"], f["lon"], HALF, RES, head=head)
        iy = int(np.argmin(abs(b["lat"] - f["lat"])))
        ix = int(np.argmin(abs(b["lon"] - (f["lon"] if f["lon"] >= b["lon"][0] else f["lon"] + 360))))
        row["vza"] = float(b["vza"][iy, ix])
        row["sat"] = str(b["satnames"][b["sat"][iy, ix]]) if b["sat"][iy, ix] >= 0 else ""
        ft = feats(c)
        row.update(ft)
        row["status"] = "ok" if ft["valid1000"] >= MIN_VALID else "partial view"
        rows.append(row)
        if row["status"] == "ok" and f["split"] == "tune":          # composites from tuning weeks only
            k = (f["basin"], f["category"])
            s, n = sums.get(k, (np.zeros_like(c, np.float64), np.zeros_like(c, np.float64)))
            ok = np.isfinite(c)
            s[ok] += c[ok]
            n[ok] += 1
            sums[k] = (s, n)
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "features.csv", index=False, float_format="%.4f")
    print(out.groupby(["basin", "category", "status"]).size().unstack(fill_value=0))
    comp = {}
    for (b, cat), (s, n) in sums.items():
        comp["%s_%s" % (b, cat)] = np.where(n > 0, s / np.maximum(n, 1), np.nan).astype(np.float32)
        comp["%s_%s_n" % (b, cat)] = n.astype(np.int16)
    np.savez_compressed(paths.cache("extra", "hf-satellite", "composites.npz"), **comp)


if __name__ == "__main__":
    main()
