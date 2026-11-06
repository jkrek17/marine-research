"""Copy the built wind drill into the Training site (a clone of jkrek17/training for GitHub Pages).

Layout (2026-11-06, Jason: "rename it training and clean up the page"):
    <site>/index.html   landing page (site/index.html), with the Fronts section and nav link when <site>/fronts/ exists
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
fronts = """  <section id="fronts">
    <div class="sechead"><h2>Frontal analysis</h2><span class="q">Place the fronts</span></div>
    <p class="about">The low and any stationary front are given. Draw the cold, warm and occluded fronts, then compare with the Unified Surface Analysis.
      Full credit within 150 nm; front type counts double. 522 cases from analyses since mid-August 2026.</p>
    <div class="cards">
      <div class="card wide"><h3>Front drill</h3><p>One system per case at a synoptic hour. Fields: MSLP and thickness, satellite imagery, 850 mb theta-e,
        10 m convergence, 3 h pressure tendency, 10 m wind with ASCAT, 250 mb isotachs.</p><span class="meta">About 90 seconds a case</span>
        <div class="acts"><a class="act primary" href="fronts/">Start the front drill</a></div></div>
    </div>
  </section>
"""
landing = (here / "site" / "index.html").read_text()
have_fronts = (site / "fronts" / "index.html").exists()
landing = landing.replace("<!--FRONTS-->", fronts if have_fronts else "")
landing = landing.replace("<!--FRONTS_NAV-->", '<a href="#fronts">Frontal analysis</a>' if have_fronts else "")
landing = landing.replace("<!--FRONTS_STEP-->", "        <li>Add the <b>Front drill</b> to practise frontal placement alongside wind speed.</li>" if have_fronts else "")
(site / "index.html").write_text(landing)
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
