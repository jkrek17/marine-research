"""Tests for rk.cases. Run with pytest or `python3 tests/test_cases.py`."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rk import cases  # noqa: E402


def test_tag_parse():
    d = dt.datetime(2026, 1, 15, 12)
    assert cases.tag(d) == "2026011512"
    assert cases.parse("2026011512") == d


def test_cycles():
    c = cases.cycles("natl", dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 10), every_days=3)
    assert [x.day for x in c] == [1, 4, 7, 10] and all(x.hour == 12 for x in c)
    p = cases.cycles("npac", dt.date(2026, 1, 1), dt.date(2026, 1, 3))
    assert len(p) == 3 and all(x.hour == 0 for x in p)
    assert cases.cycles("npac", dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 2), hour=6)[0].hour == 6


def test_winter():
    assert cases.winter(dt.datetime(2026, 11, 1)) and cases.winter(dt.datetime(2026, 3, 31))
    assert not cases.winter(dt.datetime(2026, 4, 1)) and not cases.winter(dt.datetime(2026, 10, 31))


def test_held_out_rule():
    # ISO week 3 of 2026: 2026 * 53 + 3 = 107381, 107381 % 5 = 1 -> tune
    assert not cases.held_out(dt.datetime(2026, 1, 15))
    # ISO week 4 of 2026: 107382 % 5 = 2; week 2 of 2026: 107380 % 5 = 0 -> held out
    assert cases.held_out(dt.datetime(2026, 1, 8)) and cases.split(dt.datetime(2026, 1, 8)) == "held_out"
    assert cases.split(dt.datetime(2026, 1, 15)) == "tune"
    # the whole ISO week shares one answer (Monday 5 Jan to Sunday 11 Jan 2026 is week 2)
    assert len({cases.held_out(dt.datetime(2026, 1, 5 + i, 12)) for i in range(7)}) == 1
    # ISO year, not calendar year: 2024-12-30 is week 1 of ISO 2025
    assert cases.held_out(dt.datetime(2024, 12, 30)) == ((2025 * 53 + 1) % 5 == 0)


def test_held_out_fraction():
    days = [dt.datetime(2025, 1, 1) + dt.timedelta(days=i) for i in range(730)]
    f = sum(cases.held_out(d) for d in days) / len(days)
    assert 0.15 < f < 0.25, f


def test_available():
    assert not cases.available("gfs", dt.datetime(2025, 2, 28, 12))
    assert cases.available("gfs", dt.datetime(2025, 3, 1))
    assert cases.available("ens", dt.datetime(2025, 3, 1)) and cases.available("aifs", dt.datetime(2025, 3, 1))
    assert not cases.available("aifs-ens", dt.datetime(2025, 7, 31, 12))
    assert cases.available("aifs-ens", dt.datetime(2025, 8, 1))


def test_steps():
    assert cases.STEPS == (24, 48, 72, 96, 120)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
