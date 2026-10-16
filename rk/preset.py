"""Shared plumbing for the standing-score presets (`studies/<study>/preset.py`) and `tools/run_presets.py`.

A preset re-runs one finished study's frozen method and judged scores on new weeks and writes one tidy table,
one row per ISO week x basin x method x metric. Nothing here fetches data; presets read through rk.store,
rk.truth and rk.score only.

Columns (COLUMNS): study, week (ISO "yyyy-Www" of the forecast cycle), basin, method, metric, value, n (cases
behind the value), truth (what the case was judged against).

A preset module defines `STUDY` (folder name), `CI` and `run(start, end, skip_missing)` and ends with
`main(__file__-level args)` via `cli(...)`. `CI` maps (method, metric) -> (lo, hi, source): the study's original
95% interval of the value, with where it comes from. The drift flag compares the newest weeks' mean to it.
"""
import argparse
import datetime as dt
import sys

import numpy as np
import pandas as pd

COLUMNS = ["study", "week", "basin", "method", "metric", "value", "n", "truth"]
DRIFT_COLUMNS = ["study", "method", "metric", "weeks_used", "recent_mean", "ci_lo", "ci_hi", "source", "drift"]
DRIFT_WEEKS = 4


class MissingInput(RuntimeError):
    """An input the preset needs is not available through rk (message says which and where it lives)."""


def iso_week(d):
    """datetime/date -> 'yyyy-Www' (ISO year and week)."""
    y, w, _ = d.isocalendar()
    return "%04d-W%02d" % (y, w)


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d")


def rows_to_frame(rows):
    """List of row dicts -> DataFrame with COLUMNS in order (empty frame if no rows)."""
    return pd.DataFrame(rows, columns=COLUMNS)


def cli(study, run, argv=None, description=None):
    """Command line shared by every preset. `run(start, end, skip_missing) -> (rows, missing)` where rows is
    a list of dicts with COLUMNS and missing is a list of strings naming inputs that were not available.
    Without --skip-missing a non-empty `missing` is an error (exit 3, nothing written); with it the rows that
    could be computed are written and the missing inputs are listed on stderr."""
    ap = argparse.ArgumentParser(description=description or "Standing scores for %s" % study)
    ap.add_argument("--start", required=True, type=parse_date, help="first forecast cycle date, YYYY-MM-DD")
    ap.add_argument("--end", required=True, type=parse_date, help="last forecast cycle date, YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="results CSV")
    ap.add_argument("--skip-missing", action="store_true",
                    help="write the methods that could run and report the rest, instead of failing")
    a = ap.parse_args(argv)
    if a.end < a.start:
        ap.error("--end is before --start")
    try:
        rows, missing = run(a.start, a.end, a.skip_missing)
    except MissingInput as e:
        sys.stderr.write("MISSING INPUT (%s): %s\n" % (study, e))
        return 3
    if missing:
        for m in missing:
            sys.stderr.write("MISSING INPUT (%s): %s\n" % (study, m))
        if not a.skip_missing:
            sys.stderr.write("nothing written; use --skip-missing to write what could be computed\n")
            return 3
    rows_to_frame(rows).to_csv(a.out, index=False)
    sys.stderr.write("%s: wrote %d rows to %s\n" % (study, len(rows), a.out))
    return 0


def drift_flags(df, ci, study=None, weeks=DRIFT_WEEKS):
    """Drift flag per (method, metric) that has an original interval in `ci`.

    df: results table (COLUMNS). ci: {(method, metric): (lo, hi, source)}. For each key the newest `weeks`
    distinct ISO weeks that have data are taken, the value averaged weighted by n over weeks and basins; drift
    is 'drift' when that mean lies outside [lo, hi], 'ok' inside, 'insufficient' when fewer than `weeks`
    weeks have data. Returns a DataFrame with DRIFT_COLUMNS."""
    out = []
    for (method, metric), (lo, hi, source) in sorted(ci.items()):
        g = df[(df["method"] == method) & (df["metric"] == metric)].dropna(subset=["value"])
        g = g[g["n"] > 0]
        wk = sorted(g["week"].unique())[-weeks:]
        if len(wk) < weeks:
            mean, flag = (np.nan if g.empty else _wmean(g[g["week"].isin(wk)])), "insufficient"
        else:
            mean = _wmean(g[g["week"].isin(wk)])
            flag = "drift" if (mean < lo or mean > hi) else "ok"
        out.append(dict(study=study if study is not None else (g["study"].iloc[0] if len(g) else ""),
                        method=method, metric=metric, weeks_used=len(wk), recent_mean=mean,
                        ci_lo=lo, ci_hi=hi, source=source, drift=flag))
    return pd.DataFrame(out, columns=DRIFT_COLUMNS)


def _wmean(g):
    return float(np.average(g["value"], weights=g["n"]))
