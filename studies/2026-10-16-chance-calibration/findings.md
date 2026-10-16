# Chance calibration, GEFS only, first look

*2026-10-16 · Atlantic at 00 and 12 UTC, Pacific at 00 UTC · all winter 2025-26 cycles already in the store (Atlantic 130 cycles, 1 Nov to 4 Jan; Pacific 71, 1 Nov to 10 Jan), +24 to +120 h · truth: ASCAT 3x3 box mean, real 10 m wind, Metop offset met halfway · GEFS member fraction only*

**GEFS only, first look. The page pools GEFS, ECMWF ENS and AIFS ENS, and none of these curves is for the page.** The store has no ECMWF or AIFS ensembles yet and no cycles after early January, so this rehearses the method; it is not a recommendation. ASCAT covers the Atlantic box equally at 00 and 12 UTC, so the Atlantic uses both hours (valid hour = cycle hour); the Pacific is 00 UTC only (06/18 UTC are not in the store).

## The answer
- **Atlantic GEFS gale chances run high against ASCAT; storm chances run low.** In the +24/48 h group a 30% gale chance is a 20% chance in ASCAT's box (it takes about 40% raw to earn a true 30%); a 30% storm chance happens 48% of the time (it takes about 19% raw). This is the opposite sign at gale to the pooled page chances (verification page: raw 30-40% gale verified 43-46%), so do not carry GEFS numbers across.
- **Pacific GEFS gale chances also run high** (21% true at raw 30%, +24/48 h); **storm is near honest** (31% at raw 30%) on few events.
- **The remap helps where there are events.** Atlantic +24/48 h reliability error falls from 0.049 to 0.017 (gale) and 0.030 to 0.010 (storm); Brier skill 0.592 to 0.618 and 0.459 to 0.515. The Pacific storm remap does nothing or slightly hurts (0.328 to 0.320): too few storm cells in the tune weeks.
- **Hurricane force cannot be calibrated from this.** Held-out 64 kt in the ASCAT box: Atlantic +24/48: 648 cells in 10 of 28 cycles; Atlantic +72: 297 cells in 7 of 27 cycles; Atlantic +96/120: 283 cells in 7 of 28 cycles; Pacific +24/48: 2 cells in 2 of 20 cycles; Pacific +72: 1 cells in 1 of 20 cycles; Pacific +96/120: 2 cells in 2 of 20 cycles. The Atlantic has 7 to 10 cycles with an event, the Pacific 1 to 2, far under the ~30 needed. Skill is about zero (Atlantic) or negative (Pacific) raw and remapped, and the curve stays on the raw chance.

## The evidence
Held-out weeks only (28 Atlantic cycles, 20 Pacific). Weeks, not cells, are the independent sample, so cell counts overstate the evidence; at 12 UTC and 00 UTC the same storm can appear in both. Truth ASCAT 3x3 box.

| Basin | Chance | Lead | Held-out cycles with an event | Brier skill raw | remapped | Reliability error raw | remapped | Raw share = true 30% | True chance at raw 30% |
|---|---|---|---|---|---|---|---|---|---|
| Atlantic | gale 34 | +24/48 | 28 of 28 | 0.592 | 0.618 | 0.049 | 0.017 | 40.5% | 20.1% |
| Atlantic | gale 34 | +72 | 27 of 27 | 0.487 | 0.503 | 0.044 | 0.024 | 35.1% | 25.2% |
| Atlantic | gale 34 | +96/120 | 28 of 28 | 0.352 | 0.358 | 0.023 | 0.010 | 33.4% | 26.9% |
| Atlantic | storm 48 | +24/48 | 22 of 28 | 0.459 | 0.515 | 0.030 | 0.010 | 19.2% | 48.2% |
| Atlantic | storm 48 | +72 | 15 of 27 | 0.363 | 0.393 | 0.026 | 0.013 | 15.3% | 45.8% |
| Atlantic | storm 48 | +96/120 | 21 of 28 | 0.329 | 0.322 | 0.011 | 0.010 | 15.6% | 42.5% |
| Pacific | gale 34 | +24/48 | 18 of 20 | 0.627 | 0.632 | 0.027 | 0.019 | 40.9% | 21.4% |
| Pacific | gale 34 | +72 | 14 of 20 | 0.480 | 0.490 | 0.034 | 0.022 | 34.6% | 25.2% |
| Pacific | gale 34 | +96/120 | 16 of 20 | 0.340 | 0.361 | 0.044 | 0.024 | 45.9% | 23.4% |
| Pacific | storm 48 | +24/48 | 8 of 20 | 0.328 | 0.320 | 0.013 | 0.014 | 28.9% | 30.8% |
| Pacific | storm 48 | +72 | 6 of 20 | 0.118 | 0.108 | 0.021 | 0.021 | 30.5% | 29.5% |
| Pacific | storm 48 | +96/120 | 8 of 20 | 0.150 | 0.156 | 0.013 | 0.013 | 31.0% | 28.9% |

Brier skill is against the held-out base rate. Reliability error is the weighted RMS gap between forecast and observed frequency over bins (0.03 = three points). Raw share for a true 90% storm chance is 88-90% in every group (flat tail; says little). Against the analysis, 48 kt +24/48 h raw Brier skill is -0.02 (Atlantic) and -0.30 (Pacific), lifted by the remap to 0.38 and 0.25: analyses see 48 kt far less often than ASCAT. Single cells give nearly the same as the box.

Figures: `reliability_box_{34,48,64}.png` (main), `reliability_cell_*`, `reliability_anl_*`. Data: `results.csv`, `reliability_bins.csv`, `curves.json` (page layout, ASCAT box), `curves_all_truths.json`.

## What it does not show
- The page's pooled chances (no ECMWF ENS or AIFS ENS); the GEFS gale over-forecast may be GEFS alone.
- Anything after 10 January 2026, or March; a few dozen weeks at most.
- Hurricane force, and Pacific storm force (6 to 8 cycles with an event).
- Pacific at 06/18 UTC; core likelihood and the 90% HF rule (inputs not in the store).

## How it was done
- Chance: GEFS member fraction p34/p48/p64 (31 members) from `rk.store`; no model downloads.
- Truths: `rk.truth.ascat_grid` (rain dropped, real 10 m wind, `intercal` on, floor(x+0.5) snapping, box kept where 6 of 9 cells valid), single-cell version, and `rk.truth.analysis` mean speed in its mask.
- Split `rk.cases.held_out` on the cycle date; remap fitted on tune weeks per basin x truth x threshold x lead group with `rk.calibrate.fit`, scored once on held-out weeks. Cycle hours per basin are `HOURS` in the run script.
- Code: `studies/2026-10-16-chance-calibration/run_first_look.py`; `rk/calibrate.py`. Not yet checked by an independent recompute.
