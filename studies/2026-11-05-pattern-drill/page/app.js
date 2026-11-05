/* Pattern drill: static page, plain JS + canvas. Reads deck/manifest.json and deck/<id>.bin
   (format in ../design.md). Session stats only. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ constants
  var CATS = ['None', 'Gale', 'Storm', 'HF'];
  var CAT_RANGE = ['<34 kt', '34-47', '48-63', '64+'];
  var CAT_OBS = ['quiet (under 34 kt)', 'gale', 'storm', 'HF'];
  var BLITZ_N = 10, BLITZ_SECS = 60, WEAK_MIN = 8;
  var RING_KM = 500;
  // Wind colours: rk/style.py WIND_LEVELS / WIND_COLORS / WIND_OVER (light-background version).
  var WIND_LEVELS = [0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80];
  var WIND_COLORS = ['#f4f6f8', '#dde6ef', '#c3d4e6', '#9fbbd9', '#7aa0c9', '#5683b5',
                     '#e8d27a', '#e8a93f', '#e06f2e', '#c9372c', '#9b1f5e'];
  var WIND_OVER = '#c86fd8';
  var LAND_RGB = [221, 224, 228];
  var LEVELS = [['Trainee', 0], ['Watch', 500], ['Gale', 1500], ['Storm', 3500], ['Hurricane Force', 7000]];
  var STORE_KEY = 'pdrill-session-1';

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
      note: 'Thin: MSLP every 4 hPa.' }
  ];
  var REVEAL_TAB = { id: 'reveal', label: 'ASCAT', name: 'ASCAT wind over MSLP', reveal: true };

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
  var session = { records: [], played: { now: {}, fc: {} } };
  try { var raw = window.sessionStorage.getItem(STORE_KEY); if (raw) { var s = JSON.parse(raw); if (s && s.records && s.played) session = s; } } catch (e) { /* storage may be blocked */ }
  function saveSession() { try { window.sessionStorage.setItem(STORE_KEY, JSON.stringify(session)); } catch (e) { /* ignore */ } }

  function score(c, o) {
    if (c < 0) return o === 3 ? -25 : 0;
    if (o === 3 && c < 3) return -25;
    if (c === o) return 100;
    if (c > o) return (c - o) === 1 ? 50 : 10;
    return (o - c) === 1 ? 25 : 0;
  }
  function levelFor(p) { var k = 0; for (var i = 0; i < LEVELS.length; i++) if (p >= LEVELS[i][1]) k = i; return k; }
  function totals(recs) {
    var t = { n: recs.length, exact: 0, within1: 0, pts: 0, time: 0, best: 0, cur: 0 };
    var run = 0;
    recs.forEach(function (r) {
      t.pts += r.pts; t.time += r.t;
      if (r.called === r.obs) { t.exact++; run++; if (run > t.best) t.best = run; } else run = 0;
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
  function parseBin(buf) {
    var ny = manifest.ny, nx = manifest.nx, n = ny * nx, nf = manifest.fields.length;
    var u8 = new Uint8Array(buf);
    var per = (nf + 3) * n;
    if (u8.length < 2 * per) throw new Error('short .bin: ' + u8.length + ' < ' + 2 * per);
    var snaps = [];
    for (var s = 0; s < 2; s++) {
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
    return fetch('deck/' + id + (b64 ? '.txt' : '.bin')).then(function (r) {
      if (!r.ok) throw new Error(id + ' ' + r.status);
      return b64 ? r.text().then(function (t) {
        var s = atob(t.trim()), u = new Uint8Array(s.length);
        for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
        return u.buffer;
      }) : r.arrayBuffer();
    }).then(function (b) { var d = parseBin(b); caseCache[id] = d; return d; });
  }

  // ------------------------------------------------------------------ case choice
  function pairsFor(game, c) {
    if (game === 'fc') return (c.t0 && c.t24) ? [{ c: c, snap: 't0', obs: c.t24.cat }] : [];
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
    var played = session.played[game];
    var pool = manifest.cases.filter(function (c) { return !played[c.id] && pairsFor(game, c).length; });
    if (!pool.length) return null;
    var recs = session.records.filter(function (r) { return r.game === game; });
    if (useWeak && recs.length >= WEAK_MIN && Math.random() < 2 / 3) {
      var w = weakestCat(recs);
      if (w >= 0) {
        var cand = [];
        pool.forEach(function (c) { pairsFor(game, c).forEach(function (p) { if (p.obs === w) cand.push(p); }); });
        if (cand.length) return cand[rand(cand.length)];
      }
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
      drawRing(ctx, g, extra.low.lat, extra.low.lon, RING_KM);
      if (extra.track) drawTrack(ctx, g, extra.track[0], extra.track[1]);
      drawLow(ctx, g, extra.low.lat, extra.low.lon);
    } else {
      tab.contours.forEach(function (c) { if (snap.f[c.key]) drawContours(ctx, g, snap.f[c.key], c, labels); });
      drawLow(ctx, g, extra.low.lat, extra.low.lon);
    }
  }

  // ------------------------------------------------------------------ legend
  function buildLegend(tab) {
    var box = $('legend'); box.innerHTML = '';
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
      box.appendChild(el('div', 'lgnote', 'Black contours: MSLP every 4 hPa. Dashed ring: 500 km around the low. The peak counts only cells inside it that are nearer this low than any other, and is the 3rd-highest cell, so one stray cell does not set it. Rain-flagged cells are left out.'));
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
  var opts = { game: 'now', mode: 'practice', weak: false };
  var cur = null, blitz = null, geom = null, tabIdx = 0, tabList = TABS, timerId = null;

  function show(id) {
    ['start', 'play', 'end'].forEach(function (s) { $(s).hidden = s !== id; });
    $('loadMsg').hidden = true;
    window.scrollTo(0, 0);
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
    $('cap').textContent = tab.name + (tab.reveal && cur.game === 'fc' ? ' (+24 h)' : '');
    buildLegend(tab);
    var snapIdx = cur.game === 'fc' && tab.reveal ? 1 : (cur.snap === 't24' && cur.game === 'now' ? 1 : 0);
    var info = cur.game === 'fc' && tab.reveal ? cur.c.t24 : cur.c[cur.snap];
    var extra = { low: info };
    if (tab.reveal && cur.game === 'fc') extra.track = [cur.c.t0, cur.c.t24];
    renderMap($('map'), geom, cur.data[snapIdx], tab, extra);
  }

  function startGame() {
    $('startMsg').textContent = '';
    blitz = opts.mode === 'blitz' ? { n: 0, recs: [] } : null;
    tabList = TABS;
    show('play');
    nextCase();
  }
  function nextCase() {
    clearTimer();
    if (blitz && blitz.n >= BLITZ_N) return endBlitz();
    var pick = pickCase(opts.game, opts.weak);
    if (!pick) {
      $('startMsg').textContent = 'You have seen every case in this game this session. Pick the other game or close the tab to reset.';
      if (blitz && blitz.recs.length) return endBlitz();
      goHome(); return;
    }
    cur = { game: opts.game, c: pick.c, snap: pick.snap, data: null, answered: false, t0: 0 };
    session.played[opts.game][pick.c.id] = 1; saveSession();
    tabList = TABS; buildTabs();
    $('result').hidden = true; $('nextBtn').hidden = true; $('answers').hidden = false;
    $('mapLoad').hidden = false; $('mapLoad').textContent = 'Loading case...';
    var played = session.records.filter(function (r) { return r.game === opts.game; }).length;
    $('pCase').textContent = blitz ? 'Case ' + (blitz.n + 1) + ' of ' + BLITZ_N : 'Case ' + (played + 1);
    $('pGame').textContent = opts.game === 'now' ? 'Right now' : 'Forecast +24 h';
    $('pBasin').textContent = pick.c.basin === 'natl' ? 'N Atlantic' : pick.c.basin === 'npac' ? 'N Pacific' : pick.c.basin;
    $('timerbar').hidden = $('pTimer').hidden = !blitz;
    buildQuestion();
    var token = cur;
    loadCase(pick.c.id).then(function (d) {
      if (cur !== token) return;
      cur.data = d; geom = makeGeom(pick.c); sizeCanvas();
      $('mapLoad').hidden = true; setTab(0);
      cur.t0 = Date.now();
      if (blitz) startTimer();
    }).catch(function (e) {
      $('mapLoad').textContent = 'Could not load this case (' + e.message + '). Tap Next.';
      $('nextBtn').hidden = false; $('answers').hidden = true;
      cur.failed = true;
    });
  }
  function buildQuestion() {
    var now = cur.game === 'now';
    $('question').textContent = now ? 'Peak wind around the circled low right now?' : 'Peak wind around this low in 24 h?';
    var nl = $('nowline');
    if (!now) { var t = cur.c.t0; nl.hidden = false; nl.textContent = 'ASCAT now: ' + CATS[t.cat] + ' (' + Math.round(t.peak) + ' kt)'; } else nl.hidden = true;
    var a = $('answers'); a.innerHTML = '';
    var names = ['None', 'Gale', 'Storm', 'HF'];
    names.forEach(function (n, i) {
      var b = el('button', 'ans', '<b>' + n + ' <kbd>' + (i + 1) + '</kbd></b><span>' + CAT_RANGE[i] + '</span>');
      b.type = 'button'; b.dataset.c = i; b.addEventListener('click', function () { answer(i); });
      a.appendChild(b);
    });
  }

  function startTimer() {
    var end = Date.now() + BLITZ_SECS * 1000, bar = $('timerbar'), tm = $('pTimer');
    function tick() {
      var left = Math.max(0, end - Date.now()), s = Math.ceil(left / 1000);
      tm.textContent = s + ' s'; tm.classList.toggle('low', s <= 10); bar.classList.toggle('low', s <= 10);
      bar.firstElementChild.style.width = (left / (BLITZ_SECS * 10)) + '%';
      if (left <= 0) { clearTimer(); answer(-1); }
    }
    tick(); timerId = setInterval(tick, 200);
  }
  function clearTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }

  function answer(called) {
    if (!cur || cur.answered || !cur.data) return;
    cur.answered = true; clearTimer();
    var obsInfo = cur.game === 'now' ? cur.c[cur.snap] : cur.c.t24;
    var o = obsInfo.cat, secs = Math.min((Date.now() - cur.t0) / 1000, 600);
    if (called < 0) secs = BLITZ_SECS;
    var pts = score(called, o);
    var rec = { game: cur.game, called: called, obs: o, pts: pts, t: Math.round(secs * 10) / 10, mode: opts.mode };
    session.records.push(rec); saveSession();
    if (blitz) { blitz.recs.push(rec); blitz.n++; }
    var tt = totals(session.records);
    updateTop();
    // result card
    var cls = called === o ? 'good' : (called >= 0 && Math.abs(called - o) === 1 && pts > 0) ? 'ok' : 'bad';
    var head = called < 0 ? 'Time up: observed ' + CATS[o] : called === o ? 'Exact: ' + CATS[o]
      : 'You called ' + CATS[called] + ', observed ' + CATS[o];
    var h = '<div class="rhead">' + head + '</div><div class="rpts">' + (pts > 0 ? '+' : '') + pts + ' pts</div>';
    if (cur.game === 'now') {
      h += '<div class="rline">ASCAT peak ' + Math.round(obsInfo.peak) + ' kt (' + CATS[o] + ')</div>';
      h += '<div class="rline">Low centre about ' + Math.round(cur.c[cur.snap].hpa) + ' hPa</div>';
    } else {
      var d = cur.c.t0.hpa - cur.c.t24.hpa, dd = Math.round(Math.abs(d));
      h += '<div class="rline">ASCAT peak at +24 h: ' + Math.round(obsInfo.peak) + ' kt (' + CATS[o] + ')</div>';
      h += '<div class="rline">' + (dd === 0 ? 'No pressure change' : (d > 0 ? 'Deepened ' : 'Filled ') + dd + ' hPa') +
        ' (' + Math.round(cur.c.t0.hpa) + ' to ' + Math.round(cur.c.t24.hpa) + ' hPa)</div>';
    }
    h += '<div class="rstats">Streak ' + tt.cur + ' &middot; Total ' + tt.pts + ' pts &middot; Best streak ' + tt.best + '</div>';
    var res = $('result'); res.className = 'result ' + cls; res.innerHTML = h; res.hidden = false;
    $('answers').hidden = true;
    var nb = $('nextBtn'); nb.hidden = false;
    nb.textContent = blitz && blitz.n >= BLITZ_N ? 'See results' : 'Next case';
    // reveal tab
    tabList = TABS.concat([REVEAL_TAB]); buildTabs(); setTab(TABS.length);
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
    return h + '</table>' + (conf.un ? '<div class="fine">' + conf.un + ' unanswered (not in table)</div>' : '');
  }
  function kpiHTML(t) {
    var pct = function (x) { return t.n ? Math.round(100 * x / t.n) + '%' : '-'; };
    var k = [[t.n, 'cases played'], [pct(t.exact), 'exact'], [pct(t.within1), 'within one'],
             [t.best, 'best streak'], [t.n ? (t.time / t.n).toFixed(1) + ' s' : '-', 'mean time per case'], [t.pts, 'total points']];
    return '<div class="kpis">' + k.map(function (x) { return '<div class="kpi"><b>' + x[0] + '</b><span>' + x[1] + '</span></div>'; }).join('') + '</div>';
  }
  function levelHTML(pts) {
    var i = levelFor(pts), nxt = LEVELS[i + 1];
    var frac = nxt ? Math.max(0, Math.min(1, (pts - LEVELS[i][1]) / (nxt[1] - LEVELS[i][1]))) : 1;
    return '<div class="level"><b>' + LEVELS[i][0] + '</b><span>' + (nxt ? (nxt[1] - pts) + ' pts to ' + nxt[0] : 'top level') + '</span></div><div class="lvbar"><i style="width:' + Math.round(frac * 100) + '%"></i></div>';
  }
  function gameSection(title, recs) {
    var h = '<h3 class="gh">' + title + '</h3>';
    if (!recs.length) return h + '<div class="empty">No cases yet.</div>';
    var conf = confusion(recs);
    return h + '<div class="read">' + readLine(conf) + '</div>' + tableHTML(conf);
  }
  function openStats() {
    var all = session.records, t = totals(all);
    var h = levelHTML(t.pts) + kpiHTML(t);
    h += gameSection('Right now', all.filter(function (r) { return r.game === 'now'; }));
    h += gameSection('Forecast +24 h', all.filter(function (r) { return r.game === 'fc'; }));
    $('statsBody').innerHTML = h; $('drawer').hidden = false;
  }
  function endBlitz() {
    clearTimer();
    var t = totals(blitz.recs), conf = confusion(blitz.recs);
    var pct = t.n ? Math.round(100 * t.exact / t.n) : 0;
    var h = '<div class="level"><b>' + t.pts + ' pts</b><span>' + pct + '% exact &middot; best streak ' + t.best + '</span></div>';
    h += levelHTML(totals(session.records).pts);
    h += '<div class="read">' + readLine(conf) + '</div>' + tableHTML(conf);
    $('endBody').innerHTML = h; show('end');
  }
  function goHome() { clearTimer(); cur = null; show('start'); }
  // startMsg is cleared whenever a game starts (see startGame)

  // ------------------------------------------------------------------ events
  function bind() {
    setupChoice('gameChoice', 'game'); setupChoice('modeChoice', 'mode');
    $('weak').addEventListener('change', function (e) { opts.weak = e.target.checked; });
    $('startBtn').addEventListener('click', startGame);
    $('againBtn').addEventListener('click', startGame);
    $('endHomeBtn').addEventListener('click', goHome);
    $('homeBtn').addEventListener('click', goHome);
    $('nextBtn').addEventListener('click', nextCase);
    $('statsBtn').addEventListener('click', openStats);
    $('closeStats').addEventListener('click', function () { $('drawer').hidden = true; });
    $('drawer').addEventListener('click', function (e) { if (e.target === $('drawer')) $('drawer').hidden = true; });
    document.addEventListener('keydown', function (e) {
      if (!$('drawer').hidden) { if (e.key === 'Escape') $('drawer').hidden = true; return; }
      if ($('play').hidden) return;
      if (e.key === 'ArrowRight') { setTab(tabIdx + 1); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { setTab(tabIdx - 1); e.preventDefault(); }
      else if (/^[1-4]$/.test(e.key) && cur && !cur.answered) answer(+e.key - 1);
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

  bind(); updateTop();
  loadManifest().then(function () { show('start'); }).catch(function (e) {
    $('loadMsg').textContent = 'Could not load the case deck (' + e.message + ').';
  });
})();
