"""Air-mass measures (design.md, air-mass addendum) at every pilot fix -> features_airmass.csv (with the IR
measures from features.csv joined), and mean air-mass bands per basin and category, tuning weeks only
(composites_airmass.npz under RK_CACHE/extra/hf-satellite).

    python3 studies/2026-10-17-hf-satellite/features_airmass.py
"""
import numpy as np
import pandas as pd

from common import HERE
from features import HALF, MIN_VALID, R, REL, RES
from rk import paths, satellite

BANDS = ("b08", "b10", "b12", "b13")
AM = ["ozone_p10_500", "ozone_rear", "wv_p90_500", "wv_dryslot", "wv_contrast", "red_share"]


def am_feats(c):
    """Six air-mass measures from the four band crops (K) -> dict, plus valid share within 1000 km."""
    ok = np.all([np.isfinite(c[k]) for k in BANDS], 0)
    oz, wv, red = c["b12"] - c["b13"], c["b08"], c["b08"] - c["b10"]
    d = {"am_valid1000": ok[R <= 1000].mean()}
    r500, ring = (R <= 500) & ok, (R >= 200) & (R <= 800) & ok
    d["ozone_p10_500"] = np.percentile(oz[r500], 10)
    d["ozone_rear"] = oz[ring & (REL >= 90) & (REL < 270)].mean()
    d["wv_p90_500"] = np.percentile(wv[r500], 90)
    d["wv_dryslot"] = wv[ring & (REL >= 90) & (REL < 180)].mean()
    v800 = wv[(R <= 800) & ok]
    d["wv_contrast"] = np.percentile(v800, 90) - np.percentile(v800, 10)
    d["red_share"] = np.mean((red[r500] > -10) & (oz[r500] < -22))
    return d


def main():
    d = pd.read_csv(HERE / "features.csv", parse_dates=["valid"])
    rows, sums = [], {}
    for _, f in d.iterrows():
        row = {"basin": f["basin"], "event_id": f["event_id"], "valid": f["valid"]}
        b = satellite.airmass_box(f["basin"], f["valid"].to_pydatetime(), download=False)
        if b is None:
            rows.append(dict(row, am_status="no air mass"))
            continue
        head = None if np.isnan(f["head"]) else float(f["head"])
        c = {k: satellite.crop({"lat": b["lat"], "lon": b["lon"], "tb": b[k]}, f["lat"], f["lon"], HALF, RES, head)
             for k in BANDS}
        iy = int(np.argmin(abs(b["lat"] - f["lat"])))
        ix = int(np.argmin(abs(b["lon"] - (f["lon"] if f["lon"] >= b["lon"][0] else f["lon"] + 360))))
        row["am_vza"] = float(b["vza"][iy, ix])
        row["am_sat"] = str(b["satnames"][0])
        ok = np.all([np.isfinite(c[k]) for k in BANDS], 0)
        if ok[R <= 1000].mean() < MIN_VALID:
            rows.append(dict(row, am_status="partial view", am_valid1000=ok[R <= 1000].mean()))
            continue
        row.update(am_feats(c))
        row["am_status"] = "ok"
        rows.append(row)
        if f["split"] == "tune" and f["status"] == "ok" and f["category"] in ("HF", "S"):
            k = (f["basin"], f["category"])
            s, n = sums.get(k, ({b_: np.zeros(ok.shape) for b_ in BANDS}, np.zeros(ok.shape)))
            for b_ in BANDS:
                s[b_][ok] += c[b_][ok]
            n[ok] += 1
            sums[k] = (s, n)
    am = pd.DataFrame(rows)
    out = d.merge(am, on=["basin", "event_id", "valid"], how="left")
    out.to_csv(HERE / "features_airmass.csv", index=False, float_format="%.4f")
    print(out[out.category.isin(["HF", "S"])].groupby(["basin", "category", "am_status"]).size().unstack(fill_value=0))
    comp = {}
    for (b, cat), (s, n) in sums.items():
        for b_ in BANDS:
            comp["%s_%s_%s" % (b, cat, b_)] = np.where(n > 0, s[b_] / np.maximum(n, 1), np.nan).astype(np.float32)
        comp["%s_%s_n" % (b, cat)] = n.astype(np.int16)
    np.savez_compressed(paths.cache("extra", "hf-satellite", "composites_airmass.npz"), **comp)


if __name__ == "__main__":
    main()
