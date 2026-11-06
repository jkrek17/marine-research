# The desk's stability wind tool (Stability_Model_Blender)

*2026-11-06 · Atlantic and Pacific, 00/12Z cycles, +24 to +126 h · winter 2025-26 · held-out: 5 weeks, 70 cycles per basin · truth: ASCAT (real 10 m, all passes; Pacific with its 06/18Z passes) · scored in `studies/2026-11-06-strong-core-lift/score.py` (branch claude/project-thread-kfr5vm), rows in `RK_DATA/extra/strong-core-lift/final_desk_rows.csv`*

## The answer
Yes, the tool is useful but applied far too widely. "Stability Height" (+18% where unstable) catches storm-force water as well as a lift aimed at the cores does. But it doubles the gale area, because almost everything it lifts is ordinary cold-sector water. Of the lifted water ASCAT saw, only 8-10% (Atlantic) and 3-5% (Pacific) was gale force. Below gale force the lifted wind runs about 3-4 kt high. The strict mask (the GFS form) and the loose mask (ECMWF form) barely differ. Both sit close to "Entire" (+18% everywhere).

The gated 925 mb mix-down (925 wind >= 34 kt and sea minus air >= 5 C, lifted to 925 x 1.04/1.13) does NOT hold as a forecast. Where it lifts, ASCAT is mostly below gale force, and those cells run +10 to +13 kt high. It draws hurricane force over 2.7-3.6x ASCAT's area. The drill factors describe the sea at analysis time near ASCAT-judged lows. At +24 h they lift too much water by too much.

The cheapest way to get the tool's storm catch without its spread is a lift aimed at the cores. The strong-core lift study's lead candidate (#95 + 6 kt where the stronger of GFS/ECMWF is 44 kt or more) catches 69% / 57% of storm tiles at 0.82 / 0.87x area, with gale unchanged. Core Lifted + 8 kt in cores (core-lift-bias study) gets 77% at 1.25x in the Atlantic.

## The evidence (held-out, all leads pooled)
| Product | Atl storm-tile catch | Atl storm area | Atl gale area | Atl lifted cells at gale (ASCAT) | Pac storm-tile catch | Pac storm area | Pac gale area | Pac lifted cells at gale |
|---|---|---|---|---|---|---|---|---|
| GFE det blend #95 | 35% | 0.25 | 0.93 | - | 22% | 0.16 | 1.02 | - |
| #95 + GEFS storm lift | 57% | 0.66 | 0.94 | - | 38% | 0.51 | 1.03 | - |
| Core Lifted | 62% | 0.72 | 1.22 | - | 40% | 0.51 | 1.28 | - |
| Desk tool, strict mask (GFS) | 75% | 1.32 | 1.88 | 10% | 60% | 1.31 | 2.53 | 5% |
| Desk tool, loose mask (ECMWF) | 77% | 1.37 | 1.97 | 9% | 66% | 1.52 | 2.63 | 4% |
| Desk tool "Entire" (+18% everywhere) | 82% | 1.46 | 2.35 | 8% | 72% | 1.97 | 3.47 | 3% |
| Gated 925 mix-down on #95 | 59% | 1.05 | 1.06 | 58% | 43% | 1.18 | 1.20 | 28% |
| Gated 925 mix-down on Core Lifted | 73% | 1.37 | 1.32 | 57% | 55% | 1.33 | 1.43 | 25% |

*Catch = 5x5 deg tiles with ASCAT 48+ seen where the forecast also has 48+ among the seen cells. Area = forecast over ASCAT, seen cells. Gale tile CSI falls from .63 (#95) to .54-.55 (desk tool) in the Atlantic and from .55 to .45 in the Pacific. Mean error on lifted cells where the base is under 34 kt: desk tool +3.1 to +3.8 kt, gated mix-down +10 to +13 kt.*

The picture is the same at +24 h and +48 h. Atlantic day 1: desk tool strict 86% storm catch at 1.55x storm area and 2.08x gale area; #95 40% at 0.25x and 0.96x.

## What it does not show
- The desk tool is applied per model and then blended in GFE. Here it was applied to the #95 blend, using GFS fields for the strict mask and ECMWF fields for the loose mask. "Boosted" and other heights were not scored.
- The strict and loose masks need low-level fields, which exist for 626 of 686 Atlantic held-out forecasts, so their Atlantic rows sit on a slightly smaller case set.
- One winter and 5 held-out weeks. No intervals yet. The numbers were recomputed here from the per-case rows and match the scoring thread's summary; an independent recheck of the scorer is still to come.
