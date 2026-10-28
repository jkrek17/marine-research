"""Cycle lists, the fixed tune / held-out split, and which model runs exist in the archive."""
import datetime as dt

from .basins import BASINS

STEPS = (24, 48, 72, 96, 120)

_START = {"gfs": dt.datetime(2025, 3, 1), "gefs": dt.datetime(2025, 3, 1), "ifs": dt.datetime(2025, 3, 1),
          "ens": dt.datetime(2025, 3, 1), "aifs": dt.datetime(2025, 3, 1),
          "aifs-ens": dt.datetime(2025, 8, 1),
          "aigfs": dt.datetime(2025, 1, 1)}   # via NOAA's hindcast of the current model (nwp.sources.aigfs)


def tag(d):
    """datetime -> 'YYYYMMDDHH'."""
    return d.strftime("%Y%m%d%H")


def parse(t):
    """'YYYYMMDDHH' -> datetime."""
    return dt.datetime.strptime(t, "%Y%m%d%H")


def _dt(x):
    return x if isinstance(x, dt.datetime) else dt.datetime(x.year, x.month, x.day)


def cycles(basin, start, end, every_days=1, hour=None):
    """Cycle datetimes from start to end (inclusive, by date) every N days at the basin's hour."""
    h = BASINS[basin]["hour"] if hour is None else hour
    d = _dt(start).replace(hour=h, minute=0, second=0, microsecond=0)
    stop = _dt(end).replace(hour=h, minute=0, second=0, microsecond=0)
    out = []
    while d <= stop:
        out.append(d)
        d += dt.timedelta(days=every_days)
    return out


def winter(d):
    """True for November to March."""
    return d.month in (11, 12, 1, 2, 3)


def held_out(d):
    """True in the fixed held-out ISO weeks, about one in five. Fixed 2026-10-16; never change it."""
    y, w, _ = d.isocalendar()
    return (y * 53 + w) % 5 == 0


def split(d):
    """'held_out' or 'tune'."""
    return "held_out" if held_out(d) else "tune"


def available(model, d):
    """True if the model's runs are archived on AWS for that date."""
    key = "aifs" if model == "aifs-single" else model
    if key not in _START:
        raise KeyError("unknown model %r" % model)
    return _dt(d) >= _START[key]
