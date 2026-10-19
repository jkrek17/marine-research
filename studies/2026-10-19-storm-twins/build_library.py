"""Storm Twins library: the 32,288 ERA5 pipeline A fixes (Oct-Apr 2014-15 to 2021-22) with their frozen 15 pattern
components and next-24 h gust class -> RK_DATA/lab/twins_library.npz, plus the 00/12 UTC climatology the live job
subtracts -> RK_DATA/lab/twins_clim0012.npz (float16).

Inputs: the rebuilt patches in STORM_PATCH_DIR (default /mnt/project-files/storm-patches, hf-low
storm_patch_analogs/extract_patches.py) and committed hf-low files read from HF_RESEARCH (a checkout of the hf-low
research branch): gfs/results/frozen_pca_full.npz and results/oof_hf_prob.csv.gz.
Run: HF_RESEARCH=<hf-low research checkout> python3 build_library.py
"""
import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import paths, twins  # noqa: E402

SD = Path(os.environ.get("STORM_PATCH_DIR", "/mnt/project-files/storm-patches"))
HF = Path(os.environ["HF_RESEARCH"]) / "research" / "era5" / "storm_patch_analogs"


def main():
    keys, xs = [], []
    for f in sorted(glob.glob(str(SD / "patches" / "*.npz"))):
        z = np.load(f)
        keys += [str(k) for k in z["keys"]]
        xs.append(z["x"])
    X = np.concatenate(xs).astype(np.float32)
    pca = twins.Frozen(HF / "gfs" / "results" / "frozen_pca_full.npz")
    pcs = pca.pcs(X)
    o = pd.read_csv(HF / "results" / "oof_hf_prob.csv.gz", dtype={"time": str}).set_index("key")
    o = o.loc[keys]
    out = paths.data("lab", "twins_library.npz")
    np.savez_compressed(out, pcs=pcs.astype(np.float32), track=o.track.values.astype(np.int64),
                        time=o.time.values.astype("U10"), basin=o.basin.values.astype("U3"),
                        season=o.season.values.astype(np.int16), lat=o.lat.values.astype(np.float32),
                        lon=o.lon.values.astype(np.float32), msl=o.msl.values.astype(np.float32),
                        gcls=o.gcls.values.astype(np.int8))
    c = np.load(SD / "clim_patch.npz")
    hours = list(c["hour"])
    pick = [hours.index(0), hours.index(12)]
    clim = paths.data("lab", "twins_clim0012.npz")
    np.savez_compressed(clim, doy=c["doy"], hour=np.array([0, 12]),
                        **{k: c[k][pick].astype(np.float16) for k in ("z500", "msl", "u250", "v250")})
    print(len(keys), "fixes; HF-outcome share %.3f;" % (o.gcls.values == 3).mean(),
          "%.1f MB library, %.1f MB clim" % (out.stat().st_size / 1e6, clim.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
