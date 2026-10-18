"""Motion-relative IR crops of every measured fix (design.md, learned-features addendum), averaged 4x4 to 60x60
pixels (40 km), written once to RK_CACHE/extra/hf-satellite/crops.npz with the fix table beside them.

    python3 studies/2026-10-17-hf-satellite/crops.py
"""
import warnings

import numpy as np
import pandas as pd

from common import HERE  # noqa: F401  (puts the repo on sys.path)
from features import HALF, RES
from rk import paths, satellite

POOL = 4


def pooled(c):
    """Average POOL x POOL blocks of a crop (K), ignoring missing pixels; missing blocks get the crop mean."""
    n = (c.shape[0] // POOL) * POOL
    v = c[:n, :n].reshape(n // POOL, POOL, n // POOL, POOL)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmean(v, axis=(1, 3))
    return np.where(np.isfinite(m), m, np.nanmean(m)).astype(np.float32)


def main():
    d = pd.read_csv(paths.data("hf-satellite", "features_full.csv"), parse_dates=["valid"])
    d = d[d["status"] == "ok"].sort_values(["basin", "valid"]).reset_index(drop=True)
    out, box_key, b = [], None, None
    for i, f in d.iterrows():
        key = (f["basin"], f["valid"])
        if key != box_key:
            b, box_key = satellite.box(f["basin"], f["valid"].to_pydatetime(), download=True), key
        head = None if np.isnan(f["head"]) else float(f["head"])
        out.append(pooled(satellite.crop(b, f["lat"], f["lon"], HALF, RES, head=head)))
        if i % 500 == 0:
            print(i, len(d), flush=True)
    x = np.stack(out).astype(np.float16)
    cols = ["basin", "event_id", "valid", "lat", "lon", "hpa", "category", "split"]
    np.savez_compressed(paths.cache("extra", "hf-satellite", "crops.npz"), x=x,
                        **{c: d[c].astype(str).to_numpy(dtype=str) for c in cols})
    print("wrote", x.shape)


if __name__ == "__main__":
    main()
