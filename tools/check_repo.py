#!/usr/bin/env python3
"""Repo hygiene check. Run before every pull request (and from the pre-commit hook).

    python3 tools/check_repo.py            # every file git would commit
    python3 tools/check_repo.py --staged   # only staged added/copied/modified files

Checks: file size, data file types, hardcoded session paths in .py/.sh,
secret-looking strings, and a design.md in every study folder.
Exits 1 with one message per problem.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 10 * 1024 * 1024
IMG_WARN_BYTES = 1024 * 1024
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
DATA_EXT = {".npz", ".npy", ".nc", ".grib2", ".grb2", ".parquet", ".zarr"}
# Built from pieces so this file does not flag itself.
PATH_RE = re.compile(r"""["'][^"'\n]*(/ho""" + r"""me/|/t""" + r"""mp/)""")
ALLOWED_PATH_LINE = "/mnt/project-files/research-data"
SECRETS = ["gh" + "p_", "github_" + "pat_", "AK" + "IA", "BEGIN " + "PRIVATE KEY"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def file_list(staged):
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    else:
        out = git("ls-files", "-co", "--exclude-standard")
    return sorted({p for p in out.splitlines() if p})


def main():
    staged = "--staged" in sys.argv[1:]
    files = file_list(staged)
    errors, warnings = [], []
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        size = p.stat().st_size
        if size > MAX_BYTES:
            errors.append(f"{rel}: {size / 1e6:.1f} MB, over the 10 MB limit")
        elif ext in IMAGE_EXT and size > IMG_WARN_BYTES:
            warnings.append(f"{rel}: image is {size / 1e6:.1f} MB (over 1 MB), shrink it or keep it out of git")
        if ext in DATA_EXT or any(part.endswith(".zarr") for part in Path(rel).parts):
            errors.append(f"{rel}: data file type, bulk data belongs in RK_DATA or the release store, not git")
        try:
            text = p.read_text(errors="replace") if size <= MAX_BYTES else ""
        except OSError:
            continue
        if ext in (".py", ".sh"):
            for n, line in enumerate(text.splitlines(), 1):
                if ALLOWED_PATH_LINE in line and rel == "rk/paths.py":
                    continue
                if PATH_RE.search(line):
                    errors.append(f"{rel}:{n}: hardcoded absolute session path in a string; "
                                  "find the repo from __file__ and data from rk.paths")
        for s in SECRETS:
            if s in text:
                errors.append(f"{rel}: contains secret-looking string '{s}'")
    # Study folders: only meaningful for the whole tree, but cheap either way.
    studies = ROOT / "studies"
    if studies.is_dir():
        for d in sorted(studies.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and not (d / "design.md").is_file():
                errors.append(f"studies/{d.name}: missing design.md (copy templates/design_card.md)")
    for w in warnings:
        print("check_repo: warning:", w)
    if errors:
        for e in errors:
            print("check_repo: FAIL:", e)
        print(f"check_repo: {len(errors)} problem(s) in {len(files)} files")
        return 1
    print(f"check_repo: OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
