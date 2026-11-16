"""Candidate MSLP fields for the day 1-7 blend study (design.md Part A; interface in BUILD.md).

build(basin, cycle, lead, z, members=None, params=None, info=None) -> {name: float32 field on the basin grid}

Names: singles gfs ifs aifs aigfs; equal means m_gi m_gia m_gif; ensemble means gefs ens aifsens grand;
weighted blend wb wb_gfe; aligned blend al al_gfe; aligned + depth fix ald ald_gfe; rivals bowl bowl_gfe
(plain blend + the same bowl) and off (plain blend + constant offset at gated lows); outlier drop od od_gfe.
The _gfe versions need AI-GFS present (they are skipped otherwise; _gfe2 is the same set without it).
A candidate is left out when a required input is missing, never imputed (see the notes below).

Reuse: low finding and km from rk.score; the grouping of lows across runs is the day 5-7 study's
method.consensus (imported, not copied). New here: the warp, the bowl, the outlier drop.

Inputs and the rules about them
- Runs for the aligned family (al, ald, bowl, off, od): gfs ifs aifs aigfs + the three ensemble means (one
  run each); GFE sets: gfs ifs aigfs gefs (_gfe) and gfs ifs gefs without AI-GFS (_gfe2, also wb_gfe2). A run that is not present is not in the blend (not imputed);
  the candidate needs >= 3 runs present (params["min_runs"]) and, unless params["strict"] is True, is built
  from whichever of its inputs exist. Pass `info={}` to get info[name] = the inputs actually used.
  m_gi, m_gia, m_gif and grand are strict (all named inputs present or the candidate is skipped).
- Ensemble means to f120 come from the extract npz; at f144/f168 (12Z only) from `members` (mean of the
  decoded 0.5 deg members, put on the 0.25 deg grid with rk.basins.to_quarter).

Aligned blend (design item 5)
- Lows of each run: rk.score.find_lows below 1010 hPa, kept when the 500 km ring mean minus the centre is
  >= 4 hPa. Groups across runs: method.consensus (R = 450 km, one low per run per group, equal weights);
  target = support-weighted mean of the runs' own low positions. A group is warped when support >= 0.5,
  each run's chosen low is the clear one within R of the target (no second low in reach that is as deep as it
  or deeper; params["amb_hpa"] widens this, default 0 hPa), and its lows are not split into camps > 800 km apart
  (a camp pair that far apart is two separate groups, each judged on its own support).
- Displacement: run i is moved by D_i(x) = sum_g a_ig * Wendland(|x - T_g| / R_ig), R = max(1200, 2.5 x
  displacement) km; a_ig solves D_i(T_g) = (T_g - P_ig) capped at params["cap"] km (a small interpolation
  system, so overlapping storms do not push each other off target; falls back to a = d if it blows up).
  D is tapered to zero within 300 km of the box edge. The warp samples run(x - D(x)) with
  scipy.ndimage.map_coordinates(order=3, mode="nearest"), only where D != 0, so cells outside every
  radius equal the input exactly. D is scaled down until det(I - grad D) > 0.3 everywhere.
- A run with no low in the group is not moved.

Depth fix (item 6)
- Gate: support >= 0.5, target depth <= 990 hPa, where the target is the median of the deterministic runs'
  own depths in the group (>= 2 of them; ensemble means never set depth). "Centre <= 990" in design.md is
  read as this median, not the blend's own centre, because the blend's centre is the smeared value the fix
  is meant to correct. The blend minimum within 250 km of the target is lowered to the target by a
  250 km Wendland bowl, only deepening, by at most params["dcap"] (default 8 hPa).
- bowl: the same bowl on the plain equal blend of the same runs (no warp). off: plain blend plus the
  constant params["off"][lead] hPa (negative deepens) with the same bowl shape, at the same gated lows.

Outlier drop (item 8)
- Storm groups and the consensus position come from the ensemble means alone (GEFS, ENS, AIFS-ENS; GEFS
  only in the GFE set): lows grouped by method.consensus, a group needs a majority of the ensemble means.
  A deterministic run whose nearest low within 1000 km of the consensus is more than X km away
  (X = params["X"][lead]) is dropped near that storm: its weight is multiplied by a smooth ramp that is 0
  within 500 km and 1 beyond 1000 km of the consensus position and of its own low. A run with no low within
  1000 km is not dropped (params["drop_missing"] switches that on). Ensemble means are never dropped.
  od_dropped() returns one row per deterministic run per group for the risk table.

params: defaults in DEFAULTS; every per-lead entry may be a scalar or {lead: value}. w may be
{basin: {lead: {model: weight}}} or {model: weight}.
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_D57 = str(REPO / "studies" / "2026-10-16-pressure-d5-7")
if _D57 not in sys.path:
    sys.path.append(_D57)

from scipy.ndimage import map_coordinates, spline_filter  # noqa: E402

from rk import basins as rkb  # noqa: E402
from rk import score as rks  # noqa: E402
import method as m57  # noqa: E402  (day 5-7 study: consensus)
from lib import dec as _dec  # noqa: E402

KMDEG = 111.195
CELL_KM = 0.25 * KMDEG
DETS = ("gfs", "ifs", "aifs", "aigfs")
ENSN = ("gefs", "ens", "aifsens")
ZENS = {"gefs": "gefs", "ens": "ens", "aifsens": "aifs-ens"}   # names in the extract npz
AL_FULL = DETS + ENSN
AL_GFE = ("gfs", "ifs", "aigfs", "gefs")
AL_GFE2 = ("gfs", "ifs", "gefs")      # GFE set without AI-GFS (it exists in few cycles, never at f168)
LEADS = tuple(range(24, 169, 24))

DEFAULTS = {
    "cap": 450.0, "X": 300.0, "off": -3.0, "w": None, "w_gfe": None,
    "dcap": 8.0, "gate_p": 990.0, "gate_sup": 0.5, "bowl_km": 250.0,
    "R": 450.0, "camp_km": 800.0, "edge_km": 300.0, "min_runs": 3, "strict": False,
    "od_assoc_km": 1000.0, "od_r0": 500.0, "od_r1": 1000.0, "drop_missing": False,
    "min_drop": 4.0, "det_min": 0.3, "amb_hpa": 0.0,
}


def grid_values():
    """Tuning grids (design.md): cap per lead from {300,450,600}; X from {200,300,400,600}; offsets;
    weight presets for wb (any {model: weight} dict also works through params["w"])."""
    eq = {m: 1.0 for m in AL_FULL}
    w = {"eq": eq}
    for k in (0.3, 0.5, 0.7):          # IFS-heavy, shrunk toward equal: weight = (1-k)*equal + k*IFS-only
        v = {m: (1 - k) / len(AL_FULL) for m in AL_FULL}
        v["ifs"] += k
        w["ifs%.0f" % (k * 100)] = v
    for nm, k in (("ens_up", 2.0), ("ens_down", 0.5)):   # ensemble means weighted k times a deterministic run
        w[nm] = {m: (1.0 if m in DETS else k) for m in AL_FULL}
    w["det_only"] = {m: (1.0 if m in DETS else 0.0) for m in AL_FULL}
    return {"cap": (300.0, 450.0, 600.0), "X": (200.0, 300.0, 400.0, 600.0),
            "off": (0.0, -2.0, -4.0, -6.0), "w": w, "leads": LEADS}


# ----------------------------------------------------------------------------------------------- geometry
class _Geo:
    def __init__(self, basin):
        self.basin = basin
        self.lats, self.lons = rkb.grid(basin)
        self.LA, self.LO = np.meshgrid(self.lats, self.lons, indexing="ij")
        self.cos = np.cos(np.radians(self.LA))
        b = rkb.BASINS[basin]
        e = np.minimum.reduce([(self.LA - b["south"]) * KMDEG, (b["north"] - self.LA) * KMDEG,
                               (self.LO - b["west"]) * KMDEG * self.cos,
                               (b["east"] - self.LO) * KMDEG * self.cos])
        self.edge_km = e
        self.shape = self.LA.shape
        self.rows = np.arange(self.shape[0], dtype=float)[:, None]
        self.cols = np.arange(self.shape[1], dtype=float)[None, :]

    def taper(self, width):
        s = np.clip(self.edge_km / width, 0, 1)
        return s * s * (3 - 2 * s)

    def dist(self, lat, lon):
        """km from (lat, lon) on the local tangent plane."""
        dx = (self.LO - lon) * np.cos(np.radians(lat)) * KMDEG
        dy = (self.LA - lat) * KMDEG
        return np.hypot(dx, dy)


_GEO = {}


def geo(basin):
    if basin not in _GEO:
        _GEO[basin] = _Geo(basin)
    return _GEO[basin]


def wendland(s):
    s = np.asarray(s, float)
    return np.where(s < 1, (1 - np.minimum(s, 1)) ** 4 * (4 * np.minimum(s, 1) + 1), 0.0)


# ------------------------------------------------------------------------------------------------- inputs
def _members_get(members, key):
    if not members:
        return None
    if key in members:
        return members[key]
    for v in members.values():          # {"noaa": {...}, "ec": {...}}
        if isinstance(v, dict) and key in v:
            return v[key]
    return None


def load_members(basin, cycle_ymdh):
    """Both mslpd57 files of a 12Z basin-cycle merged into one dict (None if neither exists)."""
    from rk import store
    out = {}
    for src in ("noaa", "ec"):
        r = store.load(basin, cycle_ymdh, "mslpd57_" + src)
        if r:
            out.update(r)
    return out or None


def run_fields(basin, lead, z, members=None):
    """{name: float32 (ny, nx)} of every run that exists and is finite: gfs ifs aifs aigfs gefs ens aifsens."""
    out = {}
    for m in DETS:
        k = "%s_f%03d" % (m, lead)
        if k in z:
            out[m] = np.asarray(z[k], np.float32)
    for e in ENSN:
        k = "%s_mean_f%03d" % (ZENS[e], lead)
        if k in z:
            out[e] = np.asarray(z[k], np.float32)
            continue
        a = _members_get(members, "mem_%s_%s_%d" % (e, basin, lead))
        if a is not None and len(a):
            out[e] = rkb.to_quarter(_dec(np.asarray(a)).mean(0), basin).astype(np.float32)
    shape = geo(basin).shape
    return {k: v for k, v in out.items() if v.shape == shape and np.isfinite(v).all()}


def _drop_hpa(f, g, lat, lon, ring=500.0, width=50.0, centre=150.0):
    """rk.score.pressure_drop on a window (same definition, much faster)."""
    ny, nx = g.shape
    r0 = (lat - g.lats[0]) / -0.25
    dr = int(ring + width) / CELL_KM + 2
    dc = dr / max(np.cos(np.radians(lat)), 0.2)
    y0, y1 = max(int(r0 - dr), 0), min(int(r0 + dr) + 1, ny)
    c0 = (lon - g.lons[0]) / 0.25
    x0, x1 = max(int(c0 - dc), 0), min(int(c0 + dc) + 1, nx)
    sub = f[y0:y1, x0:x1]
    d = rks.km(lat, lon, g.LA[y0:y1, x0:x1], g.LO[y0:y1, x0:x1])
    rg, co = sub[np.abs(d - ring) <= width], sub[d <= centre]
    if not rg.size or not co.size:
        return np.nan
    return float(rg.mean() - co.min())


def lows_of(f, basin, min_drop=4.0):
    """(k, 3) lat, lon, hPa: minima < 1010 hPa with a 500 km drop >= min_drop (design item 5)."""
    g = geo(basin)
    L = rks.find_lows(f, basin, below=1010.0)[["lat", "lon", "hpa"]].to_numpy(float)
    if not len(L):
        return L.reshape(0, 3)
    keep = [i for i in range(len(L)) if (_drop_hpa(f, g, L[i, 0], L[i, 1]) >= min_drop)]
    return L[keep].reshape(-1, 3)


# --------------------------------------------------------------------------------------------- the case
class Case:
    """Everything shared by all settings of one basin-cycle-lead: fields, lows, groups."""

    def __init__(self, basin, cycle, lead, z, members=None):
        self.basin, self.cycle, self.lead = basin, cycle, int(lead)
        self.g = geo(basin)
        self.runs = run_fields(basin, lead, z, members)
        self._lows, self._grp, self._ens = {}, {}, {}

    def lows(self, name, min_drop=4.0):
        if name not in self._lows:
            self._lows[name] = lows_of(self.runs[name], self.basin, min_drop)
        return self._lows[name]

    def names(self, wanted, strict=False, min_runs=3):
        have = [n for n in wanted if n in self.runs]
        if strict and len(have) < len(wanted):
            return None
        return have if len(have) >= min_runs else None

    def groups(self, names, p):
        """Groups across the named runs (list of dicts), cached per input set and R."""
        key = (tuple(names), p["R"], p["camp_km"], p["min_drop"])
        if key not in self._grp:
            self._grp[key] = _make_groups(self, names, p)
        return self._grp[key]


def _nearest_idx(L, la, lo):
    return int(np.argmin(np.abs(L[:, 0] - la) + np.abs(L[:, 1] - lo)))


def _make_groups(case, names, p, tmin=None, ens_majority=False):
    n = len(names)
    V = [(1.0 / n, case.lows(m, p["min_drop"])) for m in names]
    T = (tmin if tmin is not None else 0.5) - 1e-6
    mem = []
    out = m57.consensus(V, R=p["R"], T=T, cand_p=1010.0, sep=600.0, members=mem)
    groups = []
    for row, mm in zip(out, mem):
        lat, lon, _, sup, _ = row
        voters = {}
        for vi, vla, vlo in mm:
            L = V[vi][1]
            j = _nearest_idx(L, vla, vlo)
            voters[names[vi]] = (float(L[j, 0]), float(L[j, 1]), float(L[j, 2]))
        # one-to-one: no voter has a second low within R of the target
        amb = False
        for vi in range(n):
            L = V[vi][1]
            if not len(L) or names[vi] not in voters:
                continue
            ch = voters[names[vi]]
            other = (rks.km(lat, lon, L[:, 0], L[:, 1]) <= p["R"]) & ~((L[:, 0] == ch[0]) & (L[:, 1] == ch[1]))
            if np.any(L[other, 2] <= ch[2] + p["amb_hpa"]):
                amb = True       # a second low in reach that is as deep as, or deeper than, the one chosen
        pts = np.array([[v[0], v[1]] for v in voters.values()])
        camp = False
        if len(pts) > 1:
            dd = rks.km(pts[:, None, 0], pts[:, None, 1], pts[None, :, 0], pts[None, :, 1])
            camp = bool(dd.max() > p["camp_km"])
        groups.append({"lat": float(lat), "lon": float(lon), "sup": float(sup), "voters": voters,
                       "ambiguous": amb, "camps": camp})
    return groups


# --------------------------------------------------------------------------------------------- warping
def _disp_km(T, P):
    """Displacement P -> T in km (east, north), tangent plane at T."""
    return ((T[1] - P[1]) * np.cos(np.radians(T[0])) * KMDEG, (T[0] - P[0]) * KMDEG)


def warp_field(f, g, items, cap, edge_km=300.0, det_min=0.3):
    """Warp one run. items: [(T=(lat, lon), P=(lat, lon))], moving each run low P to the target T.
    Returns (warped float32 field, scale actually applied, max displacement km)."""
    if not items:
        return f, 1.0, 0.0
    d = []
    for T, P in items:
        e, n = _disp_km(T, P)
        m = float(np.hypot(e, n))
        s = min(1.0, cap / m) if m > 0 else 0.0
        d.append((e * s, n * s))
    d = np.array(d)
    mag = np.hypot(d[:, 0], d[:, 1])
    if mag.max() < 0.5:
        return f, 1.0, float(mag.max())
    Rg = np.maximum(1200.0, 2.5 * mag)
    Tc = np.array([t[0] for t in items])
    # interpolation weights so that D(T_k) = d_k also where footprints overlap
    A = np.eye(len(items))
    for k in range(len(items)):
        for q in range(len(items)):
            if k != q:
                A[k, q] = float(wendland(rks.km(Tc[k][0], Tc[k][1], Tc[q][0], Tc[q][1]) / Rg[q]))
    a = d
    if len(items) > 1:
        try:
            sol = np.linalg.solve(A + 1e-3 * np.eye(len(items)), d)
            if np.abs(sol).max() <= 2.0 * np.abs(d).max():
                a = sol
        except np.linalg.LinAlgError:
            pass
    DE = np.zeros(g.shape)
    DN = np.zeros(g.shape)
    for k, (T, _) in enumerate(items):
        ph = wendland(g.dist(*T) / Rg[k])
        DE += a[k, 0] * ph
        DN += a[k, 1] * ph
    taper = g.taper(edge_km)
    DE *= taper
    DN *= taper
    Dx = DE / (CELL_KM * g.cos)          # cells (columns, eastward)
    Dy = -DN / CELL_KM                   # cells (rows grow southward)
    scale = 1.0
    for _ in range(14):
        ddy_dy, ddy_dx = np.gradient(Dy * scale)
        ddx_dy, ddx_dx = np.gradient(Dx * scale)
        det = (1 - ddy_dy) * (1 - ddx_dx) - ddy_dx * ddx_dy
        if det.min() > det_min:
            break
        scale *= 0.85
    Dx, Dy = Dx * scale, Dy * scale
    m = (np.abs(Dx) + np.abs(Dy)) > 1e-7
    out = np.array(f, np.float32, copy=True)
    if m.any():
        coef = spline_filter(np.asarray(f, np.float64), order=3, mode="nearest")
        rr = (g.rows - Dy)[m]
        cc = (g.cols - Dx)[m]
        out[m] = map_coordinates(coef, [rr, cc], order=3, mode="nearest", prefilter=False)
    return out, scale, float(mag.max())


def aligned_runs(case, names, p):
    """{name: warped field} and the groups that were warped, for the aligned family."""
    cap = _pick(p["cap"], case.lead)
    groups = case.groups(names, p)
    use = [gr for gr in groups if gr["sup"] >= p["gate_sup"] - 1e-9 and not gr["ambiguous"] and not gr["camps"]]
    out = {}
    for m in names:
        items = [((gr["lat"], gr["lon"]), gr["voters"][m][:2]) for gr in use if m in gr["voters"]]
        out[m], _, _ = warp_field(case.runs[m], case.g, items, cap, p["edge_km"], p["det_min"])
    return out, use


def _mean(fields, w=None):
    names = list(fields)
    ww = np.ones(len(names)) if w is None else np.array([w[n] for n in names], float)
    ww = ww / ww.sum()
    acc = np.zeros(next(iter(fields.values())).shape, np.float64)
    for wi, n in zip(ww, names):
        acc += wi * fields[n]
    return acc.astype(np.float32)


def _pick(v, lead):
    return v[lead] if isinstance(v, dict) else v


# ------------------------------------------------------------------------------------- depth, offset
def _gated(case, groups, names, p):
    """[(group, target hPa)] for groups passing the depth gate (>= 2 deterministic runs' own depths)."""
    out = []
    for gr in groups:
        if gr["sup"] < p["gate_sup"] - 1e-9 or gr["camps"]:
            continue
        dp = [v[2] for m, v in gr["voters"].items() if m in DETS]
        if len(dp) < 2:
            continue
        tgt = float(np.median(dp))
        if tgt <= p["gate_p"]:
            out.append((gr, tgt))
    return out


def _apply_bowl(f, g, gr, delta_fn, p):
    """Add a bowl at the minimum within 250 km of the group target. delta_fn(min hPa) -> change (<= 0)."""
    d = g.dist(gr["lat"], gr["lon"])
    win = d <= p["bowl_km"]
    if not win.any():
        return f
    idx = np.argmin(np.where(win, f, np.inf))
    iy, ix = np.unravel_index(idx, f.shape)
    delta = delta_fn(float(f[iy, ix]))
    if delta == 0:
        return f
    r = g.dist(g.lats[iy], g.lons[ix]) / p["bowl_km"]
    return (f + delta * wendland(r)).astype(np.float32)


def depth_fix(case, f, names, p, groups=None):
    groups = case.groups(names, p) if groups is None else groups
    for gr, tgt in _gated(case, groups, names, p):
        f = _apply_bowl(f, case.g, gr, lambda pm, t=tgt: -float(np.clip(pm - t, 0.0, p["dcap"])), p)
    return f


def offset_fix(case, f, names, p, off):
    for gr, tgt in _gated(case, case.groups(names, p), names, p):
        f = _apply_bowl(f, case.g, gr, lambda pm: float(off), p)
    return f


# --------------------------------------------------------------------------------------- outlier drop
def _ens_groups(case, ens_names, p):
    key = ("ens", tuple(ens_names), p["R"])
    if key not in case._ens:
        n = len(ens_names)
        tmin = (n // 2 + 1) / n
        case._ens[key] = _make_groups(case, ens_names, p, tmin=tmin)
    return case._ens[key]


def _od_rows(case, ens_names, det_names, p, X):
    rows = []
    for gi, gr in enumerate(_ens_groups(case, ens_names, p)):
        c = (gr["lat"], gr["lon"])
        for m in det_names:
            L = case.lows(m, p["min_drop"])
            row = {"group": gi, "clat": c[0], "clon": c[1], "n_ens": len(gr["voters"]), "model": m,
                   "has_low": False, "dist_km": np.nan, "low_lat": np.nan, "low_lon": np.nan,
                   "low_hpa": np.nan, "dropped": False}
            if len(L):
                d = rks.km(c[0], c[1], L[:, 0], L[:, 1])
                j = int(d.argmin())
                if d[j] <= p["od_assoc_km"]:
                    row.update(has_low=True, dist_km=float(d[j]), low_lat=float(L[j, 0]),
                               low_lon=float(L[j, 1]), low_hpa=float(L[j, 2]), dropped=bool(d[j] > X))
            if not row["has_low"] and p["drop_missing"]:
                row["dropped"] = True
            rows.append(row)
    return rows


def _od_blend(case, ens_names, det_names, p, X):
    g = case.g
    names = list(det_names) + list(ens_names)
    wgt = {m: np.ones(g.shape) for m in names}
    r0, r1 = p["od_r0"], p["od_r1"]
    for row in _od_rows(case, ens_names, det_names, p, X):
        if not row["dropped"]:
            continue
        cs = [(row["clat"], row["clon"])]
        if row["has_low"]:
            cs.append((row["low_lat"], row["low_lon"]))
        r = np.minimum.reduce([g.dist(*c) for c in cs])
        s = np.clip((r - r0) / (r1 - r0), 0, 1)
        wgt[row["model"]] *= s * s * (3 - 2 * s)
    num = np.zeros(g.shape)
    den = np.zeros(g.shape)
    for m in names:
        num += wgt[m] * case.runs[m]
        den += wgt[m]
    return (num / den).astype(np.float32)


def od_dropped(basin, cycle, lead, z, members=None, params=None, gfe=False):   # gfe: False | True | "gfe2"
    """Rows (list of dicts) for the risk table: per storm group of the ensemble means and per deterministic
    run (gfs ifs aifs aigfs; gfe=True: gfs ifs aigfs; gfe="gfe2": gfs ifs): consensus position clat/clon, whether the run has a low
    within 1000 km (has_low), its distance to the consensus (dist_km), that low's position and depth, and
    dropped (distance > X, X = params['X'][lead] km)."""
    p = _params(params)
    case = z if isinstance(z, Case) else Case(basin, cycle, lead, z, members)
    ens = [e for e in (("gefs",) if gfe else ENSN) if e in case.runs]
    dets = [m for m in (DETS if not gfe else ("gfs", "ifs") if gfe == "gfe2" else ("gfs", "ifs", "aigfs"))
            if m in case.runs]
    if not ens or not dets:
        return []
    return _od_rows(case, ens, dets, p, _pick(p["X"], case.lead))


# ----------------------------------------------------------------------------------------------- build
def _params(params):
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    return p


def _weights(p, basin, lead, key, names):
    w = p.get(key)
    if w is None and key == "w_gfe":
        w = p.get("w")
    if w is None:
        return None
    if basin in w:
        w = w[basin]
    if isinstance(w, dict) and lead in w:
        w = w[lead]
    out = {n: float(w.get(n, 0.0)) for n in names}
    return out if sum(out.values()) > 0 else None


def prepare(basin, cycle, lead, z, members=None):
    return Case(basin, cycle, lead, z, members)


def build(basin, cycle, lead, z, members=None, params=None, info=None, case=None):
    """All candidates for one basin-cycle-lead with one settings dict. See module docstring."""
    p = _params(params)
    case = case or Case(basin, cycle, lead, z, members)
    return _emit(case, p, info)


def _emit(case, p, info=None, which=None):
    R, lead, basin = case.runs, case.lead, case.basin
    out = {}

    def put(name, f, used=None):
        if which is None or name in which:
            out[name] = np.asarray(f, np.float32)
            if info is not None:
                info[name] = list(used) if used is not None else None

    for m in DETS:
        if m in R:
            put(m, R[m], [m])
    for e in ENSN:
        if e in R:
            put(e, R[e], [e])
    for nm, need in (("m_gi", ("gfs", "ifs")), ("m_gia", ("gfs", "ifs", "aigfs")), ("m_gif", ("gfs", "ifs", "aifs")),
                     ("grand", ENSN)):
        if all(n in R for n in need):
            put(nm, _mean({n: R[n] for n in need}), need)
    # weighted blends
    for nm, wanted, key in (("wb", AL_FULL, "w"), ("wb_gfe", AL_GFE, "w_gfe"),
                               ("wb_gfe2", AL_GFE2, "w_gfe")):
        have = [n for n in wanted if n in R]
        if len(have) >= 2 and not (nm == "wb_gfe" and "aigfs" not in R):
            w = _weights(p, basin, lead, key, have)
            put(nm, _mean({n: R[n] for n in have}, w), have)
    # aligned family
    for sfx, wanted in (("", AL_FULL), ("_gfe", AL_GFE), ("_gfe2", AL_GFE2)):
        names = case.names(wanted, p["strict"] or sfx == "_gfe", p["min_runs"])   # _gfe = the set with AI-GFS: only when present
        if names is None:
            continue
        sub = {n: R[n] for n in names}
        if which is None or {"al" + sfx, "ald" + sfx} & set(which):
            warped, used = aligned_runs(case, names, p)
            al = _mean(warped)
            put("al" + sfx, al, names)
            if which is None or "ald" + sfx in which:
                put("ald" + sfx, depth_fix(case, al, names, p), names)
        plain = None
        if which is None or "bowl" + sfx in which:
            plain = _mean(sub)
            put("bowl" + sfx, depth_fix(case, plain, names, p), names)
        if sfx == "" and (which is None or "off" in which):
            plain = _mean(sub) if plain is None else plain
            put("off", offset_fix(case, plain, names, p, _pick(p["off"], lead)), names)
        # outlier drop
        if which is None or "od" + sfx in which:
            ens = [e for e in (("gefs",) if sfx else ENSN) if e in R]
            dets = [m for m in (DETS if not sfx else ("gfs", "ifs") if sfx == "_gfe2" else ("gfs", "ifs", "aigfs")) if m in R]
            if sfx == "_gfe" and "aigfs" not in R:
                continue
            if ens and len(dets) >= 2 and (len(ens) + len(dets)) >= p["min_runs"]:
                put("od" + sfx, _od_blend(case, ens, dets, p, _pick(p["X"], lead)), dets + ens)
    return out


def build_grid(basin, cycle, lead, z, members=None, params=None, grid=None):
    """Every setting of grid_values() in one pass (shared lows and groups).
    Returns a list of (cand, setting label, field): al/ald(+_gfe) per cap ("cap=450"), od(+_gfe) per X ("X=300"),
    off per offset ("off=-2"), wb/wb_gfe per weight preset ("w=ifs50"); everything else once with "base"."""
    base = _params(params)
    gv = grid or grid_values()
    case = Case(basin, cycle, lead, z, members)
    res = []
    for name, f in _emit(case, base, which={"gfs", "ifs", "aifs", "aigfs", "gefs", "ens", "aifsens", "m_gi", "m_gia",
                                              "m_gif", "grand", "bowl", "bowl_gfe", "bowl_gfe2"}).items():
        res.append((name, "base", f))
    for c in gv["cap"]:
        for name, f in _emit(case, dict(base, cap=float(c)), which={"al", "ald", "al_gfe", "ald_gfe", "al_gfe2", "ald_gfe2"}).items():
            res.append((name, "cap=%g" % c, f))
    for x in gv["X"]:
        for name, f in _emit(case, dict(base, X=float(x)), which={"od", "od_gfe", "od_gfe2"}).items():
            res.append((name, "X=%g" % x, f))
    for o in gv["off"]:
        for name, f in _emit(case, dict(base, off=float(o)), which={"off"}).items():
            res.append((name, "off=%g" % o, f))
    for k, w in gv["w"].items():
        for name, f in _emit(case, dict(base, w=w, w_gfe=w), which={"wb", "wb_gfe", "wb_gfe2"}).items():
            res.append((name, "w=%s" % k, f))
    return res
