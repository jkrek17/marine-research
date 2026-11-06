"""Copy the built wind drill into the Training site (a clone of jkrek17/training for GitHub Pages).

Layout (2026-11-06, Jason: "rename it training and clean up the page"):
    <site>/index.html   landing page (site/index.html), with a Front drill card when <site>/fronts/ exists
    <site>/wind/        the wind drill: index.html, app.js, style.css, deck/ (manifest, bench.json, each case's
                        .bin, its +24 h forecast .bin files and satellite JPEGs)
    <site>/fronts/      the front drill, written by studies/2026-11-06-front-drill (not touched here)
The pre-2026-11-06 layout (drill files at the root) is removed.

    python3 export_site.py <site folder>
"""
import json
import shutil
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
site = Path(sys.argv[1])
wind = site / "wind"
deck, out = here / "deck", wind / "deck"
out.mkdir(parents=True, exist_ok=True)
for f in ("index.html", "app.js", "style.css"):
    shutil.copy2(here / f, wind / f)
for old in ("app.js", "style.css"):                  # old root layout
    (site / old).unlink(missing_ok=True)
if (site / "deck").is_dir():
    shutil.rmtree(site / "deck")
(site / ".nojekyll").write_text("")
card = ('    <a class="card" href="fronts/"><h2>Front drill</h2><p>Analyse the fronts on a real Atlantic storm, then compare with '
        'the OPC unified surface analysis.</p><span class="go">Open the front drill &rarr;</span></a>')
landing = (here / "site" / "index.html").read_text()
(site / "index.html").write_text(landing.replace("<!--FRONTS-->", card if (site / "fronts" / "index.html").exists() else ""))
m = json.loads((deck / "manifest.json").read_text())
keep = {"manifest.json", "bench.json"}
for c in m["cases"]:
    keep.add(c["id"] + ".bin")
    keep.update("%s_fc_%s.bin" % (c["id"], k) for k in c.get("fc", {}))
    keep.update(p.name for p in deck.glob(c["id"] + "_*.jpg"))
for name in keep:
    if (deck / name).exists():
        shutil.copy2(deck / name, out / name)
for p in out.iterdir():          # cases dropped from the deck since the last export
    if p.name not in keep:
        p.unlink()
size = sum(p.stat().st_size for p in site.rglob("*") if p.is_file() and ".git" not in p.parts)
print(len(m["cases"]), "cases,", len(keep), "deck files,", round(size / 1e6, 1), "MB ->", site)
