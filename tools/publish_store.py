#!/usr/bin/env python3
"""Publish locally written model fields and truth files (rk.store) to the marine-research-data releases.

  python3 tools/publish_store.py --repo <clone of jkrek17/marine-research-data> [--max-mb 500]
         [--what all|fields|truth] [--include-legacy] [--include-legacy-truth] [--dry-run]
  python3 tools/publish_store.py --direct <folder> [--what ...]     (the scheduled jobs)

--repo defaults to the RK_DATA_REPO environment variable.

Truth files (analysis, obs, airsea, ascat, smap, gridsat; rk.store.truth_*) travel the same way as plain assets, one
file per valid time or day: incoming/truth/{kind}[/{basin}]/{stem}.npz becomes asset {stem}.npz of release
truth-{kind}[-{basin}]-{YYYYMM}. Merge semantics: the published asset is downloaded and compared with the
local file by array content; a file already published with the same content is skipped (its mark is cleared),
a different local file replaces the published one (local wins, as for fields), and a local NRT smap day never
replaces a published FINAL one. The hf-low archive CSVs are not published (rk.truth.hf_archive reads them
from the hf-low repo over HTTPS).

--direct <folder> does not touch git: the files (field zips as {basin}/{cycle}.zip, truth as truth/...) are
written under <folder> exactly as they would sit under incoming/, for scripts/upload_incoming.sh in the data
repo to upload (the scheduled workflows). Marks are left alone in this mode, since the upload comes after;
a rerun finds the content already published and skips it.

For every cache cycle with unpublished files (rk.store.dirty), the cycle's zip is built from the files
already published (downloaded from the release, if the asset exists) plus the local unpublished files, so
a new step or a gfs_low file never drops what another thread published. Zips are committed as
incoming/{basin}/{YYYYMMDDHH}.zip on a branch upload/<utc-timestamp>-<n> (batches of at most --max-mb)
and pushed; the data repo's workflow turns them into release assets and deletes the branch. The
unpublished marks are cleared only after a batch's push succeeded; then the local upload branch and its
remote-tracking ref are deleted, the clone's reflogs are expired and its loose objects pruned, and the built
zips of the batch are deleted, so a long run holds about one batch on disk (they once filled the disk); a run
that pushed anything ends with gc --prune=now. A cycle whose local files are all
identical to the published ones is not re-uploaded (its marks are just cleared).

--what lab --lab FILE... sends the lab job's fixed inputs: each {name}.npz becomes asset {name}.npz of release
lab-assets (rk.store.lab_asset), replacing the published one.

--include-legacy also treats every file under RK_DATA/fields (the old shared layout) as local, for the
one-time move; identical files are skipped, so it is safe to repeat. --include-legacy-truth does the same
for RK_DATA/truth (analysis, obs, airsea, ascat, smap; about 0.7 GB, about 1,300 files; hf_lows is left out).
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


def collect_truth(include_legacy=False):
    """Truth files to publish -> list of (kind, basin or None, stem, Path, dirty names to clear)."""
    jobs = {}
    for (kind, b), names in store.truth_dirty().items():
        for n in names:
            stem = n[:-4]
            jobs[(kind, b, stem)] = (store.truth_cache_path(kind, b, stem), True)
    if include_legacy:
        for kind, (per_basin, n) in store.TRUTH_KINDS.items():
            for b in (sorted(store.BASINS) if per_basin else [None]):
                root = paths.DATA / "truth" / kind / (b or "")
                for f in sorted(root.glob("*.npz")) if root.is_dir() else []:
                    if len(f.stem) == n and f.stem.isdigit():
                        jobs.setdefault((kind, b, f.stem), (f, False))   # a dirty cache file wins
    return [(k, b, stem, p, dirty) for (k, b, stem), (p, dirty) in sorted(jobs.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2]))]


def build_truth(kind, basin, stem, path):
    """-> (status, published?). status as rk.store.truth_merge: new, same, kept, replaced."""
    remote = store._http_get(store.truth_url(kind, basin, stem))
    return store.truth_merge(kind, path, remote), remote is not None


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
    """Commit the batch's files (rel path under incoming/, source path, size, clear) on a new branch cut from
    origin/main and push it. Returns the branch."""
    branch = "upload/%s-%d" % (stamp, n)
    git(repo, "checkout", "-q", "-B", branch, "origin/main")
    rels = []
    for rel, src, _, _ in batch:
        rel = "incoming/" + rel
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(Path(src).read_bytes())
        rels.append(rel)
    git(repo, "add", "-f", "--", *rels)
    mb = sum(size for _, _, size, _ in batch) / 1e6
    git(repo, "commit", "-q", "-m", "upload: %d files, %.1f MB\n\n%s" % (len(batch), mb, "\n".join(rels)))
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
    ap.add_argument("--direct", metavar="FOLDER", help="write the files to FOLDER (incoming/ layout) "
                    "for scripts/upload_incoming.sh instead of pushing a branch")
    ap.add_argument("--what", choices=("all", "fields", "truth", "lab"), default="all")
    ap.add_argument("--lab", nargs="+", default=[], metavar="FILE", help="lab inputs ({name}.npz) to send with --what lab")
    ap.add_argument("--max-mb", type=float, default=500.0, help="most MB per pushed branch")
    ap.add_argument("--include-legacy", action="store_true", help="also the old RK_DATA/fields files")
    ap.add_argument("--include-legacy-truth", action="store_true", help="also the old RK_DATA/truth files")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    fjobs = collect(a.include_legacy) if a.what in ("all", "fields") else []
    tjobs = collect_truth(a.include_legacy_truth) if a.what in ("all", "truth") else []
    ljobs = [Path(f) for f in a.lab] if a.what == "lab" else []
    for f in ljobs:
        if f.suffix != ".npz" or not f.is_file():
            raise SystemExit("--lab takes existing .npz files, got %s" % f)
    if not fjobs and not tjobs and not ljobs:
        print("nothing to publish")
        return 0
    outdir = Path(a.direct).resolve() if a.direct else None
    repo = was = None
    if not a.dry_run and outdir is None:
        if not a.repo:
            raise SystemExit("give --repo (or --direct) or set RK_DATA_REPO")
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
    limit = float("inf") if outdir else a.max_mb * 1e6
    batch, size, n, branches = [], 0, 0, []
    total = built = 0
    tmp_dir = None

    def flush():
        nonlocal batch, size, n
        if not batch:
            return
        n += 1
        if repo is not None:
            branches.append(push_batch(repo, batch, stamp, n))
        if outdir is not None and not a.dry_run:
            for rel, src, _, _ in batch:
                (outdir / rel).parent.mkdir(parents=True, exist_ok=True)
                (outdir / rel).write_bytes(Path(src).read_bytes())
        if repo is not None:                      # pushed: the marks can go
            for _, _, _, clear in batch:
                clear()
            # free the batch now, not at the end: the pushed zips in the object store and the built zips in
            # the temporary folder once filled the disk on a 500-cycle run
            git(repo, "reflog", "expire", "--expire=now", "--all", check=False)
            git(repo, "prune", "--expire=now", check=False)
        for _, src, _, _ in batch:
            if tmp_dir and Path(src).parent == Path(tmp_dir):   # built zips only, never cache files
                Path(src).unlink(missing_ok=True)
        batch, size = [], 0

    def add(rel, src, nbytes, clear):
        nonlocal batch, size, total, built
        total += nbytes
        built += 1
        if batch and size + nbytes > limit:
            flush()
        batch.append((rel, src, nbytes, clear))
        size += nbytes

    keep_marks = a.dry_run or outdir is not None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = tmp
            for basin, cycle, files, clear in fjobs:
                z, st, published = build(basin, cycle, files, tmp)
                desc = "%s %s: %d local (%d new, %d replaced, %d identical), %d kept from published asset%s" % (
                    basin, cycle, len(files), st["new"], st["replaced"], st["same"], st["kept"],
                    "" if published else " (no published asset yet)")
                if z is None:
                    print(desc, "-> already published")
                    if not keep_marks:
                        store.mark_clean(basin, cycle, clear)
                    continue
                print(desc, "-> %.1f MB" % (st["size"] / 1e6))
                add("%s/%s.zip" % (basin, cycle), z, st["size"],
                    lambda b=basin, c=cycle, cl=clear: store.mark_clean(b, c, cl))
            counts = {}
            for kind, b, stem, path, dirty in tjobs:
                status, published = build_truth(kind, b, stem, path)
                counts[status] = counts.get(status, 0) + 1
                label = "truth %s%s %s" % (kind, "/" + b if b else "", stem)
                if status in ("same", "kept"):
                    if status == "kept":
                        print(label, ": published smap day is FINAL, local is NRT -> kept published")
                    if dirty and not keep_marks:
                        store.truth_mark_clean(kind, b, [stem])
                    continue
                rel = "truth/%s/%s%s.npz" % (kind, b + "/" if b else "", stem)
                add(rel, path, path.stat().st_size,
                    lambda k=kind, bb=b, s_=stem, d=dirty: store.truth_mark_clean(k, bb, [s_]) if d else None)
            for f in ljobs:
                print("lab %s -> %.1f MB" % (f.name, f.stat().st_size / 1e6))
                add("lab/" + f.name, f, f.stat().st_size, lambda: None)
            if tjobs:
                print("truth: %d files (%s)" % (len(tjobs), ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items()))))
            flush()
    finally:
        if repo is not None:
            git(repo, "checkout", "-q", was, check=False)   # back to the branch (or commit) it was on
            if branches:                                    # free the pushed zips from the local object store
                git(repo, "reflog", "expire", "--expire=now", "--all", check=False)
                git(repo, "gc", "-q", "--prune=now", check=False)
    print("%s %d files, %.1f MB%s" % ("would push" if a.dry_run else ("wrote to %s:" % outdir if outdir else "pushed"),
          built, total / 1e6, (" on " + ", ".join(branches)) if branches else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
