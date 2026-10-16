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
