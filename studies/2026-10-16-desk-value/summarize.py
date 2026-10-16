"""Summaries of the desk-value scores: reads scores.csv.gz and edits.csv.gz (RK data folder extra/desk-value/),
writes small CSVs to results/. Lead day = ceil(lead / 24) (day 1 = 1-24 h from the model cycle).

  by_method.csv        basin x lead day x class x method x truth: MAE25, bias, POD/FAR/CSI/area ratio at 34/48/64
  by_method_held_out.csv  the same for class "all", split tune / held-out weeks
  paired.csv           desk minus baseline, per-issuance MAE25 and CSI34/CSI48 against ASCAT, week-block 95% intervals
  class_shares.csv     share of water cells, cell-hours and desk edits per class; toward/away share of edits
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from rk import compare, paths  # noqa: E402

DATA = paths.data("extra", "desk-value", "x").parent
RES = HERE / "results"
THR = (34, 48, 64)
KEY = ["basin", "leadday", "class", "method", "truth"]
BASELINES = ("auto24", "prev12", "prev24", "gfs", "ifs", "aifs", "mean3", "blend")


def load():
    s = pd.read_csv(DATA / "scores.csv.gz")
    e = pd.read_csv(DATA / "edits.csv.gz")
    for d in (s, e):
        d["leadday"] = np.ceil(d["lead"] / 24).astype(int)
        d["cycle"] = pd.to_datetime(d["cycle"])
    return s, e


def metrics(g):
    """g: DataFrame of sums (already grouped) -> metric columns."""
    out = pd.DataFrame(index=g.index)
    out["n_issues"] = g["n_issues"]
    out["n_cells"] = g["n"]
    out["n25"] = g["n25"]
    out["mae25"] = g["sum_abs"] / g["n25"].where(g["n25"] > 0)
    out["bias25"] = g["sum_err"] / g["n25"].where(g["n25"] > 0)
    for t in THR:
        h, fa, mi = g[f"hits{t}"], g[f"fa{t}"], g[f"miss{t}"]
        out[f"pod{t}"] = h / (h + mi).where(h + mi > 0)
        out[f"far{t}"] = fa / (h + fa).where(h + fa > 0)
        out[f"csi{t}"] = h / (h + fa + mi).where(h + fa + mi > 0)
        out[f"area_ratio{t}"] = g[f"fc_cells{t}"] / g[f"ob_cells{t}"].where(g[f"ob_cells{t}"] > 0)
        out[f"ob_cells{t}"] = g[f"ob_cells{t}"]
    return out


def sums(s, by):
    cols = ["n", "n25", "sum_abs", "sum_err"] + [f"{k}{t}" for t in THR for k in ("hits", "fa", "miss", "fc_cells", "ob_cells")]
    g = s.groupby(by)[cols].sum()
    g["n_issues"] = s.groupby(by)["cycle"].nunique()
    return g


def paired_table(s):
    a = s[s["truth"] == "ascat"]
    rows = []
    for base in BASELINES:
        d, b = a[a["method"] == "desk"], a[a["method"] == base]
        if b.empty:
            continue
        # match on the same valid times, then aggregate per issuance x basin x lead day x class
        k = ["issue", "basin", "valid", "class", "leadday"]
        m = d.merge(b, on=k, suffixes=("_d", "_b"))
        for side in ("_d", "_b"):
            m[f"cell{side}"] = 1
        per = []
        for side, name in (("_d", "desk"), ("_b", base)):
            g = m.groupby(["issue", "basin", "leadday", "class"]).agg(
                **{c: (c + side, "sum") for c in ["n25", "sum_abs", "hits34", "fa34", "miss34", "hits48", "fa48", "miss48"]},
                cycle=("cycle_d", "first"), held_out=("held_out_d", "first")).reset_index()
            g["method"] = name
            per.append(g)
        p = pd.concat(per, ignore_index=True)
        p["mae25"] = p["sum_abs"] / p["n25"].where(p["n25"] > 0)
        for t in (34, 48):
            p[f"csi{t}"] = p[f"hits{t}"] / (p[f"hits{t}"] + p[f"fa{t}"] + p[f"miss{t}"]).where(
                p[f"hits{t}"] + p[f"fa{t}"] + p[f"miss{t}"] > 0)
        for val in ("mae25", "csi34", "csi48"):
            q = p.dropna(subset=[val])
            r = compare.paired(q[["issue", "basin", "leadday", "class", "method", "cycle", val]], "desk", base, val,
                               by=["basin", "leadday", "class"], case_cols=["issue", "basin", "leadday", "class"])
            r.insert(0, "baseline", base)
            r.insert(1, "metric", val)
            rows.append(r)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def class_shares(e):
    c = e[e["class"] != "all"].copy()
    allr = e[e["class"] == "all"]
    out = []
    for by in (["basin", "leadday"], ["basin"], []):
        grp_cols = by + ["class"]
        g = c.groupby(grp_cols).agg(cells=("cells", "sum"), edited=("edited", "sum"), sum_abs_edit=("sum_abs_edit", "sum"),
                                    raised=("raised", "sum"), lowered=("lowered", "sum"),
                                    edited_ascat=("edited_ascat", "sum"), n_ascat=("n_ascat", "sum"),
                                    toward_ed=("toward_ed", "sum"), away_ed=("away_ed", "sum"),
                                    n_ascat_a=("n_ascat_a", "sum"), toward_a=("toward_a", "sum"), away_a=("away_a", "sum"),
                                    n_rows=("cells", "size")).reset_index()
        tot = g.groupby(by)[["cells", "edited"]].transform("sum") if by else g[["cells", "edited"]].sum()
        g["share_cell_hours"] = g["cells"] / (tot["cells"] if by else tot["cells"])
        g["share_edits"] = g["edited"] / (tot["edited"] if by else tot["edited"])
        g["edit_rate"] = g["edited"] / g["cells"]
        g["mean_abs_edit_kt"] = g["sum_abs_edit"] / g["cells"]
        g["toward_share_of_edits"] = g["toward_ed"] / g["edited_ascat"].where(g["edited_ascat"] > 0)
        g["away_share_of_edits"] = g["away_ed"] / g["edited_ascat"].where(g["edited_ascat"] > 0)
        g["toward_vs_auto24"] = g["toward_a"] / g["n_ascat_a"].where(g["n_ascat_a"] > 0)
        g["away_vs_auto24"] = g["away_a"] / g["n_ascat_a"].where(g["n_ascat_a"] > 0)
        # share of water cells: mean over (issue, basin, valid) of the class fraction
        keys = ["issue", "basin", "valid"]
        cc = c.copy()
        cc["frac"] = cc["cells"] / cc.groupby(keys)["cells"].transform("sum")
        # frac summed over rows divided by the number of (issue, basin, valid) slices in the group
        nslice = cc.drop_duplicates(keys).groupby(by).size() if by else pd.Series({0: len(cc.drop_duplicates(keys))})
        fs = cc.groupby(grp_cols)["frac"].sum().reset_index()
        if by:
            fs = fs.merge(nslice.rename("nslice").reset_index(), on=by)
        else:
            fs["nslice"] = len(cc.drop_duplicates(keys))
        fs["share_water"] = fs["frac"] / fs["nslice"]
        g = g.merge(fs[grp_cols + ["share_water"]], on=grp_cols)
        for col in ("basin", "leadday"):
            if col not in g:
                g[col] = "all"
        out.append(g)
    cols = ["basin", "leadday", "class", "share_water", "share_cell_hours", "share_edits", "edit_rate", "mean_abs_edit_kt",
            "toward_share_of_edits", "away_share_of_edits", "toward_vs_auto24", "away_vs_auto24",
            "cells", "edited", "edited_ascat", "n_ascat", "n_rows"]
    res = pd.concat(out, ignore_index=True)[cols]
    # whole-water edit rate and toward/away (class "all") for reference
    ga = allr.groupby(["basin", "leadday"]).agg(cells=("cells", "sum"), edited=("edited", "sum"),
                                                edited_ascat=("edited_ascat", "sum"), n_ascat=("n_ascat", "sum"),
                                                toward_ed=("toward_ed", "sum"), away_ed=("away_ed", "sum"),
                                                n_ascat_a=("n_ascat_a", "sum"), toward_a=("toward_a", "sum"),
                                                away_a=("away_a", "sum"), n_rows=("cells", "size")).reset_index()
    ga["class"] = "all"
    ga["edit_rate"] = ga["edited"] / ga["cells"]
    ga["toward_share_of_edits"] = ga["toward_ed"] / ga["edited_ascat"].where(ga["edited_ascat"] > 0)
    ga["away_share_of_edits"] = ga["away_ed"] / ga["edited_ascat"].where(ga["edited_ascat"] > 0)
    ga["toward_vs_auto24"] = ga["toward_a"] / ga["n_ascat_a"].where(ga["n_ascat_a"] > 0)
    ga["away_vs_auto24"] = ga["away_a"] / ga["n_ascat_a"].where(ga["n_ascat_a"] > 0)
    return pd.concat([res, ga.reindex(columns=cols)], ignore_index=True)


def main():
    RES.mkdir(exist_ok=True)
    s, e = load()
    metrics(sums(s, KEY)).round(4).reset_index().to_csv(RES / "by_method.csv", index=False)
    ho = s[s["class"] == "all"].copy()
    ho["split"] = np.where(ho["held_out"], "held_out", "tune")
    metrics(sums(ho, ["split"] + KEY)).round(4).reset_index().to_csv(RES / "by_method_held_out.csv", index=False)
    p = paired_table(s)
    p.round(4).to_csv(RES / "paired.csv", index=False)
    class_shares(e).round(4).to_csv(RES / "class_shares.csv", index=False)
    print("wrote", [f.name for f in RES.glob("*.csv")])


if __name__ == "__main__":
    main()
