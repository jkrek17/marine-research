"""Offline tests for rk.preset (CLI, drift flag) and tools/run_presets.py with fake presets.
Run with pytest or `python3 tests/test_presets.py`."""
import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pandas as pd  # noqa: E402

from rk import preset  # noqa: E402
import run_presets  # noqa: E402

FAKE = '''
import sys
from pathlib import Path
sys.path.insert(0, %(root)r)
STUDY = "fake-study"
CI = {("m1", "score"): (0.4, 0.6, "fake source"), ("m1", "other"): (0.0, 1.0, "fake source")}


def run(start, end, skip_missing=False):
    from rk.preset import iso_week
    rows, d = [], start
    while d <= end:
        for basin in ("natl", "npac"):
            rows.append(dict(study=STUDY, week=iso_week(d), basin=basin, method="m1", metric="score",
                             value=%(value)s, n=2, truth="fake"))
        d += __import__("datetime").timedelta(days=7)
    return rows, %(missing)s

if __name__ == "__main__":
    from rk.preset import cli
    sys.exit(cli(STUDY, run))
'''


def _frame(values, n=None, metric="score", method="m1", study="s"):
    rows = []
    for i, v in enumerate(values):
        rows.append(dict(study=study, week="2026-W%02d" % (10 + i), basin="natl", method=method, metric=metric,
                         value=v, n=1 if n is None else n[i], truth="t"))
    return pd.DataFrame(rows, columns=preset.COLUMNS)


def test_iso_week():
    assert preset.iso_week(dt.datetime(2025, 12, 29)) == "2026-W01"
    assert preset.iso_week(dt.datetime(2026, 1, 4)) == "2026-W01"
    assert preset.iso_week(dt.datetime(2025, 11, 3)) == "2025-W45"


def test_drift_inside_outside_and_window():
    ci = {("m1", "score"): (0.4, 0.6, "src")}
    # older weeks far outside, newest four inside: only the newest four count
    df = _frame([9.0, 9.0, 0.5, 0.45, 0.55, 0.5])
    r = preset.drift_flags(df, ci, study="s").iloc[0]
    assert r.drift == "ok" and r.weeks_used == 4 and abs(r.recent_mean - 0.5) < 1e-12 and r.source == "src"
    # newest four mean above the interval
    r = preset.drift_flags(_frame([0.5, 0.5, 0.7, 0.7, 0.7, 0.7]), ci, study="s").iloc[0]
    assert r.drift == "drift" and abs(r.recent_mean - 0.7) < 1e-12
    # below the interval
    assert preset.drift_flags(_frame([0.1] * 4), ci, study="s").iloc[0].drift == "drift"
    # boundary values are inside
    assert preset.drift_flags(_frame([0.6] * 4), ci, study="s").iloc[0].drift == "ok"
    assert preset.drift_flags(_frame([0.4] * 4), ci, study="s").iloc[0].drift == "ok"


def test_drift_weights_by_n_and_basins():
    ci = {("m1", "score"): (0.0, 0.5, "src")}
    # four weeks; one week with n=97 at 1.0 outweighs three weeks of n=1 at 0.0
    df = _frame([0.0, 0.0, 0.0, 1.0], n=[1, 1, 1, 97])
    r = preset.drift_flags(df, ci, study="s").iloc[0]
    assert abs(r.recent_mean - 0.97) < 1e-12 and r.drift == "drift"
    # two basins in the same week count as one week
    df = pd.concat([_frame([0.3, 0.3, 0.3, 0.3]), _frame([0.5, 0.5, 0.5, 0.5])], ignore_index=True)
    r = preset.drift_flags(df, ci, study="s").iloc[0]
    assert r.weeks_used == 4 and abs(r.recent_mean - 0.4) < 1e-12 and r.drift == "ok"


def test_drift_insufficient_and_other_methods_ignored():
    ci = {("m1", "score"): (0.4, 0.6, "src"), ("m2", "score"): (0.4, 0.6, "src")}
    df = pd.concat([_frame([0.9, 0.9, 0.9]), _frame([0.5] * 5, method="m2")], ignore_index=True)
    r = preset.drift_flags(df, ci, study="s").set_index("method")
    assert r.loc["m1", "drift"] == "insufficient" and r.loc["m1", "weeks_used"] == 3
    assert r.loc["m2", "drift"] == "ok"      # m1's rows do not leak into m2
    # nothing at all for a key with an interval
    r = preset.drift_flags(_frame([0.5] * 4), {("zz", "score"): (0, 1, "s")}, study="s").iloc[0]
    assert r.drift == "insufficient" and r.weeks_used == 0


def _studies(tmp, specs):
    for name, (value, missing) in specs.items():
        d = Path(tmp) / "studies" / name
        d.mkdir(parents=True)
        (d / "preset.py").write_text(FAKE % dict(root=str(ROOT), value=value, missing=missing))
    return Path(tmp) / "studies"


def test_cli_missing_input_policy():
    with tempfile.TemporaryDirectory() as tmp:
        studies = _studies(tmp, {"a": ("0.5", "['gfs f144 not in the store']")})
        out = Path(tmp) / "o.csv"
        base = [sys.executable, str(studies / "a" / "preset.py"), "--start", "2026-03-02", "--end", "2026-03-23", "--out", str(out)]
        r = subprocess.run(base, capture_output=True, text=True)
        assert r.returncode == 3 and not out.exists()
        assert "gfs f144 not in the store" in r.stderr
        r = subprocess.run(base + ["--skip-missing"], capture_output=True, text=True)
        assert r.returncode == 0 and out.exists()
        df = pd.read_csv(out)
        assert list(df.columns) == preset.COLUMNS and len(df) == 8      # 4 weeks x 2 basins


def test_run_presets_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        studies = _studies(tmp, {"2026-01-01-good": ("0.5", "[]"), "2026-01-02-high": ("0.9", "[]")})
        bad = studies / "2026-01-03-broken"
        bad.mkdir()
        (bad / "preset.py").write_text("import sys\nsys.stderr.write('boom\\n')\nsys.exit(2)\n")
        out = Path(tmp) / "out"
        rc = run_presets.main(["--start", "2026-03-02", "--end", "2026-03-23", "--out-dir", str(out),
                               "--studies-dir", str(studies)])
        assert rc == 1                                        # one preset failed
        st = pd.read_csv(out / "preset_status.csv").set_index("study")
        assert st.loc["2026-01-01-good", "status"] == "ok"
        assert st.loc["2026-01-03-broken", "status"] == "failed" and "boom" in st.loc["2026-01-03-broken", "message"]
        sc = pd.read_csv(out / "standing_scores.csv")
        assert list(sc.columns) == preset.COLUMNS
        assert len(sc) == 16 and set(sc.study) == {"fake-study"}      # 2 good presets x 4 weeks x 2 basins
        dr = pd.read_csv(out / "drift_flags.csv")
        good = dr[(dr.study == "2026-01-01-good") & (dr.metric == "score")].iloc[0]
        high = dr[(dr.study == "2026-01-02-high") & (dr.metric == "score")].iloc[0]
        assert good.drift == "ok" and high.drift == "drift"
        # metric with an interval but no rows is reported, not dropped
        assert dr[(dr.study == "2026-01-01-good") & (dr.metric == "other")].iloc[0].drift == "insufficient"


def test_run_presets_no_presets():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "studies").mkdir()
        rc = run_presets.main(["--start", "2026-03-02", "--end", "2026-03-09", "--out-dir", str(Path(tmp) / "o"),
                               "--studies-dir", str(Path(tmp) / "studies")])
        assert rc == 0 and (Path(tmp) / "o" / "standing_scores.csv").exists()


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)
