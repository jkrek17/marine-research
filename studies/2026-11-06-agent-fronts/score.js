// Node bridge to the front drill's scorer: loads scoreCase from the drill page (page/app.js) unchanged.
// Usage: node score.js <app.js> <manifest.json> <drawn.json>   drawn.json = {case_id: [{type, pts: [{lat, lon}, ...]}, ...]}
// Prints {case_id: {pct, rows, extras...}} as JSON.
'use strict';
const fs = require('fs'), vm = require('vm');
const [appPath, manPath, drawnPath] = process.argv.slice(2);
const src = fs.readFileSync(appPath, 'utf8');
const a = src.indexOf('var SCORE = {'), b = src.indexOf('// triple point');
if (a < 0 || b < 0) throw new Error('scoreCase block not found in ' + appPath);
const body = src.slice(a, b).replace('new URLSearchParams(window.location.search)', "new URLSearchParams('')");
const ctx = { document: {}, Math, console, URLSearchParams };
vm.createContext(ctx);
vm.runInContext(body + '\nthis.scoreCase = scoreCase; this.SCORE = SCORE;', ctx);
const man = JSON.parse(fs.readFileSync(manPath, 'utf8'));
const byId = {}; man.cases.forEach(c => { byId[c.id] = c; });
const drawn = JSON.parse(fs.readFileSync(drawnPath, 'utf8'));
const out = {};
for (const id of Object.keys(drawn)) {
  const r = ctx.scoreCase(byId[id], drawn[id], null);
  out[id] = { pct: r.pct, frontSum: r.frontSum, frontMax: r.frontMax, extraPen: r.extraPen, extras: r.extras.length,
              rows: r.rows.map(x => ({ type: x.type, len: x.len, W: x.W, matched: x.matched, drawnType: x.drawnType || null, dist: x.dist === undefined ? null : x.dist, pos: x.pos === undefined ? null : x.pos })) };
}
process.stdout.write(JSON.stringify(out));
