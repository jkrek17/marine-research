"""Rebuild the five worked storm cases for the report from the store (held-out weeks only).

    python3 reports/2026-11-07-best-wind/cases/build.py

Reuses studies/2026-11-07-most-likely-wind/build_cases.case_job (same grids, same ASCAT target).
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUDY = REPO / "studies" / "2026-11-07-most-likely-wind"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(STUDY))

CASES = [  # basin, cycle, step
    ("natl", dt.datetime(2025, 12, 9, 0), 48),
    ("natl", dt.datetime(2026, 1, 11, 12), 48),
    ("natl", dt.datetime(2026, 3, 20, 12), 48),
    ("npac", dt.datetime(2025, 11, 6, 0), 48),
    ("npac", dt.datetime(2026, 3, 22, 0), 72),
]


def bc():
    spec = importlib.util.spec_from_file_location("ml_build_cases", STUDY / "build_cases.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


if __name__ == "__main__":
    m = bc()
    for job in CASES:
        print(job, m.case_job(job), m.out_path(*job), flush=True)
