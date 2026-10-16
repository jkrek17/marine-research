# Chance calibration, GEFS only, first look

*2026-10-16 · both basins (Atlantic 12 UTC, Pacific 00 UTC) · winter 2025-26 cycles already in the store (Atlantic 47 cycles, 1 Nov-17 Dec; Pacific 54, 1 Nov-24 Dec), +24 to +120 h · truth: ASCAT 3x3 box mean, real 10 m wind, Metop offset met halfway · GEFS member fraction only*

**GEFS only, first look. The page pools GEFS, ECMWF ENS and AIFS ENS, and none of these curves is for the page.** The store has no ECMWF or AIFS ensembles yet, and only Nov-Dec cycles, so this is a rehearsal of the method, not a recommendation.

## The answer
- **Atlantic GEFS chances run high against ASCAT, not low.** In the +24/48 h group a 30% gale chance is a 17% chance in ASCAT's box (it takes about 43% raw to earn a true 30%); a 30% storm chance happens 43% of the time (it takes about 22% raw). So GEFS over-states gale and under-states storm, in the Atlantic. This is the opposite sign to the pooled page chances at gale (the verification page: raw 30-40% gale verified 43-46%), so do not carry GEFS numbers across.
- **Pacific GEFS is close to honest** at gale (30% raw is 23% true, remap changes Brier skill 0.62 to 0.62) and at storm (30% raw is 31% true at +24/48 h) on few events.
- **The remap helps where there are events and does little elsewhere.** Atlantic gale and storm: reliability error falls (gale +24/48 h 0.048 to 0.012; storm 0.030 to 0.019) and Brier skill edges up (0.59 to 0.61; 0.43 to 0.47). The Pacific barely moves, and at storm it is slightly worse (0.30 to 0.29), because the tune weeks hold too few storm cells.
- **Hurricane force cannot be calibrated from this.** In the held-out weeks 64 kt in the ASCAT box happened in 4, 3 and 3 Atlantic cycles (151, 70 and 132 cells for the three lead groups) and 2, 1, 2 Pacific cycles (2, 1, 2 cells). Far below the ~30 cycles needed. Brier skill is negative for both raw and remapped, and the curve stays on the raw chance.

## The evidence
Held-out weeks only (14 cycles per basin; weeks, not cells, are the independent sample, so cell counts overstate the evidence). Truth ASCAT 3x3 box.

| Basin | Chance | Lead | Held-out cycles with an event | Brier skill raw | remapped | Reliability error raw | remapped | Raw share = true 30% | True chance at raw 30% |
|---|---|---|---|---|---|---|---|---|---|
| Atlantic | gale 34 | +24/48 | 14 of 14 | 0.586 | 0.613 | 0.048 | 0.012 | 42.6% | 17.5% |
| Atlantic | gale 34 | +72 | 13 of 13 | 0.397 | 0.421 | 0.054 | 0.034 | 33.4% | 26.7% |
| Atlantic | gale 34 | +96/120 | 14 of 14 | 0.269 | 0.271 | 0.042 | 0.041 | 30.0% | 30.0% |
| Atlantic | storm 48 | +24/48 | 12 of 14 | 0.435 | 0.472 | 0.030 | 0.019 | 22.0% | 42.7% |
| Atlantic | storm 48 | +72 | 8 of 13 | 0.333 | 0.361 | 0.030 | 0.022 | 16.8% | 40.7% |
| Atlantic | storm 48 | +96/120 | 12 of 14 | 0.328 | 0.334 | 0.019 | 0.015 | 15.3% | 36.8% |
| Pacific | gale 34 | +24/48 | 13 of 14 | 0.623 | 0.622 | 0.023 | 0.023 | 39.3% | 22.6% |
| Pacific | gale 34 | +72 | 10 of 14 | 0.516 | 0.518 | 0.032 | 0.030 | 31.4% | 28.4% |
| Pacific | gale 34 | +96/120 | 11 of 14 | 0.349 | 0.350 | 0.039 | 0.029 | 55.5% | 24.3% |
| Pacific | storm 48 | +24/48 | 4 of 14 | 0.301 | 0.286 | 0.008 | 0.011 | 29.2% | 30.8% |
| Pacific | storm 48 | +72 | 4 of 14 | 0.171 | 0.147 | 0.019 | 0.021 | 30.0% | 30.0% |
| Pacific | storm 48 | +96/120 | 7 of 14 | 0.170 | 0.182 | 0.015 | 0.014 | 30.7% | 29.2% |

The raw share that earns a true 90% storm chance is 88-90% in every group (the curve is flat or at the raw chance at the top, so this says little). Brier skill is against the held-out base rate. Reliability error is the weighted RMS gap between forecast and observed frequency over the bins (0.03 = three points). The Pacific gale +96/120 h 55% is one noisy bin; do not read it. Against the analysis the picture changes: the same GEFS storm chance has raw Brier skill of -0.13 (Atlantic) and -0.03 (Pacific), and the remap lifts it to 0.36 and 0.28, because analyses see 48 kt far less often than ASCAT (2,549 Atlantic held-out cells against 6,138). Single-cell ASCAT gives nearly the same numbers as the box (e.g. Atlantic storm +24/48 h Brier skill 0.428 raw, 0.468 remapped), so smoothing to 75 km does not change the answer here.

Figures: `reliability_box_{34,48,64}.png` (main), `reliability_cell_*`, `reliability_anl_*`. Data: `results.csv`, `reliability_bins.csv`, `curves.json` (page layout, ASCAT box), `curves_all_truths.json`.

## What it does not show
- Anything about the page's pooled chances: no ECMWF ENS or AIFS ENS. The GEFS over-forecast at gale may be GEFS alone.
- Anything beyond 1 Nov-24 Dec 2025: the store holds no later winter cycles yet. Fit weeks are 33 Atlantic and 40 Pacific cycles, held-out 14 each (a few weeks); the weeks are the sample.
- Hurricane force (above), and Pacific storm force: 4 to 7 cycles with an event.
- The core-likelihood product and the 90% HF rule, whose inputs are not in the store.

## How it was done
- Chance: GEFS member fraction p34/p48/p64 (31 members) from `rk.store`; nothing downloaded for models.
- Truths: `rk.truth.ascat_grid` (rain dropped, real 10 m wind, `intercal` on, cells snapped with floor(x+0.5), box kept where 6 of 9 cells valid, event = box mean at or above the threshold); single-cell version; `rk.truth.analysis` mean speed inside its mask.
- Split `rk.cases.held_out` on the cycle date; remap fitted on tune weeks per basin x truth x threshold x lead group with `rk.calibrate.fit` (the page's fitter, bins fine under 10%, nmin 2000), scored once on held-out weeks.
- Code: `studies/2026-10-16-chance-calibration/run_first_look.py`; `rk/calibrate.py`.
- Not yet checked by an independent recompute.
