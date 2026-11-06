/* Front drill: static page, plain JS + canvas. Reads deck/manifest.json and deck/<id>.bin (+ imagery JPEG)
   in the format of ../design.md ("Deck format"). One case = one storm system at one analysis hour (a dashed ring marks it): the trainee taps
   points to lay the fronts, picks each type, places the low, submits; the reveal overlays the analysed fronts.
   Sibling of the pattern drill (../../2026-11-05-pattern-drill/page/): map drawing, deck loading and look are reused. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ scoring constants (all tunable here)
  var SCORE = {
    TIMER_SECS: 90,            // countdown per case; ?secs=N in the URL overrides it
    STEP_NM: 25,               // trainee fronts are curved (Catmull-Rom) and sampled at this spacing (truth already is a curve)
    OVERLAP_NM: 300,           // a point counts toward the mean distance only if within this of the other line
    COVER_NM: 150,             // coverage = share of the analysed front's length within this of the drawn line
    POS_FULL_NM: 150,          // position credit 1 up to here ...
    POS_ZERO_NM: 300,          // ... falling linearly to 0 here
    COVER_W: 0.2,              // position credit is multiplied by (1 - COVER_W) + COVER_W * coverage
    POS_W: 1,                  // per-front weights: type counts twice as much as position
    TYPE_W: 2,
    TYPE_HALF: ['occluded|cold', 'stationary|cold', 'stationary|warm'],   // unordered pairs worth TYPE_HALF_CREDIT
    TYPE_HALF_CREDIT: 0.5,
    NEAR_FULL_NM: 300,         // missed-front weight: 1 within this of the low ...
    NEAR_ZERO_NM: 900,         // ... falling to NEAR_MIN at this distance and beyond
    NEAR_MIN: 0.5,
    EXTRA_PEN: 0.25,           // each extra drawn non-trough front with no match (units: a front is POS_W+TYPE_W, the low LOW_W)
    EXTRA_MAX: 1,
    RING_OFFSET_NM: 0,         // the analysed L is given (Jason 2026-11-06), so the ring is centred on it       // the ring centre is off the true low by 0-RING_OFFSET_NM (deterministic per case) so it does not give away the L
    EXTRA_IN_RING: 0.5,        // a drawn front with no match counts as extra only if at least this share of it lies inside the ring
    LOW_FULL_NM: 60,           // low: full credit within this ...
    LOW_ZERO_NM: 120,          // ... none from here
    LOW_W: 0,                  // the L is given, not scored (Jason 2026-11-06)
    MATCH_TYPE_BIAS: 0.1,      // greedy matching cost = (1 - position credit) - bias * type credit, so a near tie goes to the right type
    PASS: 70                   // percent counted for the streak
  };

  // ------------------------------------------------------------------ constants
  var FT = {   // front types: colour, button label
    cold: { c: '#1565c0', name: 'Cold' },
    warm: { c: '#d32f2f', name: 'Warm' },
    occluded: { c: '#7b1fa2', name: 'Occluded' },
    stationary: { c: '#d32f2f', c2: '#1565c0', name: 'Stationary' },
    trough: { c: '#e08a00', name: 'Trough' }
  };
  // Jason 2026-11-06: "place the L for me. I just want to draw fronts ... just place the stationary already", "dont worry about troughs":
  // the trainee draws cold, warm and occluded only; the system's lows and stationary fronts are drawn for them; troughs are not shown until the reveal.
  var FT_ORDER = ['cold', 'warm', 'occluded'];
  var SCORED_ORDER = ['cold', 'warm', 'occluded'];
  var GIVEN = { stationary: true };
  var STORE_KEY = 'fdrill-stats-1';
  var LAND_RGB = [221, 224, 228];
  // Wind colours: same as the pattern drill (rk/style.py light-background version).
  var WIND_LEVELS = [0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80];
  var WIND_COLORS = ['#f4f6f8', '#dde6ef', '#c3d4e6', '#9fbbd9', '#7aa0c9', '#5683b5',
                     '#f7e68a', '#f2a93b', '#d4531f', '#9e1f1f', '#5c0f45'];
  var WIND_OVER = '#c86fd8';
  var ISOTACHS = [70, 90, 110, 130];
  var KT_PER_MS = 1.94384;

  function mix(a, b, t) { return [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * t); }); }
  function rgbs(c) { return 'rgb(' + c.join(',') + ')'; }
  function thkColor(v) {   // blue at and below 540 dam, red above
    if (v <= 540) { var t = Math.max(0, Math.min(1, (v - 480) / 60)); return rgbs(mix([24, 52, 150], [60, 130, 220], t)); }
    var u = Math.max(0, Math.min(1, (v - 546) / 54)); return rgbs(mix([228, 96, 44], [140, 16, 16], u));
  }
  var f0 = function (v) { return String(Math.round(v)); };
  function hexRGB(c) { var n = parseInt(c.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
  function rampFn(stops) {   // [[value, hex], ...] -> v -> [r,g,b]
    var S = stops.map(function (s) { return [s[0], hexRGB(s[1])]; });
    return function (v) {
      if (v <= S[0][0]) return S[0][1];
      for (var i = 1; i < S.length; i++) if (v <= S[i][0]) return mix(S[i - 1][1], S[i][1], (v - S[i - 1][0]) / (S[i][0] - S[i - 1][0]));
      return S[S.length - 1][1];
    };
  }
  var TE_STEP = 3;
  var teRamp = rampFn([[255, '#2a2f8f'], [270, '#3a73c4'], [280, '#74c4d4'], [288, '#b9e2a8'], [296, '#f7efa0'], [304, '#fbc060'], [312, '#ee7a3a'], [322, '#c0282b'], [335, '#6a1456']]);
  var teFill = function (v) { return teRamp(Math.floor(v / TE_STEP) * TE_STEP + TE_STEP / 2); };   // banded every 3 K
  var DP_MAX = 6;
  var dpFill = function (v) {   // diverging, 1 hPa bands: falls red, rises blue; |change| under 1 hPa left clear
    var a = Math.abs(v); if (a < 1) return null;
    var t = Math.min(1, (Math.floor(a) - 1) / (DP_MAX - 1));
    return v < 0 ? mix([253, 219, 199], [160, 28, 36], t) : mix([209, 229, 240], [20, 60, 150], t);
  };

  var TABS = [
    { id: 'msl', label: 'Default', name: 'MSLP + 1000-500 thickness + 10 m wind',
      note: 'Solid black: MSLP every 4 hPa. Dashed: 1000-500 hPa thickness every 6 dam (blue cold, red warm; 540 heavy). Barbs: GFS 10 m wind in knots.' },
    { id: 'img', label: 'Imagery', name: 'Satellite imagery + MSLP', sat: true,
      note: 'Black and white contours: MSLP every 4 hPa.' },
    { id: 'te850', label: '850 theta-e', name: '850 hPa equivalent potential temperature', key: 'te850', fill: teFill,
      legend: { title: '850 hPa theta-e (K), bands of 3 K', lo: 255, hi: 342, step: 3, every: 15, color: teFill },
      contours: [{ key: 'te850', step: 3, width: function (l) { return l % 15 === 0 ? 1.2 : 0.6; }, color: 'rgba(50,25,10,.75)', label: true, fmt: f0, minGap: 170, only: function (l) { return l % 6 === 0; } }],
      note: 'Thin: MSLP every 4 hPa. Brown contours: theta-e every 3 K; a front is a tight packing of them, and analysts draw it on the warm edge of that packing.' },
    { id: 'te700', label: '700 theta-e', name: '700 hPa equivalent potential temperature', key: 'te700', fill: teFill,
      legend: { title: '700 hPa theta-e (K), bands of 3 K', lo: 255, hi: 342, step: 3, every: 15, color: teFill },
      contours: [{ key: 'te700', step: 3, width: function (l) { return l % 15 === 0 ? 1.2 : 0.6; }, color: 'rgba(50,25,10,.75)', label: true, fmt: f0, minGap: 170, only: function (l) { return l % 6 === 0; } }],
      note: 'Thin: MSLP every 4 hPa. The warm ridge wrapping into the low (a TROWAL) marks an occlusion.' },
    { id: 'dp3', label: '3 h tendency', name: '3 h MSLP change', key: 'dp3', fill: dpFill,
      legend: { title: '3 h pressure change (hPa): red falls, blue rises; under 1 hidden', lo: -6, hi: 6, step: 1, every: 2, color: function (v) { return dpFill(v + 0.01 * (v < 0 ? -1 : 1)); }, mid: true },
      note: 'Thin: MSLP every 4 hPa. Falls ahead of the warm front; a fall/rise couplet near the triple point.' },
    { id: 'wind', label: '10 m wind', name: 'GFS 10 m wind speed + MSLP', key: 'ws10', fill: function (v) { return hexRGB(windColor(v)); }, windLegend: 'GFS 10 m wind speed (kt), shading and barbs',
      note: 'Shading and barbs: GFS 10 m wind (model analysis). Black: MSLP every 4 hPa.' }
  ];

  // ------------------------------------------------------------------ helpers
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function shuffle(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  var QS = new URLSearchParams(window.location.search);
  var TIMER_SECS = QS.get('secs') ? +QS.get('secs') : SCORE.TIMER_SECS;

  // ------------------------------------------------------------------ geometry (nm)
  var RAD = Math.PI / 180, NM_PER_DEG = 60;
  function wrapd(d) { return ((d + 540) % 360) - 180; }
  function distNm(a, b) {   // haversine, nm
    var dla = (b.lat - a.lat) * RAD, dlo = (b.lon - a.lon) * RAD;
    var h = Math.sin(dla / 2) * Math.sin(dla / 2) + Math.cos(a.lat * RAD) * Math.cos(b.lat * RAD) * Math.sin(dlo / 2) * Math.sin(dlo / 2);
    return 6880.13 * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function ptSegNm(p, a, b) {   // distance from p to segment ab in a local plane at p
    var c = Math.cos(p.lat * RAD);
    var ax = wrapd(a.lon - p.lon) * c * NM_PER_DEG, ay = (a.lat - p.lat) * NM_PER_DEG;
    var bx = wrapd(b.lon - p.lon) * c * NM_PER_DEG, by = (b.lat - p.lat) * NM_PER_DEG;
    var dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    var t = L2 > 0 ? clamp(-(ax * dx + ay * dy) / L2, 0, 1) : 0;
    return Math.hypot(ax + t * dx, ay + t * dy);
  }
  function distToLine(p, line) {
    if (line.length === 1) return distNm(p, line[0]);
    var m = Infinity;
    for (var i = 0; i < line.length - 1; i++) { var d = ptSegNm(p, line[i], line[i + 1]); if (d < m) m = d; }
    return m;
  }
  function lineLenNm(pts) { var s = 0; for (var i = 1; i < pts.length; i++) s += distNm(pts[i - 1], pts[i]); return s; }
  function densify(pts, step) {   // points at most `step` nm apart, straight in lat/lon (fine at 25 nm)
    if (!pts.length) return [];
    var out = [{ lat: pts[0].lat, lon: pts[0].lon }];
    for (var i = 1; i < pts.length; i++) {
      var a = pts[i - 1], b = pts[i], d = distNm(a, b), n = Math.max(1, Math.ceil(d / step)), dl = wrapd(b.lon - a.lon);
      for (var k = 1; k <= n; k++) out.push({ lat: a.lat + (b.lat - a.lat) * k / n, lon: ((a.lon + dl * k / n) % 360 + 360) % 360 });
    }
    return out;
  }

  // Centripetal Catmull-Rom (alpha 0.5) through the tapped points: no loops or overshoot at uneven spacing, passes through
  // every point, a straight line for two. Same curve as rk.fronts.smooth (which cuts the analysed fronts in the deck).
  // P: [[x, y], ...] in any plane; returns points about `step` apart along each span (the control points included).
  function crSpline(P, step) {
    var Q = [P[0]];
    for (var i = 1; i < P.length; i++) if (Math.hypot(P[i][0] - Q[Q.length - 1][0], P[i][1] - Q[Q.length - 1][1]) > 1e-9) Q.push(P[i]);
    P = Q; var n = P.length;
    if (n < 2) return P.slice();
    var ext = [[2 * P[0][0] - P[1][0], 2 * P[0][1] - P[1][1]]].concat(P, [[2 * P[n - 1][0] - P[n - 2][0], 2 * P[n - 1][1] - P[n - 2][1]]]);
    var out = [P[0]];
    var lc = function (a, b, wa, wb) { return [a[0] * wa + b[0] * wb, a[1] * wa + b[1] * wb]; };
    for (var k = 0; k < n - 1; k++) {
      var p0 = ext[k], p1 = ext[k + 1], p2 = ext[k + 2], p3 = ext[k + 3];
      var d = function (a, b) { return Math.max(Math.pow(Math.hypot(a[0] - b[0], a[1] - b[1]), 0.5), 1e-3); };
      var t0 = 0, t1 = t0 + d(p0, p1), t2 = t1 + d(p1, p2), t3 = t2 + d(p2, p3);
      var m = Math.max(1, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step));
      for (var j = 1; j < m; j++) {
        var t = t1 + (t2 - t1) * j / m;
        var a1 = lc(p0, p1, (t1 - t) / (t1 - t0), (t - t0) / (t1 - t0)), a2 = lc(p1, p2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1)), a3 = lc(p2, p3, (t3 - t) / (t3 - t2), (t - t2) / (t3 - t2));
        var b1 = lc(a1, a2, (t2 - t) / (t2 - t0), (t - t0) / (t2 - t0)), b2 = lc(a2, a3, (t3 - t) / (t3 - t1), (t - t1) / (t3 - t1));
        out.push(lc(b1, b2, (t2 - t) / (t2 - t1), (t - t1) / (t2 - t1)));
      }
      out.push(P[k + 1]);
    }
    return out;
  }
  function smoothGeo(pts, stepNm) {   // [{lat, lon}] -> the same curve in a local plane (nm, centred on the front), sampled every stepNm
    if (pts.length < 3) return pts.map(function (p) { return { lat: p.lat, lon: p.lon }; });
    var NM = 60.04, lat0 = pts.reduce(function (s, p) { return s + p.lat; }, 0) / pts.length, lon0 = pts[0].lon, c = Math.cos(lat0 * RAD);
    var P = pts.map(function (p) { return [wrapd(p.lon - lon0) * NM * c, (p.lat - lat0) * NM]; });
    return crSpline(P, stepNm).map(function (q) { return { lat: q[1] / NM + lat0, lon: ((lon0 + q[0] / (NM * c)) % 360 + 360) % 360 }; });
  }

  // ------------------------------------------------------------------ the system (ring)
  function hash01(str, salt) {   // FNV-1a -> [0, 1)
    var h = 2166136261 >>> 0, t = salt + str;
    for (var i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
    return h / 4294967296;
  }
  function destPt(p, brgDeg, nm) {
    var b = brgDeg * RAD, dlat = nm * Math.cos(b) / NM_PER_DEG, dlon = nm * Math.sin(b) / (NM_PER_DEG * Math.cos(p.lat * RAD));
    return { lat: p.lat + dlat, lon: (((p.lon + dlon) % 360) + 360) % 360 };
  }
  function ringOf(c) {   // {lat, lon, r} or null (a deck without sys_r_nm has no ring: every front is scored)
    if (!(c.sys_r_nm > 0)) return null;
    var c0 = destPt(c.low, hash01(c.id, 'b') * 360, hash01(c.id, 'd') * SCORE.RING_OFFSET_NM);
    return { lat: c0.lat, lon: c0.lon, r: c.sys_r_nm };
  }
  function inRing(ring, p) { return !ring || distNm(ring, p) <= ring.r; }
  function isSys(f) { return f.sys !== false; }   // an older deck has no flag: everything is the system

  function givenOf(c) {   // what the trainee is given before submitting: the system's stationary fronts and its analysed lows in the ring
    var ring = ringOf(c);
    return { fronts: c.fronts.filter(function (f) { return isSys(f) && GIVEN[f.type]; }),
             lows: (c.lows && c.lows.length ? c.lows : [c.low]).filter(function (l) { return inRing(ring, l); }) };
  }

  // ------------------------------------------------------------------ scoring
  function typeCredit(truthType, drawnType) {
    if (truthType === drawnType) return 1;
    if (SCORE.TYPE_HALF.indexOf(truthType + '|' + drawnType) >= 0 || SCORE.TYPE_HALF.indexOf(drawnType + '|' + truthType) >= 0) return SCORE.TYPE_HALF_CREDIT;
    return 0;
  }
  function pairStats(T, D) {   // T analysed (dense), D drawn (dense); null if the lines do not overlap
    var dT = T.map(function (p) { return distToLine(p, D); }), dD = D.map(function (p) { return distToLine(p, T); });
    var oT = dT.filter(function (d) { return d <= SCORE.OVERLAP_NM; }), oD = dD.filter(function (d) { return d <= SCORE.OVERLAP_NM; });
    if (!oT.length || !oD.length) return null;
    var mean = function (a) { return a.reduce(function (s, x) { return s + x; }, 0) / a.length; };
    var dist = (mean(oT) + mean(oD)) / 2;
    var cov = dT.filter(function (d) { return d <= SCORE.COVER_NM; }).length / dT.length;
    var base = clamp((SCORE.POS_ZERO_NM - dist) / (SCORE.POS_ZERO_NM - SCORE.POS_FULL_NM), 0, 1);
    return { dist: dist, cov: cov, posBase: base, pos: base * ((1 - SCORE.COVER_W) + SCORE.COVER_W * cov) };
  }
  // c: case; drawn: [{type, pts:[{lat,lon}]}]; low: {lat,lon} or null. Returns the whole breakdown.
  function scoreCase(c, drawn, low) {
    var ring = ringOf(c);
    var lows = (c.lows && c.lows.length ? c.lows : [c.low]).filter(function (l) { return inRing(ring, l); });
    if (!lows.length) lows = [c.low];
    var truths = c.fronts.filter(function (f) { return f.type !== 'trough' && !GIVEN[f.type] && isSys(f); }).map(function (f, i) {
      var pts = f.pts.map(function (p) { return { lat: p[0], lon: p[1] }; });
      var near = Infinity;
      pts.forEach(function (p) { lows.forEach(function (l) { var d = distNm(p, l); if (d < near) near = d; }); });
      var nearness = clamp(1 - (1 - SCORE.NEAR_MIN) * (near - SCORE.NEAR_FULL_NM) / (SCORE.NEAR_ZERO_NM - SCORE.NEAR_FULL_NM), SCORE.NEAR_MIN, 1);
      return { type: f.type, pts: pts, len: lineLenNm(pts), nearLow: near, nearness: nearness };
    });
    var dr = drawn.filter(function (f) { return f.pts.length >= 2; }).map(function (f) { return { type: f.type, pts: f.pts, dense: densify(smoothGeo(f.pts, SCORE.STEP_NM), SCORE.STEP_NM) }; });
    var totLen = truths.reduce(function (s, t) { return s + t.len; }, 0) || 1;
    var wsum = 0;
    truths.forEach(function (t) { t.share = t.len / totLen; t.w = t.share * t.nearness; wsum += t.w; });
    truths.forEach(function (t) { t.W = wsum ? t.w / wsum : 0; });
    // one-to-one greedy matching
    var pairs = [];
    truths.forEach(function (t, ti) {
      dr.forEach(function (d, di) {
        var st = pairStats(t.pts, d.dense); if (!st || st.pos <= 0) return;
        var tc = typeCredit(t.type, d.type);
        pairs.push({ ti: ti, di: di, st: st, tc: tc, cost: (1 - st.pos) - SCORE.MATCH_TYPE_BIAS * tc });
      });
    });
    pairs.sort(function (a, b) { return a.cost - b.cost || a.st.dist - b.st.dist; });
    var usedT = {}, usedD = {};
    pairs.forEach(function (p) {
      if (usedT[p.ti] !== undefined || usedD[p.di] !== undefined) return;
      usedT[p.ti] = p; usedD[p.di] = p;
    });
    var perUnit = SCORE.POS_W + SCORE.TYPE_W, frontMax = truths.length ? perUnit : 0;
    var frontSum = 0;
    var rows = truths.map(function (t, ti) {
      var p = usedT[ti], r = { type: t.type, len: t.len, share: t.share, nearLow: t.nearLow, nearness: t.nearness, W: t.W, max: t.W * perUnit, matched: !!p };
      if (p) {
        r.drawnType = dr[p.di].type; r.drawnIdx = p.di; r.dist = p.st.dist; r.cov = p.st.cov; r.pos = p.st.pos;
        r.typeCred = p.tc; r.type_scaled = p.tc * p.st.pos;
        r.earned = t.W * (SCORE.POS_W * p.st.pos + SCORE.TYPE_W * r.type_scaled);
      } else r.earned = 0;
      frontSum += r.earned;
      return r;
    });
    var extras = [];
    dr.forEach(function (d, di) {   // a front drawn out beyond the ring is not penalised
      if (usedD[di] !== undefined || d.type === 'trough') return;
      var inside = d.dense.filter(function (p) { return inRing(ring, p); }).length / d.dense.length;
      if (inside >= SCORE.EXTRA_IN_RING) extras.push(di);
    });
    var extraPen = Math.min(SCORE.EXTRA_MAX, extras.length * SCORE.EXTRA_PEN);
    var lowRes = { dist: null, credit: 0, nearest: null };
    lows.forEach(function (l) { if (low) { var d = distNm(low, l); if (lowRes.dist === null || d < lowRes.dist) { lowRes.dist = d; lowRes.nearest = l; } } });
    if (lowRes.dist !== null) lowRes.credit = clamp((SCORE.LOW_ZERO_NM - lowRes.dist) / (SCORE.LOW_ZERO_NM - SCORE.LOW_FULL_NM), 0, 1);
    var denom = frontMax + SCORE.LOW_W;
    var raw = frontSum + SCORE.LOW_W * lowRes.credit - extraPen;
    return {
      pct: clamp(raw / denom, 0, 1) * 100, denom: denom, frontSum: frontSum, frontMax: frontMax, extraPen: extraPen,
      rows: rows, extras: extras, drawnDense: dr, low: lowRes, lowPts: SCORE.LOW_W * lowRes.credit,
      pairs: rows.map(function (r) { return [r.type, r.matched ? r.drawnType : 'none']; })
    };
  }
  // triple point: where an occluded front's end meets both a cold and a warm front (within 120 nm); null if none
  function triplePoint(c) {
    var by = function (t) { return c.fronts.filter(function (f) { return f.type === t && isSys(f); }); };
    var occ = by('occluded'), cold = by('cold'), warm = by('warm');
    if (!occ.length || !cold.length || !warm.length) return null;
    var best = null, toPts = function (f) { return f.pts.map(function (p) { return { lat: p[0], lon: p[1] }; }); };
    occ.forEach(function (o) {
      var P = toPts(o);
      [P[0], P[P.length - 1]].forEach(function (e) {
        var dc = Infinity, dw = Infinity, pc = null, pw = null;
        cold.forEach(function (f) { toPts(f).forEach(function (p) { var d = distNm(e, p); if (d < dc) { dc = d; pc = p; } }); });
        warm.forEach(function (f) { toPts(f).forEach(function (p) { var d = distNm(e, p); if (d < dw) { dw = d; pw = p; } }); });
        if (dc <= 120 && dw <= 120 && (!best || dc + dw < best.s)) best = { s: dc + dw, lat: (e.lat * 2 + pc.lat + pw.lat) / 4, lon: e.lon };
      });
    });
    return best ? { lat: best.lat, lon: best.lon } : null;
  }

  // ------------------------------------------------------------------ stats (localStorage, this device; falls back to memory)
  var stats = { records: [] };
  try { var raw = window.localStorage.getItem(STORE_KEY); if (raw) { var s0 = JSON.parse(raw); if (s0 && s0.records) stats = s0; } } catch (e) { /* storage may be blocked */ }
  function saveStats() { try { window.localStorage.setItem(STORE_KEY, JSON.stringify({ records: stats.records.slice(-500) })); } catch (e) { /* ignore */ } }
  function summary(recs) {
    var n = recs.length, t = { n: n, avg: 0, avgT: 0, cur: 0, best: 0 }, run = 0;
    recs.forEach(function (r) { t.avg += r.pct; t.avgT += r.t; if (r.pct >= SCORE.PASS) { run++; if (run > t.best) t.best = run; } else run = 0; });
    if (n) { t.avg /= n; t.avgT /= n; }
    t.cur = run;
    return t;
  }
  function confusion(recs) {
    var cols = FT_ORDER.concat(['none']), m = {};
    SCORED_ORDER.forEach(function (a) { m[a] = {}; cols.forEach(function (b) { m[a][b] = 0; }); });
    recs.forEach(function (r) { (r.pairs || []).forEach(function (p) { if (m[p[0]]) m[p[0]][p[1]]++; }); });
    return { m: m, cols: cols };
  }
  function updateTop() {
    var t = summary(stats.records);
    $('topAvg').textContent = t.n ? t.n + ' case' + (t.n === 1 ? '' : 's') + ' · avg ' + Math.round(t.avg) + '%' : '0 cases';
  }
  function statsHTML() {
    var recs = stats.records, t = summary(recs);
    if (!recs.length) return '<div class="statsempty"><p><b>No cases yet.</b></p><p class="fine">Play a few and your average, pace and front-type confusions appear here.</p></div>';
    var h = '<div class="kpis"><div class="kpi"><b>' + t.n + '</b><span>cases</span></div><div class="kpi"><b>' + Math.round(t.avg) + '%</b><span>average score</span></div><div class="kpi"><b>' + Math.round(t.avgT) + ' s</b><span>average time</span></div></div>';
    h += '<div class="kpis"><div class="kpi"><b>' + t.cur + '</b><span>streak of ' + SCORE.PASS + '%+</span></div><div class="kpi"><b>' + t.best + '</b><span>best streak</span></div><div class="kpi"><b>' + Math.round(100 * recs.filter(function (r) { return r.pct >= SCORE.PASS; }).length / t.n) + '%</b><span>cases at ' + SCORE.PASS + '%+</span></div></div>';
    var cf = confusion(recs);
    h += '<h3 class="gh">Front types: analysed (rows) against what you drew (columns)</h3><table class="conf"><tr><th class="corner">analysed \\ drawn</th>' +
      cf.cols.map(function (c) { return '<th>' + (c === 'none' ? 'missed' : FT[c].name) + '</th>'; }).join('') + '</tr>';
    SCORED_ORDER.forEach(function (a) {
      h += '<tr><th class="rowh">' + FT[a].name + '</th>' + cf.cols.map(function (b) {
        var v = cf.m[a][b]; return '<td class="' + (a === b ? 'diag' : '') + (v ? '' : ' zero') + '">' + v + '</td>';
      }).join('') + '</tr>';
    });
    h += '</table><p class="fine">Matched fronts only, plus the analysed fronts you missed. Troughs are never scored.</p>';
    return h;
  }

  // ------------------------------------------------------------------ deck
  var manifest = null, fidx = {}, caseCache = {};
  function loadManifest() {
    return fetch('deck/manifest.json', { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('manifest ' + r.status);
      return r.json();
    }).then(function (m) {
      manifest = m;
      m.fields.forEach(function (f, i) { fidx[f.key] = i; });
      m.byId = {}; m.cases.forEach(function (c) { m.byId[c.id] = c; });
    });
  }
  function parseBin(buf) {
    var ny = manifest.ny, nx = manifest.nx, n = ny * nx, nf = manifest.fields.length;
    var u8 = new Uint8Array(buf);
    if (u8.length < nf * n) throw new Error('short .bin: ' + u8.length + ' < ' + nf * n);
    var snap = { f: {} };
    manifest.fields.forEach(function (f, k) {
      var o = k * n;
      if (f.key === 'ascat_spd') { snap.aspd = u8.slice(o, o + n); return; }
      if (f.key === 'ascat_dir') { snap.adir = u8.slice(o, o + n); return; }
      var a = new Float32Array(n), mul = 1;
      if ((f.key === 'u10' || f.key === 'v10') && /^m\/?s/i.test(f.units || '')) mul = KT_PER_MS;   // wind kept in knots
      for (var i = 0; i < n; i++) { var b = u8[o + i]; a[i] = b === 255 ? NaN : (f.offset + f.scale * b) * mul; }
      snap.f[f.key] = a;
    });
    if (snap.f.u10 && snap.f.v10) {   // GFS 10 m speed (kt) for the wind tab
      snap.f.ws10 = new Float32Array(n);
      for (var w = 0; w < n; w++) snap.f.ws10[w] = Math.hypot(snap.f.u10[w], snap.f.v10[w]);
    }
    var land = snap.f.land || new Float32Array(n);
    for (var q = 0; q < n; q++) land[q] = land[q] >= 0.5 ? 1 : 0;
    snap.land = land;
    return snap;
  }
  var imgData = {};   // base64 decks (Artifact preview): id -> image data URI
  var packs = {};    // pack name -> promise of its parsed JSON
  function b64buf(s) { var bin = atob(s), u = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u.buffer; }
  function imgSrc(c) { return imgData[c.id] || ('deck/' + c.id + '_' + c.img + '.jpg'); }
  function loadCase(id) {
    if (caseCache[id]) return Promise.resolve(caseCache[id]);
    if (manifest.encoding === 'pack') {   // Artifact preview: several cases per JSON file ("pack" in the case), each {z: base64 of the zlib-deflated .bin, img: data URI or absent}
      var pk = manifest.byId[id].pack;
      if (!packs[pk]) packs[pk] = fetch('deck/' + pk + '.json').then(function (r) {
        if (!r.ok) throw new Error(pk + ' ' + r.status);
        return r.json();
      });
      return packs[pk].then(function (P) {
        var j = P[id]; if (!j) throw new Error(id + ' missing from ' + pk);
        if (j.img) imgData[id] = j.img;
        if (typeof DecompressionStream === 'undefined') throw new Error('this browser cannot unpack the preview');
        var ds = new DecompressionStream('deflate');
        return new Response(new Blob([b64buf(j.z)]).stream().pipeThrough(ds)).arrayBuffer();
      }).then(function (buf) { var d = parseBin(buf); caseCache[id] = d; return d; });
    }
    if (manifest.encoding === 'base64') {   // one JSON per case: {bin, img}
      return fetch('deck/' + id + '.json').then(function (r) {
        if (!r.ok) throw new Error(id + ' ' + r.status);
        return r.json();
      }).then(function (j) { if (j.img) imgData[id] = j.img; var d = parseBin(b64buf(j.bin)); caseCache[id] = d; return d; });
    }
    return fetch('deck/' + id + '.bin').then(function (r) {
      if (!r.ok) throw new Error(id + ' ' + r.status);
      return r.arrayBuffer();
    }).then(function (b) { var d = parseBin(b); caseCache[id] = d; return d; });
  }
  var imgCache = {};
  function loadImage(url) {   // resolves to an Image, or null if the file is missing
    if (!imgCache[url]) imgCache[url] = new Promise(function (res) {
      var im = new Image(); im.onload = function () { res(im); }; im.onerror = function () { res(null); }; im.src = url;
    });
    return imgCache[url];
  }

  // ------------------------------------------------------------------ projection
  function makeGeom(c) {
    var g = { nx: manifest.nx, ny: manifest.ny, res: manifest.res, lat0: c.lat0, lon0: c.lon0 };
    g.latc = c.lat0 - (g.ny - 1) * g.res / 2;
    g.aspect = ((g.nx - 1) * Math.cos(g.latc * RAD)) / (g.ny - 1);   // width / height
    return g;
  }
  function proj(g, lat, lon) {
    var dl = (((lon - g.lon0) % 360) + 540) % 360 - 180;
    return [dl / g.res * g.cw / (g.nx - 1), (g.lat0 - lat) / g.res * g.ch / (g.ny - 1)];
  }
  function unproj(g, x, y) {
    return { lat: g.lat0 - y / g.ch * (g.ny - 1) * g.res, lon: (((g.lon0 + x / g.cw * (g.nx - 1) * g.res) % 360) + 360) % 360 };
  }

  // ------------------------------------------------------------------ contouring (marching squares; from the pattern drill)
  function contourSegs(F, nx, ny, L) {
    var segs = [];
    for (var j = 0; j < ny - 1; j++) for (var i = 0; i < nx - 1; i++) {
      var a = F[j * nx + i], b = F[j * nx + i + 1], c = F[(j + 1) * nx + i + 1], d = F[(j + 1) * nx + i];
      if (a !== a || b !== b || c !== c || d !== d) continue;
      var idx = (a >= L ? 8 : 0) | (b >= L ? 4 : 0) | (c >= L ? 2 : 0) | (d >= L ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      var T = [i + (L - a) / (b - a), j], R = [i + 1, j + (L - b) / (c - b)],
          B = [i + (L - d) / (c - d), j + 1], Lf = [i, j + (L - a) / (d - a)];
      var s = function (p, q) { segs.push([p[0], p[1], q[0], q[1]]); };
      switch (idx) {
        case 1: case 14: s(Lf, B); break;
        case 2: case 13: s(B, R); break;
        case 3: case 12: s(Lf, R); break;
        case 4: case 11: s(T, R); break;
        case 6: case 9: s(T, B); break;
        case 7: case 8: s(Lf, T); break;
        case 5: case 10: {
          var hiCentre = (a + b + c + d) / 4 >= L;
          var aroundB = (idx === 5) ? hiCentre === false : hiCentre === true;
          if (aroundB) { s(T, R); s(Lf, B); } else { s(Lf, T); s(B, R); }
        }
      }
    }
    return segs;
  }
  function range(F) {
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i < F.length; i++) { var v = F[i]; if (v === v) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    return [lo, hi];
  }
  function halo(ctx, t, x, y, font, fill) {
    ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round'; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.9)';
    ctx.setLineDash([]);
    ctx.strokeText(t, x, y); ctx.fillStyle = fill; ctx.fillText(t, x, y);
  }
  function drawContours(ctx, g, F, spec, labels) {
    var r = range(F); if (r[0] === Infinity) return;
    var sx = g.cw / (g.nx - 1), sy = g.ch / (g.ny - 1);
    var lv = [];
    if (spec.levels) spec.levels.forEach(function (L) { if (L >= r[0] && L <= r[1]) lv.push(L); });
    else for (var L0 = Math.ceil(r[0] / spec.step) * spec.step; L0 <= r[1]; L0 += spec.step) lv.push(L0);
    lv.forEach(function (L) {
      var segs = contourSegs(F, g.nx, g.ny, L);
      if (!segs.length) return;
      var col = typeof spec.color === 'function' ? spec.color(L) : spec.color;
      ctx.beginPath();
      segs.forEach(function (q) { ctx.moveTo(q[0] * sx, q[1] * sy); ctx.lineTo(q[2] * sx, q[3] * sy); });
      ctx.lineWidth = typeof spec.width === 'function' ? spec.width(L) : spec.width;
      ctx.strokeStyle = col; ctx.setLineDash(spec.dash || []); ctx.lineCap = 'round';
      ctx.stroke(); ctx.setLineDash([]);
      if (spec.label && (!spec.only || spec.only(L))) {
        var mine = [];
        segs.forEach(function (q) {
          var x = (q[0] + q[2]) / 2 * sx, y = (q[1] + q[3]) / 2 * sy;
          if (x < 30 || y < 10 || x > g.cw - 16 || y > g.ch - 10) return;
          for (var k = 0; k < labels.length; k++) if (Math.abs(labels[k][0] - x) < 26 && Math.abs(labels[k][1] - y) < 12) return;
          for (k = 0; k < mine.length; k++) if (Math.hypot(mine[k][0] - x, mine[k][1] - y) < (spec.minGap || 120)) return;
          mine.push([x, y]); labels.push([x, y]);
          halo(ctx, spec.fmt(L), x, y, '600 10px system-ui,sans-serif', typeof col === 'string' && col.indexOf('rgba') === 0 ? '#222' : col);
        });
      }
    });
  }

  // ------------------------------------------------------------------ map drawing (base layer)
  function bil(F, nx, ny, gx, gy) {
    var i = Math.min(Math.floor(gx), nx - 2), j = Math.min(Math.floor(gy), ny - 2);
    var fx = gx - i, fy = gy - j;
    var a = F[j * nx + i], b = F[j * nx + i + 1], c = F[(j + 1) * nx + i], d = F[(j + 1) * nx + i + 1];
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
  }
  function paintBase(canvas, ctx, g, snap, tab) {
    var Wd = canvas.width, Hd = canvas.height, nx = g.nx, ny = g.ny;
    var img = ctx.createImageData(Wd, Hd), px = img.data;
    var F = tab && tab.key ? snap.f[tab.key] : null, fn = tab && tab.fill, A = 0.85;
    for (var y = 0; y < Hd; y++) {
      var gy = (y + 0.5) / Hd * (ny - 1);
      for (var x = 0; x < Wd; x++) {
        var gx = (x + 0.5) / Wd * (nx - 1);
        var land = bil(snap.land, nx, ny, gx, gy) >= 0.5;
        var r = land ? LAND_RGB[0] : 255, gg = land ? LAND_RGB[1] : 255, b = land ? LAND_RGB[2] : 255;
        if (F && fn) {
          var v = bil(F, nx, ny, gx, gy);
          if (v === v) {
            var c = fn(v);
            if (c) { r = r + (c[0] - r) * A; gg = gg + (c[1] - gg) * A; b = b + (c[2] - b) * A; }
          }
        }
        var o = (y * Wd + x) * 4; px[o] = r; px[o + 1] = gg; px[o + 2] = b; px[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }
  function lonLabel(lo) {   // continuous longitude (may pass 180 or 360) -> '170E', '180', '170W', '0'
    var l = ((lo + 540) % 360) - 180;
    if (l === 0) return '0';
    return Math.abs(l) === 180 ? '180' : l < 0 ? -l + 'W' : l + 'E';   // 180 is the date line, neither E nor W
  }
  function drawGrid(ctx, g) {
    var lat1 = g.lat0 - (g.ny - 1) * g.res, lon1 = g.lon0 + (g.nx - 1) * g.res;
    ctx.save();
    ctx.strokeStyle = 'rgba(40,50,70,.22)'; ctx.lineWidth = 0.6; ctx.setLineDash([]);
    var lab = [];
    for (var la = Math.ceil(lat1 / 5) * 5; la <= g.lat0; la += 5) {
      var y = proj(g, la, g.lon0)[1];
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(g.cw, y); ctx.stroke();
      lab.push([la >= 0 ? la + 'N' : -la + 'S', 3, y - 6, 'left']);
    }
    for (var lo = Math.ceil(g.lon0 / 5) * 5; lo <= lon1; lo += 5) {
      var x = proj(g, g.lat0, lo)[0];
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, g.ch); ctx.stroke();
      lab.push([lonLabel(lo), x, g.ch - 8, 'center']);
    }
    ctx.restore();
    lab.forEach(function (t) {
      ctx.save(); ctx.textAlign = t[3]; ctx.textBaseline = 'middle'; ctx.font = '10px system-ui,sans-serif';
      ctx.lineJoin = 'round'; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.85)';
      var x = t[1]; if (t[3] === 'center') x = Math.max(12, Math.min(g.cw - 12, x));
      ctx.strokeText(t[0], x, t[2]); ctx.fillStyle = '#44505f'; ctx.fillText(t[0], x, t[2]); ctx.restore();
    });
  }
  function drawCoast(ctx, g, snap) {
    var segs = contourSegs(snap.land, g.nx, g.ny, 0.5), sx = g.cw / (g.nx - 1), sy = g.ch / (g.ny - 1);
    ctx.beginPath();
    segs.forEach(function (q) { ctx.moveTo(q[0] * sx, q[1] * sy); ctx.lineTo(q[2] * sx, q[3] * sy); });
    ctx.lineWidth = 0.9; ctx.strokeStyle = 'rgba(15,20,30,.8)'; ctx.setLineDash([]); ctx.stroke();
  }
  function windColor(v) {
    if (v >= 80) return WIND_OVER;
    for (var k = WIND_LEVELS.length - 2; k >= 0; k--) if (v >= WIND_LEVELS[k]) return WIND_COLORS[k];
    return WIND_COLORS[0];
  }
  function drawAscatFill(ctx, g, snap) {
    var nx = g.nx, ny = g.ny, cx = g.cw / (nx - 1), cy = g.ch / (ny - 1);
    ctx.save(); ctx.globalAlpha = 0.6;
    for (var j = 0; j < ny; j++) for (var i = 0; i < nx; i++) {
      var s = snap.aspd[j * nx + i]; if (s === 255) continue;
      ctx.fillStyle = windColor(s);
      ctx.fillRect(i * cx - cx / 2, j * cy - cy / 2, cx + 0.6, cy + 0.6);
    }
    ctx.restore();
  }
  function drawBarb(ctx, x, y, fromDeg, kt, L, col) {   // standard NH barb; staff points to where the wind comes from
    if (!(kt >= 0)) return;
    if (kt < 2.5) {
      ctx.beginPath(); ctx.arc(x, y, 2.6, 0, 7); ctx.lineWidth = 2.6; ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.stroke();
      ctx.lineWidth = 1; ctx.strokeStyle = col; ctx.stroke(); return;
    }
    var n = Math.round(kt / 5) * 5, flags = Math.floor(n / 50); n -= flags * 50;
    var full = Math.floor(n / 10), half = (n % 10) / 5;
    var a = fromDeg * RAD, sx = Math.sin(a), sy = -Math.cos(a), px = -sy, py = sx;   // staff direction, clockwise perpendicular
    var ex = x + sx * L, ey = y + sy * L, bl = L * 0.42, sp = L * 0.15;
    var passes = [[3.2, 'rgba(255,255,255,.8)', false], [1.1, col, true]];
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.setLineDash([]);
    passes.forEach(function (ps) {
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ex, ey);
      var d = 0, k, bx, by;
      for (k = 0; k < flags; k++) {
        var ax = ex - sx * d, ay = ey - sy * d, cx = ex - sx * (d + sp * 1.1), cy = ey - sy * (d + sp * 1.1);
        ctx.moveTo(ax, ay); ctx.lineTo(ax + px * bl + sx * bl * 0.2, ay + py * bl + sy * bl * 0.2); ctx.lineTo(cx, cy); d += sp * 1.3;
      }
      for (k = 0; k < full; k++) {
        bx = ex - sx * d; by = ey - sy * d;
        ctx.moveTo(bx, by); ctx.lineTo(bx + px * bl * 0.87 + sx * bl * 0.5, by + py * bl * 0.87 + sy * bl * 0.5); d += sp;
      }
      if (half) {
        if (!flags && !full) d += sp;
        bx = ex - sx * d; by = ey - sy * d;
        ctx.moveTo(bx, by); ctx.lineTo(bx + px * bl * 0.43 + sx * bl * 0.25, by + py * bl * 0.43 + sy * bl * 0.25);
      }
      ctx.lineWidth = ps[0]; ctx.strokeStyle = ps[1]; ctx.stroke();
      if (ps[2] && flags) { ctx.fillStyle = col; ctx.fill(); }
    });
    ctx.restore();
  }
  function drawBarbs(ctx, g, snap, ascat, hideSwath) {   // hideSwath: GFS barbs are left out where ASCAT has a cell
    var nx = g.nx, ny = g.ny, cell = g.cw / (nx - 1), L = clamp(g.cw / 30, 15, 22);
    var step = Math.max(2, Math.ceil((ascat ? 20 : 26) / cell)), col = ascat ? '#0d2a5c' : '#1a1d21';
    for (var j0 = 0; j0 < ny; j0 += step) for (var i0 = 0; i0 < nx; i0 += step) {
      var i = Math.min(nx - 1, i0 + (step >> 1)), j = Math.min(ny - 1, j0 + (step >> 1)), kt, from;
      if (ascat) {   // the seen cell nearest the block centre
        var best = -1, bd = 1e9;
        for (var jj = j0; jj < Math.min(ny, j0 + step); jj++) for (var ii = i0; ii < Math.min(nx, i0 + step); ii++) {
          if (snap.aspd[jj * nx + ii] === 255 || snap.adir[jj * nx + ii] === 255) continue;
          var d = Math.abs(ii - i) + Math.abs(jj - j); if (d < bd) { bd = d; best = jj * nx + ii; i = ii; j = jj; }
        }
        if (best < 0) { i = Math.min(nx - 1, i0 + (step >> 1)); j = Math.min(ny - 1, j0 + (step >> 1)); continue; }
        kt = snap.aspd[best]; from = snap.adir[best] * 2;
        i = best % nx; j = Math.floor(best / nx);
      } else {
        var u = snap.f.u10[j * nx + i], v = snap.f.v10[j * nx + i];
        if (u !== u || v !== v) continue;
        if (hideSwath && snap.aspd[j * nx + i] !== 255) continue;
        kt = Math.hypot(u, v); from = (Math.atan2(-u, -v) / RAD + 360) % 360;
      }
      drawBarb(ctx, i * cell, j * (g.ch / (ny - 1)), from, kt, L, col);
    }
  }
  function drawIsotachs(ctx, g, snap, labels) {
    if (!snap.f.wspd250) return;
    drawContours(ctx, g, snap.f.wspd250, { levels: ISOTACHS, width: function (l) { return 1 + (l - 70) / 30; }, color: '#6a1b9a', label: true, fmt: function (l) { return l + ' kt'; }, minGap: 150 }, labels);
  }
  var ISOBAR = { key: 'msl', step: 4, width: function (l) { return l % 20 === 0 ? 1.8 : 1.1; }, color: '#111', label: false, fmt: f0, minGap: 150 };

  function ascatOn() { return !!(cur && cur.c.ascat && cur.data && cur.data.aspd && $('ascChk').checked); }
  function baseDefault(ctx, g, snap, c, iso) {
    var asc = ascatOn();
    drawGrid(ctx, g); drawCoast(ctx, g, snap);
    if (asc) drawAscatFill(ctx, g, snap);
    var labels = [];
    if (snap.f.thk) drawContours(ctx, g, snap.f.thk, { step: 6, dash: [5, 3], width: function (l) { return l === 540 ? 2.6 : 1.2; }, color: thkColor, label: true, fmt: f0, minGap: 150 }, labels);
    drawContours(ctx, g, snap.f.msl, { key: 'msl', step: 4, width: ISOBAR.width, color: '#111', label: true, fmt: f0, minGap: 130 }, labels);
    if (iso) drawIsotachs(ctx, g, snap, labels);
    drawBarbs(ctx, g, snap, false, asc);
    if (asc) drawBarbs(ctx, g, snap, true);
  }
  function baseFill(ctx, g, snap, tab, iso) {
    var asc = ascatOn();
    drawGrid(ctx, g); drawCoast(ctx, g, snap);
    if (asc) drawAscatFill(ctx, g, snap);
    var labels = [];
    (tab.contours || []).forEach(function (sp) { drawContours(ctx, g, snap.f[sp.key], sp, labels); });
    drawContours(ctx, g, snap.f.msl, { step: 4, width: function (l) { return l % 20 === 0 ? 1.5 : 0.9; }, color: 'rgba(0,0,0,.85)', label: false }, labels);
    if (iso) drawIsotachs(ctx, g, snap, labels);
    if (tab.id === 'wind') drawBarbs(ctx, g, snap, false, asc);   // the model barbs; ASCAT's replace them inside the swath
    if (asc) drawBarbs(ctx, g, snap, true);
  }
  function baseSat(ctx, g, snap, img, iso) {
    var cx = g.cw / (g.nx - 1), cy = g.ch / (g.ny - 1);
    ctx.fillStyle = '#e8ebef'; ctx.fillRect(0, 0, g.cw, g.ch);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, -cx / 2, -cy / 2, g.cw + cx, g.ch + cy);   // the image covers cell edges: half a cell beyond the centres
    if (ascatOn()) drawAscatFill(ctx, g, snap);
    drawCoast(ctx, g, snap); drawGrid(ctx, g);
    var none = [];
    [{ step: 4, width: 3.2, color: 'rgba(0,0,0,.55)' }, { step: 4, width: 1.0, color: 'rgba(255,255,255,.95)' }].forEach(function (sp) { drawContours(ctx, g, snap.f.msl, sp, none); });
    if (iso) drawIsotachs(ctx, g, snap, none);
    if (ascatOn()) drawBarbs(ctx, g, snap, true);
  }

  // ------------------------------------------------------------------ fronts and lows (overlay)
  // +1 / -1: which side of the line the symbols go. Northern-hemisphere convention for fronts of a cyclone:
  // walking along the front AWAY from its low (or the triple point chain), the symbols sit on the LEFT, i.e. on the
  // side the front moves toward: cold-front triangles face the warm sector, warm-front semicircles face the cold
  // air ahead, occluded symbols continue the cold front's side through the triple point (Jason 2026-11-06), and
  // stationary triangles take the left. 850 hPa theta-e was tried first and fails ahead of warm fronts (warm air
  // aloft). `ref` = screen point of the low the front belongs to.
  function sidePicker(P, type, g, ref) {
    var a = P[0], b = P[P.length - 1];
    if (!ref) ref = [g.cw / 2, g.ch / 2];
    var outward = Math.hypot(a[0] - ref[0], a[1] - ref[1]) <= Math.hypot(b[0] - ref[0], b[1] - ref[1]);
    // the symbol normal for side +1 is (-ty, tx): screen-right of travel (y down); left of travel is side -1
    return outward ? -1 : 1;
  }
  function lowFor(f) {   // the analysed low nearest either end of a front (its parent low)
    var ls = cur.c.lows && cur.c.lows.length ? cur.c.lows : [cur.c.low], e = [f.pts[0], f.pts[f.pts.length - 1]], best = null, bd = 1e9;
    ls.forEach(function (l) { e.forEach(function (p) { var d = distNm(l, { lat: p[0], lon: p[1] }); if (d < bd) { bd = d; best = l; } }); });
    return best;
  }
  function pathPoint(P, cum, s) {   // position and unit tangent at arc length s
    var i = 1; while (i < P.length - 1 && cum[i] < s) i++;
    var a = P[i - 1], b = P[i], seg = cum[i] - cum[i - 1] || 1, t = clamp((s - cum[i - 1]) / seg, 0, 1), L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    return { x: a[0] + (b[0] - a[0]) * t, y: a[1] + (b[1] - a[1]) * t, tx: (b[0] - a[0]) / L, ty: (b[1] - a[1]) / L };
  }
  function subPath(ctx, P, cum, s0, s1) {
    var p = pathPoint(P, cum, s0); ctx.moveTo(p.x, p.y);
    for (var i = 1; i < P.length - 1; i++) if (cum[i] > s0 && cum[i] < s1) ctx.lineTo(P[i][0], P[i][1]);
    p = pathPoint(P, cum, s1); ctx.lineTo(p.x, p.y);
  }
  // o: { lw, u (symbol unit px), outline (dark colour under the line), alpha, dots }
  function drawFront(ctx, g, f, o) {
    var P0 = f.pts.map(function (p) { return proj(g, p.lat, p.lon); }), ft = FT[f.type];
    var P = o.curve && P0.length > 2 ? crSpline(P0, 5) : P0;   // the trainee's taps are control points of a smooth curve
    if (o.tint) ft = { c: o.tint, c2: o.tint, name: ft.name };   // other systems: one grey
    ctx.save(); ctx.globalAlpha = o.alpha == null ? 1 : o.alpha; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.setLineDash([]);
    if (P.length < 2) {
      if (P.length === 1) { ctx.beginPath(); ctx.arc(P[0][0], P[0][1], 5, 0, 7); ctx.fillStyle = ft.c; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke(); }
      ctx.restore(); return;
    }
    var cum = [0]; for (var i = 1; i < P.length; i++) cum.push(cum[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]));
    var total = cum[cum.length - 1], u = o.u, spacing = 5.2 * u;
    var path = function () { ctx.beginPath(); ctx.moveTo(P[0][0], P[0][1]); for (var k = 1; k < P.length; k++) ctx.lineTo(P[k][0], P[k][1]); };
    path(); ctx.lineWidth = o.lw + 3.4; ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.stroke();
    if (o.outline) { path(); ctx.lineWidth = o.lw + 1.8; ctx.strokeStyle = o.outline; ctx.stroke(); }
    if (f.type === 'trough') {
      path(); ctx.lineWidth = o.lw; ctx.strokeStyle = ft.c; ctx.setLineDash([u * 2.2, u * 1.4]); ctx.lineCap = 'butt'; ctx.stroke(); ctx.setLineDash([]);
    } else if (f.type === 'stationary') {
      for (var s = 0, k2 = 0; s < total; s += spacing, k2++) {
        ctx.beginPath(); subPath(ctx, P, cum, s, Math.min(total, s + spacing));
        ctx.lineWidth = o.lw; ctx.strokeStyle = k2 % 2 ? ft.c2 : ft.c; ctx.stroke();
      }
    } else { path(); ctx.lineWidth = o.lw; ctx.strokeStyle = ft.c; ctx.stroke(); }
    if (f.type !== 'trough') {
      var side = sidePicker(P, f.type, g, o.ref ? proj(g, o.ref.lat, o.ref.lon) : null), n = Math.max(1, Math.floor(total / spacing));
      for (var m = 0; m < n; m++) {
        var s2 = total / n * (m + 0.5), q = pathPoint(P, cum, s2), nx = -q.ty * side, ny = q.tx * side;
        var kind = f.type === 'cold' ? 'tri' : f.type === 'warm' ? 'semi' : f.type === 'occluded' ? (m % 2 ? 'semi' : 'tri') : (m % 2 ? 'semi' : 'tri');
        var sd = 1, col = ft.c;
        if (f.type === 'stationary') { col = m % 2 ? ft.c : ft.c2; sd = m % 2 ? -1 : 1; }   // blue triangles one side, red half-circles the other
        var ex = nx * sd, ey = ny * sd;
        ctx.beginPath();
        if (kind === 'tri') {
          ctx.moveTo(q.x - q.tx * u * 1.1, q.y - q.ty * u * 1.1); ctx.lineTo(q.x + q.tx * u * 1.1, q.y + q.ty * u * 1.1); ctx.lineTo(q.x + ex * u * 1.9, q.y + ey * u * 1.9); ctx.closePath();
        } else {
          var an = Math.atan2(ey, ex); ctx.arc(q.x, q.y, u * 1.1, an - Math.PI / 2, an + Math.PI / 2, false); ctx.closePath();
        }
        ctx.fillStyle = col; ctx.fill();
        if (o.outline) { ctx.lineWidth = 0.9; ctx.strokeStyle = o.outline; ctx.stroke(); }
      }
    }
    if (o.dots) P0.forEach(function (p) {
      ctx.beginPath(); ctx.arc(p[0], p[1], 4.5, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = ft.c; ctx.stroke();
    });
    ctx.restore();
  }
  function drawLowMark(ctx, g, lat, lon, o) {   // o: {color, text, sub}
    var p = proj(g, lat, lon), r = Math.max(11, Math.min(15, g.cw / 28));
    ctx.save(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(255,255,255,.92)'; ctx.stroke();
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.lineWidth = 2.4; ctx.strokeStyle = o.color; ctx.stroke();
    ctx.restore();
    halo(ctx, 'L', p[0], p[1] + 0.5, '800 ' + Math.round(r * 1.05) + 'px system-ui,sans-serif', o.color);
    if (o.sub) halo(ctx, o.sub, p[0], Math.min(g.ch - 9, p[1] + r + 9), '700 11px system-ui,sans-serif', o.color);
  }
  function drawRing(ctx, g, ring) {   // soft dashed navy circle (true circle on the sphere, so it bends a little on the map)
    var pts = [];
    for (var k = 0; k <= 120; k++) { var q = destPt(ring, k * 3, ring.r); pts.push(proj(g, q.lat, q.lon)); }
    ctx.save(); ctx.lineJoin = 'round';
    ctx.beginPath(); pts.forEach(function (p, i) { if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
    ctx.setLineDash([]); ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.stroke();
    ctx.setLineDash([9, 7]); ctx.lineWidth = 2.2; ctx.strokeStyle = 'rgba(13,42,92,.8)'; ctx.stroke();
    ctx.restore();
  }
  function drawTriple(ctx, g, tp) {
    var p = proj(g, tp.lat, tp.lon);
    ctx.save(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(p[0], p[1], 8, 0, 7); ctx.lineWidth = 4.5; ctx.strokeStyle = 'rgba(255,255,255,.95)'; ctx.stroke();
    ctx.lineWidth = 2; ctx.strokeStyle = '#111'; ctx.stroke();
    ctx.beginPath(); ctx.arc(p[0], p[1], 2.5, 0, 7); ctx.fillStyle = '#111'; ctx.fill();
    ctx.restore();
    halo(ctx, 'triple pt', p[0], p[1] - 16, '700 11px system-ui,sans-serif', '#111');
  }

  // ------------------------------------------------------------------ legend
  function buildLegend(tab, c) {
    var box = $('legend'); box.innerHTML = '';
    var L = tab.legend;
    if (L) {
      var lg = el('div', 'lg'); lg.appendChild(el('div', 'lgt', L.title));
      var bar = el('div', 'lgbar');
      for (var v = L.lo; v <= L.hi; v += L.step) {
        var col = L.color(v + L.step / 2), d = el('div', col ? '' : 'none');
        if (col) d.style.background = rgbs(col);
        if ((L.mid ? v : v - L.lo) % L.every === 0 && v !== L.lo) d.appendChild(el('span', null, String(v)));
        bar.appendChild(d);
      }
      lg.appendChild(bar); box.appendChild(lg);
    }
    var windBar = function (title) {
      var lw = el('div', 'lg'); lw.appendChild(el('div', 'lgt', title));
      var wb = el('div', 'lgbar');
      WIND_COLORS.concat([WIND_OVER]).forEach(function (cl, i) {
        var d2 = el('div'); d2.style.background = cl;
        if (i >= 1 && i <= WIND_LEVELS.length - 1) d2.appendChild(el('span', null, String(WIND_LEVELS[i])));
        wb.appendChild(d2);
      });
      lw.appendChild(wb); box.appendChild(lw);
    };
    if (tab.windLegend) windBar(tab.windLegend);
    if (ascatOn()) windBar('ASCAT 10 m wind (kt), swath shading and navy barbs');
    var note = tab.note + (ascatOn() ? ' ASCAT overlay on: its shading and navy barbs cover the swath (same colours as the GFS wind); GFS barbs are hidden there and shown outside it. Untick ASCAT for the model alone.' : (c.ascat ? ' Tick ASCAT to overlay the scatterometer swath.' : '')) + ($('isoChk').checked ? ' Purple: 250 hPa isotachs at 70, 90, 110, 130 kt.' : '');
    box.appendChild(el('div', 'lgnote', note));
  }

  // ------------------------------------------------------------------ game state
  var cur = null, geom = null, baseCv = null, baseTok = 0, deck = [], deckPos = 0, timerId = null, startFirst = QS.get('case');
  var lastTap = { t: 0, x: -99, y: -99 };

  function show(id) {
    ['start', 'play'].forEach(function (s) { $(s).hidden = s !== id; });
    $('loadMsg').hidden = true; window.scrollTo(0, 0);
  }
  function nextId() {
    if (startFirst && manifest.byId[startFirst]) { var id = startFirst; startFirst = null; return id; }
    startFirst = null;
    if (deckPos >= deck.length) { deck = shuffle(manifest.cases.map(function (c) { return c.id; })); deckPos = 0; }
    return deck[deckPos++];
  }
  function buildTabs() {
    var t = $('tabs'); t.innerHTML = '';
    TABS.forEach(function (tb, i) {
      var b = el('button', 'tab', tb.label); b.type = 'button'; b.setAttribute('role', 'tab'); b.dataset.i = i; b.dataset.tab = tb.id;
      b.addEventListener('click', function () { setTab(i); });
      t.appendChild(b);
    });
  }
  function buildTools() {
    var t = $('types'); t.innerHTML = '';
    FT_ORDER.forEach(function (k) {
      var b = el('button', 'tbtn ty', FT[k].name); b.type = 'button'; b.dataset.type = k; b.style.setProperty('--c', FT[k].c);
      if (k === 'stationary') b.style.setProperty('--c', FT[k].c);
      b.addEventListener('click', function () { clickType(k); });
      t.appendChild(b);
    });
    var lab = function (id, long, short) { $(id).innerHTML = '<span class="lg">' + long + '</span><span class="sh">' + short + '</span>'; };
    lab('finBtn', 'Finish front', 'Finish'); lab('undoBtn', 'Undo point', 'Undo'); lab('delBtn', 'Delete last front', 'Del front'); lab('clrBtn', 'Clear', 'Clear'); lab('lowBtn', 'Place L', 'Place L');
  }
  function sizeCanvas() {
    if (!geom) return;
    var box = $('mapbox'), avail = box.parentNode.clientWidth, w = avail;
    if (window.innerWidth >= 900) w = Math.min(avail, Math.max(320, (window.innerHeight - 250) * geom.aspect));
    w = Math.floor(w);
    var h = Math.round(w / geom.aspect), dpr = Math.min(window.devicePixelRatio || 1, 2);
    geom.cw = w; geom.ch = h; geom.dpr = dpr;
    var cv = $('map'); cv.style.width = w + 'px'; cv.style.height = h + 'px';
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    box.style.width = w + 'px';
  }
  function updateCap() {
    var tab = TABS[cur.tabIdx];
    $('cap').textContent = tab.name + (ascatOn() ? ' + ASCAT swath (GFS outside it)' : '');
  }
  function setTab(i) {
    cur.tabIdx = i;
    [].forEach.call($('tabs').children, function (b, k) { b.classList.toggle('on', k === i); b.setAttribute('aria-selected', k === i); });
    var tab = TABS[i];
    updateCap();
    buildLegend(tab, cur.c);
    renderBase();
  }
  function renderBase() {
    if (!cur || !cur.data || !geom) return;
    var tok = ++baseTok, tab = TABS[cur.tabIdx], g = geom, snap = cur.data, iso = $('isoChk').checked;
    var cv = document.createElement('canvas'); cv.width = $('map').width; cv.height = $('map').height;
    var ctx = cv.getContext('2d'), dpr = g.dpr;
    var done = function () { if (tok !== baseTok) return; baseCv = cv; paint(); };
    if (tab.sat) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!cur.c.img) {
        ctx.fillStyle = '#e8ebef'; ctx.fillRect(0, 0, g.cw, g.ch);
        ctx.fillStyle = '#44505f'; ctx.font = '600 15px system-ui,sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('No imagery for this case', g.cw / 2, g.ch / 2);
        if (ascatOn()) drawAscatFill(ctx, g, snap);
        drawCoast(ctx, g, snap); drawGrid(ctx, g); drawContours(ctx, g, snap.f.msl, { step: 4, width: 1, color: '#111' }, []);
        if (ascatOn()) drawBarbs(ctx, g, snap, true);
        if (iso) drawIsotachs(ctx, g, snap, []);
        return done();
      }
      loadImage(imgSrc(cur.c)).then(function (img) {
        if (tok !== baseTok) return;
        if (!img) { ctx.fillStyle = '#e8ebef'; ctx.fillRect(0, 0, g.cw, g.ch); ctx.fillStyle = '#44505f'; ctx.font = '600 15px system-ui,sans-serif'; ctx.textAlign = 'center'; ctx.fillText('Imagery file missing', g.cw / 2, g.ch / 2); drawGrid(ctx, g); }
        else baseSat(ctx, g, snap, img, iso);
        done();
      });
      return;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    paintBase(cv, ctx, g, snap, tab);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (tab.id === 'msl') baseDefault(ctx, g, snap, cur.c, iso); else baseFill(ctx, g, snap, tab, iso);
    done();
  }
  function paint() {
    if (!cur || !cur.data || !baseCv || !geom) return;
    var g = geom, cv = $('map'), ctx = cv.getContext('2d'), dpr = g.dpr;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height); ctx.drawImage(baseCv, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var u = clamp(g.cw / 80, 3.8, 6.5), showT = cur.submitted && $('showTruth').checked, showM = !cur.submitted || $('showMine').checked;
    var ring = ringOf(cur.c);
    if (ring) drawRing(ctx, g, ring);
    if (!showT) {   // given to the trainee: the system's stationary fronts and its analysed lows
      var toPtsG = function (f) { return { type: f.type, pts: f.pts.map(function (p) { return { lat: p[0], lon: p[1] }; }) }; };
      givenOf(cur.c).fronts.forEach(function (f) { drawFront(ctx, g, toPtsG(f), { lw: 3, u: u * 1.1, outline: '#0c1220', ref: cur.c.low }); });
      givenOf(cur.c).lows.forEach(function (l) {
        drawLowMark(ctx, g, l.lat, l.lon, { color: '#d00018', sub: l.hpa != null ? String(Math.round(l.hpa)) : '' });
      });
    }
    if (showT) {
      var toPts = function (f) { return { type: f.type, pts: f.pts.map(function (p) { return { lat: p[0], lon: p[1] }; }) }; };
      cur.c.fronts.filter(function (f) { return !isSys(f); }).forEach(function (f) { drawFront(ctx, g, toPts(f), { lw: 1.7, u: u * 0.8, tint: '#7c8693', alpha: 0.8, ref: lowFor(f) }); });
      cur.c.fronts.filter(isSys).forEach(function (f) { drawFront(ctx, g, toPts(f), { lw: 3.4, u: u * 1.2, outline: '#0c1220', ref: cur.c.low }); });
      if (cur.triple) drawTriple(ctx, g, cur.triple);
      (cur.c.lows && cur.c.lows.length ? cur.c.lows : [cur.c.low]).forEach(function (l) {
        var sub = l.hpa != null ? String(Math.round(l.hpa)) : '';
        drawLowMark(ctx, g, l.lat, l.lon, { color: inRing(ring, l) ? '#d00018' : '#7c8693', sub: sub });
      });
    }
    if (showM) {
      var myRef = cur.low || ringOf(cur.c) || cur.c.low;
      cur.drawn.forEach(function (f) { drawFront(ctx, g, f, { lw: 2.4, u: u, alpha: cur.submitted ? 0.85 : 1, curve: true, ref: myRef }); });
      if (cur.active && !cur.submitted) drawFront(ctx, g, cur.active, { lw: 2.4, u: u, dots: true, curve: true, ref: myRef });
      if (cur.low) {
        if (cur.submitted && cur.result && cur.result.low.nearest && showT) {
          var a = proj(g, cur.low.lat, cur.low.lon), b = proj(g, cur.result.low.nearest.lat, cur.result.low.nearest.lon);
          ctx.save(); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.setLineDash([4, 3]); ctx.lineWidth = 1.5; ctx.strokeStyle = '#0b4fa8'; ctx.stroke(); ctx.restore();
        }
        drawLowMark(ctx, g, cur.low.lat, cur.low.lon, { color: '#0b4fa8', sub: cur.submitted ? '' : 'you' });
      }
    }
  }

  // ------------------------------------------------------------------ drawing interaction
  function msg(t) { $('toolMsg').textContent = t; }
  function updateTools() {
    [].forEach.call($('types').children, function (b) { b.classList.toggle('on', cur.tool === b.dataset.type); b.setAttribute('aria-pressed', cur.tool === b.dataset.type); });
    $('lowBtn').classList.toggle('on', cur.tool === 'L'); $('lowBtn').setAttribute('aria-pressed', cur.tool === 'L');
    var n = cur.active ? cur.active.pts.length : 0;
    $('finBtn').disabled = n < 2;
    $('undoBtn').disabled = !(n || cur.drawn.length);
    $('delBtn').disabled = !(cur.active || cur.drawn.length);
    $('clrBtn').disabled = !(cur.active || cur.drawn.length || cur.low);
    var have = cur.drawn.length + ' front' + (cur.drawn.length === 1 ? '' : 's') + (SCORE.LOW_W ? (cur.low ? ', low placed' : ', no low yet') : '');
    if (!cur.tool) msg('The low and any stationary front are drawn for you. Pick cold, warm or occluded, then tap points on the map. (' + have + ')');
    else if (cur.tool === 'L') msg('Tap the map to place the low (tap again to move it). (' + have + ')');
    else if (!n) msg(FT[cur.tool].name + ': tap points along the front, in order. (' + have + ')');
    else msg(FT[cur.tool].name + ', ' + n + ' point' + (n === 1 ? '' : 's') + ': keep tapping, then tap ' + FT[cur.tool].name + ' again, Finish front, or double-tap the last point. (' + have + ')');
  }
  function finishFront() {
    if (cur.active && cur.active.pts.length >= 2) cur.drawn.push(cur.active);
    cur.active = null; cur.tool = null;
    updateTools(); paint();
  }
  function clickType(k) {
    if (!cur || cur.submitted) return;
    if (cur.tool === k) { if (cur.active && cur.active.pts.length) finishFront(); else { cur.tool = null; updateTools(); } return; }
    if (cur.active) finishFront();
    cur.tool = k; cur.active = null; updateTools();
  }
  function mapTap(e) {
    if (!cur || cur.submitted || !cur.data || !geom) return;
    var r = $('map').getBoundingClientRect();
    var x = (e.clientX - r.left) * geom.cw / r.width, y = (e.clientY - r.top) * geom.ch / r.height;
    var now = Date.now(), dbl = now - lastTap.t < 350 && Math.hypot(x - lastTap.x, y - lastTap.y) < 16;
    lastTap = { t: now, x: x, y: y };
    if (!cur.tool) { msg('Pick a front type first, then tap the map.'); return; }
    var p = unproj(geom, x, y);
    if (cur.tool === 'L') { cur.low = { lat: p.lat, lon: p.lon }; updateTools(); paint(); return; }
    if (dbl && cur.active) { if (cur.active.pts.length >= 2) finishFront(); return; }   // second tap of a double-tap ends the front
    if (!cur.active) cur.active = { type: cur.tool, pts: [] };
    cur.active.pts.push({ lat: p.lat, lon: p.lon });
    updateTools(); paint();
  }
  function undoPoint() {
    if (!cur || cur.submitted) return;
    if (!cur.active && cur.drawn.length) { cur.active = cur.drawn.pop(); cur.tool = cur.active.type; }
    if (cur.active) { cur.active.pts.pop(); if (!cur.active.pts.length) cur.active = null; }
    updateTools(); paint();
  }
  function delFront() {
    if (!cur || cur.submitted) return;
    if (cur.active) cur.active = null; else cur.drawn.pop();
    updateTools(); paint();
  }
  function clearAll() {
    if (!cur || cur.submitted) return;
    cur.active = null; cur.drawn = []; cur.low = null; cur.tool = null; updateTools(); paint();
  }
  function placeLow() {
    if (!cur || cur.submitted) return;
    if (cur.active) finishFront();
    cur.tool = cur.tool === 'L' ? null : 'L'; updateTools();
  }

  // ------------------------------------------------------------------ clock
  var tEnd = 0, lastTick = 0;
  function clearTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }
  function startTimer() {
    clearTimer();
    var on = $('useTimer').checked && TIMER_SECS > 0;
    $('pTimer').hidden = $('timerbar').hidden = !on;
    if (!on) return;
    tEnd = Date.now() + TIMER_SECS * 1000; lastTick = Date.now();
    var tick = function () {
      var now = Date.now();
      if (!$('drawer').hidden || $('play').hidden) { tEnd += now - lastTick; cur.paused = (cur.paused || 0) + now - lastTick; }   // paused while Stats is open
      lastTick = now;
      var left = Math.max(0, tEnd - now), s = Math.ceil(left / 1000);
      $('pTimer').textContent = s + ' s'; $('pTimer').classList.toggle('low', s <= 10); $('timerbar').classList.toggle('low', s <= 10);
      $('timerbar').firstElementChild.style.width = (left / (TIMER_SECS * 10)) + '%';
      if (left <= 0) { clearTimer(); submit(true); }
    };
    tick(); timerId = setInterval(tick, 200);
  }

  // ------------------------------------------------------------------ case flow
  function startCase(id) {
    clearTimer();
    var c = manifest.byId[id];
    cur = { c: c, id: id, data: null, drawn: [], active: null, low: null, tool: null, submitted: false, tabIdx: 0, t0: 0, paused: 0, triple: null, result: null };
    $('isoChk').checked = false; $('ascChk').checked = false; $('ascLbl').hidden = !c.ascat; $('showTruth').checked = true; $('showMine').checked = true;
    show('play'); buildTabs(); buildTools();
    $('drawPane').hidden = false; $('revealPane').hidden = true;
    $('mapLoad').hidden = false; $('mapLoad').textContent = 'Loading case...';
    $('pCase').textContent = 'Case ' + (stats.records.length + 1);
    $('pBasin').textContent = c.basin === 'npac' ? 'N Pacific' : 'N Atlantic';   // a deck without basin is the Atlantic one
    $('ringPrompt').hidden = !(c.sys_r_nm > 0);
    $('pTimer').hidden = $('timerbar').hidden = true;
    updateTools();
    var tok = cur;
    loadCase(id).then(function (d) {
      if (cur !== tok) return;
      cur.data = d; geom = makeGeom(c); sizeCanvas();
      $('mapLoad').hidden = true; setTab(0);
      cur.t0 = Date.now();
      if (c.img && manifest.encoding !== 'base64') loadImage(imgSrc(c));
      startTimer();
    }).catch(function (e) {
      $('mapLoad').textContent = 'Could not load this case (' + e.message + '). Tap Next.';
      $('drawPane').hidden = true; $('revealPane').hidden = false; $('result').innerHTML = ''; $('debrief').innerHTML = '';
    });
  }
  function fmtPct(v) { return Math.round(v) + '%'; }
  function submit(auto) {
    if (!cur || cur.submitted || !cur.data) return;
    if (cur.active && cur.active.pts.length >= 2) cur.drawn.push(cur.active);
    cur.active = null; cur.tool = null;
    clearTimer();
    cur.submitted = true;
    var secs = Math.max(0, (Date.now() - cur.t0 - cur.paused) / 1000);
    var res = scoreCase(cur.c, cur.drawn, cur.low);
    cur.result = res; cur.triple = triplePoint(cur.c);
    $('ringPrompt').hidden = true;
    stats.records.push({ pct: Math.round(res.pct * 10) / 10, t: Math.round(secs * 10) / 10, pairs: res.pairs, low: Math.round(res.low.credit * 100) / 100, extras: res.extras.length, auto: !!auto });
    saveStats(); updateTop();
    $('drawPane').hidden = true; $('revealPane').hidden = false;
    renderResult(res, auto, secs);
    paint();
    $('result').focus({ preventScroll: true });
  }
  function renderResult(res, auto, secs) {
    var cls = res.pct >= SCORE.PASS ? 'good' : res.pct >= 40 ? 'ok' : 'bad';
    var r = $('result'); r.className = 'result ' + cls;
    var unit = 100 / res.denom;
    var h = '<div class="bigpct">' + fmtPct(res.pct) + '</div><div class="rline">' + (auto ? 'Time up: submitted what you had. ' : '') + Math.round(secs) + ' s. Fronts ' + fmtPct(res.frontMax ? res.frontSum / res.frontMax * 100 : 0) + ' of what was available' + (SCORE.LOW_W ? ', low ' + fmtPct(res.low.credit * 100) : '') + '.</div>';
    h += '<table class="brk"><tr><th>Analysed</th><th>You drew</th><th class="n">Off</th><th class="n cov">Cover</th><th class="n">Pos</th><th>Type</th><th class="n">Points</th></tr>';
    res.rows.forEach(function (rw) {
      var sw = '<span class="sw" style="background:' + FT[rw.type].c + '"></span>';
      var pts = '<td class="n">' + (rw.earned * unit).toFixed(0) + ' / ' + (rw.max * unit).toFixed(0) + '</td>';
      if (!rw.matched) h += '<tr><td>' + sw + FT[rw.type].name + ' <span class="fine">' + Math.round(rw.len) + ' nm</span></td><td colspan="5" class="mis"><b>Missed</b> <span class="fine">(' + Math.round(rw.share * 100) + '% of the length' + (rw.nearness > 0.99 ? ', near the low' : '') + ')</span></td>' + pts + '</tr>';
      else {
        var tcTxt = rw.typeCred === 1 ? 'exact' : rw.typeCred > 0 ? 'half' : 'wrong';
        h += '<tr><td>' + sw + FT[rw.type].name + ' <span class="fine">' + Math.round(rw.len) + ' nm</span></td><td>' + FT[rw.drawnType].name + '</td><td class="n">' + Math.round(rw.dist) + ' nm</td><td class="n">' + Math.round(rw.cov * 100) + '%</td><td class="n">' + Math.round(rw.pos * 100) + '%</td><td>' + tcTxt + '</td>' + pts + '</tr>';
      }
    });
    if (SCORE.LOW_W) h += '<tr><td colspan="6">Low' + (res.low.dist === null ? ' <span class="fine">(not placed)</span>' : ' <span class="fine">' + Math.round(res.low.dist) + ' nm from the nearest analysed low</span>') + '</td><td class="n">' + (res.lowPts * unit).toFixed(0) + ' / ' + (SCORE.LOW_W * unit).toFixed(0) + '</td></tr>';
    if (res.extras.length) h += '<tr><td colspan="6">Extra drawn front' + (res.extras.length > 1 ? 's' : '') + ' in the ring with no analysed match (' + res.extras.map(function (i) { return FT[res.drawnDense[i].type].name.toLowerCase(); }).join(', ') + ')</td><td class="n">-' + (res.extraPen * unit).toFixed(0) + '</td></tr>';
    h += '</table><p class="fine">Only the fronts of the system in the ring are scored; troughs, other systems and fronts drawn outside the ring are not. Position is generous (full within ' + SCORE.POS_FULL_NM + ' nm, none at ' + SCORE.POS_ZERO_NM + '); type counts ' + SCORE.TYPE_W + 'x position and is scaled by it.</p>';
    r.innerHTML = h;
    var d = $('debrief'), types = [];
    cur.c.fronts.forEach(function (f) { if (isSys(f) && types.indexOf(f.type) < 0) types.push(f.type); });
    var nOther = cur.c.fronts.filter(function (f) { return !isSys(f); }).length;
    var dh = '<h3>What to look for in this case</h3>';
    types.forEach(function (t) { var hint = cur.c.hints && cur.c.hints[t]; if (hint) dh += '<div class="hintrow" style="--c:' + FT[t].c + '"><b>' + FT[t].name + '.</b> ' + hint + '</div>'; });
    if (cur.triple) dh += '<div class="hintrow" style="--c:#111"><b>Triple point</b> (ringed): occluded, cold and warm fronts meet here.</div>';
    dh += '<p class="fine">Analysts put a front on the warm edge of the temperature change and at the wind shift, so expect your line on that edge rather than in the middle of the theta-e gradient.</p>';
    dh += '<p class="fine">Thick outlined lines: the analysis (OPC / WPC / NHC) for the system in the ring. ' + (nOther ? 'Thin grey lines and L: other systems, not scored. ' : '') + 'Thinner coloured lines: yours. Red L: analysed low. Blue L: yours.</p>';
    d.innerHTML = dh;
  }
  function goHome() { clearTimer(); cur = null; show('start'); }
  function openStats() { $('statsBody').innerHTML = statsHTML(); $('drawer').hidden = false; }
  function closeStats() { $('drawer').hidden = true; }

  // ------------------------------------------------------------------ wiring
  function init() {
    $('clockSmall').textContent = TIMER_SECS + ' s a case. At zero, what you have drawn is submitted.';
    $('startBtn').addEventListener('click', function () { startCase(nextId()); });
    $('homeBtn').addEventListener('click', goHome);
    $('statsBtn').addEventListener('click', openStats);
    $('closeStats').addEventListener('click', closeStats);
    $('resetStats').addEventListener('click', function () { if (window.confirm('Clear all stats on this device?')) { stats.records = []; saveStats(); updateTop(); $('statsBody').innerHTML = statsHTML(); } });
    $('drawer').addEventListener('click', function (e) { if (e.target === $('drawer')) closeStats(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeStats(); });
    $('map').addEventListener('click', mapTap);
    $('finBtn').addEventListener('click', function () { if (cur && !cur.submitted) finishFront(); });
    $('undoBtn').addEventListener('click', undoPoint);
    $('delBtn').addEventListener('click', delFront);
    $('clrBtn').addEventListener('click', clearAll);
    $('lowBtn').addEventListener('click', placeLow);
    $('subBtn').addEventListener('click', function () { submit(false); });
    $('nextBtn').addEventListener('click', function () { startCase(nextId()); });
    $('ascChk').addEventListener('change', function () { if (cur) { updateCap(); buildLegend(TABS[cur.tabIdx], cur.c); renderBase(); } });
    $('isoChk').addEventListener('change', function () { if (cur) { buildLegend(TABS[cur.tabIdx], cur.c); renderBase(); } });
    $('showTruth').addEventListener('change', paint);
    $('showMine').addEventListener('change', paint);
    var rz = null;
    window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if (cur && cur.data) { sizeCanvas(); renderBase(); } }, 120); });
    updateTop();
    loadManifest().then(function () {
      if (!manifest.cases.length) throw new Error('empty deck');
      show('start');
    }).catch(function (e) {
      $('loadMsg').hidden = false; $('loadMsg').textContent = 'Could not load the deck (' + e.message + ').';
    });
  }
  function toClient(lat, lon) {   // for tests: geographic point -> page client coordinates
    var r = $('map').getBoundingClientRect(), q = proj(geom, lat, lon);
    return { x: r.left + q[0] * r.width / geom.cw, y: r.top + q[1] * r.height / geom.ch };
  }
  window.FD = { toClient: toClient, lonLabel: lonLabel, givenOf: givenOf, crSpline: crSpline, smoothGeo: smoothGeo, ringOf: ringOf, SCORE: SCORE, scoreCase: scoreCase, densify: densify, distNm: distNm, state: function () { return cur; }, stats: function () { return stats; } };
  init();
})();
