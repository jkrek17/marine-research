"""Method 3: buoys and ships against ASCAT and SMAP, winter 2025-26 (Atlantic 12 UTC, Pacific 00 UTC cycles).

Obs: rk.truth.obs(..., platforms=("buoy","drifter","ship","fixed"), max_dt=0.5) (real 10 m wind, buoys raised to 10 m,
ships x0.88, 75 fixed coastal stations removed by the function). Instrument cell: nearest within 25 km among cells
within 30 min of the valid time (rain-free ASCAT with intercalibration; SMAP as is), equivalent-neutral wind converted
to real 10 m wind with rk.truth.enw_to_real and the GFS air-sea temperature difference (rk.truth.airsea) at the cell.
The obs time is only known to +-30 min around the valid time (obs() averages a station's reports), so a pair is
within 60 min worst case, about 30 typical.
Run: python3 obs_pairs.py   (needs the truth/obs cache from obs_fill.py)"""
import datetime as dt
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare import WORK  # noqa: E402
sys.path.insert(0, str(HERE.parents[1]))
from rk import basins, fetch, truth  # noqa: E402
from summarize import boot_stat, f_mean, week_sums  # noqa: E402

START, END = dt.date(2025, 11, 1), dt.date(2026, 3, 31)
R_EARTH = 6371.0


def xyz(lat, lon):
    la, lo = np.radians(lat.astype(float)), np.radians(lon.astype(float))
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], 1)


def cells_near(valid, basin):
    """ASCAT (rain-free, intercalibrated) and SMAP cells within 30 min of valid, inside the basin box."""
    out = {}
    days = sorted({(valid - dt.timedelta(minutes=30)).date(), (valid + dt.timedelta(minutes=30)).date()})
    for name, fn in (("ascat", truth.ascat_day), ("smap", truth.smap_day)):
        parts = []
        for d in days:
            c = fn(d)
            if c is None:
                continue
            c = dict(c)
            c["dt_min"] = c["t_min"].astype(np.float32) + (dt.datetime.combine(d, dt.time()) - valid).total_seconds() / 60.0
            if name == "ascat":
                c["spd_enw_kt"] = truth._intercal(c["spd_enw_kt"], c["sat"])
                c["ok"] = (c["scat_rain"] == 0) & (c["rad_rain"] < 2)
            else:
                c["ok"] = np.ones(len(c["lat"]), bool)
            parts.append({k: c[k] for k in ("lat", "lon", "dt_min", "spd_enw_kt", "ok")})
        if not parts:
            continue
        c = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        k = (np.abs(c["dt_min"]) <= 30) & c["ok"] & basins.inside(basin, c["lat"], c["lon"])
        out[name] = {f: v[k] for f, v in c.items()}
    return out


def run():
    fetch.wait_for_quiet()
    rows = []
    n_cyc = n_obs = 0
    for i in range((END - START).days + 1):
        day = START + dt.timedelta(days=i)
        for b, info in basins.BASINS.items():
            valid = dt.datetime.combine(day, dt.time(info["hour"]))
            o = truth.obs(b, valid, platforms=("buoy", "drifter", "ship", "fixed"), max_dt=0.5)
            if o is None or not len(o["lat"]):
                continue
            n_cyc += 1
            n_obs += len(o["lat"])
            cells = cells_near(valid, b)
            matches = {}
            for name, c in cells.items():
                if not len(c["lat"]):
                    continue
                d, j = cKDTree(xyz(c["lat"], c["lon"])).query(xyz(o["lat"], o["lon"]))
                km = 2 * R_EARTH * np.arcsin(np.clip(d / 2, 0, 1))
                ok = km <= 25.0
                if ok.any():
                    matches[name] = (np.nonzero(ok)[0], j[ok], km[ok])
            if not matches:
                continue
            a = truth.airsea(b, valid)
            if a is None:
                continue
            iso = day.isocalendar()
            for name, (io, jc, km) in matches.items():
                c = cells[name]
                dT = basins.sample(a, b, c["lat"][jc], c["lon"][jc])
                real = truth.enw_to_real(c["spd_enw_kt"][jc], np.where(np.isfinite(dT), dT, 0.0))
                for k in range(len(io)):
                    rows.append(dict(instrument=name, basin=b, valid=str(valid), week=iso[0] * 100 + iso[1],
                                     held_out=bool(__import__("rk.cases", fromlist=["x"]).held_out(day)),
                                     station=o["station_id"][io[k]], platform=o["platform"][io[k]],
                                     obs_kt=float(o["speed_kt"][io[k]]), inst_real_kt=float(real[k]),
                                     inst_enw_kt=float(c["spd_enw_kt"][jc[k]]), dist_km=float(km[k]),
                                     dt_min=float(c["dt_min"][jc[k]]), dT=float(dT[k])))
    df = pd.DataFrame(rows)
    (WORK).mkdir(exist_ok=True)
    df.to_pickle(WORK / "obs_pairs.pkl")
    return df, n_cyc, n_obs


def summarize(df):
    df = df.copy()
    df["d"] = df.inst_real_kt - df.obs_kt
    df["mean_pair"] = 0.5 * (df.inst_real_kt + df.obs_kt)
    bands = [("25-34", 25, 34), ("34-48", 34, 48), ("48+", 48, 1e9), ("25+", 25, 1e9)]
    out = []
    for inst in ("ascat", "smap"):
        for plat in ["all", "buoy", "drifter", "ship", "fixed"]:
            for basin in ("all", "natl", "npac"):
                s = df[df.instrument == inst]
                if plat != "all":
                    s = s[s.platform == plat]
                if basin != "all":
                    s = s[s.basin == basin]
                for bn, lo, hi in bands:
                    t = s[(s.mean_pair >= lo) & (s.mean_pair < hi)]
                    if not len(t):
                        continue
                    row = dict(instrument=inst, platform=plat, basin=basin, band=bn, n=len(t), n_weeks=t.week.nunique(),
                               n_stations=t.station.nunique(), mean_obs=t.obs_kt.mean(), mean_inst=t.inst_real_kt.mean(),
                               bias=t.d.mean(), sd=t.d.std(ddof=1) if len(t) > 1 else np.nan, bias_lo=np.nan, bias_hi=np.nan)
                    if len(t) >= 5:
                        uw, W = week_sums(t.week.to_numpy(), np.stack([np.ones(len(t)), t.d.to_numpy()], 1))
                        p, l, h = boot_stat(W, f_mean)
                        row.update(bias_lo=l[0], bias_hi=h[0])
                    out.append(row)
    return pd.DataFrame(out)


if __name__ == "__main__":
    import time
    t0 = time.time()
    df, n_cyc, n_obs = run()
    print("cycles with obs %d, obs %d, pairs %d (ascat %d, smap %d), %.0f s" % (
        n_cyc, n_obs, len(df), (df.instrument == "ascat").sum(), (df.instrument == "smap").sum(), time.time() - t0))
    s = summarize(df)
    s.round(3).to_csv(WORK / "obs_summary.csv", index=False)
    print(s[(s.basin == "all")].round(2).to_string())
