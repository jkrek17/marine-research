"""Offline tests of the MSLP blend study's candidates (synthetic Gaussian lows on the natl grid).
Run: python3 tests/test_mslp_blend_candidates.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-16-mslp-blend-d7"))

import numpy as np  # noqa: E402

import candidates as C  # noqa: E402
from rk import basins, score as rks  # noqa: E402

G = C.geo("natl")


def low(lat, lon, hpa, sigma=350.0, base=1016.0):
    d = G.dist(lat, lon)
    return (base + (hpa - base) * np.exp(-0.5 * (d / sigma) ** 2)).astype(np.float32)


def two(f1, f2, base=1016.0):
    return (f1 + f2 - base).astype(np.float32)


def z_of(**runs):
    return {("%s_f096" % k if k in C.DETS else "%s_mean_f096" % C.ZENS[k]): v for k, v in runs.items()}


def case_of(runs, lead=96):
    return C.prepare("natl", "2026010112", lead, z_of(**runs))


def argmin_ll(f):
    i = np.unravel_index(np.argmin(f), f.shape)
    return G.lats[i[0]], G.lons[i[1]], float(f[i])


def km(a, b):
    return float(rks.km(a[0], a[1], b[0], b[1]))


P = [(50.0, 320.0), (52.5, 323.0), (48.0, 317.5)]
D = [960.0, 965.0, 970.0]


def three_runs(extra=None):
    runs = {k: low(*P[i], D[i]) for i, k in enumerate(("gfs", "ifs", "aifs"))}
    runs.update(extra or {})
    return runs


def test_aligned_position_and_depth():
    runs = three_runs()
    mean_pos = (np.mean([p[0] for p in P]), np.mean([p[1] for p in P]))
    plain = C._mean(runs)
    out = C.build("natl", "x", 96, z_of(**runs))
    assert "al" in out and "gfs" in out and "m_gi" in out and "m_gia" not in out and "grand" not in out
    la, lo, mn = argmin_ll(out["al"])
    assert km((la, lo), mean_pos) < 60, (la, lo, mean_pos)
    assert abs(mn - np.median(D)) < 3.0, mn
    assert mn < plain.min() - 3.0       # the plain blend smears the low shallow; alignment keeps it deep
    assert out["al"].dtype == np.float32 and out["al"].shape == G.shape


def test_no_low_run_not_moved_and_far_field_untouched():
    flat = np.full(G.shape, 1016.0, np.float32)
    runs = three_runs({"aigfs": flat})
    case = case_of(runs)
    p = C._params(None)
    names = case.names(C.AL_FULL, False, 3)
    warped, used = C.aligned_runs(case, names, p)
    assert len(used) == 1 and abs(used[0]["sup"] - 0.75) < 1e-9
    assert np.array_equal(warped["aigfs"], flat)
    assert not np.array_equal(warped["gfs"], runs["gfs"])
    # cells farther than the largest Wendland radius from the target are bit-identical
    T = (used[0]["lat"], used[0]["lon"])
    far = G.dist(*T) > 1500.0 + 2.5 * 450
    assert far.sum() > 1000
    for m in ("gfs", "ifs", "aifs"):
        assert np.array_equal(warped[m][far], runs[m][far]), m


def test_box_edges_untouched():
    lat0 = 33.0                         # 330 km from the southern edge: footprint reaches the edge
    runs = {"gfs": low(lat0, 320.0, 962), "ifs": low(lat0 + 1.5, 322.0, 966), "aifs": low(lat0 + 1, 318.5, 970)}
    case = case_of(runs)
    names = case.names(C.AL_FULL, False, 3)
    warped, used = C.aligned_runs(case, names, C._params(None))
    assert used
    edge = G.edge_km < 1.0
    assert edge.sum() > 100
    for m in runs:
        assert np.array_equal(warped[m][edge], runs[m][edge])
        assert np.abs(warped[m] - runs[m]).max() > 1.0     # but it did move inside


def test_two_camps_not_merged():
    A, B = (55.0, 300.0), (50.0, 332.0)
    assert km(A, B) > 1500
    runs = {"gfs": low(*A, 965), "ifs": low(A[0] + 1, A[1] + 1.5, 968), "aifs": low(A[0] - 1, A[1] - 1, 970),
            "aigfs": low(*B, 965), "gefs": low(B[0] + 1, B[1] + 1, 968), "ens": low(B[0], B[1] - 2, 970)}
    case = case_of(runs)
    names = case.names(C.AL_FULL, False, 3)
    groups = case.groups(names, C._params(None))
    assert len(groups) == 2 and all(abs(g["sup"] - 0.5) < 1e-9 for g in groups)
    al = C.build("natl", "x", 96, z_of(**runs))["al"]
    lows = rks.find_lows(al, "natl", below=1005.0)
    assert len(lows) == 2
    for L in lows[["lat", "lon"]].to_numpy():
        assert min(km(L, A), km(L, B)) < 250
    # nothing sits between the camps
    mid = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
    assert al[np.argmin(np.abs(G.lats - mid[0])), np.argmin(np.abs(G.lons - mid[1]))] > 1010


def test_depth_fix_only_deepens_and_gate():
    runs = three_runs({"aigfs": low(51.0, 321.0, 975)})
    out = C.build("natl", "x", 96, z_of(**runs))
    assert np.all(out["ald"] <= out["al"] + 1e-4)
    assert (out["al"] - out["ald"]).max() <= 8.0 + 1e-3
    assert np.all(out["bowl"] <= C._mean(runs) + 1e-4)
    shallow = {k: low(*P[i], 996.0 + i) for i, k in enumerate(("gfs", "ifs", "aifs"))}
    o2 = C.build("natl", "x", 96, z_of(**shallow))
    assert np.array_equal(o2["ald"], o2["al"])          # median depth above the 990 gate: no bowl
    o3 = C.build("natl", "x", 96, z_of(**runs), params={"off": -4.0})
    assert abs((C._mean(runs) - o3["off"]).max() - 4.0) < 0.5


def test_grid_values_and_build_grid():
    gv = C.grid_values()
    assert set(gv["cap"]) == {300.0, 450.0, 600.0} and set(gv["X"]) == {200.0, 300.0, 400.0, 600.0}
    res = C.build_grid("natl", "x", 96, z_of(**three_runs()))
    caps = {s for n, s, f in res if n == "al"}
    assert caps == {"cap=300", "cap=450", "cap=600"}


def test_missing_inputs_skipped_never_imputed():
    out = C.build("natl", "x", 96, z_of(gfs=low(50, 320, 970)))
    assert set(out) == {"gfs"}
    info = {}
    out = C.build("natl", "x", 96, z_of(**three_runs()), info=info)
    assert info["al"] == ["gfs", "ifs", "aifs"] and "aigfs" not in info["wb"]


def test_outlier_drop_and_gfe2():
    cons = (52.0, 320.0)
    runs = {"gfs": low(*cons, 965), "ifs": low(52.0, 328.0, 963),          # ifs ~ 550 km east of consensus
            "aifs": low(51.5, 320.5, 968), "gefs": low(*cons, 975), "ens": low(52.5, 319.0, 976),
            "aifsens": low(51.5, 321.0, 977)}
    z = z_of(**runs)
    rows = C.od_dropped("natl", "x", 96, z, params={"X": 300.0})
    by = {r["model"]: r for r in rows}
    assert by["ifs"]["dropped"] and by["ifs"]["dist_km"] > 400
    assert not by["gfs"]["dropped"] and not by["aifs"]["dropped"]
    out = C.build("natl", "x", 96, z, params={"X": 300.0})
    la, lo, _ = argmin_ll(out["od"])
    assert km((la, lo), cons) < 80
    assert km(argmin_ll(out["bowl"])[:2], cons) < 400
    out2 = C.build("natl", "x", 96, z, params={"X": 600.0})
    assert not {r["model"]: r for r in C.od_dropped("natl", "x", 96, z, params={"X": 600.0})}["ifs"]["dropped"]
    for n in ("al_gfe2", "ald_gfe2", "bowl_gfe2", "od_gfe2", "wb_gfe2"):
        assert n in out, n
    for n in ("al_gfe", "ald_gfe", "bowl_gfe", "od_gfe", "wb_gfe"):
        assert n not in out, n                 # no AI-GFS: the _gfe set is skipped, not imputed
    assert all(not np.isnan(v).any() for v in out.values())


if __name__ == "__main__":
    fails = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_") and callable(v):
            try:
                v()
                print("ok  ", k)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                print("FAIL", k, repr(ex))
                fails += 1
    sys.exit(1 if fails else 0)
