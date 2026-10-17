"""Offline tests of the gale-core study: the --thr / --cand options of the retrain code, rk.calib, rk.features
candidate rules and the gale scorer. Run: python3 tests/test_gale_core_study.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-16-core-lift-retrain"))
sys.path.insert(0, str(ROOT / "studies" / "2026-10-17-gale-core"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import score_gale as G  # noqa: E402
import train as T  # noqa: E402
from rk import calib, features  # noqa: E402

CURVES = ROOT / "studies" / "2026-10-17-gale-core" / "p34_curves.json"


def test_target_names():
    assert C.target_name("live28+basin") == "live28+basin" and C.target_name("live28+basin", 48) == "live28+basin"
    assert C.target_name("live28+basin", 34) == "live28+basin@34"
    assert C.split_target("live28+basin@34") == ("live28+basin", 34) and C.split_target("store") == ("store", 48)
    assert C.r10_keep(48) == 40.0 and C.r10_keep(34) == 30.0
    d = pd.DataFrame({"thr": [34, 34], "cand_rule": ["gale", "gale"]})
    assert C.table_target(d) == (34, "gale")
    try:
        C.table_target(pd.DataFrame({"thr": [34, 48], "cand_rule": ["gale", "storm"]}))
        raise AssertionError("mixed table accepted")
    except SystemExit:
        pass


def test_old_table_defaults():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "natl").mkdir()
        pd.DataFrame({"y": [0, 1], "no_low": [0, 0]}).to_parquet(Path(td) / "natl" / "a.parquet")
        d = C.load_table(td)
        assert C.table_target(d) == (48, "storm")


def test_cand_rules():
    shape = (1, 5)
    r10 = np.array([[20, 24, 27, 28, 20]], np.float32)
    mm = np.array([[20, 20, 20, 20, 30]], np.float32)
    ocean = np.ones(shape, bool)
    c_storm = ocean & ((r10 >= features.CAND_R10) | (mm >= features.CAND_MOD))
    c_gale = ocean & ((r10 >= features.CAND_GALE_R10) | (mm >= features.CAND_GALE_MOD))
    f = {"cand": c_storm, "cand_gale": c_gale}
    assert features.cand_mask(f, "storm") is c_storm and features.cand_mask(f, "gale") is c_gale
    assert c_storm.tolist() == [[False, False, False, True, False]]
    assert c_gale.tolist() == [[False, True, True, True, True]]
    try:
        features.cand_mask(f, "x")
        raise AssertionError
    except ValueError:
        pass


def test_calib():
    cur = calib.load_curves(CURVES)
    assert [calib.lead_group(s) for s in (24, 48, 72, 96, 120)] == ["le48", "le48", "72", "ge96", "ge96"]
    k = cur["winter"]["ascat"]["natl"]["le48"]
    p = calib.p34_remap(np.array([0.0, 0.145, 1.0, 0.5]), "natl", 24, cur)
    assert abs(p[0]) < 1e-6 and abs(p[2] - 1) < 1e-6
    i = k["raw"].index(14.5)
    assert abs(p[1] - k["cal"][i] / 100) < 1e-6
    q = calib.p34_remap(np.linspace(0, 1, 101), "npac", 120, cur)
    assert np.all(np.diff(q) >= -1e-6)                       # monotone remap


def test_metrics_ref_name():
    rng = np.random.default_rng(1)
    n = 2000
    cyc = np.array(["2025120100", "2025121500", "2026010800", "2026011500", "2026012200", "2026020500"])[
        rng.integers(0, 6, n)]
    sub = pd.DataFrame({"cycle": cyc})
    p = rng.random(n)
    sub["y"] = (rng.random(n) < p).astype(int)
    sub["w"] = 1.0
    rows = T.metrics(sub, {"p34_cal": np.clip(p + rng.normal(0, 0.3, n), 0, 1), "good": p}, 100, ref="p34_cal")
    good = [r for r in rows if r["model"] == "good"][0]
    assert "dbss_vs_p34_cal" in good and good["dbss_vs_p34_cal"] > 0 and "dbss_vs_live" not in good


def _grids():
    r10 = np.array([[40., 30.], [20., 33.]], np.float32)
    Pl = np.array([[0.5, 0.0], [0.0, 0.0]], np.float16)       # baseline: 45, 30, 20, 33
    Pg = np.array([[0.2, 0.45], [0.8, 0.35]], np.float16)
    cal = np.array([[0.9, 0.2], [0.35, 0.5]], np.float32)
    ocean = np.array([[True, True], [False, True]])
    return r10, Pl, Pg, cal, ocean


def test_gale_products():
    r10, Pl, Pg, cal, ocean = _grids()
    pr = G.products(r10, Pl, Pg, cal, cal, ocean)
    assert set(pr) == set(G.product_names())
    assert np.allclose(pr["baseline"], [[45, 30], [20, 33]])
    assert np.allclose(pr["galecore@0.3"], [[45, 34], [34, 34]])
    assert np.allclose(pr["galecore@0.5"], [[45, 30], [34, 33]])
    assert np.allclose(pr["galecore@0.7"], [[45, 30], [34, 33]])
    assert np.allclose(pr["ref@0.3"], [[45, 30], [20, 34]])      # land cell (ocean False) never lifted
    assert np.allclose(pr["ref@0.5"], [[45, 30], [20, 34]]) and np.allclose(pr["ref@0.6"], [[45, 30], [20, 33]])
    assert np.all(pr["galecore@0.3"] >= pr["baseline"])          # max(), never lowers


def test_case_counts():
    f = np.array([[40., 30.], [20., 34.]])
    spd = np.array([[36., 35.], [np.nan, 20.]])
    seen = np.array([[True, True], [False, True]])
    lats, lons = np.array([50.0, 49.75]), np.array([300.0, 300.25])
    c = G.case_counts(f, spd, seen, lats, lons)
    assert c["ob34"] == 2 and c["caught"] == 1 and c["fc34"] == 2          # fc 34+ at seen: (0,0) and (1,1)
    assert c["nt34"] == 0                                                   # 3 seen cells: no tile has 150


def _fake_cases():
    rows = []
    for b in ("natl", "npac"):
        for w, cyc in enumerate(["2025120100", "2025120800", "2025121500", "2025122200", "2026010500", "2026011200"]):
            for step in (24, 48):
                for prod, (ob, caught, fc, h, m, fa) in {
                        "baseline": (100, 40, 50, 5, 5, 1),
                        "galecore@0.3": (100, 70, 120, 7, 3, 3), "galecore@0.4": (100, 60, 90, 7, 3, 1),
                        "galecore@0.5": (100, 50, 70, 6, 4, 1), "galecore@0.6": (100, 45, 60, 5, 5, 1),
                        "galecore@0.7": (100, 42, 52, 5, 5, 1)}.items():
                    rows.append(dict(basin=b, cycle=cyc, step=step, split="tune", product=prod, ob34=ob,
                                     caught=caught + (w % 2), fc34=fc, nt34=h + m + fa, h34=h, m34=m, fa34=fa))
                for t in G.TS:
                    g = [r for r in rows if r["basin"] == b and r["cycle"] == cyc and r["step"] == step
                         and r["product"] == G.gname(t)][0]
                    rows.append(dict(g, product=G.rname(t), caught=g["caught"] - 5))
                    rows.append(dict(g, product=G.rnbname(t), caught=g["caught"] - 8))
    return pd.DataFrame(rows)


def test_selection():
    cs = _fake_cases()
    with tempfile.TemporaryDirectory() as td:
        summ = G.summarize(cs, td, 200)
        tab, chosen = G.select(summ, cs, G.TS, 200)
    # 0.3 has area 1.2 (fc 120/100) <= 1.3 but gale CSI 7/13 vs 5/11: fine -> qualifies with the biggest gain
    assert chosen == 0.3, (chosen, tab[["t", "basin", "area", "d_catch", "d_gale_csi"]])
    assert tab.groupby("t").qualifies.first().all()
    assert tab[tab.t == 0.3].vs_ref_catch.min() > 0
    assert any("t = 0.3 would be chosen" in x for x in G.verdict_lines(tab, chosen, "TUNE"))
    # tighten the area cap: nothing at 0.3 (area 1.2 -> 1.5)
    cs2 = cs.copy()
    cs2.loc[cs2["product"] == "galecore@0.3", "fc34"] = 150
    with tempfile.TemporaryDirectory() as td:
        summ2 = G.summarize(cs2, td, 200)
        tab2, chosen2 = G.select(summ2, cs2, G.TS, 200)
    assert chosen2 == 0.4
    # lower gale CSI in one basin disqualifies
    cs3 = cs.copy()
    m = (cs3["product"] == "galecore@0.3") & (cs3.basin == "npac")
    cs3.loc[m, ["h34", "m34", "fa34"]] = [3, 7, 4]
    with tempfile.TemporaryDirectory() as td:
        summ3 = G.summarize(cs3, td, 200)
        _, chosen3 = G.select(summ3, cs3, G.TS, 200)
    assert chosen3 == 0.4


def test_final_gate():
    import subprocess
    script = str(ROOT / "studies" / "2026-10-17-gale-core" / "score_gale.py")
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, script, "--final", "--choice-dir", td, "--results", td],
                           capture_output=True, text=True)
        assert r.returncode != 0 and "FINAL_CHOICE.json does not exist" in (r.stdout + r.stderr)
        (Path(td) / "FINAL_CHOICE.json").write_text(json.dumps({"t": 0.5, "set": "live28+basin"}))
        (Path(td) / "FINAL_RUN.json").write_text("{}")
        r = subprocess.run([sys.executable, script, "--final", "--choice-dir", td, "--results", td],
                           capture_output=True, text=True)
        assert r.returncode != 0 and "already" in (r.stdout + r.stderr)
    assert not (ROOT / "studies" / "2026-10-17-gale-core" / "FINAL_CHOICE.json").exists()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
