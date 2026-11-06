"""Offline tests of the front drill's pure pieces (studies/2026-11-06-front-drill/frontlib.py).
Run: python3 tests/test_front_drill_study.py"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studies" / "2026-11-06-front-drill"))

import numpy as np  # noqa: E402

import frontlib as FL  # noqa: E402

LAT_N, LON_W = 62.0, 290.0     # box: 62N..37N, 290E..330E


def line(typ, lat, lon):
    return {"type": typ, "lat": np.array(lat, float), "lon": np.array(lon, float)}


def test_attach_and_type_set():
    cold = line("cold", [50.0, 47.0], [310.0, 306.0])           # one end ~ at the low
    far = line("warm", [60.0, 58.0], [330.0, 328.0])            # more than 300 km away
    trough = line("trough", [50.0, 49.0], [310.0, 309.0])
    fr = [cold, far, trough]
    assert FL.type_set(fr, 50.5, 310.0) == ("cold",)
    assert FL.type_set(fr, 59.0, 329.0) == ("warm",)
    assert FL.type_set([trough], 50.0, 310.0) == ()
    # an end 250 km away attaches, 350 km does not
    assert FL.type_set([line("cold", [50.0, 40.0], [310.0, 310.0])], 50.0 + 250 / 111.19, 310.0) == ("cold",)
    assert FL.type_set([line("cold", [50.0, 40.0], [310.0, 310.0])], 50.0 + 350 / 111.19, 310.0) == ()


def test_types_match_across_times():
    lows = [(990.0, 50.0, 310.0)]
    cold_occ = [line("cold", [50, 45], [310, 306]), line("occluded", [50, 54], [310, 312])]
    nb = (lows, cold_occ)
    assert FL.types_match(nb, nb, ("cold", "occluded"), 50.0, 310.0)
    # the type changes 6 h later
    nb2 = (lows, [line("cold", [50, 45], [310, 306])])
    assert not FL.types_match(nb, nb2, ("cold", "occluded"), 50.0, 310.0)
    # an analysis is missing, or the low is gone
    assert not FL.types_match(None, nb, ("cold", "occluded"), 50.0, 310.0)
    assert not FL.types_match(nb, ([(990.0, 62.0, 330.0)], cold_occ), ("cold", "occluded"), 50.0, 310.0)
    # the low moved 250 km: still linked and attached, trough fronts do not count
    mv = ([(985.0, 50.0 + 250 / 111.19, 310.0)], cold_occ + [line("trough", [50, 52], [310, 311])])
    assert FL.types_match(mv, mv, ("cold", "occluded"), 50.0, 310.0)


def test_types_match_relaxed():
    lows = [(990.0, 50.0, 310.0)]
    cold_occ = (lows, [line("cold", [50, 45], [310, 306]), line("occluded", [50, 54], [310, 312])])
    cold_only = (lows, [line("cold", [50, 45], [310, 306])])
    occ_only = (lows, [line("occluded", [50, 54], [310, 312])])
    # the cold and the occluded front were each present 6 h before or 6 h after (not strict: the sets differ)
    assert FL.types_match_relaxed(cold_only, occ_only, ("cold", "occluded"), 50.0, 310.0)
    assert not FL.types_match(cold_only, occ_only, ("cold", "occluded"), 50.0, 310.0)
    # a type that was in neither neighbour fails; a stationary front now is not needed in the neighbours
    assert not FL.types_match_relaxed(cold_only, cold_only, ("cold", "occluded"), 50.0, 310.0)
    assert FL.types_match_relaxed(cold_occ, cold_occ, ("cold", "stationary"), 50.0, 310.0)
    # one missing analysis is skipped, both missing (or no low in either) is False
    assert FL.types_match_relaxed(None, cold_occ, ("cold", "occluded"), 50.0, 310.0)
    assert not FL.types_match_relaxed(None, None, ("cold",), 50.0, 310.0)
    assert not FL.types_match_relaxed(([(990.0, 62.0, 330.0)], cold_occ[1]), None, ("cold",), 50.0, 310.0)


def test_basin_edge_clipped():
    def sysf(typ, a, b):
        return {"type": typ, "sys": True, "pts": [a, b]}
    assert FL.basin_edge_clipped([sysf("cold", [45.0, 180.4], [40.0, 190.0])], "npac")        # starts on the 180 edge
    assert not FL.basin_edge_clipped([sysf("cold", [45.0, 186.0], [40.0, 190.0])], "npac")
    assert FL.basin_edge_clipped([sysf("warm", [50.0, 340.0], [52.0, 358.8])], "natl")        # ends at the 1W edge
    assert not FL.basin_edge_clipped([sysf("warm", [50.0, 340.0], [52.0, 350.0])], "natl")
    # not the system, or a trough: ignored
    assert not FL.basin_edge_clipped([{"type": "cold", "sys": False, "pts": [[45.0, 180.0], [40.0, 190.0]]}], "npac")
    assert not FL.basin_edge_clipped([sysf("trough", [45.0, 180.0], [40.0, 190.0])], "npac")


def test_find_cases_basins():
    import find_cases as FC
    assert FC.basin_of(300.0) == "natl" and FC.basin_of(200.0) == "npac" and FC.basin_of(150.0) is None and FC.basin_of(359.0) is None
    assert FC.excluded_water("natl", 27.0, 270.0) and not FC.excluded_water("natl", 27.0, 285.0)        # Gulf of Mexico vs off Florida
    assert FC.excluded_water("natl", 55.0, 280.0) and FC.excluded_water("natl", 48.0, 295.0)            # Hudson Bay, Gulf of St Lawrence
    assert not FC.excluded_water("natl", 55.0, 320.0)
    assert FC.excluded_water("npac", 28.0, 246.0) and FC.excluded_water("npac", 49.0, 237.0)            # Gulf of California, Strait of Georgia
    assert not FC.excluded_water("npac", 50.0, 200.0) and not FC.excluded_water("npac", 49.0, 232.0)


def test_second_low():
    lows = [(990.0, 50.0, 310.0), (1000.0, 53.0, 310.0)]      # 333 km apart
    assert FL.has_second_low(lows, 50.0, 310.0)
    assert not FL.has_second_low(lows[:1], 50.0, 310.0)
    assert not FL.has_second_low([lows[0], (1000.0, 58.0, 310.0)], 50.0, 310.0)    # 890 km


def test_link_tracks():
    t0 = dt.datetime(2025, 1, 1, 0)
    h = dt.timedelta(hours=6)
    by_t = {t0: [(990.0, 50.0, 310.0), (1000.0, 40.0, 280.0)],
            t0 + h: [(985.0, 40.5, 281.0), (988.0, 51.0, 312.0)],        # order swapped
            t0 + 3 * h: [(980.0, 52.0, 314.0)]}                          # gap at +12 h: new track
    ids = FL.link_tracks(by_t)
    assert ids[(t0, 0)] == ids[(t0 + h, 1)] and ids[(t0, 1)] == ids[(t0 + h, 0)]
    assert ids[(t0, 0)] != ids[(t0, 1)]
    assert ids[(t0 + 3 * h, 0)] not in (ids[(t0, 0)], ids[(t0, 1)])


def test_clip_fronts():
    # a front crossing the whole box north-south at 310E, 62N..37N: clipped to 61N..38N, about 1,380 nm
    f = line("cold", [66.0, 30.0], [310.0, 310.0])
    out = FL.clip_fronts([f], LAT_N, LON_W)
    assert len(out) == 1
    lat = [p[0] for p in out[0]["pts"]]
    assert max(lat) <= 61.0 + 1e-6 and min(lat) >= 38.0 - 1e-6
    steps = np.diff(lat)
    assert np.all(np.abs(steps) * 60 <= 25.5)                    # densified to 25 nm
    # a short piece inside (under 150 nm) is dropped, a long one kept
    short = line("warm", [50.0, 51.5], [310.0, 310.0])           # 90 nm
    assert FL.clip_fronts([short], LAT_N, LON_W) == []
    # a front that leaves the box and comes back gives two long pieces
    loop = line("stationary", [60.0, 50.0, 45.0, 66.0, 70.0, 45.0, 40.0], [300, 300, 300, 300, 300, 300, 300])
    loop = line("stationary", [45.0, 55.0, 61.5, 66.0, 61.5, 55.0, 45.0],
                [295.0, 295.0, 295.0, 295.0, 299.0, 299.0, 299.0])
    assert len(FL.clip_fronts([loop], LAT_N, LON_W)) == 2
    # one entirely outside is dropped; the west and east margins apply (a front at 290.5E is outside)
    assert FL.clip_fronts([line("cold", [60.0, 40.0], [290.5, 290.5])], LAT_N, LON_W) == []
    assert FL.clip_fronts([line("cold", [60.0, 40.0], [329.5, 329.5])], LAT_N, LON_W) == []
    assert len(FL.clip_fronts([line("cold", [60.0, 40.0], [291.5, 291.5])], LAT_N, LON_W)) == 1


def test_clip_fronts_curved_through_coded_points():
    pts_la, pts_lo = [60.0, 55.0, 53.0, 47.0, 42.0], [300.0, 303.0, 308.0, 310.0, 316.0]
    out = FL.clip_fronts([line("cold", pts_la, pts_lo)], LAT_N, LON_W)
    assert len(out) == 1
    la, lo = np.array([p[0] for p in out[0]["pts"]]), np.array([p[1] for p in out[0]["pts"]])
    for a, b in zip(pts_la[1:], pts_lo[1:]):       # every coded point inside the box is on the curve (within rounding)
        assert np.min(FL.km(a, b, la, lo)) < 0.5


def test_old_edge_clipped():
    assert FL.COVERAGE_FULL_FROM == dt.datetime(2026, 8, 12, 18)
    la, lo = FL.old_edge()
    e45 = float(np.interp(45.0, la, lo))
    assert 325 < e45 < 340                           # about 29-23W at 45N
    def sysf(lon_end):
        return [{"type": "cold", "sys": True, "pts": [[45.0, lon_end - 6.0], [45.0, lon_end]]}]
    assert FL.edge_clipped(sysf(e45 - 0.5))          # ends on the edge
    assert not FL.edge_clipped(sysf(e45 - 4.0))      # ends well inside
    assert not FL.edge_clipped([{"type": "trough", "sys": True, "pts": [[45.0, e45 - 6], [45.0, e45]]}])
    assert not FL.edge_clipped([{"type": "cold", "sys": False, "pts": [[45.0, e45 - 6], [45.0, e45]]}])


def test_lows_in_box():
    lows = [(990.0, 50.0, 310.0), (1000.0, 70.0, 310.0), (1004.0, 50.0, 340.0)]
    got = FL.lows_in_box(lows, LAT_N, LON_W)
    assert [g["hpa"] for g in got] == [990.0]


def test_mark_system():
    low = (50.0, 310.0)
    occ = {"type": "occluded", "pts": [[50.3, 310.0], [52.0, 311.0], [53.5, 312.0]]}            # end at the low: seed
    cold = {"type": "cold", "pts": [[53.5, 312.3], [51.0, 313.0], [46.0, 312.0]]}               # end 15 nm from the occlusion's end
    tro = {"type": "trough", "pts": [[46.2, 312.2], [44.0, 316.0], [42.0, 319.0]]}              # trough off the cold front's end
    far = {"type": "warm", "pts": [[58.0, 296.0], [58.0, 300.0], [57.0, 304.0]]}                # another system
    far_tro = {"type": "trough", "pts": [[50.0, 300.0], [50.0, 297.0], [50.0, 294.0]]}          # trough nowhere near it
    fr = [occ, cold, tro, far, far_tro]
    r = FL.mark_system(fr, *low)
    assert [f["sys"] for f in fr] == [True, True, True, False, False]
    # ring: farthest system point from the low (the trough's far end, ~560 nm) + 60 nm
    assert 600 <= r <= 680, r
    assert FL.sys_length_nm(fr) > 400
    # nothing within 300 km of the low: no system, radius 0, no length
    fr2 = [dict(far)]
    assert FL.mark_system(fr2, *low) == 0 and fr2[0]["sys"] is False and FL.sys_length_nm(fr2) == 0
    # a front 100 nm from the system front's end is not chained (60 nm rule); the radius is capped at 900
    gap = {"type": "stationary", "pts": [[46.0 - 100 / 60, 312.0], [40.0, 312.0]]}
    long_occ = {"type": "occluded", "pts": [[50.3, 310.0], [38.0, 312.0]]}
    r3 = FL.mark_system([long_occ, gap], *low)
    assert r3 > 0
    far_end = {"type": "cold", "pts": [[50.3, 310.0], [30.0, 330.0]]}
    assert FL.mark_system([far_end], *low) == 900


def grid_field(fn):
    lat = LAT_N - np.arange(51) * 0.5
    lon = LON_W + np.arange(81) * 0.5
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    return fn(LA, LO)


def test_bilin_and_directions():
    f = grid_field(lambda la, lo: la * 2 + lo)
    v = FL.bilin(f, LAT_N, LON_W, np.array([50.25]), np.array([301.25]))
    assert abs(v[0] - (50.25 * 2 + 301.25)) < 1e-9
    assert np.isnan(FL.bilin(f, LAT_N, LON_W, np.array([20.0]), np.array([301.0]))[0])
    assert abs(FL.wind_dir(0.0, -10.0) - 0.0) < 1e-9          # from the north
    assert abs(FL.wind_dir(-10.0, 0.0) - 90.0) < 1e-9         # from the east
    assert abs(FL.wrap180(350 - 10) - (-20.0)) < 1e-9


def synthetic_cold_front():
    """Front along 310E running south (pts from 55N to 42N). West of it cold, NW wind; east warm, SW wind."""
    pts = [[55.0 - 0.2 * i, 310.0] for i in range(66)]
    te = grid_field(lambda la, lo: np.where(lo < 310.0, 280.0, 296.0))
    ang_w = np.radians(225.0)       # from the SW
    ang_c = np.radians(315.0)       # from the NW
    spd = 12.0
    warm_u, warm_v = -spd * np.sin(ang_w), -spd * np.cos(ang_w)
    cold_u, cold_v = -spd * np.sin(ang_c), -spd * np.cos(ang_c)
    u = grid_field(lambda la, lo: np.where(lo < 310.0, cold_u, warm_u))
    v = grid_field(lambda la, lo: np.where(lo < 310.0, cold_v, warm_v))
    return pts, te, u, v


def test_thermal_contrast_cold():
    pts, te, u, v = synthetic_cold_front()
    c = FL.thermal_contrast([pts], te, u, v, LAT_N, LON_W)
    assert abs(c["dte"] - 16.0) < 0.5 and c["te_warm"] > c["te_cold"]
    assert abs(c["turn"] - 90.0) < 5.0                        # SW -> NW veers 90 deg
    # the same front drawn in the other direction gives the same answer (the warm side is found, not assumed)
    c2 = FL.thermal_contrast([pts[::-1]], te, u, v, LAT_N, LON_W)
    assert abs(c2["dte"] - c["dte"]) < 1e-6 and abs(c2["turn"] - c["turn"]) < 1e-6
    h = FL.hint("cold", [pts], {"te850": te, "u10": u, "v10": v}, LAT_N, LON_W)
    assert h.startswith("Cold front: 850 hPa theta-e falls 16 K") and "veers 90 deg" in h, h
    # backing wind gives a warm-front style line
    h2 = FL.hint("warm", [pts], {"te850": te, "u10": v, "v10": u}, LAT_N, LON_W)
    assert "backs" in h2 or "veers" in h2


def test_convergence():
    # u = -k x (east-west convergence) on the sphere: div = du/dx = -k, so convergence = +k (x1e-5)
    la = LAT_N - np.arange(51)[:, None] * 0.5 + 0 * np.arange(81)[None, :]
    lo = np.arange(81)[None, :] * 0.5 + 0 * la
    k = 1e-5
    x_m = np.radians(lo) * 6371000.0 * np.cos(np.radians(la))
    c = FL.convergence(-k * (x_m - x_m[:, 40:41]), np.zeros_like(la), LAT_N)
    assert abs(float(np.median(c[5:-5, 5:-5])) - 1.0) < 0.03, np.median(c)
    # v = k y (north-south divergence): convergence -k
    y_m = np.radians(la) * 6371000.0
    c2 = FL.convergence(np.zeros_like(la), k * (y_m - y_m[25:26, :]), LAT_N)
    assert abs(float(np.median(c2[5:-5, 5:-5])) + 1.0) < 0.1, np.median(c2)
    assert abs(float(np.max(np.abs(FL.convergence(np.full_like(la, 7.0), np.full_like(la, -3.0), LAT_N)[5:-5, 5:-5])))) < 0.2


def test_conv_contrast_and_occluded_hint():
    pts = [[55.0 - 0.2 * i, 310.0] for i in range(66)]
    cv = grid_field(lambda la, lo: 3.0 * np.exp(-((lo - 310.0) / 0.7) ** 2))
    r = FL.conv_contrast([pts], cv, LAT_N, LON_W)
    assert 2.5 < r["on"] <= 3.0 and abs(r["around"]) < 0.1 and r["excess"] > 2.4
    u = grid_field(lambda la, lo: -3.0 * np.tanh((lo - 310.0) / 1.0))      # winds meet along 310E
    h = FL.hint("occluded", [pts], {"u10": u, "v10": u * 0, "msl": u * 0, "te850": u * 0}, LAT_N, LON_W)
    assert "10 m convergence" in h and "700" not in h, h


def test_no_symbols_in_page():
    from pathlib import Path as P
    js = (P(__file__).resolve().parents[1] / "studies/2026-11-06-front-drill/page/app.js").read_text()
    assert "sidePicker" not in js and "te700" not in js and "'semi'" not in js


def test_export_has_no_key_or_absolute_paths():
    import json, tempfile, importlib.util
    from pathlib import Path as P
    page = P(__file__).resolve().parents[1] / "studies/2026-11-06-front-drill/page"
    td = page / "testdeck"
    if not (td / "manifest.json").exists():
        return                                   # make_test_deck.py not run: nothing to export
    spec = importlib.util.spec_from_file_location("export_site", page / "export_site.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as site:
        (P(site) / "fronts").mkdir()
        (P(site) / "fronts" / "stale.txt").write_text("old")
        (td / "key.csv").write_text("never published")       # a stray key beside the deck must not travel
        try:
            out = m.export(site, td)
        finally:
            (td / "key.csv").unlink()
        files = [p for p in out.rglob("*") if p.is_file()]
        names = {p.name for p in files}
        assert "key.csv" not in names and "stale.txt" not in names and "index.html" in names and "manifest.json" in names
        assert not any("work" in p.relative_to(out).parts for p in files)
        for p in files:
            if p.suffix in (".html", ".js", ".css", ".json"):
                t = p.read_text()
                for bad in ("/ho" + "me/", "/t" + "mp/", "/m" + "nt/", "file:" + "//"):
                    assert bad not in t.replace("https://", ""), (p.name, bad)
        assert 'href="../"' in (out / "index.html").read_text()
        json.loads((out / "deck" / "manifest.json").read_text())


def test_ridge_contrast():
    pts = [[55.0 - 0.2 * i, 310.0] for i in range(66)]
    te = grid_field(lambda la, lo: 285.0 + 10.0 * np.exp(-((lo - 310.0) / 1.0) ** 2))
    r = FL.ridge_contrast([pts], te, LAT_N, LON_W)
    assert 8.0 < r["ridge"] < 10.5 and abs(r["around"] - 285.0) < 0.5
    flat = FL.ridge_contrast([pts], grid_field(lambda la, lo: 285.0 + 0 * la), LAT_N, LON_W)
    assert abs(flat["ridge"]) < 1e-6


def test_isobar_angle():
    ns = [[55.0 - 0.2 * i, 310.0] for i in range(66)]          # runs north-south
    along = grid_field(lambda la, lo: 1000.0 + 0.5 * (lo - 310.0))      # isobars run north-south too
    across = grid_field(lambda la, lo: 1000.0 + 0.5 * (la - 50.0))      # isobars run east-west
    a = FL.isobar_angle([ns], along, LAT_N, LON_W)
    b = FL.isobar_angle([ns], across, LAT_N, LON_W)
    assert a["angle"] < 5.0 and b["angle"] > 85.0
    assert FL.isobar_angle([ns], grid_field(lambda la, lo: 1000.0 + 0 * la), LAT_N, LON_W) is None
    h = FL.hint("stationary", [ns], {"msl": along}, LAT_N, LON_W)
    assert h.startswith("Stationary front: the isobars run 0 deg off") or h.startswith("Stationary front: the isobars run 1 deg")
    assert FL.hint("trough", [ns], {}, LAT_N, LON_W) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
