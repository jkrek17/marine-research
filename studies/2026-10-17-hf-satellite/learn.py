"""Learned image features (design.md, learned-features addendum): EOFs and an autoencoder learned from the IR crops
without labels, and a small labelled CNN, each joined to pressure and latitude in a logistic model and compared
with the seven hand-built IR measures. Reads crops.npz (crops.py) and results_full.csv (run_full.py); writes
scores_learn.csv and results_learn.csv.

    python3 studies/2026-10-17-hf-satellite/learn.py            # tuning weeks only (choose the method)
    python3 studies/2026-10-17-hf-satellite/learn.py --final    # adds the one-time held-out score
"""
import argparse

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.model_selection import GroupKFold

from common import HERE
from rk import compare, paths, score
from run import BASE, model, week_boot_auc

WIN_AUC = 0.03
EOF_K = (5, 10, 20, 40)
CODE = 32
SEED = 0
torch.set_num_threads(1)                 # one thread: runs repeat exactly
torch.use_deterministic_algorithms(True)


def load():
    z = np.load(paths.cache("extra", "hf-satellite", "crops.npz"), allow_pickle=False)
    d = pd.DataFrame({c: z[c] for c in ("basin", "event_id", "valid", "category", "split")})
    for c in ("lat", "lon", "hpa"):
        d[c] = pd.to_numeric(z[c], errors="coerce")
    d["valid"] = pd.to_datetime(d["valid"])
    x = (z["x"].astype(np.float32) - 250.0) / 30.0          # K -> about -1..1
    return d, x


def net(out):
    """Encoder 60x60 -> out numbers (three stride-2 convolutions)."""
    return torch.nn.Sequential(
        torch.nn.Conv2d(1, 16, 4, 2, 1), torch.nn.ReLU(),          # 30
        torch.nn.Conv2d(16, 32, 4, 2, 1), torch.nn.ReLU(),         # 15
        torch.nn.Conv2d(32, 64, 3, 2, 1), torch.nn.ReLU(),         # 8
        torch.nn.Flatten(), torch.nn.Linear(64 * 8 * 8, out))


def decoder():
    return torch.nn.Sequential(
        torch.nn.Linear(CODE, 64 * 8 * 8), torch.nn.ReLU(), torch.nn.Unflatten(1, (64, 8, 8)),
        torch.nn.ConvTranspose2d(64, 32, 3, 2, 1), torch.nn.ReLU(),            # 15
        torch.nn.ConvTranspose2d(32, 16, 4, 2, 1), torch.nn.ReLU(),            # 30
        torch.nn.ConvTranspose2d(16, 1, 4, 2, 1))                              # 60


def fit(model_, loss_fn, xs, ys, groups, epochs=40, patience=5):
    """Adam with early stopping on 15% of the storms held aside; returns the model at its best epoch."""
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    u = np.unique(groups)
    val = np.isin(groups, rng.choice(u, max(1, int(0.15 * len(u))), replace=False))
    xt, yt = torch.tensor(xs[~val][:, None]), torch.tensor(ys[~val])
    xv, yv = torch.tensor(xs[val][:, None]), torch.tensor(ys[val])
    opt = torch.optim.Adam(model_.parameters(), lr=1e-3, weight_decay=1e-4)
    best, best_state, wait = np.inf, None, 0
    for _ in range(epochs):
        model_.train()
        for i in torch.randperm(len(xt)).split(64):
            opt.zero_grad()
            loss_fn(model_(xt[i]), yt[i]).backward()
            opt.step()
        model_.eval()
        with torch.no_grad():
            v = float(loss_fn(model_(xv), yv))
        if v < best - 1e-5:
            best, best_state, wait = v, {k: t.clone() for k, t in model_.state_dict().items()}, 0
        else:
            wait += 1
            if wait >= patience:
                break
    model_.load_state_dict(best_state)
    model_.eval()
    return model_


def ae_codes(x_fit, groups, x_all):
    """Autoencoder trained on x_fit (no labels) -> CODE numbers for every crop in x_all."""
    torch.manual_seed(SEED)                         # the starting weights too, so runs repeat
    enc = net(CODE)
    ae = torch.nn.Sequential(enc, decoder())
    fit(ae, torch.nn.functional.mse_loss, x_fit, x_fit[:, None], groups)
    with torch.no_grad():
        return enc(torch.tensor(x_all[:, None])).numpy()


def cnn_logit(x_tr, y_tr, g_tr, x_out, x_extra=None):
    """Small CNN trained on HF (1) vs storm force (0) -> logit for x_out (and for x_extra, if given)."""
    torch.manual_seed(SEED)
    m = torch.nn.Sequential(net(16), torch.nn.ReLU(), torch.nn.Dropout(0.3), torch.nn.Linear(16, 1))
    pos = torch.tensor(float((1 - y_tr).sum() / max(y_tr.sum(), 1)))
    lf = lambda o, t: torch.nn.functional.binary_cross_entropy_with_logits(o[:, 0], t, pos_weight=pos)  # noqa: E731
    fit(m, lf, x_tr, y_tr.astype(np.float32), g_tr)
    with torch.no_grad():
        out = m(torch.tensor(x_out[:, None]))[:, 0].numpy()
        if x_extra is None:
            return out
        return out, m(torch.tensor(x_extra[:, None]))[:, 0].numpy()


def logit_oof(t, cols):
    p = np.zeros(len(t))
    for tr, te in GroupKFold(5).split(t, t["y"], t["event_id"]):
        p[te] = model("x").fit(t.iloc[tr][cols], t.iloc[tr]["y"]).predict_proba(t.iloc[te][cols])[:, 1]
    return p


def gate(g, a, b, label, win_auc):
    lo, hi, nw = week_boot_auc(g, "p_" + a, "p_" + b, n=10000)
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


def scores(g, label, methods):
    return [{"set": label, "method": m, "n": len(g), "n_hf": int(g["y"].sum()), "storms": g["event_id"].nunique(),
             "auc": score.auc(g["p_" + m], g["y"]), "brier": float(np.mean((g["p_" + m] - g["y"]) ** 2))}
            for m in methods]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    d, x = load()
    r = pd.read_csv(HERE / "results_full.csv", parse_dates=["valid"])[["event_id", "valid", "p_base", "p_ir"]]
    d = d.merge(r, on=["event_id", "valid"], how="left")
    lab = d["category"].isin(["HF", "S"]) & d["p_ir"].notna()      # the fixes scored in run_full.py
    d["y"] = (d["category"] == "HF").astype(int)
    tune_all = (d["split"] == "tune").to_numpy()
    xt = x[tune_all]

    # learned without labels, on every tuning-week crop
    pcs = PCA(max(EOF_K), random_state=SEED).fit(xt.reshape(len(xt), -1)).transform(x.reshape(len(x), -1))
    for k in range(max(EOF_K)):
        d["eof%d" % k] = pcs[:, k]
    codes = ae_codes(xt, d.loc[tune_all, "event_id"].to_numpy(), x)
    for k in range(CODE):
        d["ae%d" % k] = codes[:, k]

    t = d[lab & tune_all].reset_index(drop=True)
    ti = np.nonzero((lab & tune_all).to_numpy())[0]
    rows, cols = [], {}
    for k in EOF_K:
        cols["eof%d" % k] = BASE + ["eof%d" % i for i in range(k)]
    cols["ae"] = BASE + ["ae%d" % i for i in range(CODE)]
    # labelled CNN, out of fold by storm
    t["cnn"] = np.nan
    hi_ = np.nonzero((lab & ~tune_all).to_numpy())[0]
    fold_held = []                                  # each fold model's logits for the held-out crops (post hoc)
    for tr, te in GroupKFold(5).split(t, t["y"], t["event_id"]):
        o, e = cnn_logit(x[ti[tr]], t["y"].to_numpy()[tr], t["event_id"].to_numpy()[tr], x[ti[te]], x[hi_])
        t.loc[te, "cnn"] = o
        fold_held.append(e)
    cols["cnn"] = BASE + ["cnn"]
    for m, c in cols.items():
        t["p_" + m] = logit_oof(t, c)
    t["p_base_cv"], t["p_ir_cv"] = t["p_base"], t["p_ir"]            # run_full.py's out-of-fold scores
    tune_auc = {m: score.auc(t["p_" + m], t["y"]) for m in cols}
    eof_best = max(EOF_K, key=lambda k: tune_auc["eof%d" % k])
    pick = max(["eof%d" % eof_best, "ae", "cnn"], key=lambda m: tune_auc[m])
    print("tuning ROC:", {m: round(v, 3) for m, v in tune_auc.items()}, "ir %.3f, base %.3f" % (
        score.auc(t["p_ir"], t["y"]), score.auc(t["p_base"], t["y"])), "-> forward:", pick)
    meth = ["base", "ir"] + list(cols)
    rows += scores(t, "tune (5-fold by storm)", meth)
    for b in ("natl", "npac"):
        rows += scores(t[t.basin == b], "tune " + b, meth)
    mt = (t["lat"] < 55) & ((t["basin"] == "npac") | (t["lon"] <= 330))
    rows += scores(t[mt], "tune matched (S of 55N, Atl W of 30W)", meth)
    t["p_learned"] = t["p_" + pick]
    rows.append(gate(t, "learned", "ir", "tune (%s)" % pick, None))
    out = [t]
    if a.final:
        h = d[lab & ~tune_all].reset_index(drop=True)
        if pick == "cnn":
            h["cnn"] = cnn_logit(x[ti], t["y"].to_numpy(), t["event_id"].to_numpy(), x[hi_])
        h["p_learned"] = model("x").fit(t[cols[pick]], t["y"]).predict_proba(h[cols[pick]])[:, 1]
        h["season"] = [v.year if v.month >= 6 else v.year - 1 for v in h["valid"]]
        new = h[h["season"] <= 2023]
        for lab_, g in (("held out 2002-24", new), ("held out pilot 2024-26", h[h["season"] >= 2024])):
            rows += scores(g, lab_, ["base", "ir", "learned"])
            for b in ("natl", "npac"):
                rows += scores(g[g.basin == b], lab_ + " " + b, ["base", "ir", "learned"])
        rows.append(gate(new, "learned", "ir", "held out 2002-24 (verdict, %s)" % pick, WIN_AUC))
        if pick == "cnn":
            # post hoc, after the verdict: the logistic was fitted on out-of-fold logits, but the verdict applied it
            # to one CNN refit on all tuning weeks, whose logits are on a wider scale (overconfident). Averaging
            # the five fold CNNs keeps the scale the logistic was fitted on.
            h["cnn"] = np.mean(fold_held, 0)
            h["p_learned_folds"] = model("x").fit(t[cols[pick]], t["y"]).predict_proba(h[cols[pick]])[:, 1]
            new = h[h["season"] <= 2023]
            rows += scores(new, "held out 2002-24 post hoc", ["learned_folds"])
            for b in ("natl", "npac"):
                rows += scores(new[new.basin == b], "held out 2002-24 post hoc " + b, ["learned_folds"])
            rows.append(gate(new, "learned_folds", "ir", "held out 2002-24 post hoc (fold-average CNN)", None))
        mt = (new["lat"] < 55) & ((new["basin"] == "npac") | (new["lon"] <= 330))
        rows += scores(new[mt], "held out 2002-24 matched (S of 55N, Atl W of 30W)", ["base", "ir", "learned"])
        rows.append(gate(new[mt], "learned", "ir", "held out 2002-24 matched", None))
        rows.append(gate(new, "learned", "base", "held out 2002-24", None))
        out.append(h)
        # ASCAT referee, winter 2025-26: rank correlation of each HF chance with the ASCAT peak
        asc = pd.read_csv(HERE / "ascat.csv", parse_dates=["valid"])
        asc = asc[asc["ascat"] == "ok"][["event_id", "valid", "peak_kt"]]
        m_ = pd.concat(out).merge(asc, on=["event_id", "valid"])
        for meth_ in ("base", "ir", "learned"):
            rc = spearmanr(m_["p_" + meth_], m_["peak_kt"])[0]
            rows.append({"set": "ASCAT 2025-26 rank corr", "method": meth_, "n": len(m_), "auc": rc})
            print("ASCAT rank corr %s %.3f (n=%d)" % (meth_, rc, len(m_)))
    s = pd.DataFrame(rows)
    print(s.to_string(index=False, float_format="%.3f"))
    s.to_csv(HERE / "scores_learn.csv", index=False, float_format="%.4f")
    keep = ["basin", "event_id", "valid", "lat", "lon", "hpa", "category", "split", "y", "p_base", "p_ir", "p_learned"] + \
        (["p_learned_folds"] if "p_learned_folds" in out[-1] else [])
    pd.concat(out)[keep].to_csv(HERE / "results_learn.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
