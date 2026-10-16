#!/usr/bin/env python3
"""Run every study's standing-score preset on a date range and collect the results.

    python3 tools/run_presets.py --start YYYY-MM-DD --end YYYY-MM-DD --out-dir DIR [--studies-dir studies]

Finds studies/*/preset.py, runs each as `preset.py --start --end --out DIR/<study>.csv --skip-missing`, and writes
into DIR:
  standing_scores.csv   all presets' rows concatenated (columns study, week, basin, method, metric, value, n, truth)
  drift_flags.csv       per study, method and metric that has an original interval (the preset's CI constant): the
                        mean of the newest 4 weeks (weighted by n) against that interval; drift is
                        ok | drift | insufficient (fewer than 4 weeks)
  preset_status.csv     per study: ok or failed, exit code and the last stderr lines (a failing preset does not
                        stop the others; the exit code of this tool is 1 if any failed)
The preset's CI is read by importing its module (heavy imports sit inside run(), so this is cheap).
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from rk.preset import COLUMNS, DRIFT_COLUMNS, drift_flags  # noqa: E402


def find_presets(studies_dir):
    return sorted(Path(studies_dir).glob("*/preset.py"))


def load_ci(preset):
    """(STUDY, CI) from a preset module, without running it."""
    spec = importlib.util.spec_from_file_location("preset_" + preset.parent.name.replace("-", "_"), preset)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(preset.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return getattr(mod, "STUDY", preset.parent.name), dict(getattr(mod, "CI", {}))


def run_one(preset, start, end, out_csv):
    p = subprocess.run([sys.executable, str(preset), "--start", start, "--end", end, "--out", str(out_csv),
                        "--skip-missing"], capture_output=True, text=True)
    return p.returncode, p.stderr.strip().splitlines()[-6:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--studies-dir", default=str(ROOT / "studies"))
    a = ap.parse_args(argv)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, status, drifts = [], [], []
    for preset in find_presets(a.studies_dir):
        study = preset.parent.name
        out_csv = out_dir / (study + ".csv")
        if out_csv.exists():
            out_csv.unlink()
        code, tail = run_one(preset, a.start, a.end, out_csv)
        ok = code == 0 and out_csv.exists()
        status.append(dict(study=study, status="ok" if ok else "failed", exit_code=code, message=" | ".join(tail)))
        if not ok:
            print("FAILED %s (exit %s): %s" % (study, code, " | ".join(tail)), file=sys.stderr)
            continue
        df = pd.read_csv(out_csv)
        frames.append(df)
        try:
            name, ci = load_ci(preset)
            drifts.append(drift_flags(df, ci, study=study))
        except Exception as e:      # a broken CI constant must not hide the scores
            status[-1]["message"] += " | CI not read: %s" % e
    allrows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    allrows[COLUMNS].to_csv(out_dir / "standing_scores.csv", index=False)
    (pd.concat(drifts, ignore_index=True) if drifts else pd.DataFrame(columns=DRIFT_COLUMNS)).to_csv(
        out_dir / "drift_flags.csv", index=False)
    pd.DataFrame(status, columns=["study", "status", "exit_code", "message"]).to_csv(out_dir / "preset_status.csv", index=False)
    print("%d rows from %d of %d presets" % (len(allrows), len(frames), len(status)))
    return 0 if all(s["status"] == "ok" for s in status) else 1


if __name__ == "__main__":
    sys.exit(main())
