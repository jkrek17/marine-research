"""Run every candidate over the winter and score it (design.md; BUILD.md "score.py + run.py + analyze.py").

    python3 run.py [--limit N] [--workers W] [--cycles YYYYMMDDHH ...] [--basins natl npac] [--stub]
    python3 run.py --merge              # only combine the per-case parts into basin-month parquet files

Reads one basin-cycle extract file per worker (rk.paths.cache("extra","mslp-blend-d7",basin,"YYYYMMDDHH.npz"),
MSLP only; 12 UTC cycles also read the day 5-7 member files through rk.store), builds every candidate for every
lead through candidates.build, and scores each against the GFS analysis, the IFS analysis and their mean.

Output under rk.paths.cache("extra","mslp-blend-d7","scores"):
  parts/{basin}/{YYYYMMDDHH}.npz-like set: field_*.parquet, lows_*.parquet, fdeep_*.parquet, risk_*.parquet,
      one set per basin-cycle (the resume unit: a basin-cycle with its `done` marker is skipped);
  {field,lows,fdeep,risk}_{basin}_{YYYYMM}.parquet   the parts merged per basin-month (--merge, run at the end).
Columns on every table: basin, cycle, lead, valid, truth (gfs, ifs, mean), cand, setting, week (ISO week of the
cycle), split (rk.cases.split on the cycle), valid_held (valid time in a held-out week: tuning leaves these out
too), month.
  field   rmse, bias, rmse_ls, sharp, false_n, n_fc          (one row per case x candidate x setting x truth)
  lows    per analysed low: lat, lon, an_hpa, pos_km, depth_err_hpa, hit, pos_h, fc_lat, fc_lon, fc_hpa,
          along_km, cross_km
  fdeep   per forecast low < 980 hPa: fc_hpa, an_hpa, err_hpa, lat, lon
  risk    outlier-drop records (candidate od / od_gfe): the dropped run, its distance to the consensus, its
          low, the analysed low, whether the dropped low was the closest of all runs' lows to it
Settings: "default" is candidates.build with params=None (untuned values); a tuning grid value v of key K from
candidates.grid_values() appears as "K=v" for the candidates that use K.
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
from rk import cases as rkc, paths, score as rks

BASINS = ("natl", "npac")
LEADS = tuple(range(24, 169, 24))
ROOT = paths.cache("extra", "mslp-blend-d7", "_root").parent
OUT = Path(os.environ.get("MSLP_BLEND_SCORES") or ROOT / "scores")     # override for smoke tests
PARTS = OUT / "parts"
D57 = REPO / "studies" / "2026-10-16-pressure-d5-7"
TRUTHS = ("gfs", "ifs", "mean")
# which tuning-grid key each candidate uses
KEY_OF = {"al": "cap", "ald": "cap", "al_gfe": "cap", "ald_gfe": "cap", "od": "X", "od_gfe": "X",
          "off": "off", "wb": "w", "wb_gfe": "w"}
VOTE_W = {"gefs": 1, "ens": 1, "aifsens": 1, "gfs": 0.3, "ifs": 0.3, "aifs": 0.3}
VOTE_R = 450.0
RUNS = ("gfs", "ifs", "aifs", "aigfs", "gefs", "ens", "aifsens")     # inputs whose own lows the risk table uses
_EXTRACT_NAME = {"gefs": "gefs", "ens": "ens", "aifsens": "aifs-ens"}


# ---------------------------------------------------------------- candidates (real module or stub)

def _stub_build(basin, cycle, lead, z, members=None, params=None):
    """Stand-in until candidates.py exists: singles and equal means from the extract file."""
    L = "f%03d" % lead
    d = {m: z["%s_%s" % (m, L)] for m in ("gfs", "ifs", "aifs", "aigfs") if "%s_%s" % (m, L) in z}
    out = dict(d)
    for name, ks in (("m_gi", ("gfs", "ifs")), ("m_gia", ("gfs", "ifs", "aigfs")), ("m_gif", ("gfs", "ifs", "aifs"))):
        if all(k in d for k in ks):
            out[name] = np.mean([d[k] for k in ks], 0).astype(np.float32)
    for name, key in (("gefs", "gefs"), ("ens", "ens"), ("aifsens", "aifs-ens")):
        if "%s_mean_%s" % (key, L) in z:
            out[name] = z["%s_mean_%s" % (key, L)]
    return out


def load_candidates(stub=False):
    if not stub:
        try:
            import candidates
            return candidates, False
        except ImportError:
            print("candidates.py not found: using the stub (singles and equal means only)", file=sys.stderr)

    class Stub:
        build = staticmethod(_stub_build)

        @staticmethod
        def grid_values():
            return {}
    return Stub, True


def build_all(cm, basin, cycle, lead, z, members):
    """[(cand, setting, field)] for every setting. candidates.build_grid labels the untuned singles/means
    "base"; those and each tuned family's untuned value are relabelled "default" in `emit` (UNTUNED)."""
    if hasattr(cm, "build_grid"):
        return cm.build_grid(basin, cycle, lead, z, members=members)
    return [(n, "base", f) for n, f in cm.build(basin, cycle, lead, z, members=members).items()]


# the setting that equals candidates' untuned defaults, per candidate (DEFAULTS cap 450, X 300; wb equal weights)
UNTUNED = {"al": "cap=450", "ald": "cap=450", "al_gfe": "cap=450", "ald_gfe": "cap=450",
           "od": "X=300", "od_gfe": "X=300", "wb": "w=eq", "wb_gfe": "w=eq",
           "al_gfe2": "cap=450", "ald_gfe2": "cap=450", "od_gfe2": "X=300", "wb_gfe2": "w=eq"}


# ---------------------------------------------------------------- members and vote

def load_members(basin, tag):
    """12 UTC day 5-7 member files merged into one dict (int16 as stored), or None."""
    from rk import store
    out = {}
    for name in ("mslpd57_noaa", "mslpd57_ec"):
        try:
            z = store.load(basin, tag, name)
        except Exception:
            z = None
        if z:
            out.update(z)
    try:            # store.load unpacked the whole cycle zip: keep only mslpd57_* and unpublished files
        import extract
        extract.clean(basin, datetime.strptime(tag, "%Y%m%d%H"))
    except Exception as ex:
        print("clean failed", basin, tag, repr(ex), file=sys.stderr)
    return out or None


_VOTE = {}


def _vote_mod():
    if not _VOTE:
        sys.path.insert(0, str(D57))
        import method as vm       # noqa: E402  (the day 5-7 study's vote; imported, not copied)
        with open(D57 / "results" / "final.json") as f:
            fin = json.load(f)
        _VOTE.update(m=vm, T={int(k): v for k, v in fin["T"].items()})
    return _VOTE


def vote_lows(basin, lead, mem):
    """Member-vote lows (lat, lon, hpa, support, spread_km) from the 12 UTC member files, or None."""
    if mem is None or lead not in (120, 144, 168):
        return None
    V = _vote_mod()
    vm = V["m"]
    c = {"det": {}, "mem": {}, "mlows": {}, "lag": {}}
    for m in ("gfs", "ifs", "aifs"):
        k = "det_%s_%s_%d" % (m, basin, lead)
        if k not in mem:
            return None
        c["det"][m] = mem[k].astype(np.float32) / 10.0 + 1000.0
    for en in ("gefs", "ens", "aifsens"):
        k = "mem_%s_%s_%d" % (en, basin, lead)
        if k in mem:
            c["mem"][en] = mem[k]
            c["mlows"][en] = mem["low_%s_%s_%d" % (en, basin, lead)]
    if "gefs" not in c["mem"] or "ens" not in c["mem"]:
        return None
    Vt = vm.voters(c, basin, VOTE_W, use_lag=False)
    return vm.consensus(Vt, R=VOTE_R, T=V["T"][lead], q=0.5)


def score_vote(vl, tp, basin):
    """Vote lows scored like a field's lows, position and depth only (a miss has no depth)."""
    fl = pd.DataFrame(vl[:, :3], columns=["lat", "lon", "hpa"]) if len(vl) else pd.DataFrame(
        {"lat": [], "lon": [], "hpa": []})
    fl = fl[fl.hpa < 1010.0].reset_index(drop=True)
    m = rks.match_lows(tp["lows"], fl, 1000.0, miss_penalty_km=1000.0, miss_depth="nan")
    lows = pd.DataFrame({"lat": m.lat.to_numpy(), "lon": m.lon.to_numpy(), "an_hpa": m.hpa.to_numpy(),
                         "pos_km": m.pos_err_km.to_numpy(), "depth_err_hpa": m.depth_err_hpa.to_numpy(),
                         "hit": (m.matched & (m.pos_err_km <= 300.0)).to_numpy()})
    lows["fc_lat"], lows["fc_lon"], lows["fc_hpa"] = [np.where(m.matched, m[c], np.nan)
                                                      for c in ("fc_lat", "fc_lon", "fc_hpa")]
    deep = fl[fl.hpa < 1000.0]
    return lows, int(rks.false_lows(tp["lows_all"], deep, 500.0)), int(len(deep))


# ---------------------------------------------------------------- outlier-drop risk records

def risk_records(cm, case, X, name, run_lows, tps):
    """One record per dropped deterministic run (cm.od_dropped rows with dropped=True) joined to the analysed
    low (< 1000 hPa) nearest the group's consensus within 1000 km.
    drop_err_km: dropped low to that analysed low; best_other_km: the smallest such distance among the other
    runs' lows within 1000 km of the consensus; closest: the dropped low beat every other run's."""
    recs = []
    rows = cm.od_dropped(case.basin, case.cycle, case.lead, case, params={"X": float(X)}, gfe=("gfe2" if name.endswith("_gfe2") else name.endswith("_gfe")))
    for r in rows:
        if not r["dropped"]:
            continue
        clat, clon = r["clat"], r["clon"]
        for tr, tp in tps.items():
            tl = tp["lows"]
            if not len(tl):
                continue
            d = rks.km(clat, clon, tl.lat.to_numpy(), tl.lon.to_numpy())
            j = int(d.argmin())
            if d[j] > 1000.0:
                continue
            a_lat, a_lon, a_hpa = float(tl.lat.iloc[j]), float(tl.lon.iloc[j]), float(tl.hpa.iloc[j])
            e_drop = float(rks.km(a_lat, a_lon, r["low_lat"], r["low_lon"])) if r["has_low"] else np.nan
            others = []
            for m, ll in run_lows.items():
                if m == r["model"] or not len(ll):
                    continue
                dc = rks.km(clat, clon, ll[:, 0], ll[:, 1])
                if (dc <= 1000.0).any():
                    k = int(np.where(dc <= 1000.0, rks.km(a_lat, a_lon, ll[:, 0], ll[:, 1]), 1e9).argmin())
                    others.append(float(rks.km(a_lat, a_lon, ll[k, 0], ll[k, 1])))
            best = min(others) if others else np.nan
            recs.append({"truth": tr, "cand": name, "setting": "X=%g" % X, "model": r["model"], "group": r["group"],
                         "dist_km": r["dist_km"], "drop_lat": r["low_lat"], "drop_lon": r["low_lon"],
                         "drop_hpa": r["low_hpa"], "cons_lat": clat, "cons_lon": clon, "an_lat": a_lat,
                         "an_lon": a_lon, "an_hpa": a_hpa, "drop_err_km": e_drop, "best_other_km": best,
                         "n_other": len(others), "closest": bool(len(others) and e_drop < best)})
    return recs


# ---------------------------------------------------------------- one basin-cycle

def tags(cycle):
    return "%s" % rkc.tag(cycle)


def stamp(rows, basin, cycle, lead):
    c = pd.Timestamp(cycle)
    v = c + pd.Timedelta(hours=lead)
    iso = cycle.isocalendar()
    rows["basin"], rows["cycle"], rows["lead"], rows["valid"] = basin, c, lead, v
    rows["week"] = "%d-W%02d" % (iso[0], iso[1])
    rows["split"] = rkc.split(cycle)
    rows["valid_held"] = bool(rkc.held_out(v.to_pydatetime()))
    rows["month"] = "%04d%02d" % (cycle.year, cycle.month)
    return rows


def run_one(args):
    basin, cycle, stub = args
    import score as S
    cm, _ = load_candidates(stub)
    tag = tags(cycle)
    out_dir = PARTS / basin
    out_dir.mkdir(parents=True, exist_ok=True)
    done = out_dir / (tag + ".done")
    if done.exists():
        return basin, tag, "skip", 0.0
    t0 = time.time()
    zf = paths.cache("extra", "mslp-blend-d7", basin, tag + ".npz")
    if not zf.exists():
        return basin, tag, "no extract", 0.0
    with np.load(zf) as zz:
        z = {k: zz[k] for k in zz.files}
    members = load_members(basin, tag) if cycle.hour == 12 else None
    F, Lw, D, R = [], [], [], []
    for lead in LEADS:
        ak = {t: "an_%s_v%03d" % (t, lead) for t in ("gfs", "ifs")}
        if ak["gfs"] not in z or ak["ifs"] not in z:
            continue
        mask = z["mask_v%03d" % lead]
        prevk = {t: "an_%s_v%03d" % (t, lead - 24) for t in ("gfs", "ifs")}
        ans = {"gfs": z[ak["gfs"]], "ifs": z[ak["ifs"]]}
        ans["mean"] = ((ans["gfs"].astype(np.float64) + ans["ifs"]) / 2).astype(np.float32)
        prev = {t: (z.get(prevk[t]) if lead > 24 else None) for t in ("gfs", "ifs")}
        prev["mean"] = None if prev["gfs"] is None or prev["ifs"] is None else \
            ((prev["gfs"].astype(np.float64) + prev["ifs"]) / 2).astype(np.float32)
        tps = {t: S.prep_truth(ans[t], mask, basin, prev[t]) for t in TRUTHS}

        def emit(cand, setting, fcp, trs=TRUTHS, f=None):
            for t in trs:
                r = S.case_full(None, None, None, basin, fcp=fcp, tp=tps[t])
                frow = dict(r["field"], false_n=r["false_n"], n_fc=r["n_fc"], truth=t, cand=cand, setting=setting)
                F.append(stamp(pd.DataFrame([frow]), basin, cycle, lead))
                if len(r["lows"]):
                    Lw.append(stamp(r["lows"].assign(truth=t, cand=cand, setting=setting), basin, cycle, lead))
                if len(r["fdeep"]):
                    D.append(stamp(r["fdeep"].assign(truth=t, cand=cand, setting=setting), basin, cycle, lead))

        try:
            res = build_all(cm, basin, cycle, lead, z, members)
        except Exception:
            print("build failed", basin, tag, lead, file=sys.stderr)
            traceback.print_exc()
            res = []
        for name, label, fld in res:
            if fld is None:
                continue
            fcp = S.prep_fc(fld, basin)
            emit(name, label, fcp)
            if label == UNTUNED.get(name):
                emit(name, "default", fcp)      # same field, labelled as the untuned value (one extra scoring)
        case = None
        run_lows = {}
        if hasattr(cm, "prepare"):
            try:
                case = cm.prepare(basin, cycle, lead, z, members)
                run_lows = {m: case.lows(m) for m in case.runs}
            except Exception:
                traceback.print_exc()
        # analyses against the other analysis: the noise floor
        for nm, other in (("an_gfs", "ifs"), ("an_ifs", "gfs")):
            emit(nm, "default", S.prep_fc(ans[nm[3:]], basin), trs=(other,))
        # member vote (12 UTC, day 5-7)
        if members is not None and lead in (120, 144, 168):
            vl = vote_lows(basin, lead, members)
            if vl is not None:
                for t in TRUTHS:
                    lows, fa, nf = score_vote(vl, tps[t], basin)
                    Lw.append(stamp(lows.assign(truth=t, cand="vote", setting="default"), basin, cycle, lead))
                    F.append(stamp(pd.DataFrame([{"false_n": fa, "n_fc": nf, "truth": t, "cand": "vote",
                                                  "setting": "default"}]), basin, cycle, lead))
        # outlier-drop risk (each X of the grid, both inputs sets)
        if case is not None and hasattr(cm, "od_dropped"):
            for X in cm.grid_values()["X"]:
                for nm in ("od", "od_gfe", "od_gfe2"):
                    try:
                        R += [stamp(pd.DataFrame([r]), basin, cycle, lead) for r in
                              risk_records(cm, case, X, nm, run_lows, tps)]
                    except Exception:
                        print("risk failed", basin, tag, lead, nm, X, file=sys.stderr)
                        traceback.print_exc()
    for name, parts in (("field", F), ("lows", Lw), ("fdeep", D), ("risk", R)):
        if parts:
            df = pd.concat(parts, ignore_index=True)
            tmp = out_dir / ("%s_%s.tmp" % (name, tag))
            df.to_parquet(tmp, index=False)
            os.replace(tmp, out_dir / ("%s_%s.parquet" % (name, tag)))
    done.write_text("%.1f\n" % (time.time() - t0))
    return basin, tag, "ok", time.time() - t0


# ---------------------------------------------------------------- driver

def merge():
    n = 0
    for name in ("field", "lows", "fdeep", "risk"):
        groups = {}
        for basin in BASINS:
            for p in sorted((PARTS / basin).glob("%s_*.parquet" % name)):
                groups.setdefault((basin, p.stem.split("_")[1][:6]), []).append(p)
        for (basin, month), ps in groups.items():
            df = pd.concat([pd.read_parquet(p) for p in ps], ignore_index=True)
            tmp = OUT / ("%s_%s_%s.tmp" % (name, basin, month))
            df.to_parquet(tmp, index=False)
            os.replace(tmp, OUT / ("%s_%s_%s.parquet" % (name, basin, month)))
            n += 1
    print("merged", n, "basin-month files into", OUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cycles", nargs="*")
    ap.add_argument("--basins", nargs="*", default=list(BASINS))
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.merge:
        merge()
        return
    jobs = []
    t, end = datetime(2025, 11, 1), datetime(2026, 3, 31, 12)
    while t <= end:
        for b in a.basins:
            if (a.cycles is None or tags(t) in a.cycles) and paths.cache("extra", "mslp-blend-d7", b, tags(t) + ".npz").exists():
                jobs.append((b, t, a.stub))
        t += timedelta(hours=12)
    jobs = [j for j in jobs if not (PARTS / j[0] / (tags(j[1]) + ".done")).exists()]
    if a.limit:
        jobs = jobs[:a.limit]
    print(len(jobs), "basin-cycles to run", flush=True)
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(a.workers) as pool:
        for i, (b, tg, st, dt_) in enumerate(pool.imap_unordered(run_one, jobs), 1):
            print("%s %s %s %s %.0fs  [%d/%d, %.0f min]" % (time.strftime("%H:%M:%S"), b, tg, st, dt_, i, len(jobs),
                                                         (time.time() - t0) / 60), flush=True)
    merge()


if __name__ == "__main__":
    main()
