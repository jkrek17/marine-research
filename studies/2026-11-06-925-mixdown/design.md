# Does a strong 925 mb wind mix down to gales? Design card

*Draft for Jason's answers. If he does not answer, the study runs on the recommended answers (marked **R**).*

**Question** (Jason's words): "but what if the wind is 40 kts at 925, and 15 kts at the surface. can you mix down 40 kts to get gales if the SeaMinusAir is +10" ... "i guess this still comes back to most likely wind vs warned area."

**What would change if the answer is yes:** a yes/no "mix-down" flag in Make_BestWind (the SeaMinusAir / HFCeiling925 check grids already exist) that either lifts the grid toward gale, or only widens the gale warning area, where the gap exists.

**Truth:** RSS ASCAT real 10 m wind (intercalibrated, rain-flagged cells dropped), cells within 90 min of the valid time; Pacific scored at its 06/18Z passes too. ASCAT is the only truth that says how strong; analyses run low in exactly this setting.

**Gap cells (the case Jason asks about):** GFS 925 mb wind >= 35 kt, GFS 10 m wind < 25 kt, sea minus 2 m air (GFS skin minus 2 m) >= 5 C, open water. Split 5-8 C and 8+ C, and warm-current boxes (Gulf Stream 33-44N 75-45W; Kuroshio Extension inside our Pacific domain, 30-42N 160E-175W) vs elsewhere. The read leans on the **GFS family** (its 925 and 2 m air); ECMWF 10 m is reported beside it.

**Baselines:** grid = the GFE #95 deterministic blend (GFS + ECMWF, lagged), which is what Make_BestWind lifts. Warning = today's gale line, strongest of GFS/ECMWF >= 30 kt.

**Two scores (Jason: most likely wind vs warned area):**
1. *Grid lift:* out = max(blend, 925 x f) in gap cells. Report gale (34 kt) cell catch, bias in gap cells, false gale water. **Win:** beats an equal-area control (the blend raised the same amount everywhere it is 28-34 kt, area matched on tune weeks) on held-out weeks, interval excluding zero.
2. *Warning trigger (yes/no):* gale line OR gap cell. Report ASCAT gale tiles/cells caught vs warned area, beside the 30 kt line and a 28 kt line at equal area. False alarm cheaper than a miss, so **win** = more gale catch per added warned area than lowering the line.

**Cases:** both basins, every 00/12Z cycle 1 Nov 2025 - 31 Mar 2026, steps +24 to +126 h including 06/18Z valid steps (the strong-core-lift case set). Physics read (what ASCAT showed) at +24/+30 h, where the model gap is most trustworthy; rules at all leads. Tune / held-out by `rk.cases.held_out` (about 1 week in 5); f picked on tune weeks only.

**Data:** all in the store (GFS/ECMWF 10 m, GFS 925 wind and t2/skt, ASCAT). ~600 basin-cycles x ~15 MB = ~9 GB streamed from the data releases, no AWS pull, kept clear of build windows. Cases saved small under `RK_CACHE/extra/925-mixdown`.

**Reused / new:** `rk.store`, `rk.features.det_blend`, `rk.truth.ascat_target`, `rk.score.tile_hits`, `rk.compare.paired`; the build follows strong-core-lift `build.py` without its ensemble/page pieces. New: a `gap_mask` helper in `rk.features` (with a test) so Make_BestWind and the page use one definition.

**Methods, simplest first:**
1. What ASCAT saw in gap cells: fraction >= 34 kt, ASCAT/925 ratio distribution, by band and region, vs the same 925 speeds in stable air.
2. Yes/no warning flag (no factor).
3. Grid: raise to 34 kt in gap cells.
4. Grid: raise to 925 x f (f = tune-week median ratio per band).

**Known traps:** a factor fitted near lows ran ~10 kt hot map-wide (LESSONS); 925 x stability failed as a gridded lift (gale area doubled); one cell counted at several leads (dedupe cell-times); lowering a threshold is a slide along the curve, so report CSI and area next to catch.

## Questions for Jason (recommended answers marked R)
1. Gap thresholds: 925 >= 35, 10 m < 25, sea-air >= 5 C? **R: yes**, plus a sensitivity row at 925 >= 30 and >= 40.
2. Grid baseline: GFE #95 blend **(R)**, or the page Best Wind blend as well (adds the ensemble downloads, ~3x the data)?
3. Is the warning-trigger score (gale line widened by gap cells) the one you would act on? **R: score both, lead with whichever wins.**
