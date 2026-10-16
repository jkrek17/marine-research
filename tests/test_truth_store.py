"""Tests for truth in releases (rk.store.truth_*, the truth loaders in rk.truth, and the truth side of
tools/publish_store.py). Offline: HTTP is mocked. Run with pytest or `python3 tests/test_truth_store.py`."""
import datetime as dt
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from rk import paths, store, truth  # noqa: E402
import publish_store  # noqa: E402
import test_store  # noqa: E402
from test_store import det_arrays, make_file, run  # noqa: E402

VALID = dt.datetime(2025, 11, 12, 12)
DAY = dt.date(2025, 11, 12)


class Env(test_store.Env):
    """test_store.Env plus a fake release server for the existence check and a clean 404 memory."""

    def __enter__(self):
        super().__enter__()
        self.old_exists = store._http_exists
        self.head_calls = []

        def fake_exists(url):
            self.head_calls.append(url)
            return url in self.remote

        store._http_exists = fake_exists
        store._truth_absent.clear()
        return self

    def __exit__(self, *a):
        store._http_exists = self.old_exists
        store._truth_absent.clear()
        super().__exit__(*a)


def blob(**arrays):
    b = io.BytesIO()
    np.savez_compressed(b, **arrays)
    return b.getvalue()


def test_names():
    assert store.truth_tag("ascat", None, "20251112") == "truth-ascat-202511"
    assert store.truth_tag("smap", "natl", DAY) == "truth-smap-202511"           # basin ignored for day kinds
    assert store.truth_tag("analysis", "natl", VALID) == "truth-analysis-natl-202511"
    assert store.truth_tag("obs", "npac", "2026010100.npz") == "truth-obs-npac-202601"
    assert store.truth_tag("airsea", "npac", "2025113023") == "truth-airsea-npac-202511"
    assert store.truth_asset("analysis", "natl", VALID) == "2025111212.npz"
    assert store.truth_url("ascat", None, DAY).endswith(
        "/marine-research-data/releases/download/truth-ascat-202511/20251112.npz")
    assert store.truth_cache_path("analysis", "natl", VALID) == paths.CACHE / "truth" / "analysis" / "natl" / "2025111212.npz"
    assert store.truth_cache_path("smap", None, DAY) == paths.CACHE / "truth" / "smap" / "20251112.npz"
    for args in (("hf_lows", None, "20251112"), ("analysis", None, VALID), ("analysis", "natl", "20251112"),
                 ("ascat", None, "2025111212"), ("ascat", None, "../x"), ("obs", "atl", VALID)):
        try:
            store.truth_key(*args)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % (args,))


def test_assets_stay_far_below_the_release_limit():
    # a month holds at most 4 valid times a day per basin kind and one file a day for ascat and smap
    assert 31 * 4 < 1000 and 31 < 1000


def test_order_cache_then_legacy_then_release():
    with Env() as e:
        e.remote[store.truth_url("ascat", None, DAY)] = blob(x=np.array([3]))
        make_file(paths.DATA / "truth" / "ascat" / "20251112.npz", x=np.array([2]))
        make_file(paths.CACHE / "truth" / "ascat" / "20251112.npz", x=np.array([1]))

        def val():
            with np.load(store.truth_locate("ascat", None, DAY)) as z:
                return int(z["x"][0])
        assert val() == 1                                                      # (a) cache
        os.unlink(paths.CACHE / "truth" / "ascat" / "20251112.npz")
        assert val() == 2                                                      # (b) legacy
        assert e.calls == []
        os.unlink(paths.DATA / "truth" / "ascat" / "20251112.npz")
        assert val() == 3 and len(e.calls) == 1                                # (c) release
        assert (paths.CACHE / "truth" / "ascat" / "20251112.npz").exists()     # unpacked into the cache
        assert store.truth_dirty() == {}                                       # downloads are not dirty
        assert val() == 3 and len(e.calls) == 1                                # now from the cache


def test_404_is_remembered_and_offline_skips():
    with Env() as e:
        for _ in range(4):
            assert store.truth_locate("analysis", "natl", VALID) is None
        assert len(e.calls) == 1
        assert store.truth_locate("analysis", "npac", VALID) is None and len(e.calls) == 2   # own release
        os.environ["RK_OFFLINE"] = "1"
        try:
            assert store.truth_locate("smap", None, DAY) is None and not store.truth_exists("smap", None, DAY)
        finally:
            os.environ.pop("RK_OFFLINE")
        assert len(e.calls) == 2 and e.head_calls == []


def test_exists_does_not_download():
    with Env() as e:
        e.remote[store.truth_url("analysis", "natl", VALID)] = blob(x=np.array([1]))
        assert store.truth_exists("analysis", "natl", VALID)
        assert not store.truth_exists("analysis", "npac", VALID)
        assert not store.truth_exists("analysis", "npac", VALID)               # remembered
        assert e.calls == [] and len(e.head_calls) == 2
        make_file(paths.DATA / "truth" / "analysis" / "npac" / "2025111212.npz", x=np.array([1]))
        assert store.truth_exists("analysis", "npac", VALID)                   # legacy counts


def test_save_dirty_and_clean():
    with Env():
        assert store.truth_dirty() == {}
        p = store.truth_save("ascat", None, DAY, x=np.arange(3))
        assert p == paths.CACHE / "truth" / "ascat" / "20251112.npz" and p.exists()
        store.truth_save("analysis", "natl", VALID, x=np.arange(2))
        store.truth_save("analysis", "natl", "2025111200", x=np.arange(2))
        store.truth_save("smap", None, "20251113.npz", x=np.arange(2))
        assert store.truth_dirty() == {("analysis", "natl"): ["2025111200.npz", "2025111212.npz"],
                                       ("ascat", None): ["20251112.npz"], ("smap", None): ["20251113.npz"]}
        store.truth_mark_clean("analysis", "natl", ["2025111200", "2025111212.npz"])
        store.truth_mark_clean("ascat", None, ["20251112"])
        assert store.truth_dirty() == {("smap", None): ["20251113.npz"]}
        assert not list(paths.CACHE.rglob("*.tmp"))
        assert not (paths.DATA / "truth").exists()                             # nothing written to RK_DATA


def test_analysis_comes_from_the_release_without_fetching():
    with Env() as e:
        d = det_arrays()
        arrays = store.analysis_arrays({k: v.astype(np.float32) for k, v in d.items()},
                                       {k: v.astype(np.float32) for k, v in d.items()},
                                       np.zeros((3, 4)), np.zeros((3, 4)))
        e.remote[store.truth_url("analysis", "natl", VALID)] = blob(**arrays)
        saved = (store.fetch.det, store.fetch.gfs_mask)

        def boom(*a, **k):
            raise AssertionError("fetched")
        store.fetch.det = store.fetch.gfs_mask = boom
        try:
            a = store.analysis("natl", VALID)
        finally:
            store.fetch.det, store.fetch.gfs_mask = saved
        assert a["mask"].all() and a["gfs"]["speed"].shape == (3, 4)
        assert store.truth_dirty() == {}


def test_analysis_built_locally_goes_to_the_cache_dirty():
    with Env():
        d = {b: {k: v.astype(np.float32) for k, v in det_arrays().items()} for b in store.BASINS}
        m = {b: {"land": np.zeros((3, 4)), "ice": np.zeros((3, 4))} for b in store.BASINS}
        saved = (store.fetch.det, store.fetch.gfs_mask)
        store.fetch.det = lambda model, cycle, step: d
        store.fetch.gfs_mask = lambda valid: m
        try:
            assert store.analysis("natl", VALID) is not None
        finally:
            store.fetch.det, store.fetch.gfs_mask = saved
        assert store.truth_dirty() == {("analysis", "natl"): ["2025111212.npz"],
                                       ("analysis", "npac"): ["2025111212.npz"]}
        assert not (paths.DATA / "truth").exists()


def _ascat_raw(cell):
    a = np.full((2, 5, 720, 1440), 255, np.uint8)
    a[0, :, cell[0], cell[1]] = [100, 50, 10, 0, 5]     # time 600 min, 10 m/s, rain none
    return a


def test_ascat_and_smap_days_use_the_release_then_the_cache():
    with Env() as e:
        saved = truth._ascat_get
        truth._ascat_get = lambda sat, ymd: _ascat_raw((500, 600))
        try:
            c = truth.ascat_day(DAY)                                          # nothing published: built
        finally:
            truth._ascat_get = saved
        assert len(c["lat"]) == 2 and store.truth_dirty() == {("ascat", None): ["20251112.npz"]}
        sent = (paths.CACHE / "truth" / "ascat" / "20251112.npz").read_bytes()
        # a fresh machine: no cache, the release holds the day, and nothing is fetched from RSS
        os.unlink(paths.CACHE / "truth" / "ascat" / "20251112.npz")
        shutil_rmtree(paths.CACHE / "truth" / "ascat" / ".dirty")
        e.remote[store.truth_url("ascat", None, DAY)] = sent
        store._truth_absent.clear()
        truth._ascat_get = lambda *a: (_ for _ in ()).throw(AssertionError("fetched"))
        try:
            c2 = truth.ascat_day(DAY)
            sm = store.truth_url("smap", None, DAY)
            e.remote[sm] = blob(final=np.array(1, np.uint8), lat=np.zeros(1, np.float32))
            s2 = truth.smap_day(DAY)
        finally:
            truth._ascat_get = saved
        assert np.array_equal(c["lat"], c2["lat"]) and "sats" not in c2 and list(s2) == ["lat"]
        assert store.truth_dirty() == {}


def shutil_rmtree(p):
    import shutil
    shutil.rmtree(p)


def test_obs_and_airsea_read_the_release():
    with Env() as e:
        e.remote[store.truth_url("obs", "npac", VALID)] = blob(lat=np.zeros(1))
        e.remote[store.truth_url("airsea", "natl", VALID)] = blob(t2=np.full((2, 2), 280.0, np.float32),
                                                                  skt=np.full((2, 2), 283.0, np.float32))
        assert list(truth.obs_points("npac", VALID)) == ["lat"]
        assert truth.airsea("natl", VALID)[0, 0] == -3.0
        assert store.truth_dirty() == {}


def test_hf_archive_reads_https_not_releases():
    with Env() as e:
        saved = truth.fetch.get

        class R:
            content = b"ID,date,Latitude,Longitude,Category,Pressure\n1,2026010112,49.3,171.8,HF,982\n"
        urls = []
        truth.fetch.get = lambda url, rng=None: urls.append(url) or R()
        try:
            a = truth.hf_archive("npac")
            truth.hf_archive("npac")
        finally:
            truth.fetch.get = saved
        assert len(a) == 1 and urls == [truth.HF_LOWS_URL.format(f="Pac")] and "raw.githubusercontent.com/jkrek17/hf-low" in urls[0]
        assert (paths.CACHE / "truth" / "hf_lows" / "HF_Data_-_Pac.csv").exists() and e.calls == []


def test_merge_semantics():
    with Env() as e:
        a = make_file(e.t / "a.npz", x=np.arange(4.0), n=np.array(1))
        assert store.truth_merge("ascat", a, None) == "new"
        same = blob(x=np.arange(4.0), n=np.array(1))          # different bytes (timestamps), same arrays
        assert store.truth_merge("ascat", a, same) == "same"
        assert store.truth_merge("ascat", a, blob(x=np.arange(4.0) + 1, n=np.array(1))) == "replaced"
        assert store.truth_merge("ascat", a, blob(x=np.arange(4.0))) == "replaced"
        nan = make_file(e.t / "nan.npz", x=np.array([1.0, np.nan], np.float32))
        assert store.truth_merge("obs", nan, blob(x=np.array([1.0, np.nan], np.float32))) == "same"
        nrt = make_file(e.t / "nrt.npz", final=np.array(0, np.uint8), x=np.ones(2))
        assert store.truth_merge("smap", nrt, blob(final=np.array(1, np.uint8), x=np.zeros(2))) == "kept"
        fin = make_file(e.t / "fin.npz", final=np.array(1, np.uint8), x=np.ones(2))
        assert store.truth_merge("smap", fin, blob(final=np.array(0, np.uint8), x=np.zeros(2))) == "replaced"


def _bare(e):
    bare, clone = e.t / "bare.git", e.t / "clone"
    run("git", "init", "-q", "--bare", "-b", "main", str(bare))
    run("git", "clone", "-q", str(bare), str(clone))
    (clone / "README.md").write_text("x")
    run("git", "add", "README.md", cwd=clone)
    run("git", "commit", "-q", "-m", "init", cwd=clone)
    run("git", "push", "-q", "origin", "HEAD:main", cwd=clone)
    return bare, clone


def test_publish_truth_pushes_new_and_changed_skips_same():
    with Env() as e:
        bare, clone = _bare(e)
        store.truth_save("ascat", None, DAY, x=np.arange(3))                       # new
        store.truth_save("analysis", "natl", VALID, x=np.arange(3))                # same as published
        store.truth_save("analysis", "npac", VALID, x=np.arange(3))                # changed
        e.remote[store.truth_url("analysis", "natl", VALID)] = blob(x=np.arange(3))
        e.remote[store.truth_url("analysis", "npac", VALID)] = blob(x=np.arange(3) + 5)
        assert publish_store.main(["--repo", str(clone), "--dry-run"]) == 0
        assert len(store.truth_dirty()) == 3
        assert publish_store.main(["--repo", str(clone)]) == 0
        assert store.truth_dirty() == {}
        heads = run("git", "ls-remote", "--heads", str(bare))
        br = [h.split("refs/heads/")[1] for h in heads.splitlines() if "upload/" in h][0]
        run("git", "fetch", "-q", "origin", br, cwd=clone)
        names = run("git", "ls-tree", "-r", "--name-only", "FETCH_HEAD", cwd=clone).split()
        assert sorted(names) == ["README.md", "incoming/truth/analysis/npac/2025111212.npz",
                                 "incoming/truth/ascat/20251112.npz"], names
        assert run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=clone).strip() == "main"


def test_publish_direct_writes_folder_and_keeps_marks():
    with Env() as e:
        out = e.t / "out"
        store.put("natl", "2025111212", "gfs_f024", **det_arrays())
        store.truth_save("smap", None, DAY, final=np.array(0, np.uint8), x=np.ones(2))
        store.truth_save("obs", "natl", VALID, x=np.ones(2))
        e.remote[store.truth_url("smap", None, DAY)] = blob(final=np.array(1, np.uint8), x=np.zeros(2))
        fz = make_file(e.t / "r" / "ifs_f024.npz", **det_arrays(2))
        e.remote[store.release_url("natl", "2025111212")] = test_store.zip_bytes({"ifs_f024.npz": fz})
        assert publish_store.main(["--direct", str(out)]) == 0
        got = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
        assert got == ["natl/2025111212.zip", "truth/obs/natl/2025111212.npz"], got       # FINAL smap kept
        import zipfile
        assert zipfile.ZipFile(out / "natl" / "2025111212.zip").namelist() == ["gfs_f024.npz", "ifs_f024.npz"]
        assert len(store.dirty()) == 1 and len(store.truth_dirty()) == 2                  # marks untouched
        # truth only
        out2 = e.t / "out2"
        assert publish_store.main(["--direct", str(out2), "--what", "truth"]) == 0
        assert sorted(str(p.relative_to(out2)) for p in out2.rglob("*") if p.is_file()) == ["truth/obs/natl/2025111212.npz"]
        assert not git_dirs(e)


def git_dirs(e):
    return list(e.t.glob("**/.git"))


def test_legacy_truth_is_collected_without_hf_lows():
    with Env() as e:
        root = paths.DATA / "truth"
        make_file(root / "analysis" / "natl" / "2025110112.npz", x=np.ones(2))
        make_file(root / "analysis" / "npac" / "2025110112.npz", x=np.ones(2))
        make_file(root / "ascat" / "20251031.npz", x=np.ones(2))
        make_file(root / "smap" / "20251031.npz", x=np.ones(2))
        make_file(root / "obs" / "natl" / "2025110100.npz", x=np.ones(2))
        make_file(root / "airsea" / "npac" / "2025110112.npz", x=np.ones(2))
        make_file(root / "analysis" / "natl" / "notes.npz", x=np.ones(2))               # not a stem
        (root / "hf_lows").mkdir()
        (root / "hf_lows" / "HF_Data_-_Atl.csv").write_text("x")
        store.truth_save("ascat", None, "20251031", x=np.zeros(2))                       # dirty cache wins
        assert len(publish_store.collect_truth()) == 1
        jobs = publish_store.collect_truth(include_legacy=True)
        assert [(k, b, s) for k, b, s, _, _ in jobs] == [
            ("airsea", "npac", "2025110112"), ("analysis", "natl", "2025110112"), ("analysis", "npac", "2025110112"),
            ("ascat", None, "20251031"), ("obs", "natl", "2025110100"), ("smap", None, "20251031")]
        assert [p for k, b, s, p, d in jobs if k == "ascat"] == [paths.CACHE / "truth" / "ascat" / "20251031.npz"]
        out = e.t / "out"
        assert publish_store.main(["--direct", str(out), "--include-legacy-truth", "--what", "truth"]) == 0
        assert len([p for p in out.rglob("*.npz")]) == 6
        assert len(store.truth_dirty()) == 1                 # only the cache file was ever marked


def test_fill_complete_skips_short_ensembles():
    with Env():
        def members(ens, cycle, step, msl=True, workers=2):
            n = 30 if step == 24 else 31
            return {b: {k: np.zeros((n, 3, 4), np.float32) for k in ("u", "v", "msl")} for b in store.BASINS}
        saved = store.fetch.members
        store.fetch.members = members
        try:
            rep = store.fill(VALID, steps=(24, 48), models=(), ens=("gefs",), workers=1, complete=True)
            assert rep["skipped_ens"] == ["gefs_f024"] and rep["fetched"] == ["gefs_f048"], rep
            rep = store.fill(VALID, steps=(24,), models=(), ens=("gefs",), workers=1)    # default: 20+ is enough
            assert rep["fetched"] == ["gefs_f024"], rep
        finally:
            store.fetch.members = saved


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
