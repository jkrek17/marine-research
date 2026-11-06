"""Read front drill cases (deck format in ../2026-11-06-front-drill/design.md) and pick the pilot's test cases.

The deck lives in the shared folder (rk.paths.data("extra", "front-drill")); nothing here downloads."""
import csv
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from rk import paths, cases as rkcases  # noqa: E402

DRILL = paths.data("extra", "front-drill")
DECK = DRILL / "deck"
DRAWN = ("cold", "warm", "occluded")      # what the trainee (and the agent) draws
SEED = 20261106
N_TEST = {"natl": 30, "npac": 20}


def manifest():
    return json.loads((DECK / "manifest.json").read_text())


def valid_times():
    with open(DRILL / "key.csv") as f:
        return {r["id"]: dt.datetime.strptime(r["valid"], "%Y%m%d%H") for r in csv.DictReader(f)}


def fields(case, man=None):
    """Decoded fields {key: (ny, nx) float array, NaN missing}, plus lat (ny,) and lon (nx,) cell centres (lon 0-360)."""
    man = man or manifest()
    ny, nx, res = man["ny"], man["nx"], man["res"]
    raw = np.fromfile(DECK / f"{case['id']}.bin", dtype=np.uint8).reshape(len(man["fields"]), ny, nx)
    out = {}
    for k, f in enumerate(man["fields"]):
        a = f["offset"] + f["scale"] * raw[k].astype(float)
        a[raw[k] == 255] = np.nan
        out[f["key"]] = a
    out["lat"] = case["lat0"] - res * np.arange(ny)
    out["lon"] = case["lon0"] + res * np.arange(nx)
    out["ws10_kt"] = np.hypot(out["u10"], out["v10"]) * 1.94384
    return out


def image_path(case):
    return DECK / f"{case['id']}_{case['img']}.jpg" if case.get("img") else None


def system_fronts(case, types=DRAWN):
    return [f for f in case["fronts"] if f.get("sys", True) and f["type"] in types]


def given(case):
    """What the trainee is given: the system's stationary fronts and the analysed lows inside the ring."""
    st = [f for f in case["fronts"] if f.get("sys", True) and f["type"] == "stationary"]
    r = case.get("sys_r_nm") or 1e9
    lows = [l for l in (case.get("lows") or [case["low"]]) if _nm(l["lat"], l["lon"], case["low"]["lat"], case["low"]["lon"]) <= r]
    return st, lows or [case["low"]]


def _nm(la1, lo1, la2, lo2):
    p1, p2, dl = np.radians(la1), np.radians(la2), np.radians(lo2 - lo1)
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6880.13 * np.arcsin(min(1.0, np.sqrt(h)))


def test_ids():
    """The pilot's 50 cases: seeded draw from held-out weeks, 30 N Atlantic, 20 N Pacific."""
    vt = valid_times()
    rng = random.Random(SEED)
    out = []
    for basin, n in N_TEST.items():
        pool = sorted(c["id"] for c in manifest()["cases"] if c["basin"] == basin and rkcases.held_out(vt[c["id"]]))
        out += sorted(rng.sample(pool, n))
    return out


def tune_ids():
    """Every case outside the held-out weeks (TFP tuning, prompt work, worked examples)."""
    vt = valid_times()
    return [c["id"] for c in manifest()["cases"] if not rkcases.held_out(vt[c["id"]])]


if __name__ == "__main__":
    t = test_ids()
    print(len(t), "test,", len(tune_ids()), "tune")
    print(" ".join(t))
