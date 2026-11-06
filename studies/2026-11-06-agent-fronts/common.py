"""Shared pieces of the agentic-fronts pilot: scoring through the front drill's own scoreCase (node), drawn-front format."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import deck  # noqa: E402

APP_JS = ROOT / "studies" / "2026-11-06-front-drill" / "page" / "app.js"


def app_js():
    """The drill page's app.js: from the working tree when the front drill is merged, else from its branch."""
    if APP_JS.exists():
        return APP_JS
    out = HERE / ".app.js"
    for ref in ("origin/main", "origin/claude/project-thread-qls2sg"):
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:studies/2026-11-06-front-drill/page/app.js"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            out.write_text(r.stdout)
            return out
    raise FileNotFoundError("front drill app.js not found on main or its branch")


def score(drawn_by_case):
    """{case_id: [{"type", "pts": [[lat, lon], ...]}]} -> {case_id: drill result (pct 0-100, rows, extras)}."""
    payload = {cid: [{"type": f["type"], "pts": [{"lat": float(p[0]), "lon": float(p[1])} for p in f["pts"]]} for f in fr]
               for cid, fr in drawn_by_case.items()}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:
        json.dump(payload, t)
    r = subprocess.run(["node", str(HERE / "score.js"), str(app_js()), str(deck.DECK / "manifest.json"), t.name],
                       capture_output=True, text=True, check=True)
    Path(t.name).unlink()
    return json.loads(r.stdout)


def taps(lat, lon, every_nm=90):
    """Thin a dense line to tap points about every_nm apart (ends kept), like a trainee's taps."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    keep, acc = [0], 0.0
    for i in range(1, len(lat)):
        acc += deck._nm(lat[i - 1], lon[i - 1], lat[i], lon[i])
        if acc >= every_nm:
            keep.append(i)
            acc = 0.0
    if keep[-1] != len(lat) - 1:
        keep.append(len(lat) - 1)
    return [[round(float(lat[i]), 2), round(float(lon[i]) % 360, 2)] for i in keep]
