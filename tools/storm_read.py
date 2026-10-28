#!/usr/bin/env python3
"""Storm read: follow one named low through every model run and ensemble member and write a page.

    python3 tools/storm_read.py --valid 2026110112 --parent 2026103112,36,310 --basin natl --name "Central Atlantic bomb"

Pulls through rk.fetch (cached under rk.paths.cache("storm-read", basin)), tracks with rk.storm_read, writes
summary.json, tracks.json, the figures and page.html into --out. How it works: tools/storm_read.md.
"""
import argparse
import base64
import datetime as dt
import gzip
import html
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rk import KT, basins, bomb, cases, paths, storm_read as sr, style  # noqa: E402

DET_MODELS = ("gfs", "ifs", "aifs", "aigfs")
ENSEMBLES = ("gefs", "ens", "aifs-ens")
TEMPLATE = ROOT / "tools" / "storm_read_page.html"
H6 = dt.timedelta(hours=6)
COLORS = dict(style.METHOD_COLORS)
COLORS["aigfs"] = "#0f9d9a"
ENS_COLORS = {e: COLORS[p] for e, p in sr.ENS_PARENT.items()}
ENS_MAX_STEP = 360


# ---------------------------------------------------------------- times and steps

def steps_of(valid):
    """Valid times pulled for MSLP: valid-48 h to valid+24 h every 6 h (13)."""
    return [valid + H6 * i for i in range(-8, 5)]


def wind_window(valid):
    return valid - dt.timedelta(hours=24), valid + dt.timedelta(hours=12)


def det_cycles(cycle, runs):
    """The newest `runs` deterministic cycles, 12 h apart, ending at `cycle`; oldest first."""
    return [cycle - dt.timedelta(hours=12 * i) for i in range(runs)][::-1]


def latest_cycle(now=None):
    """The most recent 00 or 12 UTC cycle at or before `now` (default: the current UTC time)."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0, hour=12 if now.hour >= 12 else 0)


def newest_ens_cycle(valid, now=None):
    """Newest 00/12 UTC cycle (not after `valid`) whose ECMWF ENS file for valid+24 h is posted."""
    from rk import fetch
    c = latest_cycle(now)
    last = valid + dt.timedelta(hours=24)
    for _ in range(10):
        step = int((last - c).total_seconds() // 3600)
        if c <= valid and 0 <= step <= ENS_MAX_STEP:
            base = fetch.sources.ecmwf("ifs", "enfo", "ef", c.strftime("%Y%m%d"), c.strftime("%H"), step)
            if fetch.nwp.ec_records(base) is not None:
                return c
        c -= dt.timedelta(hours=12)
    raise SystemExit("storm_read: no recent cycle with ECMWF ENS posted for %s; pass --cycle" % cases.tag(last))


# ---------------------------------------------------------------- pull (cached)

def _enc(msl):
    return np.round(np.asarray(msl, np.float32) * 10.0 - 10000.0).astype(np.int16)


def _save(path, **arrs):
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **arrs)
    tmp.replace(path)


def _speed(d):
    return (np.hypot(d["u"], d["v"]) * KT).astype(np.float16)


def pull_det_one(basin, model, cycle, valid):
    """One deterministic field -> (msl hPa, speed kt) on the basin grid, from the cache or the fetch; None if not posted."""
    from rk import fetch
    step = int((valid - cycle).total_seconds() // 3600)
    if step < 0:
        return None
    f = paths.cache("storm-read", basin, "det_%s_%s_%03d.npz" % (model, cases.tag(cycle), step))
    if not f.exists():
        try:
            r = fetch.det(model, cycle, step)
        except Exception as e:   # one bad file never stops the read
            print("storm_read: %s %s +%d h: %s" % (model, cases.tag(cycle), step, e), file=sys.stderr)
            return None
        if r is None:
            return None
        _save(f, msl=_enc(r[basin]["msl"]), speed=_speed(r[basin]))
    z = np.load(f)
    return bomb.dec(z["msl"]), z["speed"].astype(np.float32)


def pull_det(basin, cycles, valid):
    """-> {model: {cycle tag: {t: (msl, speed)}}}"""
    jobs = [(m, c, t) for m in DET_MODELS for c in cycles for t in steps_of(valid)]
    with ThreadPoolExecutor(4) as ex:
        got = list(ex.map(lambda j: pull_det_one(basin, *j), jobs))
    out = {}
    for (m, c, t), g in zip(jobs, got):
        if g is not None:
            out.setdefault(m, {}).setdefault(cases.tag(c), {})[t] = g
    return out


def pull_ens_one(basin, ens, cycle, valid, key):
    """One ensemble step -> (msl [n,y,x], speed [n,y,x] | None) from the cache or the fetch; None if not posted.
    Wind (the large part) is pulled only inside the key time's wind window."""
    from rk import fetch
    step = int((valid - cycle).total_seconds() // 3600)
    w0, w1 = wind_window(key)
    wind = w0 <= valid <= w1
    if step < 0 or step > ENS_MAX_STEP:
        return None
    f = paths.cache("storm-read", basin, "ens_%s_%s_%03d.npz" % (ens, cases.tag(cycle), step))
    if f.exists():
        z = np.load(f)
        if not wind or "speed" in z.files:
            return bomb.dec(z["msl"]), (z["speed"].astype(np.float32) if "speed" in z.files else None)
    try:
        r = fetch.members(ens, cycle, step, msl=True, wind=wind)
    except Exception as e:
        print("storm_read: %s %s +%d h: %s" % (ens, cases.tag(cycle), step, e), file=sys.stderr)
        return None
    if r is None:
        return None
    arrs = {"msl": _enc(r[basin]["msl"])}
    if wind:
        arrs["speed"] = _speed(r[basin])
    _save(f, **arrs)
    z = np.load(f)
    return bomb.dec(z["msl"]), (z["speed"].astype(np.float32) if "speed" in z.files else None)


def pull_ens(basin, cycle, valid):
    """-> {ens: {t: (msl, speed | None)}}. Steps with fewer members than the fullest step are dropped (member
    numbers would no longer line up)."""
    out = {}
    for e in ENSEMBLES:
        got = {}
        for t in steps_of(valid):
            g = pull_ens_one(basin, e, cycle, t, valid)
            if g is not None:
                got[t] = g
            print("storm_read: %s %s %s" % (e, sr.tstr(t), "n=%d" % len(g[0]) if g else "missing"), file=sys.stderr)
        if got:
            n = max(len(g[0]) for g in got.values())
            got = {t: g for t, g in got.items() if len(g[0]) == n}
            out[e] = got
    return out


# ---------------------------------------------------------------- tracking

def analyze(det, ens, lats, lons, t0, lat0, lon0):
    """-> (tracks_det {model: {cycle: points|None}}, tracks_ens {ens: [points|None per member]})"""
    td, te = {}, {}
    for m, cs in det.items():
        for c, fl in cs.items():
            msl = {t: g[0] for t, g in fl.items()}
            spd = {t: g[1] for t, g in fl.items() if g[1] is not None}
            td.setdefault(m, {})[c] = sr.track(msl, spd, lats, lons, t0, lat0, lon0)
    for e, fl in ens.items():
        n = len(next(iter(fl.values()))[0])
        te[e] = [sr.track({t: g[0][i] for t, g in fl.items()},
                          {t: g[1][i] for t, g in fl.items() if g[1] is not None}, lats, lons, t0, lat0, lon0)
                 for i in range(n)]
    return td, te


# ---------------------------------------------------------------- the marine wind page's fields

def page_fields(ref, valid):
    """Decode the page's Core Lifted wind, warning bits and mean MSLP for `valid` from a local awips-tools clone
    (git show of `ref`). -> (dict | None, note)."""
    if not ref or ref == "none":
        return None, "Page fields were switched off (--page-run none)."
    repo = ROOT.parent / "awips-tools"
    if not (repo / ".git").exists():
        return None, "No local awips-tools clone next to this repository, so the page's own fields are not drawn."

    def show(path):
        r = subprocess.run(["git", "-C", str(repo), "show", "%s:%s" % (ref, path)], capture_output=True)
        if r.returncode:
            raise FileNotFoundError("%s:%s" % (ref, path))
        return r.stdout
    try:
        man = json.loads(show("latest/global/manifest.json"))
        cyc = dt.datetime.strptime(man["cycle"], "%Y-%m-%dT%H:%MZ")
        step = int((valid - cyc).total_seconds() // 3600)
        have = [s["step"] for s in man["steps"]]
        if step not in have:
            return None, ("The page's %sZ run reaches +%d h at most, not the +%d h this read needs."
                          % (cyc.strftime("%d %H"), max(have), step))
        F = {f["name"]: f for f in man["fields"]}
        out = {"cycle": man["cycle"], "step": step}
        for name in ("windcore", "warn", "msl"):
            b = np.frombuffer(gzip.decompress(show("latest/global/f%03d/%s.gz" % (step, name))), np.uint8).reshape(721, 1440)
            v = np.cumsum(b.astype(np.int64), axis=1) % 256
            out[name] = v + 900.0 if name == "msl" else v / F[name]["scale"] - F[name]["offset"]
    except Exception as e:
        return None, "The page's fields could not be read (%s)." % e
    lon = (-180 + 0.25 * np.arange(1440) + 360) % 360
    o = np.argsort(lon)
    out["lon"], out["lat"] = lon[o], 90 - 0.25 * np.arange(721)
    for n in ("windcore", "warn", "msl"):
        out[n] = out[n][:, o]
    return out, "Page run %sZ +%d h." % (cyc.strftime("%d %H"), step)


# ---------------------------------------------------------------- figures

def _jit(i, n):
    return np.random.default_rng(i).uniform(-0.18, 0.18, n)


def _rows(ens_keys):
    top = 3 + len(ens_keys)
    return {e: top - 1 - i for i, e in enumerate(ens_keys)}, top


def _lab(t):
    return t.strftime("%a %d %HZ")


def figures(summary, tracks, valid, outdir, page):
    """Write the PNG/SVG figures -> {name: path of the png}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style.use()
    D, E = tracks["det"], tracks["ens"]
    latest = summary["latest"]
    ens_keys = [e for e in ENSEMBLES if e in E]
    ey, top = _rows(ens_keys)
    models = [m for m in DET_MODELS if m in D and D[m].get(latest)]
    my = {m: 1.6 - 0.35 * j for j, m in enumerate(models)}
    times = steps_of(valid)
    x0 = times[0]
    X = lambda t: (t - x0).total_seconds() / 3600
    lt = lambda s: dt.datetime.strptime(s, "%Y%m%d%H").strftime("%d %b %HZ")
    out = {}
    ylab = [ey[e] for e in ens_keys] + [1.1]
    ylabn = [sr.NAMES[e] for e in ens_keys] + ["Models"]

    # 1 central pressure
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for e in ens_keys:
        M = E[e]
        q = []
        for t in times:
            v = [sr.at(m, t)["p"] for m in M if sr.at(m, t)]
            q.append(np.percentile(v, [10, 50, 90]) if len(v) >= 0.5 * len(M) else [np.nan] * 3)
        q = np.array(q)
        ax.fill_between([X(t) for t in times], q[:, 0], q[:, 2], color=ENS_COLORS[e], alpha=0.13, lw=0)
        ax.plot([X(t) for t in times], q[:, 1], color=ENS_COLORS[e], dashes=(4, 2), lw=1.6,
                label=f"{sr.NAMES[e]} middle, 10-90% shaded")
    for m in models:
        tr = D[m][latest]
        ax.plot([X(sr.tparse(x["t"])) for x in tr], [x["p"] for x in tr], color=COLORS[m], lw=2.2, label=sr.NAMES[m])
    ax.axvline(X(valid), color=style.INK2, lw=0.8)
    ax.set_xticks([X(t) for t in times[::2]])
    ax.set_xticklabels([_lab(t) for t in times[::2]])
    ax.set_ylabel("Central pressure (hPa)")
    ax.legend(fontsize=8, ncol=2, loc="lower left")
    style.title(ax, "How deep: central pressure of the low", f"{lt(latest)} runs; vertical line = {_lab(valid)}")
    style.save(fig, outdir / "pressure")
    plt.close(fig)
    out["pressure"] = outdir / "pressure.png"

    # 2 deepening (Bergeron: strongest 24 h along the track)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    allb = [1.5]
    for i, e in enumerate(ens_keys):
        b = np.array([r for r in (sr.bergeron(m, valid)[0] for m in E[e] if m) if r is not None])
        allb += list(b)
        ax.scatter(b, ey[e] + _jit(i, len(b)), s=10, color=ENS_COLORS[e], alpha=0.55, lw=0)
    xmax = max(allb) + 0.45
    for e in ens_keys:
        ax.text(xmax - 0.05, ey[e], f"{100 * summary['ens'][e]['bomb_share']:.0f}% bomb", va="center", ha="right",
                fontsize=9, color=ENS_COLORS[e])
    for m in models:
        b = sr.bergeron(D[m][latest], valid)[0]
        if b is not None:
            ax.scatter([b], [my[m]], marker="D", s=40, color=COLORS[m])
            ax.text(b + 0.04, my[m], sr.NAMES[m], va="center", fontsize=8, color=COLORS[m])
    ax.axvline(1, color=style.INK, lw=1)
    ax.text(1.01, top + 0.5, "bomb line", fontsize=8, color=style.INK2)
    ax.set_yticks(ylab)
    ax.set_yticklabels(ylabn)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0.3, top + 0.8)
    ax.set_xlabel("Fastest 24 h deepening (Bergeron: 1 = bomb, latitude-adjusted 24 hPa/24 h at 60N)")
    style.title(ax, "How fast: every member and model", f"one dot per tracked member, {lt(latest)} runs")
    style.save(fig, outdir / "bomb")
    plt.close(fig)
    out["bomb"] = outdir / "bomb.png"

    # 3 peak wind near the low at the key time
    fig, ax = plt.subplots(figsize=(8, 3.6))
    allw = [70.0]
    for i, e in enumerate(ens_keys):
        w = np.array([p["wmax"] for p in (sr.at(m, valid) for m in E[e]) if p and p["wmax"] is not None])
        allw += list(w)
        ax.scatter(w, ey[e] + _jit(i, len(w)), s=10, color=ENS_COLORS[e], alpha=0.55, lw=0)
    for m in models:
        p = sr.at(D[m][latest], valid)
        if p and p["wmax"] is not None:
            allw.append(p["wmax"])
    hi = max(allw) + 8
    xr = hi + 4
    for e in ens_keys:
        k = summary["ens"][e]["key"]
        ax.text(xr, ey[e], " / ".join(f"{100 * k[str(t)]:.0f}%" for t in sr.THRESH), va="center", fontsize=9, color=ENS_COLORS[e])
    ax.text(xr, top + 0.45, "34 / 48 / 64 kt", fontsize=8, color=style.INK2)
    for m in models:
        p = sr.at(D[m][latest], valid)
        if p and p["wmax"] is not None:
            ax.scatter([p["wmax"]], [my[m]], marker="D", s=40, color=COLORS[m])
            ax.text(p["wmax"] + 0.8, my[m], sr.NAMES[m], va="center", fontsize=8, color=COLORS[m])
    for k, n in ((34, "gale"), (48, "storm"), (64, "hf")):
        ax.axvline(k, color=style.HAZARD_COLORS[n], lw=1)
    ax.set_yticks(ylab)
    ax.set_yticklabels(ylabn)
    ax.set_xlim(20, hi)
    ax.set_ylim(0.3, top + 0.8)
    ax.set_xlabel(f"Highest 10 m wind within {sr.WIND_KM:.0f} km of the low, {_lab(valid)} (kt)")
    style.title(ax, "How strong: highest wind near the low", f"one dot per tracked member, {lt(latest)} runs; shares at right (all members)")
    ax.spines["right"].set_visible(False)
    fig.subplots_adjust(right=0.82)
    style.save(fig, outdir / "wind")
    plt.close(fig)
    out["wind"] = outdir / "wind.png"

    # 4 run to run
    cycs = sorted({c for m in D for c in D[m]})
    if len(cycs) > 1:
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.6))
        for m in DET_MODELS:
            xs, p, w = [], [], []
            for i, c in enumerate(cycs):
                x = sr.at(D.get(m, {}).get(c), valid)
                if x:
                    xs.append(i)
                    p.append(x["p"])
                    w.append(x["wmax"])
            if xs:
                a1.plot(xs, p, marker="o", color=COLORS[m], label=sr.NAMES[m])
                a2.plot(xs, [np.nan if v is None else v for v in w], marker="o", color=COLORS[m])
        for a in (a1, a2):
            a.set_xticks(range(len(cycs)))
            a.set_xticklabels([f"{c[6:8]}/{c[8:]}Z" for c in cycs], fontsize=8)
        a1.set_ylabel(f"hPa at {_lab(valid)}")
        a2.set_ylabel(f"kt within {sr.WIND_KM:.0f} km")
        a1.legend(fontsize=8)
        for k, n in ((48, "storm"), (64, "hf")):
            a2.axhline(k, color=style.HAZARD_COLORS[n], lw=0.8)
        style.title(a1, "Run to run: depth", "model run (day/cycle)")
        style.title(a2, "Run to run: peak wind", "model run (day/cycle)")
        style.save(fig, outdir / "runs")
        plt.close(fig)
        out["runs"] = outdir / "runs.png"

    # 5 map with the page's fields
    if page:
        out["map"] = _map(page, summary, tracks, valid, outdir, ens_keys, models)
    return out


def _map(page, summary, tracks, valid, outdir, ens_keys, models):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    D, E, latest = tracks["det"], tracks["ens"], summary["latest"]
    pts = [x for m in models for x in D[m][latest]] + [x for e in ens_keys for tr in E[e] if tr for x in tr]
    la, lo = np.array([x["lat"] for x in pts]), np.array([x["lon"] for x in pts])
    bx = next(b for b in basins.BASINS.values() if b["west"] <= np.median(lo) <= b["east"])
    b = dict(south=max(bx["south"], la.min() - 3), north=min(bx["north"], la.max() + 3),
             west=max(bx["west"], lo.min() - 5), east=min(bx["east"], lo.max() + 5))
    fig, ax = plt.subplots(figsize=(9, 6.4))
    style.map_axes(b, ax=ax)
    r = (page["lat"] >= b["south"] - 1) & (page["lat"] <= b["north"] + 1)
    c = (page["lon"] >= b["west"] - 1) & (page["lon"] <= b["east"] + 1)
    X, Y = page["lon"][c], page["lat"][r]
    sub = lambda a: a[r][:, c]
    pm = ax.pcolormesh(X, Y, sub(page["windcore"]), cmap=style.wind_cmap(), norm=style.wind_norm(), shading="nearest", zorder=1)
    ax.contour(X, Y, sub(page["msl"]), levels=range(900, 1060, 4), colors="#5f5e5a", linewidths=0.5, zorder=2)
    wn = sub(page["warn"]).astype(int)
    for bit, name in ((1, "gale"), (2, "storm"), (4, "hf")):
        if ((wn & bit) > 0).any():
            ax.contour(X, Y, ((wn & bit) > 0).astype(float), levels=[0.5], colors=style.HAZARD_COLORS[name],
                       linewidths=1.8, linestyles="--", zorder=4)
    for e in ens_keys:
        p = [sr.at(m, valid) for m in E[e] if m]
        p = [x for x in p if x]
        ax.scatter([x["lon"] for x in p], [x["lat"] for x in p], s=9, color=ENS_COLORS[e], alpha=0.7, lw=0, zorder=5,
                   label=f"{sr.NAMES[e]} members at {_lab(valid)}")
    for m in models:
        tr = D[m][latest]
        ax.plot([x["lon"] for x in tr], [x["lat"] for x in tr], color=COLORS[m], lw=2, zorder=6, label=sr.NAMES[m] + " track")
        k = sr.at(tr, valid)
        if k:
            ax.scatter([k["lon"]], [k["lat"]], s=50, color=COLORS[m], edgecolor="white", zorder=7)
    h, l = ax.get_legend_handles_labels()
    h += [Line2D([], [], color=style.HAZARD_COLORS[n], ls="--") for n in ("gale", "storm", "hf")]
    l += ["Gale warning area", "Storm warning area", "HF warning area"]
    ax.legend(h, l, fontsize=7.5, loc="upper left", ncol=1, frameon=True, facecolor="white", framealpha=0.9)
    style.wind_colorbar(fig, pm, ax)
    pc = dt.datetime.strptime(page["cycle"], "%Y-%m-%dT%H:%MZ")
    style.title(ax, f"Where: Core Lifted wind and warning areas, {_lab(valid)}",
                f"page run {pc.strftime('%HZ %d %b')} (+{page['step']} h); tracks and member lows from the "
                f"{dt.datetime.strptime(summary['latest'], '%Y%m%d%H').strftime('%HZ %d %b')} runs; isobars page mean, 4 hPa")
    style.save(fig, outdir / "map")
    plt.close(fig)
    return outdir / "map.png"


# ---------------------------------------------------------------- page

def _fig(key, files, alt, caption):
    if key not in files:
        return ""
    b64 = base64.b64encode(Path(files[key]).read_bytes()).decode()
    return ('<figure><img src="data:image/png;base64,%s" alt="%s"><figcaption>%s</figcaption></figure>'
            % (b64, html.escape(alt), html.escape(caption)))


def _table(summary):
    latest, key = summary["latest"], sr.tparse(summary["key"])
    rows = []
    for m, cs in summary["det"].items():
        r = cs.get(latest)
        if not r:
            continue
        if not r["tracked"] or r["p"] is None:
            rows.append((sr.NAMES[m], "no low at the key time", "", "", "no" if not r["tracked"] else ""))
            continue
        rows.append((sr.NAMES[m], "%.0f" % r["p"], sr._pos(r["lat"], r["lon"]),
                     "%.0f (%s)" % (r["pmin"], sr._when(r["tmin"])),
                     ("yes" if r["bomb"] else "no") + (", %.2f" % r["berg"] if r["berg"] is not None else "")))
    for e, s in summary["ens"].items():
        if s["p"] is None:
            rows.append(("%s (%d)" % (sr.NAMES[e], s["n"]), "no tracked low at the key time", "", "", ""))
            continue
        rows.append(("%s (%d)" % (sr.NAMES[e], s["n"]), "%.0f-%.0f, middle %.0f" % (s["p"][0], s["p"][2], s["p"][1]),
                     "middle %.0fN" % s["lat"], "middle %.0f" % s["pmin"], "%.0f%% of members" % (100 * s["bomb_share"])))
    body = "\n".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(c) for c in r) for r in rows)
    return ("<tr><th>%s</th><th>Low (hPa)</th><th>Where</th><th>Lowest (time)</th><th>Bomb?</th></tr>\n%s"
            % (html.escape(sr._when(summary["key"])), body))


def build_page(summary, meta, files, page_note, nar):
    key = sr.tparse(summary["key"])
    pl = summary.get("pooled")
    nmem = pl["n"] if pl else 0
    models = [sr.NAMES[m] for m, cs in summary["det"].items() if summary["latest"] in cs]
    run = dt.datetime.strptime(summary["latest"], "%Y%m%d%H")
    sub = ("Read made %s from the %sZ %s runs (day %.1f), %s. It uses %s and %d deterministic model%s (%s), with each low "
           "tracked forward from the parent low at %s."
           % (meta["made"], run.strftime("%H"), run.strftime("%d %b"), (key - run).total_seconds() / 86400,
              meta["page_phrase"], ("all %d ensemble members" % nmem) if nmem else "no ensemble members",
              len(models), "" if len(models) == 1 else "s", ", ".join(models), meta["parent_phrase"]))
    if summary.get("note"):
        sub += " " + summary["note"]
    p = lambda s: "<p>%s</p>" % html.escape(s) if s else ""
    figs = {
        "map": _fig("map", files, "Map of the page's Core Lifted wind, warning areas and model tracks",
                    "The page's Core Lifted wind and warning areas with the tracks of the latest deterministic runs and the "
                    "members' lows at the key time. " + page_note + " Averaging models whose lows sit apart smooths the core "
                    "away: read the warning lines and the members, not the blend."),
        "pressure": _fig("pressure", files, "Central pressure by model and ensemble over time",
                         "Solid lines are the deterministic runs. Dashed lines are the ensemble middles, with 10-90% of members "
                         "shaded (drawn where at least half the members have a low)."),
        "bomb": _fig("bomb", files, "Fastest 24-hour deepening of every member and model",
                     "Each dot is one tracked member. The percentage counts all members of that ensemble; a member that loses "
                     "the low counts as no bomb."),
        "wind": _fig("wind", files, "Highest 10 m wind near the low at the key time",
                     "Shares on the right are all members at 34, 48 and 64 kt or more (an untracked member counts as below). "
                     "The lines are the gale, storm and hurricane-force thresholds."),
        "runs": _fig("runs", files, "Run-to-run change in depth and peak wind at the key time",
                     "Pressure and highest wind near the low at the key time in each deterministic run."),
    }
    if not figs["map"]:
        figs["map"] = '<p class="note">Map of the page\'s fields not drawn. %s</p>' % html.escape(page_note)
    vals = {
        "title": html.escape(meta["name"]), "key_label": html.escape(sr._when(summary["key"])),
        "subtitle": html.escape(sub), "sentence_bomb": p(nar["bomb"]), "sentence_depth": p(nar["depth"]),
        "sentence_wind": p(nar["wind"]), "sentence_trend": p(nar["trend"]),
        "caveats": "\n".join("<li>%s</li>" % html.escape(c) for c in nar["caveats"]),
        "table": _table(summary), "fig_map": figs["map"], "fig_pressure": figs["pressure"], "fig_bomb": figs["bomb"],
        "fig_wind": figs["wind"], "fig_runs": figs["runs"], "method": html.escape(meta["method"]),
    }
    page = TEMPLATE.read_text()
    for k, v in vals.items():
        page = page.replace("{{%s}}" % k, v)
    if "{{" in page:
        raise SystemExit("storm_read: unfilled placeholder in the page template: %s" % page[page.index("{{"):][:40])
    return page


# ---------------------------------------------------------------- main

def parse_parent(s):
    t, la, lo = s.split(",")
    return cases.parse(t), float(la), float(lo) % 360


def run(args):
    valid, (t0, lat0, lon0) = cases.parse(args.valid), parse_parent(args.parent)
    if t0 not in steps_of(valid):
        raise SystemExit("storm_read: parent time %s is outside valid-48 h .. valid+24 h on the 6 h grid" % cases.tag(t0))
    basin = args.basin
    lats, lons = basins.grid(basin)
    out = Path(args.out) if args.out else paths.data("extra", "storm-read", "%s-%s" % (cases.tag(valid), basin))
    out.mkdir(parents=True, exist_ok=True)
    cycle = cases.parse(args.cycle) if args.cycle else (latest_cycle() if args.no_ens else newest_ens_cycle(valid))
    print("storm_read: cycle %s, valid %s, parent %s %.2fN %.2fE" % (cases.tag(cycle), args.valid, cases.tag(t0), lat0, lon0), file=sys.stderr)
    det = pull_det(basin, det_cycles(cycle, args.runs), valid)
    ens = {} if args.no_ens else pull_ens(basin, cycle, valid)
    return finish(args, valid, t0, lat0, lon0, basin, lats, lons, out, cycle, det, ens)


def finish(args, valid, t0, lat0, lon0, basin, lats, lons, out, cycle, det, ens):
    """Everything after the pull: tracks, summary, figures, page (so a test can feed it fields)."""
    td, te = analyze(det, ens, lats, lons, t0, lat0, lon0)
    w0, w1 = wind_window(valid)
    summary = sr.summarize(td, te, valid, w0, w1)
    page, page_note = page_fields(args.page_run, valid)
    nar = sr.narrative(summary)
    now = dt.datetime.now(dt.timezone.utc)
    page_phrase = ("plus the marine wind page's %sZ run" % dt.datetime.strptime(page["cycle"], "%Y-%m-%dT%H:%MZ").strftime("%d %b %H")
                   if page else "without the marine wind page's fields")
    meta = {"name": args.name or "Storm read, " + sr._when(summary["key"]), "valid": sr.tstr(valid),
            "parent": {"t": sr.tstr(t0), "lat": lat0, "lon": lon0}, "basin": basin, "cycle": cases.tag(cycle),
            "runs": args.runs, "page_run": page and page["cycle"], "page_note": page_note,
            "made": now.strftime("%d %b %H:%MZ"), "page_phrase": page_phrase,
            "parent_phrase": "%s, %.1fN %.1f%s" % (sr._when(sr.tstr(t0)), lat0, 360 - lon0 if lon0 > 180 else lon0, "W" if lon0 > 180 else "E"),
            "method": ("Lows come from the shared bomb-watch low finder (rk.bomb) and are tracked forward every 6 h from the parent low "
                       "(nearest low within %d km at the parent time, then the nearest within %d km each step, both directions). Peak wind "
                       "is the highest 10 m wind within %d km of each run's own low. Deterministic runs: the last %d cycles of GFS, ECMWF, "
                       "AIFS and AI-GFS; ensembles: %s from the %sZ %s run. Pulled through rk.fetch from the AWS open-data mirrors."
                       % (sr.PARENT_KM, sr.STEP_KM, sr.WIND_KM, args.runs, "none" if not ens else "GEFS, ECMWF ENS, AIFS ENS",
                          cases.tag(cycle)[8:], cases.tag(cycle)[4:8]))}
    tracks = {"det": td, "ens": te}
    (out / "tracks.json").write_text(json.dumps(tracks))
    (out / "summary.json").write_text(json.dumps({"meta": meta, **summary, "narrative": nar}, indent=1))
    files = figures(summary, tracks, valid, out, page)
    (out / "page.html").write_text(build_page(summary, meta, files, page_note, nar))
    print("storm_read: wrote %s" % (out / "page.html"), file=sys.stderr)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH, the time the read is about")
    ap.add_argument("--parent", required=True, help="YYYYMMDDHH,lat,lon of the parent low (lon 0-360 or negative west)")
    ap.add_argument("--basin", required=True, choices=sorted(basins.BASINS))
    ap.add_argument("--cycle", help="YYYYMMDDHH of the newest run (default: newest with ECMWF ENS posted)")
    ap.add_argument("--runs", type=int, default=5, help="deterministic runs, 12 h apart (default 5)")
    ap.add_argument("--name", help="page title")
    ap.add_argument("--out", help="output folder (default: RK_DATA/extra/storm-read/<valid>-<basin>)")
    ap.add_argument("--no-ens", action="store_true", help="deterministic models only")
    ap.add_argument("--page-run", default="origin/marine-wind-live", metavar="REF",
                    help="git ref of the marine wind page data in the sibling awips-tools clone ('none' to skip)")
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
