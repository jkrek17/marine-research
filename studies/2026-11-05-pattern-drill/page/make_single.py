"""Inline style.css and app.js into one HTML body fragment (for an Artifact preview, which wants a single
page with its deck files beside it). Writes <out>/index.html; the deck folder is published alongside.

    python3 make_single.py <out folder>
"""
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
html = (here / "index.html").read_text()
body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
body = body.replace('<script src="app.js"></script>', "<script>\n%s\n</script>" % (here / "app.js").read_text())
page = ("<title>Pattern drill</title>\n<style>\n:root{color-scheme:light}\n%s\n</style>\n%s"
        % ((here / "style.css").read_text(), body))
(out / "index.html").write_text(page)
print(out / "index.html", len(page))

# The Artifact host does not serve .bin and caps a publish at 255 files: one base64 JSON per case, images inside, with "encoding" in the manifest.
import base64
import json
deck = here / "deck"
od = out / "deck"
od.mkdir(exist_ok=True)
m = json.loads((deck / "manifest.json").read_text())
m["encoding"] = "base64"
(od / "manifest.json").write_text(json.dumps(m, separators=(",", ":")))
for c in m["cases"]:
    img = {}
    for snap in ("t0", "t24"):
        for kind in ("ir", "am"):
            f = deck / ("%s_%s_%s.jpg" % (c["id"], snap, kind))
            if f.exists():
                img[snap + "_" + kind] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
    rec = {"bin": base64.b64encode((deck / (c["id"] + ".bin")).read_bytes()).decode(), "img": img}
    (od / (c["id"] + ".json")).write_text(json.dumps(rec, separators=(",", ":")))
print(len(m["cases"]), "cases as base64 JSON (one file each, images inside)")
