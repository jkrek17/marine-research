# The desk's stability wind tool: design card

*Status: questions to Jason posted 2026-11-06 12:32Z; building on the recommended answers meanwhile. Scoring shared with `studies/2026-11-06-strong-core-lift/` (draft PR #73) so the case set is built once.*

**Question** (Jason, via the project chat, 2026-11-06): is the desk's "stability enhanced wind" GFE tool useful but applied too widely? Read as: on held-out weeks, does the desk's rule reproduced from deterministic fields catch more ASCAT gale and storm water than the GFE deterministic blend (#95) and Core Lifted, at what cost in area, and does a version gated to strong cold-air cores keep the catch without the spread?

**The desk tools, in forecaster terms** (awips-tools `main` da421e4):
- `GFE/smarttools/Stability_Model_Blender.py` (OPC), option "Stability Height" (default 30 m): where the air is unstable, model 10 m wind x (30/10)^0.15 = **+18%**, the mask grown 2 cells and tapered. Unstable = theta at 925 mb <= theta at the surface. GFS uses 2 m air temperature and surface pressure (strict: needs a near-dry-adiabatic layer from 2 m to 925 mb); ECMWF, UKMet, ECENS use skin temperature, i.e. the SST over water (loose: most cold-sector water passes). "Entire" applies +18% everywhere. "30m Stability" swaps in GFS 30 m wind where unstable (scored 2026-10-15: loses to the 10 m blend). "Boosted": x(0.0086 x speed + 0.914), 1.0 at 10 kt up to 1.15 at 27.5 kt+, no stability.
- `GFE/procedures/Calc_MixingEfficiency.py` ("Marine Wind Adjustment"): 30 m wind (925 if 30 m missing) x 0.775-0.935 by T925 - SST (unstable below -2 C; between -2 and +2 C the stronger of model and mixed), never below the model 10 m wind; stable air with 925/10 m >= 1.3 adds 15% of the difference.
- Neither tool has a wind-speed gate.

**What would change if the answer is yes:** which stability option the desk reaches for, and a gated stability step as a deterministic GFE tool (925 wind, SST and 2 m air are all in Jason's AWIPS; no members). Any awips-tools change waits for Jason.

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat_target`), every pass near valid time, Pacific with its 06/18Z passes; winter 2025-26 is before the 12 Oct 2026 RSS outage. Beside it, all water vs the model's own analysis (00/12Z).

**Baselines:** the GFE deterministic blend (#95: GFS+IFS lagged, `det_blend`) and Core Lifted (live page layer), rebuilt on the same cases.

**Products (all fixed rules, nothing tuned, so they are set before the held-out score):**
1. SH-strict: #95 blend x 1.179 where GFS theta925 <= theta(2 m), 2-cell grown and tapered mask, raise only.
2. SH-loose: the same with skin temperature for the surface (the ECMWF form of the tool).
3. SH-everywhere ("Entire"): #95 blend x 1.179 everywhere (reference: the whole-grid boost).
4. Gated: where GFS 925 wind >= 34 kt AND GFS skin minus 2 m air >= 5 C, out = max(base, 925 wind x f), f = 1.04 (5-8 C) or 1.13 (8 C+), the drill's factors (fit at analysis time on the drill deck; the test is whether they hold as a forecast). On both #95 and Core Lifted.
5. Calc_MixingEfficiency, only if Jason says that is the tool the desk uses (needs GFS 30 m wind, not in the store).

**Win means (held-out weeks, each basin on its own, +24 and +48 h reported separately, whole-week paired 95% intervals):**
- Gale: catch of ASCAT 34+ tiles at EQUAL AREA with the baseline (the baseline's catch read off its hit-vs-area curve at the product's gale area), no worse than -2 pts; and the gale area ratio reported.
- Storm: storm-tile (5x5 deg, ASCAT 48+) catch at least +5 pts over the base it modifies, storm area <= 1.5x ASCAT, false storm tiles reported.
- "Applied too widely" is answered by where each product adds wind: share of lifted cells with ASCAT 34+ / 48+, and the bias of lifted cells below gale.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), both basins, 00Z and 12Z cycles, +24 and +48 h headline (+30/+54 for 06/18Z-valid Pacific passes), day 3-5 shown; held-out weeks `rk.cases.held_out` ((y*53+w)%5==0).

**Data:** everything in the store (GFS/IFS det, GFS low-level `t2`, `skt`, `t925`, `u925`, `v925`; ASCAT truth for the winter). No new download unless product 5 is wanted (GFS 30 m wind, ~1-2 GB for the winter at two leads).

**Reused / new:** cases, products and scoring live in the strong-core lift study's `build.py` / `score.py` (which reuses `studies/2026-11-05-core-lift-bias/fit_score.py`, `rk.features`, `rk.truth.ascat_target`, `rk.score.tile_hits`, `rk.compare.paired_counts`); this study adds only the desk-rule products and the "where does it lift" breakdown. If the stability mask proves general, it goes into `rk/features.py` with a test.

**Known traps:** condition on the forecast, never on ASCAT; whole-grid boosts win peaks and lose gales (30 m switch, whole-grid boosts, average-style corrections are dead ends: not rebuilt, product 3 is a reference only); weeks are the sample; the drill factors were fit at analysis time; ASCAT reads equivalent-neutral wind high in unstable air, so use the real-10 m conversion; Pacific dateline.

**Out of scope:** gusts, waves, the LLJ part of Calc_MixingEfficiency, any page or GFE change.

## Questions for Jason (posted 2026-11-06)
1. Which tool and option does the desk run (Stability Height / Calc_MixingEfficiency), which models, Unstable or Entire, height left at 30 m? Recommended default: Stability Height, GFS and ECMWF, Unstable, 30 m.
2. Gated version: stronger of base and 925 x factor inside the gate (never lowers)? Recommended: yes.
3. Leads: +24/+48 h headline, day 3-5 shown. Recommended: yes.
