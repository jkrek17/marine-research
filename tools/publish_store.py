#!/usr/bin/env python3
"""Publish locally written model fields (rk.store) to the marine-research-data releases.

  python3 tools/publish_store.py --repo <clone of jkrek17/marine-research-data> [--max-mb 500]
         [--include-legacy] [--dry-run]

--repo defaults to the RK_DATA_REPO environment variable.

For every cache cycle with unpublished files (rk.store.dirty), the cycle's zip is built from the files
already published (downloaded from the release, if the asset exists) plus the local unpublished files, so
a new step or a gfs_low file never drops what another thread published. Zips are committed as
incoming/{basin}/{YYYYMMDDHH}.zip on a branch upload/<utc-timestamp>-<n> (batches of at most --max-mb)
and pushed; the data repo's workflow turns them into release assets and deletes the branch. The
unpublished marks are cleared only after a batch's push succeeded; then the local upload branch and its
remote-tracking ref are deleted, and at the end of a run that pushed anything the clone's reflogs are
expired and it is gc'd with --prune=now, so the uploaded zips are not kept locally (they once filled the disk). A cycle whose local files are all
identical to the published ones is not re-uploaded (its marks are just cleared).

--include-legacy also treats every file under RK_DATA/fields (the old shared layout) as local, for the
one-time move; identical files are skipped, so it is safe to repeat.
--dry-run builds and measures everything but touches neither the repo nor the marks.
"""
import argparse
import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make the repo importable

from rk import paths, store  # noqa: E402


def collect(include_legacy=False):
    """Cycles to publish -> list of (basin, cycle tag, {member name: Path}, [dirty names to clear])."""
    jobs = {}
    for (b, c), names in store.dirty().items():
        d = paths.CACHE / "fields" / b / c
        jobs[(b, c)] = ({n: d / n for n in names}, list(names))
    if include_legacy:
        root = paths.DATA / "fields"
        for f in sorted(root.glob("*/*/*.npz")) if root.is_dir() else []:
            b, c = f.parent.parent.name, f.parent.name
            if b in store.BASINS and len(c) == 10 and c.isdigit():
                files, clear = jobs.setdefault((b, c), ({}, []))
                files.setdefault(f.name, f)   # a dirty cache file wins over the legacy copy
    return [(b, c, files, clear) for (b, c), (files, clear) in sorted(jobs.items())]


def build(basin, cycle, files, outdir):
    """Merged zip for one cycle in outdir. Returns (path or None when nothing differs from the published
    asset, stats, published?)."""
    remote = store._http_get(store.release_url(basin, cycle))
    out = Path(outdir) / ("%s_%s.zip" % (basin, cycle))
    st = store.build_zip(out, files, remote)
    if remote is not None and st["new"] == 0 and st["replaced"] == 0:
        out.unlink()
        return None, st, True
    return out, st, remote is not None


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit("git %s failed in %s:\n%s%s" % (" ".join(args), repo, r.stdout, r.stderr))
    return r.stdout.strip()


def push_batch(repo, batch, stamp, n):
    """Commit the batch's zips on a new branch cut from origin/main and push it. Returns the branch."""
    branch = "upload/%s-%d" % (stamp, n)
    git(repo, "checkout", "-q", "-B", branch, "origin/main")
    rels = []
    for basin, cycle, zpath, _ in batch:
        rel = "incoming/%s/%s.zip" % (basin, cycle)
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(Path(zpath).read_bytes())
        rels.append(rel)
    git(repo, "add", "-f", "--", *rels)
    mb = sum(Path(z).stat().st_size for _, _, z, _ in batch) / 1e6
    git(repo, "commit", "-q", "-m", "upload: %d cycles, %.1f MB\n\n%s" % (len(batch), mb, "\n".join(rels)))
    git(repo, "push", "-q", "origin", "%s:refs/heads/%s" % (branch, branch))
    # pushed: drop the local refs so the zips become unreachable (the data repo's workflow owns the remote one)
    git(repo, "checkout", "-q", "--detach")
    git(repo, "branch", "-q", "-D", branch)
    git(repo, "update-ref", "-d", "refs/remotes/origin/" + branch, check=False)
    return branch


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("RK_DATA_REPO"),
                    help="clone of marine-research-data (default: $RK_DATA_REPO)")
    ap.add_argument("--max-mb", type=float, default=500.0, help="most MB of zips per pushed branch")
    ap.add_argument("--include-legacy", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    jobs = collect(a.include_legacy)
    if not jobs:
        print("nothing to publish")
        return 0
    if not a.dry_run:
        if not a.repo:
            raise SystemExit("give --repo or set RK_DATA_REPO")
        repo = Path(a.repo).resolve()
        if not (repo / ".git").exists():
            raise SystemExit("%s is not a git clone" % repo)
        if git(repo, "status", "--porcelain", "--untracked-files=no"):
            raise SystemExit("%s has uncommitted changes to tracked files; clean it first" % repo)
        was = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if was == "HEAD":
            was = git(repo, "rev-parse", "HEAD")
        git(repo, "fetch", "-q", "origin", "main")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    limit = a.max_mb * 1e6
    batch, size, n, branches = [], 0, 0, []
    total = built = 0

    def flush():
        nonlocal batch, size, n
        if not batch:
            return
        n += 1
        if not a.dry_run:
            branches.append(push_batch(repo, batch, stamp, n))
            for basin, cycle, _, clear in batch:
                store.mark_clean(basin, cycle, clear)
        batch, size = [], 0

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for basin, cycle, files, clear in jobs:
                z, st, published = build(basin, cycle, files, tmp)
                desc = "%s %s: %d local (%d new, %d replaced, %d identical), %d kept from published asset%s" % (
                    basin, cycle, len(files), st["new"], st["replaced"], st["same"], st["kept"],
                    "" if published else " (no published asset yet)")
                if z is None:
                    print(desc, "-> already published")
                    if not a.dry_run:
                        store.mark_clean(basin, cycle, clear)
                    continue
                print(desc, "-> %.1f MB" % (st["size"] / 1e6))
                total += st["size"]
                built += 1
                if batch and size + st["size"] > limit:
                    flush()
                batch.append((basin, cycle, z, clear))
                size += st["size"]
            flush()
    finally:
        if not a.dry_run:
            git(repo, "checkout", "-q", was, check=False)   # back to the branch (or commit) it was on
            if branches:                                    # free the pushed zips from the local object store
                git(repo, "reflog", "expire", "--expire=now", "--all", check=False)
                git(repo, "gc", "-q", "--prune=now", check=False)
    print("%s %d cycles, %.1f MB%s" % ("would push" if a.dry_run else "pushed",
          built, total / 1e6, (" on " + ", ".join(branches)) if branches else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
