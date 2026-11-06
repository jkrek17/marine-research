"""Inline style.css and app.js into one page for an Artifact preview, deck beside it in packs (several cases per JSON file,
each case the zlib-deflated .bin and a re-compressed JPEG, both base64): the Artifact host does not serve .bin and a publish
takes at most 255 files and a page of about 16 MB.

    python3 make_single.py <deck folder> <out folder> [--since=YYYYMMDDHH] [--max-mb 15] [--per-pack 25] [--jpeg-q 50]

--max-mb caps the deck's total size (0 = no cap): when the cases do not fit, a random subset (fixed seed) is taken that keeps
the Atlantic / Pacific split. The summary line says how many of how many cases were kept and the total size.
"""
import base64
import csv
import json
import random
import re
import sys
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image

here = Path(__file__).resolve().parent
argv = sys.argv[1:]


def opt(name, default):
    for i, a in enumerate(argv):
        if a.startswith("--%s=" % name):
            return a.split("=", 1)[1]
        if a == "--%s" % name:
            return argv[i + 1]
    return default


since = opt("since", None)           # keep cases valid from then on (key.csv beside the deck)
max_mb, per_pack, jpeg_q = float(opt("max-mb", 15)), int(opt("per-pack", 25)), int(opt("jpeg-q", 50))
flagged = {"--since", "--max-mb", "--per-pack", "--jpeg-q"}
args, skip = [], False
for i, a in enumerate(argv):
    if skip:
        skip = False
    elif a in flagged:
        skip = True
    elif not a.startswith("--"):
        args.append(a)
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

# not the enclosed or coastal waters find_cases.excluded_water() names (Gulf of Mexico, Hudson Bay, Gulf of St Lawrence in
# the Atlantic; Gulf of California, Puget Sound in the Pacific), and not south of 25N. Pacific lows are at 180-250E: no longitude cut.
sys.path.insert(0, str(here.parent))
from find_cases import excluded_water  # noqa: E402
m["cases"] = [c for c in m["cases"] if c["low"]["lat"] >= 25 and not excluded_water(c.get("basin", "natl"), c["low"]["lat"], c["low"]["lon"])]
if since:
    when = {r["id"]: r["valid"] for r in csv.DictReader(open(deck.parent / "key.csv"))}
    m["cases"] = [c for c in m["cases"] if when.get(c["id"], "") >= since]
# the trainee draws cold, warm and occluded only (lows and stationary fronts are given): keep cases with one to draw
drawable = {"cold", "warm", "occluded"}
m["cases"] = [c for c in m["cases"] if any(f.get("sys", True) and f["type"] in drawable for f in c["fronts"])]


def encode(c):
    """{"z": base64 deflated bin, "img": data URI}, the second only when the case has a picture."""
    rec = {"z": base64.b64encode(zlib.compress((deck / (c["id"] + ".bin")).read_bytes(), 9)).decode()}
    f = deck / ("%s_%s.jpg" % (c["id"], c.get("img")))
    if c.get("img") and f.exists():
        buf = BytesIO()
        Image.open(f).convert("L" if c["img"] == "ir" else "RGB").save(buf, "JPEG", quality=jpeg_q, optimize=True)
        rec["img"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return rec


n_all = len(m["cases"])
enc = {c["id"]: encode(c) for c in m["cases"]}
size = {k: len(json.dumps(v, separators=(",", ":"))) + len(k) + 6 for k, v in enc.items()}
fixed = len(page.encode()) + 4000          # index.html and a pack's wrapper
if max_mb > 0:
    budget = max_mb * 1e6 - fixed
    cost = {c["id"]: size[c["id"]] + len(json.dumps(c, separators=(",", ":"))) for c in m["cases"]}   # pack share + manifest entry
    if sum(cost.values()) > budget:
        rng = random.Random(1106)
        by = {}
        for c in m["cases"]:
            by.setdefault(c.get("basin", "natl"), []).append(c)
        for v in by.values():
            rng.shuffle(v)
        total = sum(cost.values())
        keep, used = [], 0.0
        # proportional: take from each basin in turn by its share of the full set until the budget is spent
        order = sorted(by, key=lambda b: -len(by[b]))
        taken = {b: 0 for b in order}
        while True:
            b = min(order, key=lambda b: (taken[b] / max(1, len(by[b])), order.index(b)))
            if taken[b] >= len(by[b]):
                break
            c = by[b][taken[b]]
            if used + cost[c["id"]] > budget:
                break
            keep.append(c)
            used += cost[c["id"]]
            taken[b] += 1
        keep_ids = {c["id"] for c in keep}
        m["cases"] = [c for c in m["cases"] if c["id"] in keep_ids]
m["encoding"] = "pack"
for f in (out / "deck").glob("*"):
    f.unlink()
total = 0
for k in range(0, len(m["cases"]), per_pack):
    name = "p%02d" % (k // per_pack)
    chunk = m["cases"][k:k + per_pack]
    for c in chunk:
        c["pack"] = name
    t = json.dumps({c["id"]: enc[c["id"]] for c in chunk}, separators=(",", ":"))
    (out / "deck" / (name + ".json")).write_text(t)
    total += len(t)
mt = json.dumps(m, separators=(",", ":"))
(out / "deck" / "manifest.json").write_text(mt)
total += len(mt) + len(page.encode())
nb = {b: sum(c.get("basin", "natl") == b for c in m["cases"]) for b in ("natl", "npac")}
print("%d of %d cases (N Atlantic %d, N Pacific %d) -> %s: %.1f MB, %d files" % (
    len(m["cases"]), n_all, nb["natl"], nb["npac"], out, total / 1e6, len(list(out.rglob("*"))) - 1))
