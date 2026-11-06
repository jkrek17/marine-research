"""Write the built front drill into a static-site clone as <site folder>/fronts/ (relative paths only): index.html,
app.js, style.css and deck/ (manifest.json + packs p00.json ..., the format make_single.py writes, the whole deck).
Never key.csv or anything from work/. The folder's previous contents are replaced. The header (Training link to "../", All exercises / Peak wind / Frontal analysis nav) is in index.html itself. Does not touch git: push the site repo yourself.

    python3 export_site.py <site folder> [--deck <deck folder>]
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent


def export(site, deck):
    out = Path(site) / "fronts"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(here / "make_single.py"), str(deck), tmp, "--max-mb", "0", "--per-pack", "25"], check=True)
        if out.exists():
            shutil.rmtree(out)
        (out / "deck").mkdir(parents=True)
        for p in (Path(tmp) / "deck").iterdir():
            shutil.copy2(p, out / "deck" / p.name)
    for f in ("index.html", "app.js", "style.css"):
        shutil.copy2(here / f, out / f)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    deck = Path(a[a.index("--deck") + 1]) if "--deck" in a else None
    if deck is None:
        sys.path.insert(0, str(here.parents[2]))
        from rk import paths
        deck = paths.data("extra", "front-drill", "deck")
    site = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--deck")][0]
    o = export(site, deck)
    size = sum(p.stat().st_size for p in o.rglob("*") if p.is_file())
    print("%d files, %.1f MB -> %s" % (sum(1 for p in o.rglob("*") if p.is_file()), size / 1e6, o))
