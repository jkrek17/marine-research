"""Tests for rk.fronts (no network). Run with pytest or `python3 tests/test_fronts.py`."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rk import fronts  # noqa: E402

SAMPLE = """
707
ASUS01 KWBC 060900
CODSUS

CODED SURFACE FRONTAL POSITIONS
NWS WEATHER PREDICTION CENTER COLLEGE PARK MD
432 AM EST FRI NOV 06 2026

VALID 110609Z
LOWS 1013 3684
COLD WK 4191 4094 4097

$$

787
ASUS02 KWBC 060900
CODSUS

CODED SURFACE FRONTAL POSITIONS
NWS WEATHER PREDICTION CENTER COLLEGE PARK MD
432 AM EST FRI NOV 06 2026

VALID 110609Z
HIGHS 1033 5241044 1030
4001000
LOWS 986 5101130 1002
4500800 990 5400500
COLD 5241044 4940950 4940950 4500900
WARM 4500900 4300850
 4100800
TROF 6000500 5800550
STNRY 5000600
$$
2345

787
ASUS02 KWBC 060930
CODSUS

CODED SURFACE FRONTAL POSITIONS
NWS WEATHER PREDICTION CENTER COLLEGE PARK MD
432 AM EST FRI NOV 06 2026

VALID 110609Z
LOWS 984 5101130
OCFNT 5101130 4800900
$$

788
ASUS02 KWBC 061500
CODSUS

CODED SURFACE FRONTAL POSITIONS
NWS WEATHER PREDICTION CENTER COLLEGE PARK MD
1032 AM EST FRI NOV 06 2026

VALID 110615Z
LOWS 990 5000500
$$

ASUS02 KWBC 312332
CODSUS

CODED SURFACE FRONTAL POSITIONS
NWS WEATHER PREDICTION CENTER COLLEGE PARK MD
632 PM EST WED DEC 31 2025

VALID 010100Z
LOWS 1001 4000700
STNRY 4000700 4100650
$$
"""


def test_parse_basic():
    out = fronts.parse(SAMPLE)
    valids = [a["valid"] for a in out]
    # the Dec 31 issue valid 0101 belongs to the next year; the Nov bulletins to 2026 (2025 issue year -> 2026)
    assert dt.datetime(2026, 1, 1, 0) in valids and dt.datetime(2026, 11, 6, 9) in valids
    assert valids == sorted(valids) and len(valids) == 3


def test_rollover_year():
    a = [x for x in fronts.parse(SAMPLE) if x["valid"].month == 1][0]
    assert a["valid"] == dt.datetime(2026, 1, 1, 0)
    assert a["lows"] == [(1001.0, 40.0, 290.0)]


def test_corrected_reissue_wins_and_asus01_skipped():
    a = [x for x in fronts.parse(SAMPLE) if x["valid"] == dt.datetime(2026, 11, 6, 9)][0]
    assert a["lows"] == [(984.0, 51.0, 360 - 113.0)]  # the 0930 reissue, not the 986/1002/990 original
    assert [f["type"] for f in a["fronts"]] == ["occluded"]
    assert (36.8, 360 - 8.4) not in [(l[1], l[2]) for l in a["lows"]]  # ASUS01 pair never read


def test_wrapped_pairs_and_trailing_number():
    # take the first (uncorrected) bulletin on its own
    first = SAMPLE.split("ASUS02 KWBC 060930")[0]
    a = fronts.parse(first)[0]
    assert a["highs"] == [(1033.0, 52.4, 360 - 104.4), (1030.0, 40.0, 360 - 100.0)]
    assert a["lows"] == [(986.0, 51.0, 360 - 113.0), (1002.0, 45.0, 360 - 80.0), (990.0, 54.0, 360 - 50.0)]
    types = [f["type"] for f in a["fronts"]]
    assert types == ["cold", "warm", "trough"]  # single-point STNRY dropped
    cold = a["fronts"][0]
    assert len(cold["lat"]) == 3  # duplicate point removed
    assert abs(cold["lon"][0] - 255.6) < 1e-9 and abs(cold["lat"][0] - 52.4) < 1e-9
    warm = a["fronts"][1]
    assert len(warm["lat"]) == 3 and warm["lat"][-1] == 41.0  # wrapped continuation line kept
    # "2345" after $$ must not leak into the trough
    assert len(a["fronts"][2]["lat"]) == 2


def test_sequence_number_before_header_not_leaked():
    text = "ASUS02 KWBC 060900\nCODSUS\n432 AM EST FRI NOV 06 2026\nVALID 110609Z\nCOLD 5000500 4800600\n787\nASUS02 KWBC 061500\nCODSUS\n1032 AM EST FRI NOV 06 2026\nVALID 110615Z\nLOWS 990 5000500\n"
    a = fronts.parse(text)[0]
    assert len(a["fronts"][0]["lat"]) == 2


def test_synoptic():
    assert fronts.synoptic(dt.datetime(2026, 1, 1, 6)) and not fronts.synoptic(dt.datetime(2026, 1, 1, 9))


def test_distance():
    assert abs(fronts.distance_nm(0, 0, 0, 1) - 60.04) < 0.1
    d = fronts.distance_nm(np.array([0.0, 60.0]), np.array([359.5, 10.0]), np.array([0.0, 60.0]), np.array([0.5, 11.0]))
    assert abs(d[0] - 60.04) < 0.1 and abs(d[1] - 30.0) < 0.5


def test_densify():
    la, lo = fronts.densify([50.0, 50.0], [330.0, 340.0], step_nm=25)
    assert la[0] == 50.0 and lo[0] == 330.0 and lo[-1] == 340.0
    steps = fronts.distance_nm(la[:-1], lo[:-1], la[1:], lo[1:])
    assert steps.max() <= 25.0 + 1e-6 and len(la) > 15
    assert la.max() > 50.0  # great circle bulges poleward
    la2, lo2 = fronts.densify([10.0], [20.0])
    assert len(la2) == 1


def test_merge_segments():
    f = [{"type": "cold", "lat": np.array([50.0, 48.0]), "lon": np.array([330.0, 332.0])},
         {"type": "cold", "lat": np.array([44.0, 47.9]), "lon": np.array([335.0, 332.1])},  # reversed
         {"type": "warm", "lat": np.array([50.0, 48.0]), "lon": np.array([330.0, 332.0])},
         {"type": "cold", "lat": np.array([30.0, 28.0]), "lon": np.array([300.0, 301.0])}]
    m = fronts.merge_segments(f, join_nm=30)
    cold = [x for x in m if x["type"] == "cold"]
    assert len(cold) == 2 and len([x for x in m if x["type"] == "warm"]) == 1
    assert len(cold[0]["lat"]) == 4 and cold[0]["lat"][-1] == 44.0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
