# Best GFE grid wind tool: design card

*Status: running. Jason 2026-11-06 14:40Z picked the pick rule (question 1): most storm catch with storm area <= ASCAT's, gales unchanged. Question 2 open; working on the recommended checkbox / stand-alone step.*

**Question** (Jason, 2026-11-06, pattern drill thread): "so how do we make that a tool. does this beat core lifted? what is the best tool for GFE" and "find me the best GFE grid tool".

Read as: one GFE procedure, built only from what Jason's AWIPS has (deterministic GFS, ECMWF, AI-GFS, CMC, UKMET; GEFS 34/48/64 probability grids; no ECMWF ENS, no AIFS, no members), that gives the best 10 m wind grid for the desk. Scored on held-out weeks against ASCAT in both basins, against the GFE blend (#95) and the page's Core Lifted.

**What would change if yes:** the storm step of the GFE deterministic blend (awips-tools PR #95, or a follow-on procedure Jason checks on AWIPS). No page change.

**Truth:** ASCAT real 10 m (`rk.truth.ascat_target`; Pacific with its 06/18Z passes). The analysis beside it for where (00/12Z only).

**Baselines (same cases, rebuilt):** #95 blend (GFS + ECMWF, lagged runs); #95 + GEFS 48 kt lift; #95 + 6 kt where stronger of GFS/ECMWF >= 44 kt (#73 winner); page Core Lifted and Core Lifted + 8 kt in cores (#70).

**Candidates** (all on #95; each must beat the one before it to stay in):
1. **Strong-core lift grid:** +L kt where the stronger of GFS/ECMWF >= T; L 4-10, T 40-46 (#73 grid, re-picked on tune weeks under the new pick rule).
2. **GEFS-gated lift:** candidate 1 only where GEFS P48 (the AWIPS probability grid, 0.5 deg neighbourhood) >= g, g 5-25%. Aim: keep the catch, cut the false storm tiles.
2b. **Strongest model plus lift** (Jason's ranking 14:46Z: "add about 8 kt where a model shows 44 kt or more; when the models disagree at storm force, take the strongest"): max(#95, stronger of GFS/ECMWF + L) where the stronger >= T; L 0-10, T 40-46.
2c. **GEFS storm floor** (ranking: "GEFS 48 kt chance >= 50% verifies ~95%"): candidate 1, then at least 48 kt where the GEFS P48 grid (0.5 deg cell) >= 50%; and the floor alone on #95.
3. **Two-tier lift:** candidate 1 plus a further +L2 where the stronger model >= T2 (T2 52-60), aimed at HF. Reported; HF is too thin to pick on.
4. **AI-GFS in the trigger or base:** stronger of GFS/ECMWF/AI-GFS as the switch; AI-GFS half weight in the base. Held-out only (AI-GFS is stored for held-out weeks), fixed parameters from 1.
5. **925 x stability HF ceiling flag (no wind change):** mark cells where the tool draws 64 kt but GFS 925 wind x drill factor (0.70 / 0.79 / 0.83 by sea-air < 2, 2-5, 5+ C) < 60 kt as "HF ceiling probably storm". Scored as a flag: share of flagged 64 kt cells where ASCAT stayed below 64, and HF catch lost if the desk believed it.

CMC and UKMET are on AWIPS but not reachable from here (blocked servers), so they cannot be scored.

**Pick rule (decided now, tune weeks, per basin):** see question 1. Gales must not move: gale tile CSI within 0.01 of #95 and gale area at or under 1.3x. False storm tiles reported next to every catch. HF (64 kt) catch and area reported, not gated.

**Cases:** winter 2025-26, both basins, 00/12Z cycles, +24..+126 h incl. 06/18Z-valid steps; tune on `rk.cases.split == "tune"` (5-fold whole-week CV), held-out weeks ((y*53+w)%5==0) scored once. Paired whole-week intervals (`rk.compare.paired`). Note: the same 5 held-out weeks were scored once by #73; this study adds new products scored once on them, and picks only on tune weeks.

**Data:** all in the store (~34 GB of winter field releases + ASCAT, under the 50 GB line); one whole-winter reader at a time. No AWS pull.

**Reused / new:** reused unchanged: strong-core-lift `build.py` (cases), `score.py` counting (fit_score tiles), `rk.features.det_blend`, `rk.features.strong_lift`, `rk.compare.paired`. New: a sidecar per case with AI-GFS and GEFS P34/P64; the gate and flag as `rk.features` functions with tests, so the GFE port and any page test share one definition.

**Known traps:** win-line picks ride the area cap (#73) -> pick at equal area or under a fixed cap; 925 x stability as a gridded lift fails (desk stability study), so it is a flag only; 44/+6 was chosen partly on lows in held-out weeks (drill), the tune-week pick is the clean check; thin HF sample; Pacific dateline.

**Port check:** say for the winner exactly which AWIPS grids it reads.

**Out of scope:** chances, warning lines beyond a re-score of the 39 kt storm line, page changes, merging into #95.

## Questions for Jason
1. **What "best" means.** Most storm-force catch with storm area no bigger than ASCAT's (1.0x), gales unchanged (recommended: forecast the highest wind, but don't paint more storm than there is); or best storm-tile score counting false tiles equally (tighter, fewer false storms); or most catch under 1.5x (the old line, which rides the cap).
2. **Deliverable shape.** A separate "Core lift" checkbox step after the #95 blend in the same procedure (recommended: Jason can turn it off), or a new stand-alone smart tool.

Not scorable here: the Greenland barrier-flow rule (trust the GFS family in terrain flow); it rests on one case and OSCAT, and ASCAT is blind near the coast. The GFE port will carry it as a note, not a scored step.

## Jason's answers
1. 2026-11-06 14:40Z (card): "Most storm catch, area <= ASCAT" -> `analyze.py --rule cap1`.
