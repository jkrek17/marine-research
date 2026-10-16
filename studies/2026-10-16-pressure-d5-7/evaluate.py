"""Score every system on every case (12Z cycle x basin x lead). Writes OUT/records_<tag>.pkl:
list of dicts {ymd, valid, dom, step, held, sys, rows (k,4: pos_km, dp, hit300, p_an), fa, nf, lows}.

Run: python3 evaluate.py TAG [json of consensus params]
"""
import os, sys, json, pickle, datetime as dt, glob
from multiprocessing import Pool
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib, method as M

OUT = lib.RECORDS
DEFAULT = {"w": {"gefs": 1.0, "ens": 1.0, "aifsens": 1.0, "gfs": 0.0, "ifs": 0.0, "aifs": 0.0},
           "R": 400.0, "T": 0.3, "q": 0.5, "lag_w": 0.0, "calib": None}


def cycles():
    a = {os.path.basename(p)[8:16] for p in glob.glob(lib.CACHE + "/fc_noaa_*.npz")}
    b = {os.path.basename(p)[6:14] for p in glob.glob(lib.CACHE + "/fc_ec_*.npz")}
    return sorted(a & b)


def run_cycle(args):
    ymd, P, base = args
    recs = []
    for dom in lib.DOMS:
        for step in lib.STEPS:
            valid = dt.datetime.strptime(ymd, "%Y%m%d") + dt.timedelta(hours=12 + step)
            if valid.hour != 12:
                continue
            an = M.analysis(valid.strftime("%Y%m%d"), dom)
            if an is None:
                continue
            c = M.case(ymd, dom, step, lag=P["lag_w"] > 0)
            if c is None:
                continue
            truth = lib.analysed_lows(an, dom)
            truth_all = lib.find_lows(an, dom, 1005.0)
            gm = M.grand_mean(c)
            systems = {}
            if base:
                for m, L in M.det_lows(c, dom).items():
                    systems[m] = (L, c["det"][m], False)
                systems["gmean"] = (lib.find_lows(gm, dom, 1010.0, half=True), gm, True)
                if "aifsens" in c["mem"]:
                    systems["gmean_noaifs"] = (lib.find_lows(M.grand_mean(c, ("gefs", "ens")), dom, 1010.0, half=True), gm, True)
            V = M.voters(c, dom, P["w"], use_lag=P["lag_w"] > 0, lag_w=P["lag_w"])
            calib = P["calib"][str(step)] if P["calib"] else None
            systems["vote"] = (M.consensus(V, R=P["R"], T=P["T"], q=P["q"], calib=calib), gm, True)
            for name, (L, fld, half) in systems.items():
                rows = lib.score(truth, L[:, :3] if len(L) else np.zeros((0, 3)), fld, dom, half)
                fa, nf = lib.false_lows(truth_all, L[:, :3] if len(L) else np.zeros((0, 3)))
                # for each forecast low: distance to the nearest analysed low < 1005, its analysed pressure
                ver = []
                for r in L:
                    if len(truth_all):
                        d = lib.km(r[0], r[1], truth_all[:, 0], truth_all[:, 1])
                        j = d.argmin()
                        ver.append((d[j], truth_all[j, 2]))
                    else:
                        ver.append((1e9, np.nan))
                extra = {}
                if name == "vote":
                    extra = {"truth": truth, "truth_all": truth_all,
                             "fvals": np.array([lib.value_at(fld, dom, la, lo, half) for la, lo, _ in truth])}
                recs.append({**extra, "ymd": ymd, "valid": valid, "dom": dom, "step": step, "held": lib.held_out(dt.datetime.strptime(ymd, "%Y%m%d")), "tune": lib.tune_ok(dt.datetime.strptime(ymd, "%Y%m%d"), valid),
                             "aifsens": "aifsens" in c["mem"], "sys": name, "rows": rows, "fa": fa, "nf": nf,
                             "lows": np.asarray(L), "ver": np.array(ver).reshape(-1, 2)})
    return recs


def main(tag, P, base=True, only=None):
    os.makedirs(OUT, exist_ok=True)
    cyc = cycles() if only is None else only
    with Pool(4) as pool:
        recs = [r for rs in pool.imap_unordered(run_cycle, [(c, P, base) for c in cyc], chunksize=4) for r in rs]
    with open(os.path.join(OUT, "records_%s.pkl" % tag), "wb") as f:
        pickle.dump({"params": P, "recs": recs}, f)
    return recs


if __name__ == "__main__":
    tag = sys.argv[1]
    P = dict(DEFAULT)
    if len(sys.argv) > 2:
        P.update(json.loads(sys.argv[2]))
    r = main(tag, P)
    print(len(r), "records")
