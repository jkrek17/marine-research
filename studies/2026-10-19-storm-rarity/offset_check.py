"""How deep does ERA5 (pipeline A) put a low compared with the OPC archive at the same place and time?

The rarity badge ranks a forecast low's pressure against ERA5 lifetime minima. Forecast lows sit within
about 1-2 hPa of the archive at day 1-2 (studies/2026-10-18-hf-depth), so the ERA5-minus-archive pressure
at matched fixes is the offset the badge inherits. Reads hf-low's era5-tracks.js and the archive CSVs over
HTTPS (cached by rk). Writes offset.csv next to this file.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import numpy as np
import pandas as pd
from rk import fetch, paths, truth
from rk.score import km

URL = "https://raw.githubusercontent.com/jkrek17/hf-low/main/docs/data/era5-tracks.js"


def era5_fixes():
    p = paths.cache("truth", "hf_lows", "era5-tracks.js")
    if not p.exists():
        p.write_bytes(fetch.get(URL).content)
    t = p.read_text()
    d = json.loads(t[t.index("{"):t.rstrip().rstrip(";").rindex("}") + 1])
    rows = []
    for tr, basin, season, start, _p, _g, _m, fx in d["ev"]:
        t0 = datetime.strptime(str(start), "%Y%m%d%H")
        for i in range(0, len(fx), 4):
            rows.append((tr, t0 + timedelta(hours=6 * (i // 4)), fx[i] / 4, (fx[i + 1] / 4) % 360, fx[i + 2]))
    return pd.DataFrame(rows, columns=["track", "valid", "lat", "lon", "hpa"])


def main():
    e = era5_fixes()
    out = []
    for basin in ("natl", "npac"):
        a = truth.hf_archive(basin)
        a = a[a.hpa.notna() & (a.category == "HF")]
        g = e.groupby("valid")
        for r in a.itertuples():
            if r.valid not in g.groups:
                continue
            c = g.get_group(r.valid)
            d = km(c.lat.values, c.lon.values, r.lat, r.lon)
            j = int(np.argmin(d))
            if d[j] <= 300:
                out.append((basin, r.event_id, r.valid, r.lat, r.hpa, c.hpa.values[j], d[j]))
    o = pd.DataFrame(out, columns=["basin", "event", "valid", "lat", "archive_hpa", "era5_hpa", "km"])
    o["diff"] = o.era5_hpa - o.archive_hpa
    o.to_csv(HERE / "offset.csv", index=False)
    ev = o.groupby(["basin", "event"])["diff"].median()
    for b in ("natl", "npac"):
        x, y = o[o.basin == b]["diff"], ev[b]
        print(b, "fixes", len(x), "events", len(y), "median fix ERA5-archive %.1f hPa" % x.median(),
              "event-median %.1f [IQR %.1f, %.1f]" % (y.median(), y.quantile(.25), y.quantile(.75)))


if __name__ == "__main__":
    main()
