"""Paired comparison of two methods with week-block bootstrap intervals.

Storms in the same week are not independent, so whole ISO weeks are resampled.
"""
import numpy as np
import pandas as pd


def _time(df, time_col):
    col = time_col or ("cycle" if "cycle" in df else None)
    if col is None or col not in df:
        raise ValueError('need a datetime column named "cycle" or pass time_col')
    return pd.to_datetime(df[col])


def _week_ids(t):
    iso = t.dt.isocalendar()
    return (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()


def _boot(d, wk, n_boot, rng, ci=95):
    """Mean of d with a percentile interval from resampling whole weeks."""
    uw, inv = np.unique(wk, return_inverse=True)
    sums = np.bincount(inv, weights=d, minlength=len(uw))
    cnt = np.bincount(inv, minlength=len(uw)).astype(float)
    idx = rng.integers(0, len(uw), size=(n_boot, len(uw)))
    tot = cnt[idx].sum(1)
    means = sums[idx].sum(1) / tot
    a = (100 - ci) / 2
    lo, hi = np.percentile(means, [a, 100 - a])
    return float(d.mean()), float(lo), float(hi), len(uw)


def paired(df, method, baseline, value, by=None, block="week", n_boot=2000, seed=0,
           time_col=None, method_col="method", case_cols=None):
    """Mean of (method - baseline) in `value`, with 95% intervals, per group.

    df is long format: one row per case x method, with `method_col` naming the method.
    Rows are matched on every other key column (cycle, step, ... or `case_cols`).
    by: column name(s) to report separately (e.g. "step"). block must be "week".
    Returns a DataFrame: [by...], mean, lo, hi, n_cases, n_weeks, significant
    (True when the interval excludes zero).
    """
    if block != "week":
        raise ValueError("only block='week' is supported")
    rng = np.random.default_rng(seed)
    by = [by] if isinstance(by, str) else list(by or [])
    tcol = time_col or "cycle"
    _time(df, time_col)
    if case_cols is None:
        case_cols = [c for c in df.columns if c not in (method_col, value)
                     and not (df[c].dtype == float and c != tcol)]
    case_cols = list(dict.fromkeys(case_cols + by + [tcol]))
    wide = df[df[method_col].isin([method, baseline])].pivot_table(
        index=case_cols, columns=method_col, values=value, aggfunc="mean")
    out = []
    if method not in wide or baseline not in wide:
        wide = pd.DataFrame(columns=[method, baseline])
    wide = wide.dropna(subset=[method, baseline]).reset_index()
    groups = wide.groupby(by) if by else [((), wide)]
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        if len(g) == 0:
            row.update(mean=np.nan, lo=np.nan, hi=np.nan, n_cases=0, n_weeks=0, significant=False)
        else:
            d = (g[method] - g[baseline]).to_numpy(float)
            m, lo, hi, nw = _boot(d, _week_ids(_time(g, time_col)), n_boot, rng)
            row.update(mean=m, lo=lo, hi=hi, n_cases=len(g), n_weeks=nw, significant=bool(lo > 0 or hi < 0))
        out.append(row)
    return pd.DataFrame(out)


def fmt(mean, lo, hi, sig, digits=1):
    """'+0.4 [+0.1, +0.7]*' ; star when the interval excludes zero."""
    if not np.isfinite(mean):
        return "n/a"
    return f"{mean:+.{digits}f} [{lo:+.{digits}f}, {hi:+.{digits}f}]{'*' if sig else ''}"


def table(df, methods, baseline, value, by="step", digits=1, **kw):
    """Formatted table: rows = `by` values, one column per method (method minus baseline)."""
    cols = {}
    for m in methods:
        r = paired(df, m, baseline, value, by=by, **kw)
        keyed = r.set_index(by if isinstance(by, (str, list)) else by)
        cols[m] = [fmt(x.mean, x.lo, x.hi, x.significant, digits) for x in keyed.itertuples()]
        idx = keyed.index
    return pd.DataFrame(cols, index=idx)


def boot_sums(week_ids, stats, n_boot=2000, seed=0):
    """Whole-week bootstrap of additive statistics. stats [n_rows, k] (counts or sums per row, e.g. per case)
    with week_ids [n_rows]; returns (total [k], draws [n_boot, k]): the column sums over all rows and over
    n_boot resamples of whole weeks (with replacement). Ratio metrics are then computed from the sums, so the
    interval is for the pooled ratio, not for a mean of per-case ratios."""
    stats = np.asarray(stats, float)
    if stats.ndim == 1:
        stats = stats[:, None]
    uw, inv = np.unique(np.asarray(week_ids), return_inverse=True)
    wk = np.zeros((len(uw), stats.shape[1]))
    np.add.at(wk, inv, stats)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uw), size=(n_boot, len(uw)))
    mult = (idx[:, :, None] == np.arange(len(uw))[None, None, :]).sum(1).astype(float)   # [n_boot, n_weeks]
    return stats.sum(0), mult @ wk


def paired_counts(df, method, baseline, metric, counts, by=None, n_boot=2000, seed=0, time_col="cycle",
                  method_col="method", case_cols=None):
    """Pooled-ratio version of `paired`: metric(method) minus metric(baseline) from summed counts, with 95%
    intervals from resampling whole ISO weeks, the same weeks for both methods.

    df is long format: one row per case x method with the count columns `counts` (list of names) and
    `method_col`. Cases are matched on `case_cols` (default: every other non-count column except the method
    and any float column) plus `by` and `time_col`; unmatched cases are dropped. `metric(c)` takes a dict
    {count name: array} (sums, any leading shape) and returns the metric as an array, e.g.
    `lambda c: c["h"] / (c["h"] + c["m"])`.
    Returns a DataFrame: [by...], method, baseline (the metric from pooled counts), diff, lo, hi, n_cases,
    n_weeks, significant (interval excludes zero)."""
    by = [by] if isinstance(by, str) else list(by or [])
    counts = list(counts)
    if case_cols is None:
        case_cols = [c for c in df.columns if c not in counts and c != method_col and df[c].dtype != float]
    case_cols = list(dict.fromkeys(list(case_cols) + by + [time_col]))
    a = df[df[method_col] == method].set_index(case_cols)[counts]
    b = df[df[method_col] == baseline].set_index(case_cols)[counts]
    j = a.join(b, how="inner", lsuffix="_m", rsuffix="_b").reset_index()
    out = []
    groups = j.groupby(by) if by else [((), j)]
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        if len(g) == 0:
            row.update(method=np.nan, baseline=np.nan, diff=np.nan, lo=np.nan, hi=np.nan, n_cases=0,
                       n_weeks=0, significant=False)
        else:
            k = len(counts)
            st = np.hstack([g[[c + "_m" for c in counts]].to_numpy(float),
                            g[[c + "_b" for c in counts]].to_numpy(float)])
            tot, dr = boot_sums(_week_ids(_time(g, time_col)), st, n_boot=n_boot, seed=seed)

            def both(x):
                mm = metric({c: x[..., i] for i, c in enumerate(counts)})
                bb = metric({c: x[..., k + i] for i, c in enumerate(counts)})
                return mm, bb
            m0, b0 = both(tot)
            md, bd = both(dr)
            d = md - bd
            d = d[np.isfinite(d)]
            lo, hi = np.percentile(d, [2.5, 97.5]) if len(d) else (np.nan, np.nan)
            row.update(method=float(m0), baseline=float(b0), diff=float(m0 - b0), lo=float(lo), hi=float(hi),
                       n_cases=len(g), n_weeks=len(np.unique(_week_ids(_time(g, time_col)))),
                       significant=bool(lo > 0 or hi < 0))
        out.append(row)
    return pd.DataFrame(out)
