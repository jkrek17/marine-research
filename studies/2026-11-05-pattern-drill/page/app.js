/* Pattern drill: static page, plain JS + canvas. Reads deck/manifest.json and deck/<id>.bin
   (format in ../design.md). Session stats only. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ constants
  var CATS = ['None', 'Gale', 'Storm', 'HF'];
  var CAT_RANGE = ['<34 kt', '34-47', '48-63', '64+'];
  function catOf(kt) { return kt < 34 ? 0 : kt < 48 ? 1 : kt < 64 ? 2 : 3; }
  var CAT_OBS = ['quiet (under 34 kt)', 'gale', 'storm', 'HF'];
  var BLITZ_N = 10, BLITZ_SECS = 60, WEAK_MIN = 8;
  var RING_KM = 500;
  var SCENE = function () { return !!(manifest && manifest.truth === 'scene'); };   // answer = strongest wind in the whole box
  // Wind colours: rk/style.py WIND_LEVELS / WIND_COLORS / WIND_OVER (light-background version).
  var WIND_LEVELS = [0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80];
  var WIND_COLORS = ['#f4f6f8', '#dde6ef', '#c3d4e6', '#9fbbd9', '#7aa0c9', '#5683b5',
                     '#f7e68a', '#f2a93b', '#d4531f', '#9e1f1f', '#5c0f45'];   // 34+: same hues, wider lightness steps (colour-blind safe)
  var WIND_OVER = '#c86fd8';
  var LAND_RGB = [221, 224, 228];
  var LEVELS = [['Trainee', 0], ['Watch', 500], ['Gale', 1500], ['Storm', 3500], ['Hurricane Force', 7000]];
  var STORE_KEY = 'pdrill-session-1';
  var BENCH_KEY = 'pdrill-bench-2';   // version 2: Beat the model cases (version 1 runs were grow/hold/decay on other cases)
  var BENCH_OLD = 'pdrill-bench-1';   // localStorage: benchmark history, this device only
  var CH_NAMES = ['Decay', 'Hold', 'Grow'], CH_OBS = ['decayed', 'held', 'grew'];   // index = change + 1
  var NM_PER_KM = 1 / 1.852;

  function thkColor(v) {
    // blue at and below 540 dam, red above
    if (v <= 540) { var t = Math.max(0, Math.min(1, (v - 480) / 60)); return mix([24, 52, 150], [60, 130, 220], t); }
    var u = Math.max(0, Math.min(1, (v - 546) / 54)); return mix([228, 96, 44], [140, 16, 16], u);
  }
  function mix(a, b, t) { return 'rgb(' + [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * t); }).join(',') + ')'; }
  var f0 = function (v) { return String(Math.round(v)); };

  var TABS = [
    { id: 'msl', label: 'MSLP', name: 'MSLP + thickness',
      contours: [
        { key: 'thk', step: 6, dash: [5, 3], width: function (l) { return l === 540 ? 2.6 : 1.2; }, color: thkColor, label: true, fmt: f0, minGap: 150 },
        { key: 'msl', step: 4, width: function (l) { return l % 20 === 0 ? 1.8 : 1.1; }, color: '#111', label: true, fmt: f0, minGap: 120 }],
      legend: [{ title: 'Thickness 1000-500 mb (dam), dashed; 540 heavy', levels: [492, 504, 516, 528, 540, 552, 564, 576],
                 colors: [486, 498, 510, 522, 534, 546, 558, 570, 582].map(thkColor) }],
      note: 'Solid black: MSLP every 4 hPa.' },
    { id: 'z500', label: '500 mb', name: '500 mb heights + absolute vorticity',
      fill: { key: 'vort500', levels: [16, 20, 24, 28, 32, 40, 48],
              colors: [null, '#fff3b0', '#fedc6a', '#fdae43', '#f46d2f', '#d7301f', '#a50f4b', '#6a1b9a'] },
      contours: [{ key: 'z500', step: 6, width: 1.2, color: '#111', label: true, fmt: f0, minGap: 120 }],
      legend: [{ title: 'Absolute vorticity (1e-5 /s)', levels: [16, 20, 24, 28, 32, 40, 48] }],
      note: 'Black: 500 mb height every 6 dam.' },
    { id: 'jet', label: '250 mb jet', name: '250 mb jet (isotachs)',
      fill: { key: 'wspd250', levels: [70, 80, 90, 100, 110, 130, 150],
              colors: [null, '#c6dbef', '#9ecae1', '#6baed6', '#3b8bc9', '#2b5fa8', '#5b3fa0', '#8e24aa'] },
      contours: [{ key: 'z250', step: 12, width: 1.1, color: '#111', label: true, fmt: f0, minGap: 120 }],
      legend: [{ title: '250 mb wind speed (kt)', levels: [70, 80, 90, 100, 110, 130, 150] }],
      note: 'Black: 250 mb height every 12 dam.' },
    { id: 'eady', label: 'Eady growth', name: 'Eady growth rate (850-500 mb)',
      fill: { key: 'eady', levels: [0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0],
              colors: [null, '#e6f2e0', '#bfe3b4', '#fff1a8', '#fdc766', '#f58a3a', '#d7301f', '#8e1b6b'] },
      contours: [{ key: 'z500', step: 6, width: 0.8, color: 'rgba(30,30,30,.7)', label: false }],
      legend: [{ title: 'Eady growth rate (per day)', levels: [0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0] }],
      note: 'Thin: 500 mb height every 6 dam.' },
    { id: 'tadv', label: '850 advection', name: '850 mb temperature advection',
      fill: { key: 'tadv850', levels: [-8, -4, -2, -1, 1, 2, 4, 8],
              colors: ['#2b5fa8', '#4a85c6', '#86b4dc', '#c5dcf0', null, '#f5cdb0', '#e8935f', '#cf5a38', '#a8301f'] },
      contours: [
        { key: 't850', step: 5, dash: [5, 3], width: 1.2, color: '#8a3a12', label: true, fmt: f0, minGap: 150 },
        { key: 'z850', step: 3, width: 1.2, color: '#111', label: true, fmt: f0, minGap: 120 }],
      legend: [{ title: 'Temperature advection (K/day): blue cold, red warm; under 1 hidden', levels: [-8, -4, -2, -1, 1, 2, 4, 8] }],
      note: 'Black: 850 mb height every 3 dam. Dashed brown: 850 mb temperature every 5 C.' },
    { id: 'sstair', label: 'Sea - air', name: 'Sea minus air temperature',
      fill: { key: 'sst_air', levels: [-4, -2, 0, 2, 4, 6, 8, 12],
              colors: ['#2b5fa8', '#6a9bd1', '#c5dcf0', '#fbe0cc', '#f5b78c', '#e8814f', '#cf4a2e', '#a8301f', '#6e1410'] },
      contours: [{ key: 'msl', step: 4, width: 0.8, color: 'rgba(30,30,30,.65)', label: false }],
      legend: [{ title: 'Sea minus 2 m air (K): red = sea warmer, more mixing', levels: [-4, -2, 0, 2, 4, 6, 8, 12] }],
      note: 'Thin: MSLP every 4 hPa.' },
    { id: 'w925', label: '925 mb wind', name: '925 mb wind + low-level stability', needs: 'wspd925',
      fill: { key: 'wspd925', levels: [20, 25, 30, 34, 41, 48, 56, 64],
              colors: [null, '#9fbbd9', '#7aa0c9', '#5683b5', '#f7e68a', '#f2a93b', '#d4531f', '#9e1f1f', '#5c0f45'] },
      contours: [{ key: 'lapse925', step: 4, dash: [4, 3], width: 1.2, color: '#6a1b9a', label: true, fmt: f0, minGap: 150 },
                 { key: 'msl', step: 4, width: 0.8, color: 'rgba(30,30,30,.6)', label: false }],
      legend: [{ title: '925 mb wind speed (kt)', levels: [20, 25, 30, 34, 41, 48, 56, 64] }],
      note: 'Dashed purple: sea surface minus 925 mb temperature every 4 C (10+ = well mixed). Thin: MSLP every 4 hPa.' },
    { id: 'ir', label: 'IR', name: 'Infrared (11 \u00b5m)', sat: 'ir', legend: [],
      noData: 'No infrared for this time',
      note: 'Cold cloud tops white. Brightness temperature, 11 \u00b5m.' },
    { id: 'am', label: 'Air mass', name: 'GOES air-mass RGB', sat: 'am', legend: [],
      noData: 'No GOES view of this area at this time',
      note: 'Red-orange: dry, ozone-rich air from a lowered tropopause (the upper-level PV anomaly). Green: warm moist air mass. Blue/purple: cold air mass. White: thick high cloud.' }
  ];
  var HINTS = {"msl": "a low in a packed thickness gradient has fuel; a low cold all the way through, under a thickness trough, is occluded and usually filling.", "z500": "a vorticity max coming in from the W or SW with the surface low downstream means deepening; a 500 low stacked over the surface low means mature or weakening.", "jet": "the right entrance and left exit of a streak are the ascent quadrants; a low that has crossed to the cold side of the jet is usually done. No jet nearby, little support.", "eady": "1+ per day along the low's track means room for rapid growth; low values around it mean the baroclinic zone is used up.", "tadv": "strong warm advection ahead and cold behind, wrapped tight to the centre, means an active system; weak or symmetric means mature or decaying.", "w925": "the best single clue to the peak. Take the strongest 925 mb wind over water on the map and multiply by about 0.70 where the sea is under 2 C warmer than the 2 m air there, 0.79 at 2-5 C, 0.83 at 5 C or more (Sea - air tab). On the cases so far that gets the category right about 7 times in 10, as often as the models, and it reads HF far better than GFS. The 925 wind near the centre mixes down more than the strongest 925 on the map, which often sits over a stable sea.", "sstair": "a mixing cue, not a growth cue: air 5+ \u00b0C colder than the sea (red) mixes strong winds down, so cold-sector winds verify high; blue (stable) keeps them aloft.", "ir": "a comma, a dry slot and a cloud head wrapping back mean deepening; a ragged spiral with warming tops is an old low.", "am": "a red-orange dry intrusion behind the low marks the upper PV anomaly (white is cold cloud, not dry air). On its own it sorted growth weakly in our 916 lows; read it with the 500 mb vorticity."};
  var REVEAL_TAB = { id: 'reveal', label: 'ASCAT', name: 'ASCAT wind over MSLP', reveal: true };
  // Beat the model: each model's +24 h forecast maps (fc_deck.py); the 10 m wind tab is the model's own surface wind.
  var MODEL_NAMES = { gfs: 'GFS', ifs: 'ECMWF', r925: '925 \u00d7 stability' }, MODELS = ['gfs', 'ifs'], BENCH = MODELS.concat(['r925']);
  // The forecaster's shortcut (Jason 2026-11-06): strongest 925 mb wind on the map times a mixing factor from sea minus
  // 2 m air where that wind is. Map-wide factors (manifest.rule925 when the deck carries a refit, else these): the
  // strongest 925 anywhere runs well above ASCAT, more so over a stable sea. On the +24 h games it reads the GFS forecast maps.
  var RULE925 = { cuts: [2, 5], f: [0.70, 0.79, 0.83], top: 20 };
  function rule925(sn) {
    var R = (manifest && manifest.rule925) || RULE925, w = sn.f.wspd925, d = sn.f.sst_air, idx = [];
    if (!w || !d) return null;
    for (var i = 0; i < w.length; i++) if (!sn.land[i] && isFinite(w[i]) && isFinite(d[i])) idx.push(i);
    if (idx.length < 3) return null;
    idx.sort(function (a, b) { return w[b] - w[a]; });
    var top = idx.slice(0, R.top), dm = -99;
    top.forEach(function (i) { if (d[i] > dm) dm = d[i]; });
    var k = dm < R.cuts[0] ? 0 : dm < R.cuts[1] ? 1 : 2, kt = w[top[2]] * R.f[k];
    return { peak: kt, cat: catOf(kt), w925: w[top[2]], sea_air: dm, f: R.f[k] };
  }
  var W10_TAB = { id: 'w10', label: '10 m wind', name: 'Model 10 m wind',
    fill: { key: 'wspd10', levels: [20, 25, 30, 34, 41, 48, 56, 64],
            colors: [null, '#9fbbd9', '#7aa0c9', '#5683b5', '#f7e68a', '#f2a93b', '#d4531f', '#9e1f1f', '#5c0f45'] },
    contours: [{ key: 'msl', step: 4, width: 1.1, color: '#111', label: true, fmt: f0, minGap: 120 }],
    legend: [{ title: 'Model 10 m wind speed (kt); ASCAT is judged against this', levels: [20, 25, 30, 34, 41, 48, 56, 64] }],
    note: 'Black: MSLP every 4 hPa. Models usually run a few knots under ASCAT at the peak, more in cold air over warm sea.' };
  HINTS.w10 = "the model's own answer. Read it against the 925 mb wind and Sea - air tabs: strong 925 wind over a warm sea means ASCAT is likely to come in above it.";

  // ------------------------------------------------------------------ helpers
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function hexRGB(c) {
    if (!c) return null;
    var m = /^#([0-9a-f]{6})$/i.exec(c); var n = parseInt(m[1], 16);
    return [n >> 16 & 255, n >> 8 & 255, n & 255];
  }
  function rand(n) { return Math.floor(Math.random() * n); }

  // ------------------------------------------------------------------ session (in memory + sessionStorage)
  var session = { records: [], played: { now: {}, fc: {}, bm: {}, sh: {} } };
  try { var raw = window.sessionStorage.getItem(STORE_KEY); if (raw) { var s = JSON.parse(raw); if (s && s.records && s.played) session = s; } } catch (e) { /* storage may be blocked */ }
  session.pairs = session.pairs || []; session.played.pair = session.played.pair || {};
  function saveSession() { try { window.sessionStorage.setItem(STORE_KEY, JSON.stringify(session)); } catch (e) { /* ignore */ } }

  function score(c, o) {
    if (c < 0) return o === 3 ? -25 : 0;
    if (o === 3 && c < 3) return -25;
    if (c === o) return 100;
    if (c > o) return (c - o) === 1 ? 50 : 10;
    return (o - c) === 1 ? 25 : 0;
  }
  // Change call (forecast game): -1 decay, 0 hold, 1 grow, relative to the ASCAT category now. Same rule as the
  // ingredient statistics: the category moved AND the peak moved by the dead band (5 kt) or more; anything else is Hold.
  function deadBand() { return manifest && manifest.ingredients && manifest.ingredients.dead_band_kt || 5; }
  function obsChange(c) {
    var d = c.ing && c.ing.dpeak != null ? c.ing.dpeak : c.t24.peak - c.t0.peak, b = deadBand();
    if (c.t24.cat > c.t0.cat && d >= b) return 1;
    if (c.t24.cat < c.t0.cat && d <= -b) return -1;
    return 0;
  }
  // Right 60; wrong direction 0; Hold when it moved 15; moved when it held 25 (a missed growth costs more than a false alarm).
  function changeScore(call, obs) {
    if (call === null || call === undefined) return 0;
    if (call === obs) return 60;
    if (call === 0) return 15;
    if (obs === 0) return 25;
    return 0;
  }
  function isRight(r) { return r.chObs !== undefined ? r.chCalled === r.chObs : r.called === r.obs; }
  function levelFor(p) { var k = 0; for (var i = 0; i < LEVELS.length; i++) if (p >= LEVELS[i][1]) k = i; return k; }
  function totals(recs) {
    var t = { n: recs.length, exact: 0, within1: 0, pts: 0, time: 0, best: 0, cur: 0 };
    var run = 0;
    recs.forEach(function (r) {
      t.pts += r.pts; t.time += r.t;
      if (isRight(r)) { t.exact++; run++; if (run > t.best) t.best = run; } else run = 0;
      if (r.called >= 0 && Math.abs(r.called - r.obs) <= 1) t.within1++;
    });
    t.cur = run;
    return t;
  }
  function confusion(recs) {
    var m = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], un = 0;
    recs.forEach(function (r) { if (r.called < 0) un++; else m[r.called][r.obs]++; });
    return { m: m, un: un };
  }
  function readLine(conf) {
    var best = null, tot = [0, 0, 0, 0];
    for (var c = 0; c < 4; c++) for (var o = 0; o < 4; o++) { tot[o] += conf.m[c][o]; }
    for (c = 0; c < 4; c++) for (o = 0; o < 4; o++) {
      if (c === o) continue;
      if (!best || conf.m[c][o] > best.n) best = { c: c, o: o, n: conf.m[c][o] };
    }
    if (!best || best.n < 2) return 'No clear bias yet.';
    var lower = best.c < best.o;
    var sameObs = 0; for (c = 0; c < 4; c++) if (lower ? c < best.o : c > best.o) sameObs += conf.m[c][best.o];
    return 'You ' + (lower ? 'under-call ' : 'over-call ') + CAT_OBS[best.o] + ' cases (' + sameObs + ' of ' + tot[best.o] + ' called ' + (lower ? 'lower' : 'higher') + ').';
  }

  // ------------------------------------------------------------------ deck
  var manifest = null, fidx = {}, caseCache = {};
  function unitFix(f) {
    var u = (f.units || '').toLowerCase().replace(/\s+/g, '');
    var key = f.key;
    var mul = 1, add = 0;
    if (/^(z500|z250|z850|thk)$/.test(key) && (u === 'm' || u === 'gpm')) mul = 0.1;
    if (key === 'wspd250' && (u === 'm/s' || u === 'ms-1' || u === 'ms^-1')) mul = 1.94384;
    if (key === 'msl' && u === 'pa') mul = 0.01;
    if (key === 't850' && u === 'k') add = -273.15;
    return { mul: mul, add: add };
  }
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
  function parseBin(buf, nsnap) {
    nsnap = nsnap || 2;
    var ny = manifest.ny, nx = manifest.nx, n = ny * nx, nf = manifest.fields.length;
    var u8 = new Uint8Array(buf);
    var per = (nf + 3) * n;
    if (u8.length < nsnap * per) throw new Error('short .bin: ' + u8.length + ' < ' + nsnap * per);
    var snaps = [];
    for (var s = 0; s < nsnap; s++) {
      var base = s * per, snap = { f: {} };
      manifest.fields.forEach(function (f, k) {
        var fx = unitFix(f), a = new Float32Array(n), o = base + k * n;
        for (var i = 0; i < n; i++) { var b = u8[o + i]; a[i] = b === 255 ? NaN : (f.offset + f.scale * b) * fx.mul + fx.add; }
        snap.f[f.key] = a;
      });
      snap.spd = u8.subarray(base + nf * n, base + (nf + 1) * n);
      snap.dir = u8.subarray(base + (nf + 1) * n, base + (nf + 2) * n);
      var land = new Float32Array(n), lo = base + (nf + 2) * n;
      for (var q = 0; q < n; q++) land[q] = u8[lo + q] ? 1 : 0;
      snap.land = land;
      snaps.push(snap);
    }
    return snaps;
  }
  function loadCase(id) {
    if (caseCache[id]) return Promise.resolve(caseCache[id]);
    // A deck published where .bin is not served carries base64 text files instead (manifest "encoding").
    var b64 = manifest && manifest.encoding === 'base64';
    return fetch('deck/' + id + (b64 ? '.json' : '.bin')).then(function (r) {
      if (!r.ok) throw new Error(id + ' ' + r.status);
      return b64 ? r.text().then(function (t) {
        // {"bin": base64 of the .bin, "img": {"t0_ir": data URL, ...}}: one file per case
        var j = JSON.parse(t);
        satData[id] = j.img || {};
        if (j.fc) fcB64[id] = j.fc;
        var s = atob(j.bin), u = new Uint8Array(s.length);
        for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
        return u.buffer;
      }) : r.arrayBuffer();
    }).then(function (b) { var d = parseBin(b); caseCache[id] = d; return d; });
  }

  // A model forecast file is one snapshot in the same layout; its "ASCAT" layers hold the model's 10 m wind.
  var fcB64 = {}, fcCache = {};
  function b64buf(t) { var s = atob(t), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u.buffer; }
  function asFc(buf) {
    var sn = parseBin(buf, 1)[0], n = sn.spd.length, w = new Float32Array(n);
    for (var i = 0; i < n; i++) w[i] = sn.spd[i] === 255 ? NaN : sn.spd[i];
    sn.f.wspd10 = w; return sn;
  }
  function loadFc(c) {
    if (fcCache[c.id]) return Promise.resolve(fcCache[c.id]);
    var ms = MODELS.filter(function (m) { return c.fc && c.fc[m]; }), out = {};
    var b64 = manifest && manifest.encoding === 'base64';
    return Promise.all(ms.map(function (m) {
      if (b64) { var t = fcB64[c.id] && fcB64[c.id][m]; if (t) out[m] = asFc(b64buf(t)); return null; }
      return fetch('deck/' + c.id + '_fc_' + m + '.bin').then(function (r) { if (!r.ok) throw new Error(c.id + ' ' + m + ' ' + r.status); return r.arrayBuffer(); })
        .then(function (b) { out[m] = asFc(b); });
    })).then(function () { fcCache[c.id] = out; return out; });
  }
  function hasModel(c) { return !!(c.fc && c.fc.gfs); }

  var imgCache = {};
  function loadImage(url) {   // cached by url; resolves to an Image, or null if the file is missing
    if (!imgCache[url]) imgCache[url] = new Promise(function (res) {
      var im = new Image(); im.onload = function () { res(im); }; im.onerror = function () { res(null); }; im.src = url;
    });
    return imgCache[url];
  }
  var satData = {};   // base64 decks carry the images inside the case file
  function satUrl(c, snap, kind) {
    var d = satData[c.id];
    if (d && d[snap + '_' + kind]) return d[snap + '_' + kind];
    return 'deck/' + c.id + '_' + snap + '_' + kind + '.jpg';
  }

  // ------------------------------------------------------------------ case choice
  function pairsFor(game, c) {
    if (game === 'sh') {   // Storm or HF?: storm-force scenes only; analysis snapshots and +24 h forecast cases
      var o = [];
      ['t0', 't24'].forEach(function (k) { if (c[k] && c[k].cat >= 2) o.push({ c: c, snap: k, obs: c[k].cat, kind: 'now' }); });
      if (c.t0 && c.t24 && hasModel(c) && c.t24.cat >= 2) o.push({ c: c, snap: 't0', obs: c.t24.cat, kind: 'fc' });
      return o;
    }
    if (c.pool === 'hf') return [];   // extra storm-force cases are only for Storm or HF?, so the other games keep their mix
    if (game === 'fc') return (c.t0 && c.t24) ? [{ c: c, snap: 't0', obs: c.t24.cat }] : [];
    if (game === 'bm') return (c.t0 && c.t24 && hasModel(c)) ? [{ c: c, snap: 't0', obs: c.t24.cat }] : [];
    var out = [];
    // every snapshot in the deck already passed the builder's ASCAT coverage rule
    ['t0', 't24'].forEach(function (k) { if (c[k]) out.push({ c: c, snap: k, obs: c[k].cat }); });
    return out;
  }
  function weakestCat(recs) {
    var st = [0, 1, 2, 3].map(function () { return { n: 0, w: 0 }; });
    recs.forEach(function (r) { st[r.obs].n++; if (r.called !== r.obs) st[r.obs].w++; });
    var best = -1, bestRate = -1, bestW = -1;
    st.forEach(function (s, i) {
      if (s.n < 2) return;
      var rate = s.w / s.n;
      if (s.w > 0 && (rate > bestRate || (rate === bestRate && s.w > bestW))) { best = i; bestRate = rate; bestW = s.w; }
    });
    return best;
  }
  function pickCase(game, useWeak) {
    var played = session.played[game] || (session.played[game] = {});
    var pool = manifest.cases.filter(function (c) { return !played[c.id] && !benchSet[c.id] && pairsFor(game, c).length; });
    if (!pool.length) return null;
    var recs = session.records.filter(function (r) { return r.game === game && !r.skip; });
    if (useWeak && recs.length >= WEAK_MIN && Math.random() < 2 / 3) {
      var w = weakestCat(recs);
      if (w >= 0) {
        var cand = [];
        pool.forEach(function (c) { pairsFor(game, c).forEach(function (p) { if (p.obs === w) cand.push(p); }); });
        if (cand.length) return cand[rand(cand.length)];
      }
    }
    if (game === 'sh') {   // half analysis scenes, half +24 h forecast cases, while both last
      var items = [];
      pool.forEach(function (c) { items = items.concat(pairsFor(game, c)); });
      var want = Math.random() < 0.5 ? 'fc' : 'now', some = items.filter(function (p) { return p.kind === want; });
      if (!some.length) some = items;
      return some[rand(some.length)];
    }
    var c = pool[rand(pool.length)], ps = pairsFor(game, c);
    return ps[rand(ps.length)];
  }

  // ------------------------------------------------------------------ geometry
  function makeGeom(c) {
    var g = { nx: manifest.nx, ny: manifest.ny, res: manifest.res, lat0: c.lat0, lon0: c.lon0 };
    g.latc = c.lat0 - (g.ny - 1) * g.res / 2;
    g.aspect = ((g.nx - 1) * Math.cos(g.latc * Math.PI / 180)) / (g.ny - 1);  // width / height
    return g;
  }
  function proj(g, lat, lon) {
    var dl = (((lon - g.lon0) % 360) + 540) % 360 - 180;
    return [dl / g.res * g.cw / (g.nx - 1), (g.lat0 - lat) / g.res * g.ch / (g.ny - 1)];
  }

  function unproj(g, x, y) {   // canvas px (CSS) -> lat, lon
    return { lat: g.lat0 - y / g.ch * (g.ny - 1) * g.res, lon: (((g.lon0 + x / g.cw * (g.nx - 1) * g.res) % 360) + 360) % 360 };
  }
  function distKm(la1, lo1, la2, lo2) {
    var r = Math.PI / 180, dla = (la2 - la1) * r, dlo = (lo2 - lo1) * r;
    var a = Math.sin(dla / 2) * Math.sin(dla / 2) + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(dlo / 2) * Math.sin(dlo / 2);
    return 12742 * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  // The cell that sets the answer. Offline it is the 3rd-highest real-wind cell within 500 km that is nearer this low than
  // any other; here, the 3rd-highest valid ASCAT cell inside the 500 km ring (fewer than 3 cells: the lowest there is).
  function peakCell(g, snap, low) {
    // scene decks (version 2): the answer is the strongest wind anywhere in the box; the cell that set it comes with the case
    if (low.plat != null) return { s: low.peak, lat: low.plat, lon: low.plon < g.lon0 ? low.plon + 360 : low.plon };
    var cells = [];
    for (var j = 0; j < g.ny; j++) for (var i = 0; i < g.nx; i++) {
      var s = snap.spd[j * g.nx + i]; if (s === 255) continue;
      var la = g.lat0 - j * g.res, lo = g.lon0 + i * g.res;
      if (distKm(low.lat, low.lon, la, lo) <= RING_KM) cells.push({ s: s, lat: la, lon: lo });
    }
    if (!cells.length) return null;
    cells.sort(function (a, b) { return b.s - a.s; });
    return cells[Math.min(2, cells.length - 1)];
  }
  function median(a) { var s = a.slice().sort(function (x, y) { return x - y; }), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; }

  // ------------------------------------------------------------------ contouring (marching squares)
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
          var aroundB = (idx === 5) ? hiCentre === false : hiCentre === true;  // cut around b and d
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
    var lv = []; for (var L = Math.ceil(r[0] / spec.step) * spec.step; L <= r[1]; L += spec.step) lv.push(L);
    lv.forEach(function (L) {
      var segs = contourSegs(F, g.nx, g.ny, L);
      if (!segs.length) return;
      var col = typeof spec.color === 'function' ? spec.color(L) : spec.color;
      ctx.beginPath();
      segs.forEach(function (q) { ctx.moveTo(q[0] * sx, q[1] * sy); ctx.lineTo(q[2] * sx, q[3] * sy); });
      ctx.lineWidth = typeof spec.width === 'function' ? spec.width(L) : spec.width;
      ctx.strokeStyle = col; ctx.setLineDash(spec.dash || []); ctx.lineCap = 'round';
      ctx.stroke(); ctx.setLineDash([]);
      if (spec.label) {
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

  // ------------------------------------------------------------------ map drawing
  function bil(F, nx, ny, gx, gy) {
    var i = Math.min(Math.floor(gx), nx - 2), j = Math.min(Math.floor(gy), ny - 2);
    var fx = gx - i, fy = gy - j;
    var a = F[j * nx + i], b = F[j * nx + i + 1], c = F[(j + 1) * nx + i], d = F[(j + 1) * nx + i + 1];
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
  }
  function paintBase(canvas, ctx, g, snap, fill, dpr) {
    var Wd = canvas.width, Hd = canvas.height, nx = g.nx, ny = g.ny;
    var img = ctx.createImageData(Wd, Hd), px = img.data;
    var F = fill ? snap.f[fill.key] : null, rgb = fill ? fill.colors.map(hexRGB) : null, lv = fill ? fill.levels : null;
    var A = 0.82;
    for (var y = 0; y < Hd; y++) {
      var gy = (y + 0.5) / Hd * (ny - 1);
      for (var x = 0; x < Wd; x++) {
        var gx = (x + 0.5) / Wd * (nx - 1);
        var land = bil(snap.land, nx, ny, gx, gy) >= 0.5;
        var r = land ? LAND_RGB[0] : 255, gg = land ? LAND_RGB[1] : 255, b = land ? LAND_RGB[2] : 255;
        if (F) {
          var v = bil(F, nx, ny, gx, gy);
          if (v === v) {
            var k = 0; while (k < lv.length && v >= lv[k]) k++;
            var c = rgb[k];
            if (c) { r = r + (c[0] - r) * A; gg = gg + (c[1] - gg) * A; b = b + (c[2] - b) * A; }
          }
        }
        var o = (y * Wd + x) * 4; px[o] = r; px[o + 1] = gg; px[o + 2] = b; px[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
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
      var l = ((lo + 540) % 360) - 180;
      lab.push([l === 0 ? '0' : l < 0 ? -l + 'W' : l + 'E', x, g.ch - 8, 'center']);
    }
    ctx.restore();
    lab.forEach(function (t) {
      ctx.save(); ctx.textAlign = t[3]; ctx.textBaseline = 'middle'; ctx.font = '10px system-ui,sans-serif';
      ctx.lineJoin = 'round'; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.85)';
      var x = t[1]; if (t[3] === 'center') x = Math.max(12, Math.min(g.cw - 12, x));
      ctx.strokeText(t[0], x, t[2]); ctx.fillStyle = '#44505f'; ctx.fillText(t[0], x, t[2]); ctx.restore();
    });
  }
  function windColor(v) {
    if (v >= 80) return WIND_OVER;
    for (var k = WIND_LEVELS.length - 2; k >= 0; k--) if (v >= WIND_LEVELS[k]) return WIND_COLORS[k];
    return WIND_COLORS[0];
  }
  function drawAscat(ctx, g, snap) {
    var nx = g.nx, ny = g.ny, cx = g.cw / (nx - 1), cy = g.ch / (ny - 1);
    ctx.save();
    ctx.globalAlpha = 0.92;
    for (var j = 0; j < ny; j++) for (var i = 0; i < nx; i++) {
      var s = snap.spd[j * nx + i]; if (s === 255) continue;
      ctx.fillStyle = windColor(s);
      ctx.fillRect(i * cx - cx / 2, j * cy - cy / 2, cx + 0.6, cy + 0.6);
      if (s < 15) { ctx.strokeStyle = 'rgba(0,0,0,.07)'; ctx.lineWidth = 0.5; ctx.strokeRect(i * cx - cx / 2, j * cy - cy / 2, cx, cy); }
    }
    ctx.globalAlpha = 1;
    // thin dark outline round the >=48 kt and >=64 kt regions (shape cue that does not rely on colour)
    [[48, 1.2], [64, 2.2]].forEach(function (th) {
      ctx.beginPath();
      var hit = function (a, b) { if (a < 0 || b < 0 || a >= nx || b >= ny) return false; var v = snap.spd[b * nx + a]; return v !== 255 && v >= th[0]; };
      for (var jj = 0; jj < ny; jj++) for (var ii = 0; ii < nx; ii++) {
        if (!hit(ii, jj)) continue;
        var x0 = ii * cx - cx / 2, y0 = jj * cy - cy / 2;
        if (!hit(ii, jj - 1)) { ctx.moveTo(x0, y0); ctx.lineTo(x0 + cx, y0); }
        if (!hit(ii, jj + 1)) { ctx.moveTo(x0, y0 + cy); ctx.lineTo(x0 + cx, y0 + cy); }
        if (!hit(ii - 1, jj)) { ctx.moveTo(x0, y0); ctx.lineTo(x0, y0 + cy); }
        if (!hit(ii + 1, jj)) { ctx.moveTo(x0 + cx, y0); ctx.lineTo(x0 + cx, y0 + cy); }
      }
      ctx.lineWidth = th[1]; ctx.strokeStyle = '#111'; ctx.lineCap = 'butt'; ctx.setLineDash([]); ctx.stroke();
    });
    var step = Math.max(2, Math.ceil(14 / Math.min(cx, cy))), len = Math.min(step * cx * 0.75, 12);
    for (j = 0; j < ny; j += step) for (i = 0; i < nx; i += step) {
      var sp = snap.spd[j * nx + i], dr = snap.dir[j * nx + i];
      if (sp === 255 || dr === 255) continue;
      var to = (dr * 2 + 180) * Math.PI / 180, dx = Math.sin(to) * len, dy = -Math.cos(to) * len;
      var x = i * cx, y = j * cy, x1 = x + dx / 2, y1 = y + dy / 2, x0 = x - dx / 2, y0 = y - dy / 2;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.65)'; ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineWidth = 1.1; ctx.strokeStyle = '#1a1d21'; ctx.stroke();
      var ang = Math.atan2(dy, dx), h = 3.2;   // arrow head at the downwind end
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 - h * Math.cos(ang - 0.5), y1 - h * Math.sin(ang - 0.5));
      ctx.moveTo(x1, y1); ctx.lineTo(x1 - h * Math.cos(ang + 0.5), y1 - h * Math.sin(ang + 0.5));
      ctx.lineWidth = 1.1; ctx.stroke();
    }
    ctx.restore();
  }
  function drawRing(ctx, g, lat, lon, km) {
    ctx.save(); ctx.beginPath();
    for (var a = 0; a <= 360; a += 4) {
      var t = a * Math.PI / 180;
      var la = lat + km * Math.cos(t) / 111.2, lo = lon + km * Math.sin(t) / (111.2 * Math.cos(la * Math.PI / 180));
      var p = proj(g, la, lo); if (a === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
    }
    ctx.closePath(); ctx.lineWidth = 3.2; ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.setLineDash([]); ctx.stroke();
    ctx.lineWidth = 1.6; ctx.strokeStyle = '#7a0f6e'; ctx.setLineDash([6, 4]); ctx.stroke();
    ctx.restore();
    var p0 = proj(g, lat + km / 111.2, lon);
    halo(ctx, '500 km', p0[0], Math.max(9, p0[1] - 8), '600 10px system-ui,sans-serif', '#7a0f6e');
  }
  function drawLow(ctx, g, lat, lon) {
    var p = proj(g, lat, lon), r = Math.max(12, Math.min(16, g.cw / 28));
    ctx.save();
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.stroke();
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.lineWidth = 2.4; ctx.strokeStyle = '#d00018'; ctx.stroke();
    ctx.restore();
    halo(ctx, 'L', p[0], p[1] + 0.5, '800 ' + Math.round(r * 1.05) + 'px system-ui,sans-serif', '#d00018');
  }
  function drawTap(ctx, g, tap) {   // the trainee's tap: blue cross in a ring, white halo
    var p = proj(g, tap.lat, tap.lon);
    ctx.save(); ctx.lineCap = 'round'; ctx.setLineDash([]);
    [[5, 'rgba(255,255,255,.95)'], [2.2, '#0b4fa8']].forEach(function (s) {
      ctx.lineWidth = s[0]; ctx.strokeStyle = s[1];
      ctx.beginPath(); ctx.arc(p[0], p[1], 7, 0, 7); ctx.moveTo(p[0] - 12, p[1]); ctx.lineTo(p[0] + 12, p[1]); ctx.moveTo(p[0], p[1] - 12); ctx.lineTo(p[0], p[1] + 12); ctx.stroke();
    });
    ctx.restore();
    halo(ctx, 'you', p[0], Math.min(g.ch - 8, p[1] + 21), '700 11px system-ui,sans-serif', '#0b4fa8');
  }
  function drawPeak(ctx, g, pk, tap) {   // ring on the ASCAT cell that set the answer, line from the tap
    var p = proj(g, pk.lat, pk.lon), r = Math.max(8, g.cw / (g.nx - 1) * 1.1);
    ctx.save(); ctx.setLineDash([]); ctx.lineCap = 'round';
    if (tap) {
      var q = proj(g, tap.lat, tap.lon);
      ctx.beginPath(); ctx.moveTo(q[0], q[1]); ctx.lineTo(p[0], p[1]);
      ctx.lineWidth = 3.4; ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.stroke();
      ctx.lineWidth = 1.5; ctx.strokeStyle = '#0b4fa8'; ctx.setLineDash([4, 3]); ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.lineWidth = 5.5; ctx.strokeStyle = 'rgba(255,255,255,.95)'; ctx.stroke();
    ctx.lineWidth = 2.6; ctx.strokeStyle = '#000'; ctx.stroke();
    ctx.restore();
    halo(ctx, Math.round(pk.s) + ' kt', p[0], Math.max(9, p[1] - r - 9), '700 11px system-ui,sans-serif', '#000');
  }
  function drawTrack(ctx, g, a, b) {
    var p = proj(g, a.lat, a.lon), q = proj(g, b.lat, b.lon);
    var d = Math.hypot(q[0] - p[0], q[1] - p[1]); if (d < 4) return;
    var ux = (q[0] - p[0]) / d, uy = (q[1] - p[1]) / d, r = 14;
    var x0 = p[0] + ux * r, y0 = p[1] + uy * r, x1 = q[0] - ux * r, y1 = q[1] - uy * r;
    ctx.save();
    [[5, 'rgba(255,255,255,.9)'], [2.4, '#111']].forEach(function (s) {
      ctx.lineWidth = s[0]; ctx.strokeStyle = s[1]; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      var ang = Math.atan2(y1 - y0, x1 - x0), h = 9;
      ctx.beginPath(); ctx.moveTo(x1 - h * Math.cos(ang - 0.45), y1 - h * Math.sin(ang - 0.45)); ctx.lineTo(x1, y1);
      ctx.lineTo(x1 - h * Math.cos(ang + 0.45), y1 - h * Math.sin(ang + 0.45)); ctx.stroke();
    });
    ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, 7); ctx.fillStyle = '#111'; ctx.fill();
    ctx.restore();
    halo(ctx, 'now', p[0], p[1] + 13, '600 10px system-ui,sans-serif', '#111');
  }

  function renderSat(canvas, g, snap, tab, extra, img) {
    var dpr = g.dpr, ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#e8ebef'; ctx.fillRect(0, 0, g.cw, g.ch);
    if (!img) {
      ctx.fillStyle = '#44505f'; ctx.font = '600 15px system-ui,sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(tab.noData, g.cw / 2, g.ch / 2);
      drawGrid(ctx, g); drawLow(ctx, g, extra.low.lat, extra.low.lon);
      if (extra.tap) drawTap(ctx, g, extra.tap);
      return;
    }
    var cx = g.cw / (g.nx - 1), cy = g.ch / (g.ny - 1);   // image covers cell edges: half a cell beyond the centres
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, -cx / 2, -cy / 2, g.cw + cx, g.ch + cy);
    // coastline: outline of the land array only
    var segs = contourSegs(snap.land, g.nx, g.ny, 0.5), sx = cx, sy = cy;
    ctx.beginPath();
    segs.forEach(function (q) { ctx.moveTo(q[0] * sx, q[1] * sy); ctx.lineTo(q[2] * sx, q[3] * sy); });
    ctx.lineWidth = 0.9; ctx.strokeStyle = 'rgba(15,20,30,.85)'; ctx.setLineDash([]); ctx.stroke();
    drawGrid(ctx, g);
    var none = [];
    [[{ step: 8, width: 3.2, color: 'rgba(0,0,0,.55)' }], [{ step: 8, width: 1.1, color: 'rgba(255,255,255,.95)' }]].forEach(function (sp) {
      drawContours(ctx, g, snap.f.msl, sp[0], none);
    });
    drawLow(ctx, g, extra.low.lat, extra.low.lon);
    if (extra.tap) drawTap(ctx, g, extra.tap);
  }
  function renderMap(canvas, g, snap, tab, extra) {
    var dpr = g.dpr, ctx = canvas.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    paintBase(canvas, ctx, g, snap, tab.reveal ? null : tab.fill, dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawGrid(ctx, g);
    var labels = [];
    if (tab.reveal) {
      drawAscat(ctx, g, snap);
      drawContours(ctx, g, snap.f.msl, { step: 4, width: function (l) { return l % 20 === 0 ? 1.5 : 1; }, color: 'rgba(0,0,0,.82)', label: true, fmt: f0, minGap: 120 }, labels);
      if (!SCENE()) drawRing(ctx, g, extra.low.lat, extra.low.lon, RING_KM);
      if (extra.track) drawTrack(ctx, g, extra.track[0], extra.track[1]);
      drawLow(ctx, g, extra.low.lat, extra.low.lon);
      if (extra.peak) drawPeak(ctx, g, extra.peak, extra.tap);
      if (extra.tap) drawTap(ctx, g, extra.tap);
    } else {
      tab.contours.forEach(function (c) { if (snap.f[c.key]) drawContours(ctx, g, snap.f[c.key], c, labels); });
      if (extra.low) drawLow(ctx, g, extra.low.lat, extra.low.lon);
      if (extra.tap) drawTap(ctx, g, extra.tap);
    }
  }

  // ------------------------------------------------------------------ legend
  function buildLegend(tab, boxEl) {
    var box = boxEl || $('legend'); box.innerHTML = '';
    if (tab.reveal) {
      var lg = el('div', 'lg'); lg.appendChild(el('div', 'lgt', 'ASCAT 10 m wind (kt); ticks show direction the wind blows toward'));
      var bar = el('div', 'lgbar');
      var lv = WIND_LEVELS.slice(1);
      WIND_COLORS.concat([WIND_OVER]).forEach(function (c, i) {
        var d = el('div'); d.style.background = c;
        if (i >= 1 && i <= lv.length) d.appendChild(el('span', null, String(WIND_LEVELS[i])));
        bar.appendChild(d);
      });
      lg.appendChild(bar); box.appendChild(lg);
      box.appendChild(el('div', 'lgnote', 'Thin black outline: 48 kt and over; thick black outline: 64 kt and over. Black contours: MSLP every 4 hPa. ' + (SCENE() ? 'The answer is the strongest wind anywhere on the map (the 3rd-highest cell, so one stray cell does not set it); it is ringed.' : 'Dashed ring: 500 km around the low. The peak counts only cells inside it that are nearer this low than any other, and is the 3rd-highest cell, so one stray cell does not set it.') + ' Rain-flagged cells are left out.'));
      return;
    }
    tab.legend.forEach(function (L) {
      var lg = el('div', 'lg'); lg.appendChild(el('div', 'lgt', L.title));
      var bar = el('div', 'lgbar'), cols = L.colors || tab.fill.colors;
      cols.forEach(function (c, i) {
        var d = el('div', c ? '' : 'none'); if (c) d.style.background = c;
        if (i >= 1) d.appendChild(el('span', null, String(L.levels[i - 1])));
        bar.appendChild(d);
      });
      lg.appendChild(bar); box.appendChild(lg);
    });
    if (tab.note) box.appendChild(el('div', 'lgnote', tab.note));
  }

  // ------------------------------------------------------------------ game state / UI
  var opts = { game: 'now', mode: 'practice', weak: false, hints: true };
  try { if (window.sessionStorage.getItem('pdrill-hints') === '0') opts.hints = false; } catch (e) { /* ignore */ }
  var lastEnd = 'blitz', bench = null, benchIds = null, benchSet = {};
  var cur = null, blitz = null, geom = null, tabIdx = 0, tabList = TABS, timerId = null;

  var lastScreen = 'start';
  function show(id) {
    if (id !== 'ingr') lastScreen = id;
    ['start', 'play', 'end', 'ingr'].forEach(function (s) { $(s).hidden = s !== id; });
    $('loadMsg').hidden = true;
    $('leaveBanner').hidden = true;
    window.scrollTo(0, 0);
    syncTimer();
  }
  function focusPlay() {   // keyboard focus: the result once answered, else the first answer button
    var t = cur && cur.answered && !$('result').hidden ? $('result') : $('answers').querySelector('.ans:not(:disabled)');
    if (t && !t.closest('[hidden]')) { try { t.focus({ preventScroll: true }); } catch (e) { t.focus(); } }
  }
  function chromeH() {   // sticky header (+ sticky map tabs on narrow screens)
    var h = document.querySelector('header.top').offsetHeight;
    if (window.innerWidth <= 720) h += $('tabs').offsetHeight;
    return h;
  }
  function updateTop() {
    var t = totals(session.records);
    $('topPts').textContent = t.pts + ' pts';
  }
  function setupChoice(id, key) {
    var g = $(id);
    g.addEventListener('click', function (e) {
      var b = e.target.closest('.opt'); if (!b) return;
      [].forEach.call(g.querySelectorAll('.opt'), function (o) { var on = o === b; o.classList.toggle('on', on); o.setAttribute('aria-checked', on); });
      opts[key] = b.dataset.v;
    });
  }

  function availTabs() {   // a tab whose field is not in this deck (an older build) is left out
    var have = {}; (manifest && manifest.fields || []).forEach(function (f) { have[f.key] = 1; });
    return TABS.filter(function (t) { return !t.needs || have[t.needs]; });
  }
  function bmTabs(src) { return src === 'now' ? availTabs() : [W10_TAB].concat(availTabs().filter(function (t) { return !t.sat; })); }
  function buildSrc() {   // Beat the model: which maps the tabs show (each model's +24 h, or the analysis now)
    var bar = $('srcbar');
    if (!bar) { bar = el('div', 'srcbar'); bar.id = 'srcbar'; bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Maps from'); $('tabs').parentNode.insertBefore(bar, $('tabs')); }
    bar.hidden = !(cur && cur.fcLike);
    if (bar.hidden) return;
    bar.innerHTML = '';
    var srcs = MODELS.filter(function (m) { return cur.c.fc && cur.c.fc[m]; }).map(function (m) { return [m, MODEL_NAMES[m] + ' +24 h']; }).concat([['now', 'Analysis now']]);
    srcs.forEach(function (x) {
      var b = el('button', 'src' + (cur.src === x[0] ? ' on' : ''), x[1]); b.type = 'button'; b.setAttribute('aria-pressed', cur.src === x[0]);
      b.addEventListener('click', function () { setSrc(x[0]); });
      bar.appendChild(b);
    });
    if (!(cur.c.fc && cur.c.fc.ifs)) bar.appendChild(el('span', 'srcnote', 'No ECMWF for this case (not in the open archive)'));
  }
  function setSrc(src) {
    if (!cur || cur.src === src) return;
    var id = tabList[tabIdx] && tabList[tabIdx].id;
    cur.src = src; buildSrc();
    if (cur.answered) return draw();
    tabList = bmTabs(src); buildTabs();
    var k = tabList.map(function (t) { return t.id; }).indexOf(id);
    setTab(k < 0 ? 0 : k);
  }
  function buildTabs() {
    var t = $('tabs'); t.innerHTML = '';
    tabList.forEach(function (tb, i) {
      var b = el('button', 'tab' + (tb.reveal ? ' reveal' : ''), tb.label);
      b.type = 'button'; b.setAttribute('role', 'tab'); b.dataset.i = i;
      b.addEventListener('click', function () { setTab(i); });
      t.appendChild(b);
    });
  }
  function setTab(i) {
    tabIdx = (i + tabList.length) % tabList.length;
    [].forEach.call($('tabs').children, function (b, k) {
      b.classList.toggle('on', k === tabIdx); b.setAttribute('aria-selected', k === tabIdx);
      if (k === tabIdx && b.scrollIntoView) { try { b.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) { /* old browsers */ } }
    });
    draw();
  }
  function sizeCanvas() {
    if (!geom) return;
    var box = $('mapbox'), avail = $('mapbox').parentNode.clientWidth;
    var w = avail;
    if (window.innerWidth >= 900) w = Math.min(avail, Math.max(320, (window.innerHeight - 250) * geom.aspect));
    w = Math.floor(w);
    var h = Math.round(w / geom.aspect), dpr = Math.min(window.devicePixelRatio || 1, 2);
    geom.cw = w; geom.ch = h; geom.dpr = dpr;
    var cv = $('map'); cv.style.width = w + 'px'; cv.style.height = h + 'px';
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    box.style.width = w + 'px';
  }
  function draw() {
    if (!cur || !cur.data) return;
    var tab = tabList[tabIdx];
    var bm = cur.fcLike, model = bm && !tab.reveal && cur.src !== 'now' && !tab.sat;
    $('cap').textContent = (model ? MODEL_NAMES[cur.src] + ' +24 h forecast: ' : bm && !tab.reveal ? 'Analysis now: ' : '') + tab.name + (tab.reveal && (cur.game === 'fc' || bm) ? ' (+24 h)' : '');
    buildLegend(tab);
    var hb = $('hint'); hb.hidden = !(opts.hints && !cur.bench && !tab.reveal && HINTS[tab.id]);
    hb.textContent = hb.hidden ? '' : 'Look for: ' + HINTS[tab.id];
    if (model) {
      var fs = cur.fcData && cur.fcData[cur.src];
      if (!fs) return;
      return renderMap($('map'), geom, fs, tab, { low: null, tap: null });
    }
    var later = (cur.game === 'fc' || bm) && tab.reveal;
    var snapIdx = later ? 1 : (cur.snap === 't24' && (cur.game === 'now' || (cur.game === 'sh' && !cur.fcLike)) ? 1 : 0);
    var info = later ? cur.c.t24 : cur.c[cur.snap];
    var extra = { low: info, tap: cur.tap || null };
    if (tab.reveal && cur.peak) extra.peak = cur.peak;
    if (later) extra.track = [cur.c.t0, cur.c.t24];
    if (tab.sat) {
      var token = cur, tg = geom;
      if (!cur.c[cur.snap][tab.sat]) { renderSat($('map'), geom, cur.data[snapIdx], tab, extra, null); return; }
      loadImage(satUrl(cur.c, cur.snap, tab.sat)).then(function (img) {
        if (cur !== token || geom !== tg || tabList[tabIdx] !== tab) return;
        renderSat($('map'), geom, cur.data[snapIdx], tab, extra, img);
      });
      return;
    }
    renderMap($('map'), geom, cur.data[snapIdx], tab, extra);
  }

  function startGame() {
    $('startMsg').textContent = '';
    lastEnd = 'blitz'; bench = null;
    blitz = opts.mode === 'blitz' ? { n: 0, recs: [] } : null;
    tabList = availTabs();
    show('play');
    nextCase();
  }
  function startBench() {   // fixed 20 Beat the model cases, no hints, no feedback until the summary
    if (!benchIds || !benchIds.length) return;
    $('startMsg').textContent = '';
    lastEnd = 'bench'; blitz = null;
    bench = { n: 0, ids: benchIds.slice(), recs: [], t: Date.now() };
    tabList = availTabs();
    show('play');
    nextCase();
  }
  function nextCase() {
    clearTimer();
    if (blitz && blitz.n >= BLITZ_N) return endBlitz();
    if (bench && bench.n >= bench.ids.length) return endBench();
    var pick = bench ? { c: manifest.byId[bench.ids[bench.n]], snap: 't0' } : pickCase(opts.game, opts.weak);
    if (!pick) {
      $('startMsg').textContent = 'You have seen every case in this game this session. Pick the other game or close the tab to reset.';
      if (blitz && blitz.recs.length) return endBlitz();
      goHome(); return;
    }
    var game = bench ? 'bm' : opts.game, fcLike = game === 'bm' || (game === 'sh' && pick.kind === 'fc');
    cur = { game: game, c: pick.c, snap: pick.snap, data: null, answered: false, t0: 0, bench: !!bench, stage: game === 'fc' ? 'change' : null, chCalled: null, tap: null, peak: null,
            src: fcLike ? 'gfs' : null, fcData: null, kind: pick.kind || null, fcLike: fcLike };
    if (!bench) { (session.played[opts.game] = session.played[opts.game] || {})[pick.c.id] = 1; saveSession(); }
    tabList = fcLike ? bmTabs('gfs') : availTabs(); buildTabs(); buildSrc();
    $('result').hidden = true; $('debrief').hidden = true; $('nextBtn').hidden = true; $('answers').hidden = false;
    $('mapLoad').hidden = false; $('mapLoad').textContent = 'Loading case...';
    var played = session.records.filter(function (r) { return r.game === opts.game; }).length;
    $('pCase').textContent = bench ? 'Benchmark ' + (bench.n + 1) + ' of ' + bench.ids.length : blitz ? 'Case ' + (blitz.n + 1) + ' of ' + BLITZ_N : 'Case ' + (played + 1);
    $('pGame').textContent = game === 'now' ? 'Right now' : game === 'bm' ? 'Beat the model' : game === 'sh' ? 'Storm or HF?' + (fcLike ? ' (+24 h)' : '') : 'Forecast +24 h';
    $('pBasin').textContent = pick.c.basin === 'natl' ? 'N Atlantic' : pick.c.basin === 'npac' ? 'N Pacific' : pick.c.basin;
    $('timerbar').hidden = $('pTimer').hidden = !blitz;
    buildQuestion();
    window.scrollTo(0, 0); focusPlay();
    var token = cur;
    Promise.all([loadCase(pick.c.id), fcLike ? loadFc(pick.c) : null]).then(function (both) {
      var d = both[0];
      if (cur !== token) return;
      cur.data = d; cur.fcData = both[1]; geom = makeGeom(pick.c); sizeCanvas();
      $('mapLoad').hidden = true; setTab(0);
      cur.t0 = Date.now();
      if (blitz) startTimer();
      ['ir', 'am'].forEach(function (k) { if (pick.c[pick.snap][k]) loadImage(satUrl(pick.c, pick.snap, k)); });
    }).catch(function (e) {
      $('mapLoad').textContent = 'Could not load this case (' + e.message + '). Tap Next.';
      $('nextBtn').hidden = false; $('answers').hidden = true;
      cur.failed = true; if (bench) bench.n++; $('nextBtn').focus({ preventScroll: true });
    });
  }
  function buildQuestion() {
    var now = cur.game === 'now', bm = cur.fcLike, fc = cur.game === 'fc', st = cur.stage, sh = cur.game === 'sh';
    $('question').textContent = sh ? (bm ? 'ASCAT 24 h from now shows at least storm force on this map. Storm or HF?' : 'ASCAT shows at least storm force on this map. Storm or HF?')
      : now ? 'Tap where the strongest wind is, then pick the category.'
      : bm ? 'What will ASCAT show 24 h from now? (strongest wind anywhere on the map)'
      : st === 'change' ? 'Will the peak wind grow, hold or decay over the next 24 h?' : 'Optional: which category in 24 h?';
    var nl = $('nowline');
    if (bm) {
      var t0 = cur.c.t0, ms = MODELS.filter(function (m) { return cur.c.fc[m] && cur.c.fc[m].peak != null; });
      nl.hidden = false;
      nl.innerHTML = 'ASCAT now: <b>' + CATS[t0.cat] + '</b> (' + Math.round(t0.peak) + ' kt).<br>Strongest +24 h model wind on the map: ' +
        ms.map(function (m) { var f = cur.c.fc[m]; return MODEL_NAMES[m] + ' <b>' + Math.round(f.peak) + ' kt</b> (' + CATS[f.cat] + ')'; }).join(' &middot; ') + '.';
    } else if (fc) { var t = cur.c.t0; nl.hidden = false; nl.textContent = 'ASCAT now: ' + CATS[t.cat] + ' (' + Math.round(t.peak) + ' kt)' + (st === 'change' ? '. Under ' + deadBand() + ' kt of change counts as Hold.' : '. You called ' + CH_NAMES[cur.chCalled + 1] + '.'); } else nl.hidden = true;
    $('catNote').hidden = sh || !(now ? session.records.length === 0 : st === 'cat' && !cur.bench && session.records.length < 3);   // legend note early in a session
    $('tapNote').hidden = !(now && !cur.answered);
    $('mapbox').classList.toggle('tappable', now && !cur.answered);
    updateTapNote();
    renderAnswers();
  }
  function renderAnswers() {
    var a = $('answers'); a.innerHTML = ''; a.hidden = false;
    if (cur.game === 'sh') {
      a.className = 'answers ch2';
      [[2, 'Storm'], [3, 'HF']].forEach(function (x, i) {
        var b = el('button', 'ans', '<b>' + x[1] + ' <kbd>' + (i + 1) + '</kbd></b><span>' + CAT_RANGE[x[0]] + '</span>');
        b.type = 'button'; b.dataset.c = x[0]; b.addEventListener('click', function () { answer(x[0]); });
        a.appendChild(b);
      });
      return;
    }
    var s0 = cur.c.t0.cat;
    if (cur.game === 'fc' && cur.stage === 'change') {
      a.className = 'answers ch3';
      var bd = deadBand();
      [[1, 'Grow', 'up ' + bd + '+ kt'], [0, 'Hold', 'within ' + bd + ' kt'], [-1, 'Decay', 'down ' + bd + '+ kt']].forEach(function (x, i) {
        var b = el('button', 'ans', '<b>' + x[1] + ' <kbd>' + (i + 1) + '</kbd></b><span>' + x[2] + '</span>');
        b.type = 'button'; b.dataset.ch = x[0];
        if ((x[0] === 1 && s0 === 3) || (x[0] === -1 && s0 === 0)) {
          b.disabled = true; b.title = x[0] === 1 ? 'A low already at HF cannot grow a category' : 'A low below gale cannot decay a category';
          b.querySelector('span').textContent = 'not possible';
        }
        b.addEventListener('click', function () { changeCall(x[0]); });
        a.appendChild(b);
      });
      return;
    }
    a.className = 'answers' + (cur.game === 'fc' ? ' cat5' : '');
    ['None', 'Gale', 'Storm', 'HF'].forEach(function (n, i) {
      var b = el('button', 'ans', '<b>' + n + ' <kbd>' + (i + 1) + '</kbd></b><span>' + CAT_RANGE[i] + '</span>');
      b.type = 'button'; b.dataset.c = i; b.addEventListener('click', function () { answer(i); });
      a.appendChild(b);
    });
    if (cur.game === 'fc') {
      var sk = el('button', 'ans skip', '<b>Skip <kbd>5</kbd></b><span>no category</span>');
      sk.type = 'button'; sk.addEventListener('click', function () { answer(-1, 'skip'); });
      a.appendChild(sk);
    }
  }
  function changeCall(v) {   // forecast game, first tap: the change call; the category is an optional second tap
    if (!cur || cur.answered || !cur.data || cur.stage !== 'change') return;
    var s0 = cur.c.t0.cat;
    if ((v === 1 && s0 === 3) || (v === -1 && s0 === 0)) return;
    cur.chCalled = v; cur.stage = 'cat';
    buildQuestion(); focusPlay();
  }
  function updateTapNote() {
    var n = $('tapNote'); if (n.hidden) return;
    n.innerHTML = cur.tap ? 'Tap placed. Tap the map again to move it, or <button type="button" class="linkbtn" id="tapClear">clear it</button>. Then pick the category.'
      : 'Optional: tap the map where you think the strongest wind is. You can also just pick the category.';
  }
  function mapTap(e) {
    if (!cur || cur.game !== 'now' || cur.answered || !cur.data || !geom) return;
    var r = $('map').getBoundingClientRect();
    var x = (e.clientX - r.left) * geom.cw / r.width, y = (e.clientY - r.top) * geom.ch / r.height;
    var p = unproj(geom, x, y); cur.tap = { lat: p.lat, lon: p.lon };
    updateTapNote(); draw();
  }

  // Blitz clock: timerLeft = ms remaining (null = no clock). It runs only while the play screen is
  // showing with no drawer or leave-banner over it (syncTimer); paused time is not charged to the case.
  var timerLeft = null, timerEnd = 0, pausedAt = 0;
  function tickTimer() {
    var left = Math.max(0, timerEnd - Date.now()), s = Math.ceil(left / 1000), bar = $('timerbar'), tm = $('pTimer');
    timerLeft = left;
    tm.textContent = s + ' s'; tm.classList.toggle('low', s <= 10); bar.classList.toggle('low', s <= 10);
    bar.firstElementChild.style.width = (left / (BLITZ_SECS * 10)) + '%';
    if (left <= 0) { clearTimer(); answer(-1, 'time'); }
  }
  function startTimer() { timerLeft = BLITZ_SECS * 1000; pausedAt = Date.now(); syncTimer(); }
  function clearTimer() { if (timerId) { clearInterval(timerId); timerId = null; } timerLeft = null; }
  function syncTimer() {
    var go = blitz && cur && cur.data && !cur.answered && timerLeft !== null && $('drawer').hidden && $('leaveBanner').hidden && !$('play').hidden;
    if (go && !timerId) {
      if (cur.t0 && pausedAt) cur.t0 += Date.now() - pausedAt;
      timerEnd = Date.now() + timerLeft; tickTimer();
      if (timerLeft !== null) timerId = setInterval(tickTimer, 200);
    } else if (!go && timerId) {
      clearInterval(timerId); timerId = null; timerLeft = Math.max(0, timerEnd - Date.now()); pausedAt = Date.now();
    }
  }

  // ------------------------------------------------------------------ ingredients
  // Statistics from score_ingredients.py (version 2): every comparison is within the starting category,
  // growth and decay have their own signals, changes under the dead band (5 kt) count as held.
  var IMEANS = {
    eady: 'How fast the baroclinic zone near the low can build it (850-500 mb Eady rate, upper part of the 500 km disc).',
    jet: 'Strongest 250 mb wind within 1000 km.',
    pva: 'Upper vorticity coming in over the low (500 mb vorticity advection): forcing for ascent.',
    tilt: 'Distance from the surface low to the 500 mb vorticity maximum. Small = stacked under the upper low (mature). Large = the upper trough is still upstream.',
    warm_adv: 'Warm advection at 850 mb near the low.',
    thk_grad: 'Thickness gradient near the low: how sharp the baroclinic zone is.',
    sea_air: 'Sea minus air temperature: cold air over warm sea mixes strong winds down.',
    dry: 'Dry upper air (red/orange, not white cloud) on the rear side of the low in the air-mass image.',
    wind925: 'Strongest 925 mb wind over water near the low (upper part of the 500 km disc): the wind waiting to mix down.',
    dp_prev: 'Central pressure change in the 12 h before (negative = deepening). Not on the maps; on the desk you would have the previous analysis.'
  };
  var SNAME = ['none', 'gale', 'storm', 'HF'], LEVEL = ['low', 'middling', 'high'];
  function nf(v) { var x = Math.abs(v); return String(parseFloat(v.toFixed(x < 2 ? 2 : x < 10 ? 1 : 0))); }
  function ingStats() { return manifest && manifest.ingredients && manifest.ingredients.version >= 2 ? manifest.ingredients : null; }
  function sig(s) { return s && s.verdict !== 'none'; }
  function ingLean(it, t, c0) {   // 1 growth, -1 decay, 0 no lean: a real signal AND this start category's own record agrees
    var M = ingStats(), sname = SNAME[c0], b = it.bars[sname], br = M.by_start[sname];
    if (!b || b.grow[t] == null || t === 1) return 0;
    var g = b.grow[t], d = b.decay[t], gs = sig(it.grow), ds = sig(it.decay);
    var upG = c0 < 3 && gs && g >= br.grew + 3, upD = c0 > 0 && ds && d >= br.decayed + 3;
    var lowG = c0 === 3 || g <= br.grew, lowD = c0 === 0 || d <= br.decayed;
    if (upG && lowD) return 1;
    if (upD && lowG) return -1;
    if (c0 === 0 && gs && g <= br.grew - 5) return -1;   // a weak low cannot decay a category: this reads as "against growth"
    return 0;
  }
  function startWord(c) { return c === 0 ? 'below gale' : 'at ' + SNAME[c]; }
  function debriefHTML() {
    var c = cur.c, ing = c.ing, M = ingStats();
    if (!ing || !M) return '';
    var c0 = c.t0.cat, sname = SNAME[c0];
    if (cur.game === 'fc') {
      var c1 = c.t24.cat, dpk = ing.dpeak, rows = '';
      var held = c1 !== c0 && Math.abs(dpk) < M.dead_band_kt;
      var out = 'Observed: <b>' + CH_OBS[obsChange(c) + 1] + '</b>. ASCAT peak ' + Math.round(c.t0.peak) + ' to ' + Math.round(c.t24.peak) + ' kt (' + (dpk >= 0 ? '+' : '') + Math.round(dpk) + ' kt).';
      if (held) out += ' It crossed a category line by less than ' + M.dead_band_kt + ' kt: borderline, close to ASCAT noise.';
      var br = M.by_start[sname], ch = '';
      if (ing.p_grow != null && c0 < 3) ch += '<b>' + ing.p_grow + '%</b> chance of growing';
      if (ing.p_decay != null && c0 > 0) ch += (ch ? ', ' : '') + '<b>' + ing.p_decay + '%</b> of decaying';
      var base = 'Lows starting ' + startWord(c0) + ': ' + Math.round(br.grew) + '% grew, ' + Math.round(br.decayed) + '% decayed, ' + Math.round(br.same_cat) + '% stayed ' + sname + '.';
      M.ingredients.forEach(function (it) {
        if ((!sig(it.grow) && !sig(it.decay)) || !ing[it.key]) return;
        var v = ing[it.key], t = v[1], f = ingLean(it, t, c0), b = it.bars[sname];
        var like = b && b.grow[t] != null ? sname + ' lows like this: ' + Math.round(b.grow[t]) + '% grew' + (c0 > 0 ? ', ' + Math.round(b.decay[t]) + '% decayed' : '') : '';
        rows += '<div class="drow"><span class="nm">' + it.name + '</span><span class="vl">' + nf(v[0]) + ' ' + it.units + ' (' + LEVEL[t] + ' for ' + sname + ')</span>' +
          '<span class="pill ' + (f > 0 ? 'g' : f < 0 ? 'd' : '') + '">' + (f > 0 ? 'leans to growth' : f < 0 ? (c0 === 0 ? 'leans against growth' : 'leans to decay') : 'no clear lean') + '</span>' +
          (like ? '<span class="dlike">' + like + '</span>' : '') + '</div>';
      });
      var jp = M.jet_pos && M.jet_pos[ing.jet_pos];
      if (ing.jet_pos) rows += '<div class="drow"><span class="nm">Jet position</span><span class="vl">' + ing.jet_pos + '</span>' +
        (jp && jp.grow_same_mix != null ? '<span class="dlike">all lows here: ' + Math.round(jp.grow_same_mix) + '% grew (same strength mix)</span>' : '') + '</div>';
      var pers = c1 === c0 ? 'Calling no change would have been right here.' : 'Calling no change would have missed this one.';
      return '<h3>Why it went this way</h3><div class="dout">' + out + '</div>' +
        (ch ? '<div class="dsum">The ingredients together gave ' + ch + '.</div>' : '') +
        '<div class="dbase">' + base + ' ' + pers + '</div>' + rows +
        '<div class="ikey">These are odds, not rules: the best single ingredient moves the chance of growth by about 20 points.</div>';
    }
    return '';   // the growth-ingredient list is retired from the games (Jason 2026-11-06); the result card shows 925 x stability
    var rw = '';
    M.ingredients.forEach(function (it) { if (ing[it.key]) rw += '<div class="drow"><span class="nm">' + it.name + '</span><span class="vl">' + nf(ing[it.key][0]) + ' ' + it.units + ' (' + LEVEL[ing[it.key][1]] + ' for ' + sname + ')</span></div>'; });
    if (ing.jet_pos) rw += '<div class="drow"><span class="nm">Jet position</span><span class="vl">' + ing.jet_pos + '</span></div>';
    return '<details class="dlite"><summary>Ingredients at this time</summary>' + rw + '</details>';
  }
  var ingStart = 1;
  function verdictTag(s, word) {
    if (!sig(s)) return '';
    return '<span class="itag ' + s.verdict + '">' + s.verdict + ': ' + (s.signal > 0 ? 'high' : 'low') + ' = ' + word + '</span>';
  }
  function ingredientsHTML() {
    var M = ingStats();
    if (!M) return '<h1>Ingredients</h1><p class="lead">No ingredient statistics in this deck.</p>';
    var sname = SNAME[ingStart], br = M.by_start[sname];
    var h = '<h1>Ingredients</h1><p class="lead">' + M.n + ' lows over two winters, judged by ASCAT 24 h later. A change of less than ' + M.dead_band_kt + ' kt counts as held. Everything here compares lows that started at the same strength.</p>';
    h += '<table class="jt"><tr><th>Start</th><th>Lows</th><th>Grew</th><th>Held</th><th>Decayed</th></tr>';
    SNAME.forEach(function (s) { var r = M.by_start[s]; h += '<tr><th>' + s + '</th><td>' + r.n + '</td><td>' + Math.round(r.grew) + '%</td><td>' + Math.round(100 - r.grew - r.decayed) + '%</td><td>' + Math.round(r.decayed) + '%</td></tr>'; });
    h += '</table><p class="ikey">Calling no change gets the category right ' + Math.round(M.persistence_exact) + '% of the time: that is the score to beat. ' +
      'All the ingredients together improve on the usual rates by about ' + Math.round(100 * M.model_grow.bss) + '% (growth) and ' + Math.round(100 * M.model_decay.bss) + '% (decay) in Brier skill.</p>';
    h += '<div class="segs" role="group" aria-label="Starting strength">';
    SNAME.forEach(function (s, i) { h += '<button type="button" class="seg' + (i === ingStart ? ' on' : '') + '" data-ist="' + i + '" aria-pressed="' + (i === ingStart) + '">Start ' + s + '</button>'; });
    h += '</div>';
    var list = M.ingredients.slice().sort(function (a, b) { return Math.max(Math.abs(b.grow.signal), Math.abs(b.decay.signal)) - Math.max(Math.abs(a.grow.signal), Math.abs(a.decay.signal)); });
    list.forEach(function (it) {
      var b = it.bars[sname], c = b.cuts, u = it.units.replace(/^per day$/, '/day');
      var lab = ['< ' + nf(c[0]), nf(c[0]) + '–' + nf(c[1]), '> ' + nf(c[1])], bars = '';
      for (var k = 0; k < 3; k++) {
        var g = b.grow[k], d = b.decay[k];
        bars += '<div>' + lab[k] + ' ' + u + '</div><div class="bar2">' +
          (ingStart < 3 && g != null ? '<i class="gr" style="width:' + Math.min(100, g) + '%"></i>' : '') +
          (ingStart > 0 && d != null ? '<i class="dc" style="width:' + Math.min(100, d) + '%"></i>' : '') +
          '<span>' + (ingStart < 3 && g != null ? 'grew ' + Math.round(g) + '%' : '') + (ingStart > 0 && ingStart < 3 ? ' &middot; ' : '') + (ingStart > 0 && d != null ? 'decayed ' + Math.round(d) + '%' : '') + '</span></div>';
      }
      var tags = verdictTag(it.grow, 'more growth') +
        (sig(it.decay) ? '<span class="itag ' + it.decay.verdict + '">' + it.decay.verdict + ': ' + (it.decay.signal < 0 ? 'low' : 'high') + ' = more decay</span>' : '');
      h += '<div class="icard"><div class="ihead"><b>' + it.name + '</b>' + (tags || '<span class="itag">no clear signal</span>') + '</div>' +
        '<div class="imean">' + (IMEANS[it.key] || '') + ' Growth signal ' + (it.grow.signal > 0 ? '+' : '') + Math.round(it.grow.signal) + ' points, decay signal ' + (it.decay.signal > 0 ? '+' : '') + Math.round(it.decay.signal) +
        ' (Atlantic ' + (it.basin.natl.grow > 0 ? '+' : '') + Math.round(it.basin.natl.grow) + ', Pacific ' + (it.basin.npac.grow > 0 ? '+' : '') + Math.round(it.basin.npac.grow) + ' for growth).</div>' +
        '<div class="ibars">' + bars + '</div></div>';
    });
    h += '<div class="ikey">Blue bar: share that grew a category. Pink bar: share that decayed. Thirds are cut among ' + sname + ' starts (' + br.n + ' lows). ' +
      'Signal = growth (or decay) share in the top third minus the bottom third, averaged over starting strengths. Strong: 15+ points and clear of zero at 99%; weak: clear of zero but smaller.</div>';
    if (M.jet_pos) {
      h += '<h2>Jet position</h2><table class="jt"><tr><th></th><th>Lows</th><th>Grew</th><th>Grew, same strength mix</th><th>Decayed</th></tr>';
      Object.keys(M.jet_pos).forEach(function (k) { var j = M.jet_pos[k]; h += '<tr><th>' + k + '</th><td>' + j.n + '</td><td>' + Math.round(j.grow) + '%</td><td>' + (j.grow_same_mix == null ? '&ndash;' : Math.round(j.grow_same_mix) + '%') + '</td><td>' + Math.round(j.decay) + '%</td></tr>'; });
      h += '</table><p class="ikey">Quadrants count only when the low is 300-1200 km along the streak from its core and within 600 km of its axis. Right entrance and left exit are the ascent quadrants. "Same strength mix" removes the effect of weak lows growing more often.</p>';
    }
    return h;
  }
  // Reading the wind (Jason 2026-11-06: "the ingredients page needs to tell you about wind speed detection").
  // Numbers from rule925.py (manifest.speed).
  function speedHTML() {
    var S = manifest && manifest.speed;
    if (!S) return '<h1>Reading the wind</h1><p class="lead">No wind-speed statistics in this deck.</p>';
    var H = S.held_out || {}, P = S.fc, pc = function (x) { return x + '%'; };
    var h = '<h1>Reading the wind</h1><p class="lead">How to judge the strongest wind ASCAT will show, from ' + S.n_now + ' analysis maps and ' + S.n_fc + ' GFS +24 h forecasts over five winters (2021-26). Truth is the strongest ASCAT wind anywhere on the map.</p>';
    h += '<h2>1. Strongest 925 mb wind &times; stability</h2>';
    h += '<p>Find the strongest 925 mb wind over water on the map (925 mb wind tab). Read sea minus air where that wind is (Sea - air tab). Multiply:</p>';
    h += '<table class="jt"><tr><th>Sea minus 2 m air</th><th>Factor</th><th>925 wind for gale</th><th>for storm</th><th>for HF</th></tr>';
    S.factors.forEach(function (r) { h += '<tr><th>' + r.sea_air + ' &deg;C</th><td>&times; ' + r.f.toFixed(2) + '</td><td>' + r.need[0] + ' kt</td><td>' + r.need[1] + ' kt</td><td>' + r.need[2] + ' kt</td></tr>'; });
    h += '</table>';
    h += '<p class="ikey">Why: air much colder than the sea mixes the wind aloft down to the surface; over a stable sea the strongest 925 wind (often a low-level jet in the warm sector) stays aloft. ' +
      'Sea minus air is the model\'s own surface (sea) temperature minus its 2 m air temperature. The factors apply to the strongest 925 wind anywhere on the map; the wind right near the centre mixes down more (about 0.9 to 1.1).</p>';
    if (H.now) h += '<div class="persist"><b>Tested on winters it never saw</b><span>Factors fitted on 2024-26, tried on 2021-24: category right ' + pc(H.now.exact) + ' of ' + H.now.n + ' analysis maps' +
      (H.fc ? ', and ' + pc(H.fc.exact) + ' on GFS +24 h maps where the GFS 10 m wind gets ' + pc(H.fc.gfs_exact) + '. HF caught ' + H.fc.hf_caught + ' of ' + H.fc.hf + ' (GFS ' + H.fc.gfs_hf_caught + ')' : '') + '.</span></div>';
    h += '<h2>2. The models\' own 10 m wind</h2><p>Median model peak minus ASCAT peak at +24 h, by what ASCAT showed:</p>';
    h += '<table class="jt"><tr><th>ASCAT showed</th><th>Cases</th><th>GFS</th><th>ECMWF</th></tr>';
    var sk = function (v) { return v == null ? '&ndash;' : (v > 0 ? '+' : '') + Math.round(v) + ' kt'; };
    S.bias.forEach(function (r) { h += '<tr><th>' + r.obs + '</th><td>' + r.n + '</td><td>' + sk(r.gfs) + '</td><td>' + sk(r.ifs) + (r.ifs != null ? ' <span class="fine">(' + r.ifs_n + ')</span>' : '') + '</td></tr>'; });
    h += '</table><p class="ikey">The models are close below storm force and run low at the top: the stronger the storm, the further under. ECMWF only from March 2025 (00/12Z runs).</p>';
    h += '<h2>3. Which shortcut wins at +24 h</h2><table class="jt"><tr><th></th><th>Right</th><th>Storm/HF right</th><th>HF caught</th><th>Too high</th><th>Too low</th></tr>';
    [['GFS 10 m as is', P.gfs], ['GFS +8 kt where GFS has 44+', P.gfs_plus8], ['925 &times; stability on GFS maps', P.r925]].forEach(function (x) {
      var r = x[1]; h += '<tr><th>' + x[0] + '</th><td>' + pc(r.exact) + '</td><td>' + pc(r.storm_plus_exact) + '</td><td>' + r.hf_caught + ' of ' + r.hf + '</td><td>' + pc(r.over) + '</td><td>' + pc(r.under) + '</td></tr>';
    });
    h += '</table><p class="ikey">All ' + S.n_fc + ' forecast cases. Both fixes lift the top end where GFS runs low; GFS +8 kt over-calls more often. Read them together: when the 925 wind over a warm sea already reads storm or HF, go to the top of the range.</p>';
    h += '<p class="fine">The earlier growth and decay study is retired from the games: its ingredients sorted growth from decay only about 10% better than the usual rates.</p>';
    return h;
  }
  function openIngredients() {
    $('drawer').hidden = true; var b = $('ingBody'); b.innerHTML = speedHTML(); show('ingr');
    b.onclick = null;
  }

  function answer(called, why) {   // called: category 0-3, or -1 (skipped, or time up)
    if (!cur || cur.answered || !cur.data) return;
    cur.answered = true; clearTimer();
    var fc = cur.game === 'fc', bm = cur.fcLike;
    var obsInfo = fc || bm ? cur.c.t24 : cur.c[cur.snap];
    var o = obsInfo.cat, secs = Math.min((Date.now() - cur.t0) / 1000, 600);
    var timeUp = why === 'time';
    if (timeUp) secs = BLITZ_SECS;
    var skipped = fc && cur.chCalled !== null && called < 0;   // the category is optional once the change is called
    var cpts = skipped ? 0 : score(called, o);
    var chObs = fc ? obsChange(cur.c) : undefined, chPts = fc ? changeScore(cur.chCalled, chObs) : 0;
    var pts = cpts + chPts;
    var rec = { id: cur.c.id, game: cur.game, called: called, obs: o, start: cur.c.t0.cat, pts: pts, cpts: cpts, t: Math.round(secs * 10) / 10, mode: cur.bench ? 'bench' : opts.mode };
    if (fc) { rec.chCalled = cur.chCalled; rec.chObs = chObs; rec.chPts = chPts; rec.skip = skipped; }
    if (bm) { rec.models = {}; MODELS.forEach(function (m) { if (cur.c.fc[m] && cur.c.fc[m].cat != null) rec.models[m] = cur.c.fc[m].cat; }); cur.peak = peakCell(geom, cur.data[1], cur.c.t24); }
    if (cur.kind) rec.kind = cur.kind;
    var rsn = bm ? (cur.fcData && cur.fcData.gfs) : fc ? null : cur.data[cur.snap === 't24' ? 1 : 0];
    cur.rule = rsn ? rule925(rsn) : null;
    if (cur.rule) { rec.models = rec.models || {}; rec.models.r925 = cur.rule.cat; }
    if (!fc && !bm) {
      var low = cur.c[cur.snap];
      cur.peak = peakCell(geom, cur.data[cur.snap === 't24' ? 1 : 0], low);
      if (cur.tap && cur.peak) { cur.tapNm = distKm(cur.tap.lat, cur.tap.lon, cur.peak.lat, cur.peak.lon) * NM_PER_KM; rec.tapNm = Math.round(cur.tapNm); }
    }
    if (cur.bench) {   // benchmark: no feedback, no session records; the summary comes at the end
      bench.recs.push(rec); bench.n++; $('mapbox').classList.remove('tappable');
      return nextCase();
    }
    session.records.push(rec); saveSession();
    if (blitz) { blitz.recs.push(rec); blitz.n++; }
    var tt = totals(session.records);
    updateTop();
    $('tapNote').hidden = true; $('mapbox').classList.remove('tappable');
    // result card
    var cls, head;
    if (fc) {
      cls = chPts === 60 ? 'good' : chPts > 0 ? 'ok' : 'bad';
      head = cur.chCalled === null ? 'Time up: it ' + CH_OBS[chObs + 1] : cur.chCalled === chObs ? 'Right: it ' + CH_OBS[chObs + 1]
        : 'You called ' + CH_NAMES[cur.chCalled + 1] + ', it ' + CH_OBS[chObs + 1];
    } else {
      cls = called === o ? 'good' : (called >= 0 && Math.abs(called - o) === 1 && pts > 0) ? 'ok' : 'bad';
      head = called < 0 ? 'Time up: observed ' + CATS[o] : called === o ? 'Exact: ' + CATS[o] : 'You called ' + CATS[called] + ', observed ' + CATS[o];
    }
    var h = '<div class="rhead">' + head + '</div><div class="rpts">' + (pts > 0 ? '+' : '') + pts + ' pts</div>';
    if (fc) {
      h += '<div class="rline">Change call: ' + (chPts > 0 ? '+' : '') + chPts + ' (peak ' + Math.round(cur.c.t0.peak) + ' to ' + Math.round(obsInfo.peak) + ' kt)</div>';
      h += '<div class="rline">Category: ' + (skipped ? 'skipped' : called < 0 ? 'no answer, observed ' + CATS[o] : called === o ? 'exact, ' + CATS[o] : 'called ' + CATS[called] + ', observed ' + CATS[o]) +
        (skipped ? '' : ' (' + (cpts > 0 ? '+' : '') + cpts + ')') + '. ASCAT at +24 h: ' + CATS[o] + '.</div>';
      var d = cur.c.t0.hpa - cur.c.t24.hpa, dd = Math.round(Math.abs(d));
      h += '<div class="rline">' + (dd === 0 ? 'No pressure change' : (d > 0 ? 'Deepened ' : 'Filled ') + dd + ' hPa') +
        ' (' + Math.round(cur.c.t0.hpa) + ' to ' + Math.round(cur.c.t24.hpa) + ' hPa)</div>';
    } else if (bm) {
      h += '<div class="rline">ASCAT at +24 h: <b>' + Math.round(obsInfo.peak) + ' kt</b> (' + CATS[o] + '), from ' + Math.round(cur.c.t0.peak) + ' kt now. Ringed on the ASCAT tab.</div>';
      MODELS.forEach(function (m) {
        var f = cur.c.fc[m]; if (!f || f.cat == null) return;
        var you = called < 0 ? 9 : Math.abs(called - o), them = Math.abs(f.cat - o);
        var v = called < 0 ? '' : you < them ? ' <span class="pill g">you beat it</span>' : you === them ? ' <span class="pill">level</span>' : ' <span class="pill d">it beat you</span>';
        h += '<div class="rline">' + MODEL_NAMES[m] + ' said ' + Math.round(f.peak) + ' kt (' + CATS[f.cat] + '), ' + (f.cat === o ? 'right' : f.cat < o ? 'too low' : 'too high') + v + '</div>';
      });
      h += ruleLine(called, o, true);
      var g = cur.c.fc.gfs;
      if (cur.game === 'sh' && g && g.peak >= 44) {   // the tested rule: GFS runs low at the top, add 8 kt when it shows 44+
        var lc = catOf(g.peak + 8);
        h += '<div class="rline">GFS +8 kt rule (GFS 44+ kt): ' + Math.round(g.peak + 8) + ' kt (' + CATS[lc] + '), ' + (lc === o ? 'right' : lc < o ? 'too low' : 'too high') + '</div>';
      }
    } else {
      h += '<div class="rline">ASCAT peak ' + Math.round(obsInfo.peak) + ' kt (' + CATS[o] + ')</div>';
      h += ruleLine(called, o, false);
      h += '<div class="rline">Low centre about ' + Math.round(cur.c[cur.snap].hpa) + ' hPa</div>';
      if (cur.peak) h += '<div class="rline">' + (cur.tap ? 'Your tap was <b>' + Math.round(cur.tapNm) + ' nm</b> from the cell that set the peak (ringed, ' + Math.round(cur.peak.s) + ' kt).'
        : 'The ringed cell on the ASCAT tab set the peak (' + Math.round(cur.peak.s) + ' kt).') + '</div>';
    }
    h += '<div class="rstats">Streak ' + tt.cur + ' &middot; Total ' + tt.pts + ' pts &middot; Best streak ' + tt.best + '</div>';
    var res = $('result'); res.className = 'result ' + cls; res.innerHTML = h; res.hidden = false;
    $('answers').hidden = true;
    var db = $('debrief'), dh = debriefHTML(); db.innerHTML = dh; db.hidden = !dh;
    var nb = $('nextBtn'); nb.hidden = false;
    nb.textContent = blitz && blitz.n >= BLITZ_N ? 'See results' : 'Next case';
    // reveal tab
    tabList = (bm ? bmTabs(cur.src) : availTabs()).concat([REVEAL_TAB]); buildTabs(); setTab(tabList.length - 1);
    focusPlay();
    if (window.innerWidth < 900) {   // result sits below the map on narrow screens: bring it up under the sticky bars
      var top = res.getBoundingClientRect().top + window.pageYOffset - chromeH() - 8;
      window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }
  }

  function ruleLine(called, o, fcst) {
    var r = cur.rule; if (!r) return '';
    var you = called < 0 ? 9 : Math.abs(called - o), them = Math.abs(r.cat - o);
    var v = called < 0 ? '' : you < them ? ' <span class="pill g">you beat it</span>' : you === them ? ' <span class="pill">level</span>' : ' <span class="pill d">it beat you</span>';
    return '<div class="rline">925 \u00d7 stability' + (fcst ? ' (GFS +24 h)' : '') + ': ' + Math.round(r.w925) + ' kt \u00d7 ' + r.f.toFixed(2) + ' (sea ' + (r.sea_air >= 0 ? '+' : '') + r.sea_air.toFixed(0) + ' \u00b0C on the air) = ' +
      Math.round(r.peak) + ' kt (' + CATS[r.cat] + '), ' + (r.cat === o ? 'right' : r.cat < o ? 'too low' : 'too high') + v + '</div>';
  }

  // ------------------------------------------------------------------ stats
  function tableHTML(conf) {
    var h = '<table class="conf"><tr><th class="corner">Called<br>&darr; / Observed &rarr;</th>';
    CATS.forEach(function (c) { h += '<th>' + c + '</th>'; });
    h += '</tr>';
    for (var c = 0; c < 4; c++) {
      h += '<tr><th>' + CATS[c] + '</th>';
      for (var o = 0; o < 4; o++) { var n = conf.m[c][o]; h += '<td class="' + (c === o ? 'diag ' : '') + (n ? '' : 'zero') + '">' + n + '</td>'; }
      h += '</tr>';
    }
    return h + '</table>' + (conf.un ? '<div class="fine">' + conf.un + ' unanswered or skipped (not in table)</div>' : '');
  }
  function kpiHTML(t) {
    var pct = function (x) { return t.n ? Math.round(100 * x / t.n) + '%' : '-'; };
    var k = [[t.n, 'cases played'], [pct(t.exact), 'right call'], [pct(t.within1), 'within one'],
             [t.best, 'best streak'], [t.n ? (t.time / t.n).toFixed(1) + ' s' : '-', 'mean time per case'], [t.pts, 'total points']];
    return '<div class="kpis">' + k.map(function (x) { return '<div class="kpi"><b>' + x[0] + '</b><span>' + x[1] + '</span></div>'; }).join('') + '</div>';
  }
  function levelHTML(pts) {
    var i = levelFor(pts), nxt = LEVELS[i + 1];
    var frac = nxt ? Math.max(0, Math.min(1, (pts - LEVELS[i][1]) / (nxt[1] - LEVELS[i][1]))) : 1;
    return '<div class="level"><b>' + LEVELS[i][0] + '</b><span>' + (nxt ? (nxt[1] - pts) + ' pts to ' + nxt[0] : 'top level') + '</span></div><div class="lvbar"><i style="width:' + Math.round(frac * 100) + '%"></i></div>';
  }
  // Bias tracker: lean = called minus observed category (+ = calls too high), answered cases only.
  function lean(recs) {
    var a = recs.filter(function (r) { return r.called >= 0; });
    if (!a.length) return null;
    return { v: a.reduce(function (s, r) { return s + r.called - r.obs; }, 0) / a.length, n: a.length };
  }
  function leanText(l) { return l === null ? '-' : (l.v > 0 ? '+' : '') + l.v.toFixed(1); }
  function leanRow(label, l, extra) {
    // diverging bar, -2 .. +2 categories
    var w = l === null ? 0 : Math.min(Math.abs(l.v), 2) / 2 * 50, side = l && l.v < 0 ? 'neg' : 'pos';
    return '<div class="lrow"><span class="ll">' + label + '</span><span class="lbar"><i class="' + side + '" style="width:' + w.toFixed(1) +
      '%"></i></span><span class="lv">' + leanText(l) + '</span><span class="ln">' + (extra || (l ? 'n ' + l.n : '')) + '</span></div>';
  }
  function biasHTML(recs, game) {
    var all = lean(recs);
    if (!all) return '';
    var h = '<div class="bias"><div class="bh">Bias tracker <span class="fine">(called minus observed, in categories; + calls too high)</span></div>';
    h += leanRow('All cases', all);
    var last = lean(recs.slice(-10)), before = recs.length > 10 ? lean(recs.slice(0, -10)) : null;
    if (before && last) h += leanRow('Last 10', last, 'was ' + leanText(before));
    for (var o = 0; o < 4; o++) {
      var l = lean(recs.filter(function (r) { return r.obs === o; }));
      if (l) h += leanRow('Observed ' + ['none', 'gale', 'storm', 'HF'][o], l);
    }
    if (game === 'fc') {
      h += '<div class="bh2">Growth vs decay over 24 h</div>';
      [['Strengthened', 1], ['Held', 0], ['Weakened', -1]].forEach(function (g) {
        var rs = recs.filter(function (r) { return r.called >= 0 && r.start !== undefined && Math.sign(r.obs - r.start) === g[1]; });
        if (!rs.length) return;
        var right = rs.filter(function (r) { return Math.sign(r.called - r.start) === g[1]; }).length;
        h += leanRow(g[0], lean(rs), right + ' of ' + rs.length + ' change called right');
      });
    }
    return h + '</div>';
  }
  // You vs each model: exact category and points on the same cases (a model counts only where it had a forecast).
  function vsModelHTML(recs) {
    var h = '';
    BENCH.forEach(function (m) {
      var rs = recs.filter(function (r) { return r.called >= 0 && r.models && r.models[m] != null; });
      if (!rs.length) return;
      var you = 0, it = 0, yp = 0, ip = 0, up = 0, dn = 0;
      rs.forEach(function (r) { if (r.called === r.obs) you++; if (r.models[m] === r.obs) it++; yp += score(r.called, r.obs); ip += score(r.models[m], r.obs); if (r.models[m] < r.obs) up++; if (r.models[m] > r.obs) dn++; });
      var n = rs.length, pc = function (x) { return Math.round(100 * x / n) + '%'; };
      h += '<div class="persist"><b>You vs ' + MODEL_NAMES[m] + '</b><span>You: ' + pc(you) + ' exact, ' + yp + ' pts. ' + MODEL_NAMES[m] + ': ' + pc(it) + ' exact, ' + ip + ' pts over the same ' + n + ' case' + (n > 1 ? 's' : '') +
        '. ' + (yp > ip ? 'You are beating it.' : yp === ip ? 'Level.' : 'It is ahead.') + ' It was too low ' + up + ' times and too high ' + dn + '.</span></div>';
    });
    return h;
  }
  function gameSection(title, recs, game) {
    var h = '<h3 class="gh">' + title + '</h3>';
    if (!recs.length) return h + '<div class="empty">No cases yet.</div>';
    if (game === 'sh') { var cs = confusion(recs); return h + shHTML(recs) + vsModelHTML(recs) + biasHTML(recs, game) + tableHTML(cs); }
    if (game === 'bm') { var cf = confusion(recs); return h + vsModelHTML(recs) + '<div class="read">' + readLine(cf) + '</div>' + biasHTML(recs, game) + tableHTML(cf); }
    var conf = confusion(recs);
    return h + (game === 'fc' ? changeHTML(recs) : tapHTML(recs) + vsModelHTML(recs)) + '<div class="read">' + readLine(conf) + '</div>' + (game === 'fc' ? persistHTML(recs) : '') + biasHTML(recs, game) + (game === 'fc' ? '<div class="bh2">Category (optional second call)</div>' : '') + tableHTML(conf);
  }
  // Storm or HF?: the HF catch and the HF over-call, the two numbers that matter at the top end.
  function shHTML(recs) {
    var a = recs.filter(function (r) { return r.called >= 0; }), hf = a.filter(function (r) { return r.obs === 3; }), st = a.filter(function (r) { return r.obs === 2; });
    var n = function (rs, f) { return rs.filter(f).length; }, isHF = function (r) { return r.called === 3; };
    var h = '<div class="persist"><b>HF caught</b><span>You called HF on ' + n(hf, isHF) + ' of ' + hf.length + ' HF cases, and on ' + n(st, isHF) + ' of ' + st.length + ' storm cases (over-calls).</span></div>';
    var f = a.filter(function (r) { return r.models && r.models.gfs != null; });
    if (f.length) {
      var fh = f.filter(function (r) { return r.obs === 3; }), fs = f.filter(function (r) { return r.obs === 2; }), gHF = function (r) { return r.models.gfs === 3; };
      h += '<div class="persist"><b>Forecast cases: you vs GFS</b><span>HF caught: you ' + n(fh, isHF) + ' of ' + fh.length + ', GFS ' + n(fh, gHF) + '. HF over-called: you ' + n(fs, isHF) + ' of ' + fs.length + ', GFS ' + n(fs, gHF) + '.</span></div>';
    }
    return h;
  }
  // You vs persistence: what calling "no change" (the category now) would have scored on the same cases.
  function persistHTML(recs) {
    var n = recs.length, you = 0, yp = 0, pe = 0, pp = 0;
    recs = recs.filter(function (r) { return !r.skip; });   // category part only: a skipped category is not scored
    n = recs.length; if (!n) return '';
    recs.forEach(function (r) { if (r.called === r.obs) you++; yp += r.cpts !== undefined ? r.cpts : r.pts; if (r.start === r.obs) pe++; pp += score(r.start, r.obs); });
    var beat = yp > pp ? 'You are beating no change.' : yp === pp ? 'Level with no change.' : 'No change is ahead: look harder for growth and decay.';
    return '<div class="persist"><b>Category: you vs calling no change</b><span>You: ' + Math.round(100 * you / n) + '% exact, ' + yp + ' pts. ' +
      'No change: ' + Math.round(100 * pe / n) + '% exact, ' + pp + ' pts. ' + beat + '</span></div>';
  }
  function openStats() {
    var all = session.records, t = totals(all);
    var h = levelHTML(t.pts) + kpiHTML(t);
    if (all.filter(function (r) { return r.called >= 0 || r.chCalled != null; }).length < 5) {
      h += '<div class="statsempty"><p><b>Play 5 cases to see your bias</b></p><p class="fine">The bias tracker and confusion table need a few answered cases first.</p>' +
        '<button type="button" class="btn small" id="statsNext">Next case</button></div>';
    } else {
      h += gameSection('Right now', all.filter(function (r) { return r.game === 'now'; }), 'now');
      h += gameSection('Beat the model', all.filter(function (r) { return r.game === 'bm'; }), 'bm');
      var shr = all.filter(function (r) { return r.game === 'sh'; });
      if (shr.length) h += gameSection('Storm or HF?', shr, 'sh');
      var old = all.filter(function (r) { return r.game === 'fc'; });
      if (old.length) h += gameSection('Forecast +24 h (grow, hold, decay)', old, 'fc');
    }
    h += benchHistHTML(null);
    statsOpener = document.activeElement;
    $('statsBody').innerHTML = h; $('drawer').hidden = false;
    $('closeStats').focus();
  }
  var statsOpener = null;
  function closeStats() {
    if ($('drawer').hidden) return;
    $('drawer').hidden = true;
    var o = statsOpener; statsOpener = null;
    if (o && o.getClientRects().length && o !== document.body) { try { o.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
    else if (!$('play').hidden) focusPlay();
  }
  function statsNext() {   // the "Next case" link in the stats empty state
    closeStats();
    if (!$('play').hidden && cur) { if (cur.answered || cur.failed) nextCase(); else focusPlay(); }
    else startGame();
  }
  function leaveBlitz() { return !$('play').hidden && ((blitz && blitz.n < BLITZ_N) || (bench && bench.n < bench.ids.length)); }
  function askLeave(on) {
    $('leaveTxt').textContent = bench ? 'Leave the benchmark? This run will not be saved.' : 'Leave blitz? Your progress in this blitz will be lost.';
    $('leaveBanner').hidden = !on; syncTimer();
    if (on) $('leaveNo').focus({ preventScroll: true }); else if (!$('play').hidden) focusPlay();
  }
  function endBlitz() {
    clearTimer();
    var t = totals(blitz.recs), conf = confusion(blitz.recs);
    var pct = t.n ? Math.round(100 * t.exact / t.n) : 0;
    var h = '<div class="level"><b>' + t.pts + ' pts</b><span>' + pct + '% exact &middot; best streak ' + t.best + '</span></div>';
    h += levelHTML(totals(session.records).pts);
    if (blitz.recs.length && blitz.recs[0].game === 'fc') h += changeHTML(blitz.recs);
    if (blitz.recs.length && (blitz.recs[0].game === 'bm' || blitz.recs[0].game === 'now')) h += vsModelHTML(blitz.recs);
    if (blitz.recs.length && blitz.recs[0].game === 'sh') h += shHTML(blitz.recs) + vsModelHTML(blitz.recs);
    h += '<div class="read">' + readLine(conf) + '</div>' + biasHTML(blitz.recs, blitz.recs.length && blitz.recs[0].game) + tableHTML(conf);
    $('endTitle').textContent = 'Blitz done'; $('endBody').innerHTML = h; show('end');
  }
  function goHome() { clearTimer(); cur = null; show('start'); }
  // startMsg is cleared whenever a game starts (see startGame)

  // ------------------------------------------------------------------ keys, change-call stats
  function pressKey(k) {   // number keys press the nth answer button; s or 0 skips the optional category
    if (/^[sS0]$/.test(k)) { var sk = $('answers').querySelector('.skip'); if (sk) sk.click(); return; }
    var b = $('answers').querySelectorAll('.ans')[+k - 1];
    if (b && !b.disabled) b.click();
  }
  var CHORD = [1, 0, -1];   // table order: Grow, Hold, Decay
  function changeHTML(recs) {   // 3x3 called vs observed, and you vs calling no change (Hold)
    var rs = recs.filter(function (r) { return r.chObs !== undefined; });
    if (!rs.length) return '';
    var m = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], un = 0, you = 0, yp = 0, pp = 0, pe = 0, grew = 0, caught = 0, fa = 0;
    rs.forEach(function (r) {
      if (r.chCalled === null) un++; else m[r.chCalled + 1][r.chObs + 1]++;
      if (r.chCalled === r.chObs) you++;
      yp += r.chPts; pp += changeScore(0, r.chObs); if (r.chObs === 0) pe++;
      if (r.chObs === 1) { grew++; if (r.chCalled === 1) caught++; }
      if (r.chCalled === 1 && r.chObs !== 1) fa++;
    });
    var n = rs.length, pc = function (x) { return Math.round(100 * x / n) + '%'; };
    var beat = yp > pp ? 'You are beating no change.' : yp === pp ? 'Level with no change.' : 'No change is ahead: look harder for growth and decay.';
    var h = '<div class="bh2">Change call: grow, hold or decay</div>' +
      '<div class="persist"><b>You vs calling no change (Hold every time)</b><span>You: ' + pc(you) + ' right, ' + yp + ' pts over ' + n + ' cases. No change: ' + pc(pe) + ' right, ' + pp + ' pts. ' + beat + '</span></div>' +
      '<div class="fine chnote">' + (grew ? 'Growth caught: ' + caught + ' of ' + grew + '. ' : 'No growth cases yet. ') + 'False alarms of growth: ' + fa + '. (A missed growth costs more than a false alarm.)</div>';
    h += '<table class="conf"><tr><th class="corner">Called<br>&darr; / Observed &rarr;</th>';
    CHORD.forEach(function (v) { h += '<th>' + CH_NAMES[v + 1] + '</th>'; });
    h += '</tr>';
    CHORD.forEach(function (c) {
      h += '<tr><th>' + CH_NAMES[c + 1] + '</th>';
      CHORD.forEach(function (o) { var k = m[c + 1][o + 1]; h += '<td class="' + (c === o ? 'diag ' : '') + (k ? '' : 'zero') + '">' + k + '</td>'; });
      h += '</tr>';
    });
    return h + '</table>' + (un ? '<div class="fine">' + un + ' with no change call (time up)</div>' : '');
  }
  function tapHTML(recs) {
    var d = recs.filter(function (r) { return r.tapNm != null; }).map(function (r) { return r.tapNm; });
    if (!d.length) return '';
    return '<div class="persist"><b>Where the strongest wind is</b><span>Median miss ' + Math.round(median(d)) + ' nm over ' + d.length + ' tap' + (d.length > 1 ? 's' : '') +
      (SCENE() ? ' (to the ringed cell: the 3rd-highest ASCAT cell on the map).' : ' (to the ringed cell: the 3rd-highest ASCAT cell within 500 km).') + '</span></div>';
  }

  // ------------------------------------------------------------------ benchmark: history on this device, summary, CSV
  var benchHist = [], benchStored = true;
  function loadBenchHist() {
    try { var r = window.localStorage.getItem(BENCH_KEY), a = r && JSON.parse(r); if (Array.isArray(a)) benchHist = a; } catch (e) { benchStored = false; }
  }
  function saveBenchHist() { try { window.localStorage.setItem(BENCH_KEY, JSON.stringify(benchHist)); return true; } catch (e) { return false; } }
  function runSummary(recs) {   // version 2: category vs ASCAT at +24 h, and the benchmarks on the same cases
    var s = { v: 2, n: recs.length, pts: 0, exact: 0, within1: 0, secs: 0, gfs: 0, gfsPts: 0, gfsN: 0, r925: 0, r925Pts: 0, r925N: 0 };
    recs.forEach(function (r) {
      s.pts += r.pts; s.secs += r.t;
      if (r.called === r.obs) s.exact++;
      if (r.called >= 0 && Math.abs(r.called - r.obs) <= 1) s.within1++;
      var m = r.models || {};
      if (m.gfs != null) { s.gfsN++; if (m.gfs === r.obs) s.gfs++; s.gfsPts += score(m.gfs, r.obs); }
      if (m.r925 != null) { s.r925N++; if (m.r925 === r.obs) s.r925++; s.r925Pts += score(m.r925, r.obs); }
    });
    return s;
  }
  function shortDate(ts) { var d = new Date(ts); return isNaN(d) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); }
  function benchHistHTML(hi) {
    var runs = benchHist.filter(function (r) { return r.v === 2; });
    if (!runs.length) return '';
    var h = '<h3 class="gh">Benchmark history (this device)</h3><table class="jt"><tr><th>Run</th><th>You exact</th><th>Your pts</th><th>GFS exact</th><th>925 &times; stability exact</th></tr>';
    var from = Math.max(0, runs.length - 8);
    runs.slice(from).forEach(function (r, i) {
      var last = hi && from + i === runs.length - 1;
      h += '<tr' + (last ? ' class="hl"' : '') + '><th>' + (from + i + 1) + '<div class="fine">' + shortDate(r.ts) + '</div></th><td>' + r.exact + ' of ' + r.n + '</td><td>' + r.pts + '</td><td>' + r.gfs + ' of ' + r.gfsN + '</td><td>' + r.r925 + ' of ' + r.r925N + '</td></tr>';
    });
    return h + '</table>' + (benchStored ? '' : '<div class="fine">Storage is blocked in this browser: history lasts only while this page stays open.</div>');
  }
  function endBench() {
    clearTimer();
    var recs = bench.recs, run = runSummary(recs), olds = benchHist.filter(function (r) { return r.v === 2; }), prev = olds.length ? olds[olds.length - 1] : null;
    run.ts = new Date().toISOString(); run.recs = recs.map(function (r) { return { id: r.id, start: r.start, called: r.called, obs: r.obs, pts: r.pts, t: r.t, models: r.models }; });
    benchHist.push(run); if (benchHist.length > 30) benchHist.shift();
    benchStored = saveBenchHist() && benchStored;
    var sg = function (x) { return (x > 0 ? '+' : '') + x; };
    var h = '<div class="level"><b>' + run.exact + ' of ' + run.n + ' right</b><span>' + run.pts + ' pts &middot; ' + run.within1 + ' within one &middot; ' + (run.secs / run.n).toFixed(1) + ' s per case</span></div>';
    h += prev ? '<div class="read">Against your previous run: ' + sg(run.exact - prev.exact) + ' right, ' + sg(run.pts - prev.pts) + ' pts.</div>'
      : '<div class="read">First benchmark run on this device. Come back later and run it again to compare.</div>';
    h += vsModelHTML(recs);
    h += '<div class="read">' + readLine(confusion(recs)) + '</div>';
    h += benchHistHTML(true);
    var rows = '', mc = function (r, k) { return r.models && r.models[k] != null ? CATS[r.models[k]] : '-'; };
    recs.forEach(function (r, i) {
      var c = manifest.byId[r.id];
      rows += '<tr><th>' + (i + 1) + '</th><td>' + (c && c.basin === 'natl' ? 'Atl' : 'Pac') + '</td><td>' + CATS[r.start] + '</td><td>' + (r.called < 0 ? '-' : CATS[r.called]) + '</td><td>' + mc(r, 'gfs') + '</td><td>' + mc(r, 'r925') +
        '</td><td>' + CATS[r.obs] + '</td></tr>';
    });
    h += '<details class="dlite"><summary>The ' + recs.length + ' cases</summary><table class="jt"><tr><th>#</th><th>Basin</th><th>ASCAT now</th><th>You</th><th>GFS</th><th>925 &times; stab.</th><th>ASCAT +24 h</th></tr>' + rows + '</table></details>';
    $('endTitle').textContent = 'Benchmark done'; $('endBody').innerHTML = h;
    lastEnd = 'bench'; bench = null; cur = null; show('end');
  }
  function csvCell(v) { var s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function exportCSV() {   // session records + benchmark runs + pairs, built here and saved through a Blob: nothing leaves the device
    var cols = ['kind', 'run', 'when', 'game', 'mode', 'case', 'start_cat', 'called_change', 'observed_change', 'change_pts', 'called_cat', 'observed_cat', 'cat_pts', 'total_pts', 'secs', 'tap_miss_nm', 'pair_pick', 'pair_right'];
    var rows = [cols];
    var chn = function (v) { return v === null || v === undefined ? '' : CH_NAMES[v + 1]; };
    var cat = function (v) { return v === null || v === undefined || v < 0 ? '' : CATS[v]; };
    session.records.forEach(function (r, i) {
      rows.push(['session', '', '', r.game === 'fc' ? 'forecast' : r.game === 'bm' ? 'beat_the_model' : r.game === 'sh' ? 'storm_or_hf' + (r.kind === 'fc' ? '_24h' : '') : 'right_now', r.mode, r.id || '', cat(r.start), chn(r.chCalled), r.chObs === undefined ? '' : CH_OBS[r.chObs + 1], r.chPts, cat(r.called), cat(r.obs), r.cpts !== undefined ? r.cpts : r.pts, r.pts, r.t, r.tapNm, '', '']);
    });
    benchHist.forEach(function (run, k) {
      (run.recs || []).forEach(function (r) {
        rows.push(['benchmark', k + 1, run.ts, 'beat_the_model', 'bench', r.id, cat(r.start), '', '', '', cat(r.called), cat(r.obs), r.pts, r.pts, r.t, '', '', '']);
      });
    });
    var csv = rows.map(function (r) { return r.map(csvCell).join(','); }).join('\r\n') + '\r\n';
    var a = document.createElement('a'), url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.href = url; a.download = 'pattern-drill-results.csv'; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    var msg = rows.length - 1 + ' rows saved to pattern-drill-results.csv.';
    $('startMsg').textContent = msg; $('exportMsg').textContent = msg;
  }

  function loadOptional() {   // bench.json is optional: without it the Benchmark button stays hidden
    return fetch('deck/bench.json', { cache: 'no-cache' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }).then(function (b) {
      if (b && b.ids) { benchIds = b.ids.filter(function (id) { return manifest.byId[id]; }); benchIds.forEach(function (id) { benchSet[id] = 1; }); if (!benchIds.length) benchIds = null; }
      $('benchBtn').hidden = !benchIds;
    });
  }

  // ------------------------------------------------------------------ events
  function bind() {
    setupChoice('gameChoice', 'game'); setupChoice('modeChoice', 'mode');
    $('hints').checked = opts.hints;
    $('hints').addEventListener('change', function (e) {
      opts.hints = e.target.checked;
      try { window.sessionStorage.setItem('pdrill-hints', opts.hints ? '1' : '0'); } catch (x) { /* ignore */ }
    });
    $('weak').addEventListener('change', function (e) { opts.weak = e.target.checked; });
    $('startBtn').addEventListener('click', startGame);
    $('againBtn').addEventListener('click', function () { if (lastEnd === 'bench') startBench(); else startGame(); });
    $('endHomeBtn').addEventListener('click', goHome);
    $('homeBtn').addEventListener('click', function () { if (leaveBlitz()) askLeave(true); else goHome(); });
    $('leaveYes').addEventListener('click', function () { $('leaveBanner').hidden = true; blitz = null; bench = null; goHome(); });
    $('leaveNo').addEventListener('click', function () { askLeave(false); });
    $('statsBody').addEventListener('click', function (e) { if (e.target.id === 'statsNext') statsNext(); });
    new MutationObserver(syncTimer).observe($('drawer'), { attributes: true, attributeFilter: ['hidden'] });   // pause the blitz clock under the drawer
    var setHdr = function () { document.documentElement.style.setProperty('--hdr', document.querySelector('header.top').offsetHeight + 'px'); };
    setHdr(); window.addEventListener('resize', setHdr); window.addEventListener('load', setHdr);
    $('nextBtn').addEventListener('click', nextCase);
    $('benchBtn').addEventListener('click', startBench);
    $('exportBtn').addEventListener('click', exportCSV);
    $('statsExport').addEventListener('click', exportCSV);
    $('map').addEventListener('click', mapTap);
    $('tapNote').addEventListener('click', function (e) { if (e.target.id === 'tapClear' && cur && !cur.answered) { cur.tap = null; updateTapNote(); draw(); } });
    $('ingBtn').addEventListener('click', openIngredients);
    $('ingLink').addEventListener('click', openIngredients);
    fetch('../fronts/index.html', { method: 'HEAD' }).then(function (r) { if (r.ok) $('navFronts').hidden = false; }).catch(function () { /* no front drill yet */ });
    $('statsIng').addEventListener('click', openIngredients);
    $('ingBack').addEventListener('click', function () { show(lastScreen); });
    $('statsBtn').addEventListener('click', openStats);
    $('closeStats').addEventListener('click', closeStats);
    $('drawer').addEventListener('click', function (e) { if (e.target === $('drawer')) closeStats(); });
    document.addEventListener('keydown', function (e) {
      if (!$('drawer').hidden) { if (e.key === 'Escape') closeStats(); return; }
      if (!$('leaveBanner').hidden) { if (e.key === 'Escape') askLeave(false); return; }
      if ($('play').hidden) return;
      var onBtn = e.target.closest && e.target.closest('button');
      if ((e.key === 'Enter' || e.key === ' ') && onBtn && onBtn !== $('nextBtn')) return;   // let the focused button act
      if (e.key === 'ArrowRight') { setTab(tabIdx + 1); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { setTab(tabIdx - 1); e.preventDefault(); }
      else if (/^[0-9sS]$/.test(e.key) && cur && !cur.answered && cur.data) pressKey(e.key);
      else if ((e.key === 'Enter' || e.key === ' ') && !$('nextBtn').hidden) { e.preventDefault(); nextCase(); }
    });
    var tx = 0, ty = 0, mb = $('mapbox');
    mb.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
    mb.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
      if (Math.abs(dx) > 45 && Math.abs(dx) > 1.5 * Math.abs(dy)) setTab(tabIdx + (dx < 0 ? 1 : -1));
    }, { passive: true });
    var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (geom && cur && cur.data && !$('play').hidden) { sizeCanvas(); draw(); } }, 120); });
  }

  bind(); updateTop(); loadBenchHist();
  loadManifest().then(loadOptional).then(function () { show('start'); }).catch(function (e) {
    $('loadMsg').textContent = 'Could not load the case deck (' + e.message + ').';
  });
})();
