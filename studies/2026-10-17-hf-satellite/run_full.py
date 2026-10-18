"""Full-archive version of run.py (design.md, addendum): same methods and rule, seasons 2002-03 to 2025-26.
Tune on all tuning weeks; the verdict is on the held-out weeks of 2002-03 to 2023-24 (never looked at); the
pilot's held-out weeks (2024-26) are reported beside it. Reads features_full.csv (RK_DATA/hf-satellite, from features.py --seasons); writes scores_full.csv and
results_full.csv.

    python3 studies/2026-10-17-hf-satellite/run_full.py            # tuning weeks only
    python3 studies/2026-10-17-hf-satellite/run_full.py --final    # adds the one-time held-out score
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from common import HERE, season
from features import FEATURES
from rk import compare, paths, score
from run import BASE, METHODS, WIN_AUC, model, scores, week_boot_auc


def table():
    d = pd.read_csv(paths.data("hf-satellite", "features_full.csv"), parse_dates=["valid"])
    d = d[(d["status"] == "ok") & d["category"].isin(["HF", "S"])].dropna(subset=BASE + FEATURES).copy()
    d["y"] = (d["category"] == "HF").astype(int)
    d["season"] = [season(t) for t in d["valid"]]
    return d.reset_index(drop=True)


def gate(g, label):
    lo, hi, nw = week_boot_auc(g, "p_ir", "p_base")
    long = pd.concat([pd.DataFrame({"cycle": g["valid"], "fix": g["event_id"] + g["valid"].astype(str),
                                    "method": m, "brier": (g["p_" + m] - g["y"]) ** 2}) for m in ("ir", "base")])
    pb = compare.paired(long, "ir", "base", "brier", case_cols=["fix"], n_boot=10000)
    gain = score.auc(g["p_ir"], g["y"]) - score.auc(g["p_base"], g["y"])
    win = gain >= WIN_AUC and pb["hi"][0] < 0
    print("%s: AUC ir - base %.3f (95%% %.3f to %.3f, %d weeks); Brier ir - base %.4f (95%% %.4f to %.4f) -> %s"
          % (label, gain, lo, hi, nw, pb["mean"][0], pb["lo"][0], pb["hi"][0], "PASSED" if win else "not passed"))
    return {"set": label, "method": "ir - base", "auc": gain, "auc_lo": lo, "auc_hi": hi, "brier": pb["mean"][0],
            "brier_lo": pb["lo"][0], "brier_hi": pb["hi"][0], "weeks": nw, "passed": win}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    d = table()
    tune, held = d[d["split"] == "tune"].copy(), d[d["split"] == "held_out"].copy()
    for name, g in (("tune", tune), ("held out", held)):
        print("%s: %d fixes (%d HF, %d S), %d storms" % (name, len(g), g.y.sum(), (1 - g.y).sum(), g.event_id.nunique()))
    for m, cols in METHODS.items():
        p = np.zeros(len(tune))
        for tr, te in GroupKFold(5).split(tune, tune["y"], tune["event_id"]):
            p[te] = model(m).fit(tune.iloc[tr][cols], tune.iloc[tr]["y"]).predict_proba(tune.iloc[te][cols])[:, 1]
        tune["p_" + m] = p
    rows = scores(tune, "tune (5-fold by storm)")
    for b in ("natl", "npac"):
        rows += scores(tune[tune.basin == b], "tune " + b)
    rows.append(gate(tune, "tune (5-fold by storm)"))
    out = [tune]
    if a.final:
        for m, cols in METHODS.items():
            held["p_" + m] = model(m).fit(tune[cols], tune["y"]).predict_proba(held[cols])[:, 1]
        new, pilot = held[held["season"] <= 2023], held[held["season"] >= 2024]
        for lab, g in (("held out 2002-24", new), ("held out pilot 2024-26", pilot)):
            rows += scores(g, lab)
            for b in ("natl", "npac"):
                rows += scores(g[g.basin == b], lab + " " + b)
        rows.append(gate(new, "held out 2002-24 (verdict)"))
        rows.append(gate(pilot, "held out pilot 2024-26"))
        for lab, k in (("pre-2017", new["valid"] < "2017-06-01"), ("2017 on", new["valid"] >= "2017-06-01"),
                       ("south of 55N", new["lat"] < 55), ("55N and north", new["lat"] >= 55)):
            rows += scores(new[k], "held out 2002-24 " + lab)
        out.append(held)
    s = pd.DataFrame(rows)
    print(s.to_string(index=False, float_format="%.3f"))
    s.to_csv(HERE / "scores_full.csv", index=False, float_format="%.4f")
    keep = ["basin", "event_id", "valid", "lat", "lon", "hpa", "category", "split", "vza", "y"] + \
        [c for c in out[-1].columns if c.startswith("p_")]
    pd.concat(out)[keep].to_csv(HERE / "results_full.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
