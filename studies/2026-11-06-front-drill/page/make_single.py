"""Inline style.css and app.js into one page for an Artifact preview, deck beside it as one base64 JSON per case
(the Artifact host does not serve .bin and caps a publish at 255 files).

    python3 make_single.py <deck folder> <out folder>
"""
import base64
import json
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--since=")]
since = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--since=")), None)   # YYYYMMDDHH: keep cases valid from then on (key.csv beside the deck)
deck, out = Path(args[0]), Path(args[1])
(out / "deck").mkdir(parents=True, exist_ok=True)
html = (here / "index.html").read_text()
body = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
body = re.sub(r'<script src="app.js"></script>', lambda _: "<script>\n%s\n</script>" % (here / "app.js").read_text(), body)
css = re.sub(r"^@import url\([^)]*\);\s*$", "", (here / "style.css").read_text(), flags=re.M)
page = ('<meta charset="utf-8">\n<title>Front drill</title>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap">\n'
        "<style>\n:root{color-scheme:light}\n%s\n</style>\n%s" % (css, body))
(out / "index.html").write_text(page)
m = json.loads((deck / "manifest.json").read_text())
m["encoding"] = "base64"
# outside the natl basin (Gulf of Mexico, south of 30N): no ASCAT, partial imagery
m["cases"] = [c for c in m["cases"] if c["low"]["lat"] >= 30 and c["low"]["lon"] >= 270]
if since:
    import csv
    when = {r["id"]: r["valid"] for r in csv.DictReader(open(deck.parent / "key.csv"))}
    m["cases"] = [c for c in m["cases"] if when.get(c["id"], "") >= since]
(out / "deck" / "manifest.json").write_text(json.dumps(m, separators=(",", ":")))
for c in m["cases"]:
    rec = {"bin": base64.b64encode((deck / (c["id"] + ".bin")).read_bytes()).decode()}
    f = deck / ("%s_%s.jpg" % (c["id"], c.get("img")))
    if c.get("img") and f.exists():
        rec["img"] = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
    (out / "deck" / (c["id"] + ".json")).write_text(json.dumps(rec, separators=(",", ":")))
print(len(m["cases"]), "cases ->", out)
