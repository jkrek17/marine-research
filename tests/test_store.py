"""Tests for rk.store (field cache, release zips) and tools/publish_store.py. Offline: HTTP is mocked.
Run with pytest or `python3 tests/test_store.py`."""
import datetime as dt
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

from rk import paths, store  # noqa: E402
import publish_store  # noqa: E402

CYC = dt.datetime(2025, 11, 12, 12)
TAG = "2025111212"


class Env:
    """Temporary RK_CACHE and RK_DATA, a fake release server, and a clean per-process memory."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.old = (paths.CACHE, paths.DATA, store._http_get, os.environ.get("RK_OFFLINE"))
        paths.CACHE, paths.DATA = t / "cache", t / "data"
        self.remote = {}   # url -> bytes
        self.calls = []

        def fake(url):
            self.calls.append(url)
            return self.remote.get(url)

        store._http_get = fake
        store._pulled.clear()
        os.environ.pop("RK_OFFLINE", None)
        self.t = t
        return self

    def __exit__(self, *a):
        paths.CACHE, paths.DATA, store._http_get, off = self.old
        if off is not None:
            os.environ["RK_OFFLINE"] = off
        store._pulled.clear()
        self.tmp.cleanup()


def det_arrays(k=1.0):
    u = (np.arange(12, dtype=np.float32).reshape(3, 4) * k).astype(np.float16)
    return {"u": u, "v": (u * 2).astype(np.float16), "msl": np.full((3, 4), 1000.0 * k, np.float32)}


def make_file(path, **arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    store._save(path, **arrays)
    return path


def zip_bytes(files):
    """files {member: Path} -> release zip bytes (via the real builder)."""
    out = Path(tempfile.mkdtemp()) / "x.zip"
    store.build_zip(out, files)
    return out.read_bytes()


def test_names():
    assert store.release_tag("natl", CYC) == "fields-natl-202511"
    assert store.release_tag("npac", TAG) == "fields-npac-202511"
    assert store.asset_name("natl", CYC) == "natl_2025111212.zip"
    assert store.release_url("natl", CYC).endswith(
        "/marine-research-data/releases/download/fields-natl-202511/natl_2025111212.zip")


def test_order_cache_then_legacy_then_release():
    with Env() as e:
        # release holds gfs_f024 with k=3; legacy holds it with k=2; cache with k=1
        rel = make_file(e.t / "rel" / "gfs_f024.npz", **det_arrays(3))
        e.remote[store.release_url("natl", CYC)] = zip_bytes({"gfs_f024.npz": rel})
        make_file(paths.DATA / "fields" / "natl" / TAG / "gfs_f024.npz", **det_arrays(2))
        make_file(paths.CACHE / "fields" / "natl" / TAG / "gfs_f024.npz", **det_arrays(1))
        assert store.load_det("natl", CYC, "gfs", 24)["msl"][0, 0] == 1000.0       # (a) cache
        os.unlink(paths.CACHE / "fields" / "natl" / TAG / "gfs_f024.npz")
        assert store.load_det("natl", CYC, "gfs", 24)["msl"][0, 0] == 2000.0       # (b) legacy
        assert e.calls == []
        os.unlink(paths.DATA / "fields" / "natl" / TAG / "gfs_f024.npz")
        d = store.load_det("natl", CYC, "gfs", 24)                                 # (c) release
        assert d["msl"][0, 0] == 3000.0 and len(e.calls) == 1
        assert (paths.CACHE / "fields" / "natl" / TAG / "gfs_f024.npz").exists()   # unpacked into the cache
        assert not store.dirty()                                                   # downloads are not dirty
        store.load_det("natl", CYC, "gfs", 24)
        assert len(e.calls) == 1                                                   # now from the cache
        for k in ("u", "v", "speed", "msl"):
            assert d[k].dtype == np.float32


def test_release_keeps_local_files():
    with Env() as e:
        rel = make_file(e.t / "rel" / "gfs_f024.npz", **det_arrays(3))
        e.remote[store.release_url("natl", CYC)] = zip_bytes({"gfs_f024.npz": rel})
        store.put("natl", CYC, "gfs_f024", **det_arrays(1))     # unpublished local version
        store._pulled.clear()
        store._pull("natl", CYC)
        assert store.load_det("natl", CYC, "gfs", 24)["msl"][0, 0] == 1000.0


def test_404_is_cached():
    with Env() as e:
        for _ in range(5):
            assert store.load_det("natl", CYC, "gfs", 24) is None
            assert store.load_ens("natl", CYC, "gefs", 48) is None
        assert len(e.calls) == 1, e.calls
        assert store.load_det("npac", CYC, "gfs", 24) is None
        assert len(e.calls) == 2
        # a cycle that is pulled but lacks the member does not download again either
        rel = make_file(e.t / "rel" / "gfs_f024.npz", **det_arrays())
        e.remote[store.release_url("npac", "2025111300")] = zip_bytes({"gfs_f024.npz": rel})
        c2 = dt.datetime(2025, 11, 13)
        assert store.load_det("npac", c2, "gfs", 48) is None and store.load_det("npac", c2, "gfs", 72) is None
        assert e.calls.count(store.release_url("npac", "2025111300")) == 1


def test_offline_skips_release():
    with Env() as e:
        os.environ["RK_OFFLINE"] = "1"
        try:
            assert store.load_det("natl", CYC, "gfs", 24) is None
        finally:
            os.environ.pop("RK_OFFLINE")
        assert e.calls == []


def test_put_and_dirty():
    with Env():
        assert store.dirty() == {}
        arr = {"lat": np.arange(3, dtype=np.float32), "n": np.array(7)}
        p = store.put("natl", CYC, "gfs_low_f024", **arr)
        assert p == paths.CACHE / "fields" / "natl" / TAG / "gfs_low_f024.npz" and p.exists()
        store.put("natl", TAG, "gfs_f030.npz", **det_arrays())     # tag string and .npz suffix both accepted
        store.put("npac", CYC, "aifs_f168", **det_arrays())
        assert store.dirty() == {("natl", TAG): ["gfs_f030.npz", "gfs_low_f024.npz"], ("npac", TAG): ["aifs_f168.npz"]}
        assert list(store.dirty("npac")) == [("npac", TAG)]
        out = store.load("natl", CYC, "gfs_low_f024")
        assert np.array_equal(out["lat"], arr["lat"]) and int(out["n"]) == 7
        assert store.load_det("natl", CYC, "gfs", 30)["u"].dtype == np.float32     # off-grid steps use the same names
        store.mark_clean("natl", CYC, ["gfs_low_f024.npz"])
        assert store.dirty("natl") == {("natl", TAG): ["gfs_f030.npz"]}
        store.mark_clean("natl", TAG, ["gfs_f030"])
        assert store.dirty("natl") == {}
        assert not list((paths.CACHE / "fields" / "natl" / TAG).glob("*.tmp"))
        for bad in ("../x", "a/b", "", ".hidden"):
            try:
                store.put("natl", CYC, bad, x=np.zeros(1))
            except ValueError:
                continue
            raise AssertionError("accepted %r" % bad)


def test_fill_writes_to_cache_and_skips_published():
    with Env() as e:
        calls = []
        old_det = store.fetch.det

        def fake_det(model, cycle, step):
            calls.append((model, step))
            return {b: {k: v.astype(np.float32) for k, v in det_arrays().items()} for b in store.BASINS}

        rel = make_file(e.t / "rel" / "gfs_f024.npz", **det_arrays())
        for b in store.BASINS:
            e.remote[store.release_url(b, CYC)] = zip_bytes({"gfs_f024.npz": rel})
        store.fetch.det = fake_det
        try:
            rep = store.fill(CYC, steps=(24, 48), models=("gfs",), ens=(), workers=2)
        finally:
            store.fetch.det = old_det
        assert rep["existing"] == ["gfs_f024"] and rep["fetched"] == ["gfs_f048"], rep
        assert calls == [("gfs", 48)]
        assert not (paths.DATA / "fields").exists()                      # nothing written to RK_DATA
        assert store.dirty() == {("natl", TAG): ["gfs_f048.npz"], ("npac", TAG): ["gfs_f048.npz"]}


def test_zip_round_trip_identical():
    with Env() as e:
        d = det_arrays(1.5)
        ens = {"mean_u": np.random.RandomState(0).randn(5, 6).astype(np.float32), "n": np.array(30)}
        files = {"gfs_f024.npz": make_file(e.t / "a" / "gfs_f024.npz", **d),
                 "gefs_f024.npz": make_file(e.t / "a" / "gefs_f024.npz", **ens)}
        blob = zip_bytes(files)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
            assert z.namelist() == ["gefs_f024.npz", "gfs_f024.npz"]
        assert blob == zip_bytes(files)                                  # deterministic
        e.remote[store.release_url("natl", CYC)] = blob
        out = store.load_det("natl", CYC, "gfs", 24)
        for k in ("u", "v", "msl"):
            assert np.array_equal(out[k], d[k].astype(np.float32))
        o = store.load("natl", CYC, "gfs_f024")
        assert all(o[k].dtype == d[k].dtype and np.array_equal(o[k], d[k]) for k in d)
        en = store.load_ens("natl", CYC, "gefs", 24)
        assert np.array_equal(en["mean_u"], ens["mean_u"]) and en["n"] == 30


def test_merge_keeps_remote_only_members():
    with Env() as e:
        a = make_file(e.t / "r" / "gfs_f024.npz", **det_arrays(1))
        b = make_file(e.t / "r" / "ifs_f024.npz", **det_arrays(2))
        remote = zip_bytes({"gfs_f024.npz": a, "ifs_f024.npz": b})
        new = make_file(e.t / "l" / "gfs_low_f024.npz", x=np.ones(2))
        repl = make_file(e.t / "l" / "ifs_f024.npz", **det_arrays(9))
        same = make_file(e.t / "l" / "gfs_f024.npz", **det_arrays(1))
        same.write_bytes(a.read_bytes())
        out = e.t / "out.zip"
        st = store.build_zip(out, {"gfs_low_f024.npz": new, "ifs_f024.npz": repl, "gfs_f024.npz": same}, remote)
        assert (st["new"], st["replaced"], st["same"], st["kept"]) == (1, 1, 1, 0)
        # remote-only member survives
        st = store.build_zip(out, {"gfs_low_f024.npz": new}, remote)
        assert (st["new"], st["kept"]) == (1, 2)
        with zipfile.ZipFile(out) as z:
            assert z.namelist() == ["gfs_f024.npz", "gfs_low_f024.npz", "ifs_f024.npz"]
            assert z.read("ifs_f024.npz") == b.read_bytes() and z.read("gfs_f024.npz") == a.read_bytes()
        st = store.build_zip(out, {"ifs_f024.npz": repl}, remote)
        with zipfile.ZipFile(out) as z:
            assert z.read("ifs_f024.npz") == repl.read_bytes() and z.read("gfs_f024.npz") == a.read_bytes()


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout


def test_publish_merges_pushes_and_clears():
    with Env() as e:
        bare, clone = e.t / "bare.git", e.t / "clone"
        run("git", "init", "-q", "--bare", "-b", "main", str(bare))
        run("git", "clone", "-q", str(bare), str(clone))
        (clone / "README.md").write_text("x")
        run("git", "add", "README.md", cwd=clone)
        run("git", "commit", "-q", "-m", "init", cwd=clone)
        run("git", "push", "-q", "origin", "HEAD:main", cwd=clone)
        # published asset has gfs_f024 and ifs_f024; this session adds gfs_low_f024 and a 06 UTC step
        a = make_file(e.t / "r" / "gfs_f024.npz", **det_arrays(1))
        b = make_file(e.t / "r" / "ifs_f024.npz", **det_arrays(2))
        e.remote[store.release_url("natl", CYC)] = zip_bytes({"gfs_f024.npz": a, "ifs_f024.npz": b})
        store.put("natl", CYC, "gfs_low_f024", x=np.ones(3))
        store.put("npac", CYC, "gfs_f030", **det_arrays())
        # dry run changes nothing
        assert publish_store.main(["--repo", str(clone), "--dry-run"]) == 0
        assert len(store.dirty()) == 2
        assert run("git", "ls-remote", "--heads", str(bare)).count("upload/") == 0
        assert publish_store.main(["--repo", str(clone)]) == 0
        assert store.dirty() == {}
        heads = run("git", "ls-remote", "--heads", str(bare))
        assert heads.count("refs/heads/upload/") == 1, heads
        br = [h.split("refs/heads/")[1] for h in heads.splitlines() if "upload/" in h][0]
        assert run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=clone).strip() == "main"   # restored
        run("git", "fetch", "-q", "origin", br, cwd=clone)
        names = run("git", "ls-tree", "-r", "--name-only", "FETCH_HEAD", cwd=clone).split()
        assert sorted(names) == ["README.md", "incoming/natl/2025111212.zip", "incoming/npac/2025111212.zip"]
        z = zipfile.ZipFile(io.BytesIO(subprocess.run(["git", "show", "FETCH_HEAD:incoming/natl/2025111212.zip"],
                                                      cwd=clone, capture_output=True, check=True).stdout))
        assert z.namelist() == ["gfs_f024.npz", "gfs_low_f024.npz", "ifs_f024.npz"]   # remote members kept
        # nothing dirty any more; republishing the identical content is skipped
        store.put("natl", CYC, "ifs_f024", **det_arrays(2))
        e.remote[store.release_url("natl", CYC)] = zip_bytes(
            {"ifs_f024.npz": paths.CACHE / "fields" / "natl" / TAG / "ifs_f024.npz"})
        assert publish_store.main(["--repo", str(clone)]) == 0
        assert store.dirty() == {}
        assert run("git", "ls-remote", "--heads", str(bare)).count("refs/heads/upload/") == 1


def test_publish_batches_by_size():
    with Env() as e:
        bare, clone = e.t / "bare.git", e.t / "clone"
        run("git", "init", "-q", "--bare", "-b", "main", str(bare))
        run("git", "clone", "-q", str(bare), str(clone))
        (clone / "README.md").write_text("x")
        run("git", "add", "README.md", cwd=clone)
        run("git", "commit", "-q", "-m", "init", cwd=clone)
        run("git", "push", "-q", "origin", "HEAD:main", cwd=clone)
        for c in ("2025111200", "2025111212", "2025111300"):
            store.put("natl", c, "gfs_f024", x=np.random.RandomState(1).randn(300, 300).astype(np.float32))
        publish_store.main(["--repo", str(clone), "--max-mb", "0.8"])      # each zip ~0.36 MB: two per branch
        heads = run("git", "ls-remote", "--heads", str(bare))
        assert heads.count("refs/heads/upload/") == 2, heads
        assert store.dirty() == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
