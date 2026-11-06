# Best GFE grid wind tool: findings

*2026-11-06. Design card: `design.md`. Pick rule (Jason, card): most storm-tile catch with storm area no bigger than ASCAT's, gales unchanged. Picked on tune weeks, scored once on the five held-out weeks (Nov 2025 - Mar 2026).*

## Answer

**Lift the GFE blend 6 kt wherever the stronger of deterministic GFS and ECMWF is 42 kt or more.** That is the #73 rule with the switch lowered from 44 to 42 kt. It needs only det GFS and ECMWF 10 m wind, which Jason's AWIPS has. GFE tool: awips-tools `GFE/smarttools/Lift_StormCores.py`, run after the #95 blend over an ocean edit area.

Held-out, against ASCAT, 5x5 deg storm tiles (Pacific includes the 06/18Z passes):

| Wind grid | Atlantic storm catch | Atl storm area vs ASCAT | Atl false storm tiles | Pacific storm catch | Pac storm area | Pac false storm tiles | Gales |
|---|---|---|---|---|---|---|---|
| #95 blend as is | 35% | 0.25x | 28 | 22% | 0.16x | 18 | — |
| #95 + GEFS 48 kt lift | 57% | 0.65x | 91 | 38% | 0.51x | 33 | same |
| #95 + 6 kt where stronger >= 44 (#73) | 69% | 0.81x | 208 | 57% | 0.87x | 105 | same |
| **#95 + 6 kt where stronger >= 42 (pick)** | **74%** | **1.02x** | **283** | **63%** | **1.16x** | **147** | **same** |
| Page Core Lifted (needs members, AIFS) | 62% | 0.72x | 78 | 40% | 0.51x | 26 | page's own |
| Page Core Lifted + 8 kt in cores (#70) | 77% | 1.25x | 190 | 53% | 1.03x | 61 | page's own |

Paired held-out differences, whole-week intervals:
- **Pick vs #95.** Storm catch rose 39 pts in the Atlantic (36 to 42) and 42 pts in the Pacific (34 to 49). Storm CSI rose 0.19 in the Atlantic and 0.17 in the Pacific. Gale CSI moved by less than 0.003.
- **Pick vs #73 (threshold 44).** Storm catch rose 5 pts in the Atlantic (4 to 5) and 7 pts in the Pacific (3 to 11). The cost was 75 more false storm tiles in the Atlantic and 42 more in the Pacific. Storm CSI did not change (-0.005 in both basins, intervals cross 0). So 42 against 44 slides along the same curve: more catch for more area, not a better tool. The pick rule chose 42 on the tune weeks, where the storm area was 0.89x Atlantic and 0.92x Pacific. On the held-out weeks it ran slightly over ASCAT's area (1.02x and 1.16x). **If storm area must stay under ASCAT's, set the threshold to 44.**
- **Pick vs Core Lifted.**
  - Storm catch is higher: +12 pts in the Atlantic (10 to 16) and +22 pts in the Pacific (16 to 28).
  - False storm tiles: about 3.5 times as many in the Atlantic and about 5 times as many in the Pacific.
  - Storm CSI is a tie in both basins.
  - Gale CSI is 0.02-0.03 lower. That gap comes from the blend, not from the lift: #95 against the page's member blend.
- **Does it beat Core Lifted?** It catches more storm-force wind, using only what is on AWIPS. It pays for that with more false storm area. By the storm score it ties.

## Other candidates (all on #95)

- **GEFS 48 kt chance >= 50% as a storm floor.**
  - On its own: +3 pts catch in both basins.
  - On top of the lift: +1 tile, because the lift already covers those cells.
  - Left as an Off switch in the tool.
- **GEFS-gated lift** (lift only where GEFS P48 is 5% or more).
  - Atlantic: catch 73%, with 241 false storm tiles, against 76% and 308 ungated at threshold 40.
  - Pacific: 62% with 132 false tiles, against 64% with 164.
  - Fewer false storms for a little catch, but it lost the pick under the rule.
- **Strongest model + lift** (Jason's ranking: take the strongest and add about 8 kt where it is 44 or more).
  - Atlantic: same storm catch as the pick (74%), with 413 false storm tiles against 283.
  - Pacific: storm area 1.56x.
  - It loses at storm force. At HF it catches the most (Atlantic 71% of HF tiles), but at about 2x ASCAT's HF area with 114 false HF tiles.
- **Two-tier lift for HF** (+8 more where the strongest is 52 or more): Atlantic HF catch 77% at 2.4x area. Too much area.
- **AI-GFS as part of the switch** (stronger of GFS, ECMWF and AI-GFS). It made no difference: +0.6 pts Atlantic, 0 Pacific.
- **AI-GFS at half weight inside the blend** (on AWIPS; held-out weeks only, paired against the pick):
  - Atlantic: 58 fewer false storm tiles (-21%; interval -121 to -7) for -2.7 pts storm catch.
  - Pacific: 44 fewer false storm tiles (-30%; interval -79 to -9) at the same catch (-0.5 pts).
  - Pacific storm CSI +0.05 (+0.01 to +0.07).
  - The worthwhile AI-GFS step is in the blend (#95's job), not in the lift.
- **Not scorable here:** CMC and UKMET (servers blocked), and the Greenland barrier-flow rule (ASCAT is blind near the coast). The tool carries the Greenland rule as a note: trust the GFS family there.

## What it does not fix: HF

- **With the pick, HF tile catch stays low:** Atlantic 26% (30 of 115 tiles), Pacific 3 of 15. A 6 kt lift seldom carries a model core in the 50s up to 64 kt.
- **Setting lift 10 kt, threshold 44** (reported, not picked; HF was not part of the pick rule):
  - Atlantic HF catch rises from 26% to 60% (+34 pts, interval +28 to +43), with HF area 0.93x ASCAT's.
  - On the tune weeks the same setting raised HF catch from 22% to 40%.
  - Cost: storm catch -2 pts and +30 false storm tiles.
  - Pacific HF is too thin to judge: 15 held-out tiles, 4 on tune.
  - This is the best HF setting found, but it is a second setting to test, not a fix.
- **925 x stability HF ceiling check** (no wind change). It flags a 64 kt cell where GFS 925 wind x 0.70 / 0.79 / 0.83 (sea minus 2 m air < 2, 2-5, 5+ C) is under 60 kt.
  - With lift 10 / threshold 44 in the Atlantic it flagged 20% of HF cells. 88% of the flagged cells stayed under 64 kt on ASCAT.
  - Believing the flag would drop 501 false HF cells and lose 66 of 752 real ones (9%).
  - With the pick it flagged 11%, and 73% of those were right.
  - In the Pacific the flag was right 96-97% of the time, on few cells.
  - Useful as a "this HF patch is probably storm" check. Default Off until the AWIPS grid names are checked.

## Port check (what the tool reads on AWIPS)

- Fcst Wind (the #95 result).
- Det GFS and ECMWF 10 m wind: newest of the last three runs, via `grid_fetch` aliases.
- Optional:
  - the GEFS 48 kt probability grid;
  - GFS 925 mb wind, surface temperature and 2 m temperature.
  - Their names are guesses and must be checked on AWIPS.

The study lifted ocean cells only. Run the tool over an ocean edit area.

## Sample

- **Held-out:** 5 weeks, 140 cycles, about 670-690 cases per basin (+24 to +126 h). ASCAT-seen tiles only.
- **Tune:** 2392 cases. 2248 had no store inputs: shoulder-season cycles that the winter store does not hold.
- **Out-of-fold picks:** the Atlantic tune pick was stable (X_L10_T44 in all 5 folds). The Pacific moved between threshold 40 and 42 at lift 6.
- **Check:** the headline numbers were recomputed from the raw rows outside `analyze.py` and matched.

Files:
- `tune_pooled.csv`, `tune_picks.csv`, `tune_oof.csv`, `PICK.json`;
- `heldout_pooled.csv`, `heldout_paired.csv`, `hf_flag.csv`;
- rows in `RK_DATA/extra/gfe-wind-tool/`.

## Follow-up: good at both storm and HF (Jason, 16:42Z)

"so whats the best combo to be good at both storm and HF". Two-step lifts: +L where the stronger of GFS/ECMWF >= T, then +M more where it >= U (L/T 6/40, 6/42, 8/42; M 2/4/6; U 44-50). Rule set before held-out (`combo.py`): in both basins on tune weeks, gales pass, storm area <= 1.0x and storm catch within 1 pt of the one-step pick; then most Atlantic HF tile catch with HF area <= 1.0x (Pacific HF too thin: 4 tune tiles). Pick: **+6 where >= 42, then +6 more where >= 48** (tune: Atl storm 67.5%, HF 52% at 0.92x; one step 66%, 22%).

Held-out (scored once):

| Wind grid | Atl storm caught | Atl storm area | Atl false storm tiles | Atl HF caught | Atl HF area | Atl false HF tiles | Pac storm caught | Pac HF caught |
|---|---|---|---|---|---|---|---|---|
| One step +6 at 42 | 74% | 1.02x | 283 | 26% (30) | 0.35x | 17 | 63% | 3 of 15 |
| +10 at 44 | 72% | 0.96x | 313 | 60% (69) | 0.93x | 37 | 64% | 3 of 15 |
| **+6 at 42, +6 more at 48 (pick)** | **75%** | 1.05x | 304 | **73% (84)** | 1.64x | 70 | **66%** | **6 of 15** |
| +6 at 42, +4 more at 48 | 75% | 1.04x | 300 | 60% (69) | 0.93x | 37 | 65% | 3 of 15 |

Gales unchanged in all. The two-step beats both one-step settings at storm and HF. The picked HF area overshot on held-out (0.92x tune -> 1.64x held-out); "+4 more" holds 0.93x with 60% HF catch. Pacific: storm area 1.26x (pick) / 1.23x. GFE tool defaults now 6/42 then 6/48 (extra lift 0 = one step).

## Follow-up: ramp instead of steps (Jason, 16:49Z)

Jason picked +6 then +4 more, and asked about the jumps (41 -> 47, 48 -> 52) and "is there a function that would ramp it up better". Ramped lifts: lift = L x clip((stronger - start) / width, 0, 1), plus the same for the extra lift; ramps ending at the threshold or centred on it, widths 2-8 kt (`tool_score.py --ramp`, `combo.py --set ramp`, same rule as the combo pick with the step +6 at 42 / +4 at 48 as the reference). Pick: **0 -> 6 kt as the stronger model goes 38 -> 42, then 0 -> 4 kt more from 48 -> 52** (tune: Atl storm 67.1% vs steps 67.2%, HF 40% both, false storm tiles 947 vs 951).

Held-out (scored once): Atl storm 75.1% (steps 74.7%), area 1.05x, false storm tiles 296 (300), HF 59% (68/115) at 0.92x (steps 60% at 0.93x); Pac storm 64.3% (65.2%), area 1.23x, HF 3 of 15. Gale area +2% Atl, +3% Pac (ramp starts at 38 kt); gale CSI within 0.005. The ramp scores the same as the steps and has no jumps; GFE tool default.

## Follow-up: one tool for any grid, and "highest model then the ramp" (Jason, 16:54Z)

`tool_score.py --self`, `selfpick.py`. Q: lift triggered by the grid's own wind (no other model): 0 -> 6 kt over A..A+4, 0 -> 4 kt more over U..U+4, on the #95 blend, GFS alone, ECMWF alone, or the stronger of GFS/ECMWF. Y: blend below A, moving to the stronger model over A..A+4, plus the ramps. Rule per family on tune: storm area <= 1.0x and gale area <= 1.3x in both basins, most mean storm catch.

Held-out (scored once):

| Grid | Atl storm | Atl area | Atl false storm | Atl HF | Atl HF area | Pac storm | Pac area | Gale CSI Atl/Pac |
|---|---|---|---|---|---|---|---|---|
| Current tool (ramps on stronger GFS/ECMWF, 38-42 / 48-52) | 75% | 1.05x | 296 | 59% | 0.92x | 64% | 1.23x | 0.632 / 0.540 |
| Blend, own wind, 36-40 / 44-48 (tune near-miss: Pac area 1.016x) | 76% | 1.08x | 311 | 60% | 0.93x | 64% | 1.26x | 0.630 / 0.547 |
| Blend, own wind, 40-44 / 44-48 (rule pick) | 69% | 0.80x | 210 | 60% | 0.93x | 55% | 0.82x | 0.630 / 0.547 |
| ECMWF alone, own wind, 30-34 / 40-44 (rule pick) | 76% | 0.99x | 433 | 42% | 0.62x | 59% | 1.15x | 0.605 / 0.506 |
| GFS alone | no setting passed the area cap on tune (GFS + ramps 1.3-1.6x Atl, 2.3-3.2x Pac) | | | | | | | |
| Stronger model everywhere + ramps 36-40 / 44-48 | 85% | 1.64x | 709 | 71% | 1.95x | 82% | 2.87x | 0.609 / 0.492 |
| Blend below 38, stronger model + ramps above | 85% | 1.66x | 711 | 75% | 2.02x | 82% | 2.90x | 0.631 / 0.534 |
| Blend below 42, stronger model + ramps above | 70% | 0.90x | 326 | 73% | 1.99x | 62% | 1.24x | 0.632 / 0.546 |

- On the blend, triggering on its own wind (4 kt lower start, since the blend runs below the stronger model) scores the same as the current tool and leaves gales exactly as the blend; it needs no GFS/ECMWF fetch.
- Settings are grid-specific: ECMWF alone wants an earlier start (30), GFS alone runs hot and no tested setting fit.
- "Highest model, then the ramp" over-draws storm 1.6x (Atl) to 2.9x (Pac) with 2.4x the false storm tiles; it is an HF-area tool (Atl HF 71-75% at ~2x).

## Follow-up: targeted HF core (Jason, 17:23Z)

"if the forecaster is trying to add value, then lets add it where it counts the most ... we dont want to blanket HF. it should be targeted to the right areas". On top of the current tool (ramps 38-42 / 48-52 of the stronger model): an extra 0 -> E kt over U..U+4 of the stronger model, only where GFS 925 mb wind x drill stability factor >= G kt (G0 = everywhere); E 4-10, U 48-56, G 0/55/60/65/70; cases with 925 mb data (`tool_score.py --hf`). Rule on tune: storm unchanged, Atl HF area <= 1.0x, most Atl HF tile catch, ties to fewer false HF tiles. Pick: **0 -> 6 kt over 52-56, gate 55 kt** (tune Atl HF 40% -> 53% at 0.96x).

Held-out (scored once): Atl HF 59% -> 70% (81/115), HF area 0.92x -> 1.67x, false HF tiles 37 -> 68; Pac HF 3 -> 6 of 15 (false 4 -> 7); storm catch, area and gales unchanged. Same lift without the gate: 71% at 1.76x (74 false) Atl, 6 of 15 (12 false) Pac. On tune the gate matched an ungated lift of equal area (no better targeting than the model's own strength); held-out it trimmed false HF ~10% Atl / ~40% Pac for one tile. HF area overshot on held-out again (0.96x -> 1.67x). In awips-tools Make_BestWind as the "HF core" option, Off by default.

## Follow-up: the ramp lift on the web page, with the ensembles (Jason, 18:56Z)

"do we need to update our web pages to use this? is this better than core lifted? can we apply the ensemble method with the new core lift?" `tool_score.py --page`, `pagepick.py`. Every product starts from the PAGE blend (r10: GFS/ECMWF/AIFS + spread) and keeps the page's gale floor (gale-core chance >= 60% -> >= 34 kt). Families: ramps on the stronger of GFS/ECMWF (PM), ramps on the page blend's own wind (PO), PM scaled by the ensemble core likelihood (PE, x clip(P/p)), PM only where core likelihood >= p (PG); HF add-ons 0 -> 6 kt over 52-56 of the stronger model gated by GFS 925 x stability (PK) or GEFS P48 (PH). Rule per family on tune as selfpick.py (storm area <= 1.0x and gale area <= 1.3x both basins, most mean storm catch); HF add-ons: most Atl HF catch with Atl HF area <= 1.7x. Cases are 00/12Z (as the whole study).

Held-out (scored once; same cases for every page product):

| Grid | Atl storm | Atl area | Atl false storm | Atl HF | Atl HF area | Pac storm | Pac area | Pac false storm | Pac HF (of 15) |
|---|---|---|---|---|---|---|---|---|---|
| #95 blend, no lift (reference) | 35% | 0.25x | 28 | 12% | 0.07x | 22% | 0.16x | 18 | 0 |
| Core Lifted (page today) | 62% | 0.71x | 76 | 16% | 0.11x | 41% | 0.51x | 26 | 1 |
| Core Lifted +8 kt in cores | 77% | 1.25x | 187 | 23% | 0.36x | 52% | 1.04x | 61 | 1 |
| **Ramps on stronger model, 36-40 / 44-48 (PM pick)** | 75% | 1.05x | 200 | 34% | 0.65x | 57% | 1.08x | 84 | 2 |
| Ramps on page blend's own wind, 32-36 / 42-46 | 71% | 0.95x | 156 | 34% | 0.65x | 51% | 0.85x | 62 | 2 |
| PM x core likelihood (pick p = 10%, i.e. nearly off) | 75% | 1.05x | 191 | 34% | 0.65x | 57% | 1.06x | 75 | 2 |
| PM + HF core, GEFS P48 >= 30% gate | 74% | 1.00x | 178 | 62% | 1.33x | 55% | 0.96x | 70 | 6 |
| PM + HF core, no gate (925 gate lost on tune) | 74% | 1.00x | 185 | 64% | 1.36x | 55% | 0.98x | 71 | 6 |
| GFE tool on the #95 blend (reference) | 75% | 1.05x | 296 | 59% | 0.92x | 64% | 1.23x | 159 | 3 |

- **Better than Core Lifted:** the stronger-model ramp on the page blend catches 75% / 57% of storm tiles against 62% / 41%, at about ASCAT's area. Against +8 kt in cores it matches the Atlantic at 0.2x less area and adds 5 pts in the Pacific.
- **The ensemble core likelihood adds nothing on top of the ramp.** Scaling or gating the ramp by it lost catch at every threshold tried on tune; the picks are the lowest thresholds (10%, 5%), which leave the ramp almost untouched. The stronger model already says where the core is.
- **For HF, the ensemble gate is the cleaner one on the page.** GEFS P48 >= 30% matches the ungated HF core in the Atlantic (62% vs 64%) and keeps the Pacific to 0 false HF tiles (ungated 3). The 925 x stability gate (55/60) lost to no gate on tune here.
- **The page blend runs hot below gale.** Its gale area is 1.23-1.38x ASCAT's against 0.93-1.06x for the #95 blend. In the Pacific the ramps on #95 catch 64% against 57% on the page blend.
- Moving the page would also need the storm warning line (Core Lifted >= 39), the HSF storm draft and the core-lift verification re-scored, because each is built on Core Lifted. That waits on Jason.

## Lessons

- **An ensemble 'where' adds nothing once a model-triggered ramp says how much.** Scaling or gating the ramp by the ensemble core likelihood only lost catch; the tune picks were the thresholds that switch it off. Test the gate against no gate before adding it.

- **A lower switch is a slide along the curve, not a win.** Threshold 42 against 44 added 5-7 pts catch and the same share of false tiles, with storm CSI unchanged. Report CSI next to catch whenever a rule lowers a threshold.
- **An area cap set on tune weeks can overshoot on held-out weeks** (0.89x to 1.02x Atlantic, 0.92x to 1.16x Pacific). Quote both, and give the conservative setting next to the pick.
- **Jason's "take the strongest + 8" is an HF rule, not a storm rule.** It wins HF catch and loses storm area. Score a forecaster's rule at the category it was written for.
