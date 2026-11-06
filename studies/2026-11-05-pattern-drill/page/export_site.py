"""Copy the built drill (page + deck) into a static-site folder, e.g. a clone of jkrek17/pattern-drill for
GitHub Pages. Only what the page loads: index.html, app.js, style.css, deck/manifest.json, pairs.json,
bench.json, each case's .bin and its satellite JPEGs.

    python3 export_site.py <site folder>
"""
import json
import shutil
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
site = Path(sys.argv[1])
deck, out = here / "deck", site / "deck"
out.mkdir(parents=True, exist_ok=True)
for f in ("index.html", "app.js", "style.css"):
    shutil.copy2(here / f, site / f)
(site / ".nojekyll").write_text("")
m = json.loads((deck / "manifest.json").read_text())
keep = {"manifest.json", "pairs.json", "bench.json"}
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
