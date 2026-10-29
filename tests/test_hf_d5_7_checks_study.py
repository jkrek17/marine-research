"""Tests for the day 5-7 HF checks (studies/2026-10-29-hf-d5-7-checks). Run: python3 tests/test_hf_d5_7_checks_study.py"""
import datetime as dt
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-29-hf-d5-7-checks"))
import numpy as np
import pandas as pd
import build
import score as S


def test_near_storms_radius_and_ids():
    clat, clon = np.array([50.0, 50.0, 40.0]), np.array([330.0, 336.0, 330.0])
    f = pd.DataFrame({"event_id": ["a", "b"], "lat": [50.0, 50.0], "lon": [330.0, 337.5]})
    got = build.near_storms(f, clat, clon)
    assert got[0] == "a"                    # b is ~535 km east: outside 500 km
    assert got[1] == "a;b"                  # ~430 km from a, ~107 km from b
    assert got[2] == ""                     # 1,110 km south


def test_archive_window_keeps_times_with_rows():
    # a filtered archive (index with gaps) must keep each fix with its own time (the to_pydatetime bug)
    a = pd.DataFrame({"event_id": ["x", "y", "z"], "valid": pd.to_datetime(["2025-10-01 00", "2025-10-12 06",
                                                                          "2025-10-20 12"]),
                      "lat": [50.0] * 3, "lon": [330.0] * 3, "category": ["S", "HF", "HF"]})
    h = a[a.category == "HF"].reset_index(drop=True)
    v = dt.datetime(2025, 10, 12, 12)
    w = h[(h.valid >= v - dt.timedelta(hours=build.WINDOW_H)) & (h.valid <= v + dt.timedelta(hours=build.WINDOW_H))]
    assert w.event_id.tolist() == ["y"]


def test_member_codes_and_share():
    assert build.code([899.0, 955.4, 1200.0]).tolist() == [0, 55, 253]
    mem = np.array([[55, 60, build.NO_LOW, build.ABSENT],
                    [build.NO_LOW, build.NO_LOW, 40, build.ABSENT]], np.uint8)
    p, k, n = S.share(mem, 955)
    assert k.tolist() == [1, 1] and n.tolist() == [3, 3] and np.allclose(p, [1 / 3, 1 / 3])
    p, k, n = S.share(mem, 960, cols=np.array([0, 1]))
    assert k.tolist() == [2, 0] and n.tolist() == [2, 2]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
