"""Chance remaps: the calibrated gale chance (P34) curves of the Chance calibration thread.

A curves file is JSON {season: {truth: {basin: {lead_group: {"raw": [...], "cal": [...]}}}}}, knots in percent,
lead groups "le48" (steps <= 48), "72" (step 72) and "ge96" (steps >= 96), as the marine wind page's
calibration.json. `p34_remap` interpolates linearly between the knots (flat beyond the ends)."""
import json

import numpy as np


def load_curves(path):
    """Read a curves JSON file -> dict."""
    with open(path) as fh:
        return json.load(fh)


def lead_group(step):
    """Lead group name of a forecast step in hours."""
    return "le48" if step <= 48 else ("72" if step == 72 else "ge96")


def p34_remap(p, basin, step, curves, season="winter", truth="ascat"):
    """Calibrated P34 (0..1) from the raw member share p (0..1, any array shape) for one basin and step."""
    k = curves[season][truth][basin][lead_group(int(step))]
    raw, cal = np.asarray(k["raw"], float), np.asarray(k["cal"], float)
    if np.any(np.diff(raw) <= 0):
        raise ValueError("raw knots must increase")
    return (np.interp(np.asarray(p, float) * 100.0, raw, cal) / 100.0).astype(np.float32)
