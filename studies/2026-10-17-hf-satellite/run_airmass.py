"""Air mass beside IR (design.md, air-mass addendum): base, ir and am (ir + six air-mass measures), refit on
the tuning fixes that have both IR and air mass, scored once on the held-out weeks. Reads features_airmass.csv;
writes scores_airmass.csv and results_airmass.csv.

    python3 studies/2026-10-17-hf-satellite/run_airmass.py            # tuning weeks only
    python3 studies/2026-10-17-hf-satellite/run_airmass.py --final    # adds the one-time held-out score
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from common import HERE
from features import FEATURES
from features_airmass import AM
from rk import compare, score
from run import BASE, model, week_boot_auc

METHODS = {"base": BASE, "ir": BASE + FEATURES, "am": BASE + FEATURES + AM, "am_only": BASE + AM}
WIN_AUC = 0.03


def table():
    d = pd.read_csv(HERE / "features_airmass.csv", parse_dates=["valid"])
    d = d[(d["status"] == "ok") & (d["am_status"] == "ok") & d["category"].isin(["HF", "S"])]
    d = d.dropna(subset=BASE + FEATURES + AM).copy()
    d["y"] = (d["category"] == "HF").astype(int)
    return d.reset_index(drop=True)


def scores(g, label):
    return [{"set": label, "method": m, "n": len(g), "n_hf": int(g["y"].sum()), "n_s": int((1 - g["y"]).sum()),
             "storms": g["event_id"].nunique(), "auc": score.auc(g["p_" + m], g["y"]),
             "brier": float(np.mean((g["p_" + m] - g["y"]) ** 2))} for m in METHODS if "p_" + m in g]


def gate(g, a, b, label, win_auc):
    lo, hi, nw = week_boot_auc(g, "p_" + a, "p_" + b)
    long = pd.concat([pd.DataFrame({"cycle": g["valid"], "fix": g["event_id"] + g["valid"].astype(str),
                                    "method": m, "brier": (g["p_" + m] - g["y"]) ** 2}) for m in (a, b)])
    pb = compare.paired(long, a, b, "brier", case_cols=["fix"], n_boot=10000)
    gain = score.auc(g["p_" + a], g["y"]) - score.auc(g["p_" + b], g["y"])
    win = win_auc is not None and gain >= win_auc and pb["hi"][0] < 0
    print("%s %s - %s: AUC %.3f (95%% %.3f to %.3f, %d weeks); Brier %.4f (95%% %.4f to %.4f)%s" % (
        label, a, b, gain, lo, hi, nw, pb["mean"][0], pb["lo"][0], pb["hi"][0],
        (" -> " + ("PASSED" if win else "not passed")) if win_auc is not None else ""))
    return {"set": label, "method": "%s - %s" % (a, b), "auc": gain, "auc_lo": lo, "auc_hi": hi,
            "brier": pb["mean"][0], "brier_lo": pb["lo"][0], "brier_hi": pb["hi"][0], "weeks": nw,
            "passed": win if win_auc is not None else np.nan}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    d = table()
    tune, held = d[d["split"] == "tune"].copy(), d[d["split"] == "held_out"].copy()
    for name, g in (("tune", tune), ("held out", held)):
        print("%s: %d fixes (%d HF, %d S), %d storms; natl %d, npac %d" % (
            name, len(g), g.y.sum(), (1 - g.y).sum(), g.event_id.nunique(), (g.basin == "natl").sum(),
            (g.basin == "npac").sum()))
    for m, cols in METHODS.items():
        p = np.zeros(len(tune))
        for tr, te in GroupKFold(5).split(tune, tune["y"], tune["event_id"]):
            p[te] = model(m).fit(tune.iloc[tr][cols], tune.iloc[tr]["y"]).predict_proba(tune.iloc[te][cols])[:, 1]
        tune["p_" + m] = p
    rows = scores(tune, "tune (5-fold by storm)")
    for b in ("natl", "npac"):
        rows += scores(tune[tune.basin == b], "tune " + b)
    rows.append(gate(tune, "am", "ir", "tune", None))
    out = [tune]
    if a.final:
        for m, cols in METHODS.items():
            held["p_" + m] = model(m).fit(tune[cols], tune["y"]).predict_proba(held[cols])[:, 1]
        rows += scores(held, "held out")
        for b in ("natl", "npac"):
            rows += scores(held[held.basin == b], "held out " + b)
        rows.append(gate(held, "am", "ir", "held out (verdict)", WIN_AUC))
        rows.append(gate(held, "am", "base", "held out", None))
        out.append(held)
    s = pd.DataFrame(rows)
    print(s.to_string(index=False, float_format="%.3f"))
    s.to_csv(HERE / "scores_airmass.csv", index=False, float_format="%.4f")
    keep = ["basin", "event_id", "valid", "lat", "lon", "hpa", "category", "split", "am_vza", "y"] + \
        [c for c in out[-1].columns if c.startswith("p_")]
    pd.concat(out)[keep].to_csv(HERE / "results_airmass.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
