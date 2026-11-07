---
title: "Storm cores in a most-likely wind forecast: what can be fixed, and what cannot"
subtitle: "A study of open-ocean 10 m wind forecasts against ASCAT, North Atlantic and North Pacific, winter 2025-26"
date: "7 November 2026"
author: "Marine research project (jkrek17/marine-research). Research directed by Jason; analysis and writing by Claude."
---

## Abstract

Numerical models put ocean storms in about the right place, but the wind in the strongest part of a storm (the *core*) is too weak and too smooth. Averaging several models, which gives the smallest error on an ordinary day, flattens the cores further. We asked whether a single wind grid can be both close to the truth on average and show storm-force (48 kt) and hurricane-force (64 kt) cores. We tested this on one winter of forecasts (November 2025 to March 2026, +24 to +126 h) over the North Atlantic and North Pacific, against ASCAT satellite winds, choosing every rule on four fifths of the weeks and scoring it once on the fifth held back.

The best grid found is a model blend with a small lean toward the ensemble spread plus a lift of up to 10 kt that ramps in only where the stronger of GFS and ECMWF already shows 36 to 48 kt. Five findings:

1. **The cores can be restored.** Storm-force tiles caught rise from 28% to 74% (Atlantic) and 12% to 58% (Pacific).
2. **So can the amount.** The grid draws 1.05, 0.94 and 0.86 times ASCAT's area at gale, storm and hurricane force (Atlantic).
3. **The position cannot.** At equal area every grid tested catches the same share. Lifting changes how much is drawn, not where.
4. **The price is small but real.** 0.2 to 0.4 kt more average error, and 5 to 7 kt too strong inside the grid's own storm cores.
5. **A good most-likely field is a poor warning threshold.** Its 39 kt contour is 1.35 to 1.4 times wider, at the same coverage, than one from a field lifted only where an ensemble sees a core.

---

## 1. The problem

Gale (34-47 kt), storm (48-63 kt) and hurricane-force (64 kt and above) winds over the open ocean come mostly from the cores of extratropical lows. Getting the core right is the forecast that matters most, and a missed storm costs far more than a false alarm.

An average of models is the right starting point for most of the ocean: it cancels each model's random errors. Near a core it fails. Each model puts its core in a slightly different spot, so the average spreads and flattens all of them. The scale of the gap, on day 1 of winter 2025-26 against ASCAT storm-force cells:

| Forecast | ASCAT storm-force cells caught, day 1 |
|---|---|
| Human forecasters (issued grids) | 64% |
| GFS alone | 26% |
| Average of models | 11% |

The models are not missing the storms. Near hurricane-force lows, GFS and ECMWF had the low's central pressure within 1-2 hPa on days 1-2, yet the core wind was still **6.1 / 7.3 / 15.9 kt below ASCAT** for GFS / ECMWF / AIFS. The lows are deep enough; the wind field around them is too smooth.

**Research questions**

1. Can a grid that is close to the truth on average still show the cores?
2. If not fully, what can be fixed (amount, position) and what does it cost?

### Key terms

| Term | Meaning |
|---|---|
| Core | The small area of strongest wind near a low. |
| ASCAT | A radar on the Metop satellites that measures wind over the sea from surface roughness. Used as truth. |
| Blend | A weighted average of model 10 m wind speeds at each grid cell. |
| Ensemble spread | How much ensemble members disagree at a cell, in knots. |
| Lift / ramp | Wind added to the blend in some cells; a ramp grows smoothly with the model wind, so the field has no jumps. |
| Tile | A 5 by 5 degree box. A storm tile is one where ASCAT saw at least one 48 kt cell. |
| Catch | Share of ASCAT storm (or HF) tiles where the forecast also had 48 (or 64) kt in the cells ASCAT saw. |
| Area ratio | Forecast area at a threshold divided by ASCAT's, over the cells ASCAT saw. 1.0 = the right amount. |
| Equal-area catch | Catch after every grid is set to draw exactly ASCAT's area. It measures *placement* with the amount taken out. |
| MAE / bias | Average size of the miss / average forecast minus truth, in knots. |

---

## 2. Data and method

| Item | What was used |
|---|---|
| Period and area | Winter 2025-26 (November to March); North Atlantic and North Pacific, 30-67N, open water. |
| Forecasts | 00Z and 12Z runs, +24 to +126 h, including 06/18Z valid times where ASCAT passes. |
| Models | GFS, ECMWF (IFS) and the ECMWF AI model (AIFS), 0.25 degree; GEFS, ECMWF ENS and AIFS ENS members. |
| Truth | RSS ASCAT 0.25 degree, rain-flagged cells removed, within 90 minutes. Against buoys: -0.3 kt bias, 2.7 kt scatter. Held-out sets: 5.2 million (Atlantic) and 4.0 million (Pacific) cells. |
| Held-out weeks | An ISO week is held out when (year x 53 + week) is divisible by 5: 3-9 Nov, 8-14 Dec, 5-11 Jan, 9-15 Feb, 16-22 Mar. Fixed before any study. |
| Rules | Each test's decision rule and pick were written down from the other (tune) weeks before the held-out weeks were scored, once. Ranges resample whole weeks. |
| Scores | Catch and false tiles at 48 and 64 kt; area ratio at 34/48/64 kt; equal-area catch; MAE on cells where ASCAT or any grid shows 30+ kt; bias sorted by the grid's own value. |
| Checks | An independent recomputation from the raw rows matched every headline number to 0.01. |

Bias was sorted by the grid's value, not ASCAT's. Sorting by ASCAT makes every grid look 11-13 kt too weak at storm force, which is regression to the mean, not a real bias.

### The grids compared

| Grid | Construction |
|---|---|
| Single models | GFS, ECMWF, AIFS as they come. |
| Blend | GFS, ECMWF, AIFS (half weight) over the latest three runs, + 0.25 x member spread (capped at 5 kt). The spread term restores the gale area averaging removes (gale-area bias 0.71 to about 1.0). |
| Ensemble-lifted blend | Blend + 5 kt where an ensemble-trained storm-core likelihood is 35% or more; 34 kt where a gale-core chance is 60% or more. |
| **Ramped blend** | Blend + 0-6 kt as the stronger of GFS/ECMWF goes 36-40 kt, + 0-4 kt more over 44-48, + 0-6 kt more over 52-56 where 30%+ of GEFS members have 48 kt nearby; 34 kt where the gale-core chance is 80%+ (Figure 1). |
| Deterministic-only version | GFS + ECMWF blend (no AIFS, no members), the same ramps over 38-42 / 48-52 kt, and an optional 52-56 kt ramp gated on GFS 925 mb wind x stability >= 55 kt. |

![Figure 1. Wind added to the blend as a function of the stronger of GFS and ECMWF at the cell. Each set of ramps was tuned on its own blend. The dashed hurricane-force ramp applies only where its gate is met.](fig_ramp.png)

---

## 3. Results

### 3.1 The cores can be restored

| Held-out, Atlantic / Pacific | Storm tiles caught | HF tiles caught | 30+ kt cell MAE (kt) |
|---|---|---|---|
| GFS | 42% / 38% | 17% / 7% | 6.3 / 6.0 |
| ECMWF | 32% / 18% | 10% / 7% | 5.8 / 5.2 |
| Blend | 28% / 12% | 2% / 0 | 4.79 / 4.43 |
| Ensemble-lifted blend | 62% / 40% | 16% / 7% | 4.68 / 4.46 |
| **Ramped blend** | **74% / 58%** | **61% / 40%** | 5.02 / 4.80 |
| Deterministic-only ramped | 75% / 63% | 57% / 20% | 5.48 / 5.16 (ramped blend 5.18 / 4.89 on the same cases) |

Lifting where the stronger model is already strong catches more cores than lifting where an ensemble-trained likelihood points (+12 / +18 points storm), and nearly four times the hurricane-force tiles. The ensembles add little here: scaling or gating the ramp by the core likelihood lost catch at every threshold tried, and the deterministic-only version catches as much storm force, for about 0.2-0.3 kt more error. Sample: 741 Atlantic and 181 Pacific storm tiles; 122 and **15** HF tiles.

![Figure 2. Held-out storm and hurricane-force catch.](fig_catch.png)

### 3.2 The amount can be restored

| Grid area / ASCAT area, Atlantic / Pacific | Gale (34 kt) | Storm (48 kt) | HF (64 kt) |
|---|---|---|---|
| Blend | 0.85 / 0.81 | far too little | 0.00 / 0.00 |
| **Ramped blend** | **1.05 / 1.13** | **0.94 / 0.87** | **0.86 / 0.46** |
| Deterministic-only, no HF ramp | 0.95 / 1.06 | 1.06 / 1.21 | 0.57 / 0.64 |
| Deterministic-only, with HF ramp | 0.95 / 1.06 | 1.06 / 1.21 | 1.13 / 1.18 |

Gale for the ramped blend is held-out; the rest is the whole winter (HF on 10,203 Atlantic and 228 Pacific ASCAT cells; the held-out weeks hold too few HF cells to judge area, and alone they had suggested the HF ramp over-draws at 1.68x).

- The gale-core chance threshold sets the gale area: at 60% the grid drew 1.27 / 1.38 times ASCAT's gale area, at 80% 1.05 / 1.13, with storm and HF unchanged and error within 0.04 kt.
- Without a hurricane-force ramp, a storm-tuned lift draws only about half of ASCAT's HF. With it, about the right amount.

### 3.3 The position cannot

| Equal-area catch, Atlantic / Pacific | Storm tiles (held-out) | HF cells (whole winter) |
|---|---|---|
| Blend | 0.60-0.62 / 0.40-0.42 | 32% / 15% |
| Ensemble-lifted blend | 0.60-0.62 / 0.40-0.42 | - |
| Ramped blend and every variant | 0.60-0.62 / 0.40-0.42 | 31% / 17% |
| Deterministic-only (with or without HF ramp) | - | 28% / 9% |

When each grid draws exactly ASCAT's area, all of them land on the same share. A lift changes a cell's wind using only what the models already show there; if no model has the core in the right cell, no lift can move it. **Lifts fix the amount, not the place.** In the Atlantic about 70% of ASCAT's hurricane-force cells fall outside a correctly sized HF area, because the models' cores sit a little off the real ones. Only better models or shorter lead times improve that.

### 3.4 The price: a little error, and hot cores

| Held-out, Atlantic / Pacific | 30+ kt cell MAE (kt) | Bias where the grid shows 48-63 kt | Storm tiles caught |
|---|---|---|---|
| Blend, AIFS full weight (lowest error) | 4.68 / 4.30 | -6.2 / -5.0 | 23% / 8% |
| Blend | 4.79 / 4.43 | -5.4 / -2.5 | 28% / 12% |
| Ramped, ramps half size | 4.79 / 4.57 | 0.0 / +2.3 | 55% / 36% |
| **Ramped blend** | **5.02 / 4.80** | **+4.6 / +6.9** | **74% / 58%** |
| Ramped, ramps 1.5 x | 5.45 / 5.10 | +8.1 / +10.5 | 87% / 76% |

- **Error and catch are one trade.** Every grid falls on one curve (Figure 3): each knot of added error buys storm catch. The ramped blend sits where the gain per knot starts to flatten.
- **No cheaper variant passed** the rule set beforehand (lower error in both basins, losing no more than 2 points of storm catch and no HF catch). AIFS at full weight cut 0.15 kt but lost 2-4 points storm and 7-13 HF; later ramps cut 0.15-0.19 kt but lost 2-3 storm and 7-11 HF; half-size ramps cut 0.23 kt but lost 20-22 storm.
- **The grid is hot where it draws storm force** (Figure 4): ASCAT averaged 4.6 kt (Atlantic) and 6.9 kt (Pacific) less. This follows from finding 3: a correctly sized core that is partly misplaced puts storm force over water that is not. Part is the referee: where SMAP saw the same 48-56 kt cells it read 0.4-2.0 kt above ASCAT.

![Figure 3. Every grid on one trade-off: left is closer to ASCAT, up catches more storm tiles. The ramped blend (labelled Best Wind, orange) sits at the knee; Core Lifted is the ensemble-lifted blend.](../../studies/2026-11-07-most-likely-wind/fig1_tradeoff.png)

![Figure 4. Bias sorted by the grid's own value. Where the ramped blend shows storm force, ASCAT averages 5-7 kt less; the plain blend runs low there.](../../studies/2026-11-07-most-likely-wind/fig2_own_band.png)

### 3.5 A good most-likely field is a poor warning threshold

A warning area has a different goal: cover nearly all of the event, accepting extra area. The 39 kt contour of each field, held-out, against ASCAT 48 kt cells with a 60 nm reach:

| Storm contour | Atl covered | Atl area / ASCAT | Pac covered | Pac area / ASCAT |
|---|---|---|---|---|
| Ensemble-lifted blend >= 39 kt | 83% | 2.07x | 67% | 3.4x |
| Ramped field, same coverage (41 / 43 kt) | 84% | 2.78x | 70% | 4.8x |

For the same coverage the ramped field's contour is 1.35 (Atlantic) and 1.4 (Pacific) times wider, because the ramps lift broad near-storm areas. The ensemble core likelihood, which added nothing to the most-likely grid, is the better guide to *where* a storm is possible. Other warning thresholds follow the same logic: the strongest single model at 30 kt covers about 97% of ASCAT gale water; the strongest model at 44 kt, where 1% or more of members reach 64 kt, catches 81% of hurricane-force lows within 150 km.

### 3.6 What did not help

| Idea | Held-out result |
|---|---|
| Lift the whole grid | Never paid |
| Highest model + ramps as the grid | 1.6-2.9x ASCAT's storm area |
| Ensemble core likelihood on top of the ramps | Lost catch at every threshold |
| Mix the 925 mb wind down in unstable air | GFS 10 m already carries 0.81 of it there and is unbiased; lifted cells verified at gale 10% (Atl) / 3% (Pac) |
| 30 m winds or a stability switch | Lost to the 10 m blend everywhere |
| Average bias correction | -4 to -12 points storm catch |
| Retrained core model; deepening-rate lift; satellite clues for HF | No gain |
| Weighting models by recent skill; wind from the pressure gradient | Worse |
| Machine-learned blend | Did not beat the simple blend |

---

## 4. Discussion

The cores are weak because the model wind fields are too smooth, not because the lows are too shallow. That is why a lift keyed to each model's own strong wind works and why correcting pressure does not. It also explains the limit: a lift can only raise wind where a model already has a core, so it restores the amount of storm and hurricane force but cannot move it. At equal area, every grid tested, from the plain blend to the most aggressive lift, puts the same share of its strong wind on the real core.

This makes error and core catch a single trade rather than two goals. A field built to minimise error must leave cores out, because the cores it draws are partly in the wrong place. A field that draws the right amount of core will be too strong over some water and too weak over other water. The defensible choice for a most-likely grid is the one that draws the right *amount*, which the ramped blend does at gale, storm and (Atlantic) hurricane force. The *possible* wind, which must cover misplaced cores, needs a wider area built from a different signal; and the ensembles, which add nothing to the most-likely grid, earn their keep there.

---

## 5. Limitations

- **One winter** (November to March). The warm season is untested.
- **Five held-out weeks.** Ranges are tighter than another winter would allow; one mid-December week holds 37% of the Atlantic storm events.
- **Pacific hurricane force is thin**: 15 held-out tiles, 228 ASCAT cells all winter.
- **ASCAT** reads low in the strongest cores, is blind within 25-30 km of ice and steep coasts, and has been in an outage since 12 October 2026.
- **Untested:** the subtropics, tropical cyclones, fast-deepening lows with a 12-18 h timing split between model families, and models other than GFS, ECMWF and AIFS.

---

## 6. Conclusion

A blend of models is the most accurate wind on average and the worst guide to a storm core. Raising the blend only where a model already shows a strong core restores the cores (storm-force catch 28% to 74% Atlantic, 12% to 58% Pacific) and the right amount of gale, storm and hurricane force, for a few tenths of a knot of average error. It cannot put the cores in a better place: at equal area every grid catches the same share. The most-likely grid should therefore aim for the right amount, and the possible wind belongs in a separate, wider warning area built from the ensemble.

---

## References (studies in jkrek17/marine-research)

| # | Study | Location | Pull requests |
|---|---|---|---|
| 1 | Wind blend experiment | `/mnt/project-files/wind-focus/experiment/` | - |
| 2 | ASCAT as referee; stability and 30 m winds; storm-force cores | `/mnt/project-files/wind-focus/ascat/`, `stability30m/`, `core/` | - |
| 3 | AIFS in the blend | `studies/2026-10-16-aifs-in-blend/` | - |
| 4 | Desk added value | `studies/2026-10-16-desk-value/` | - |
| 5 | Storm-force truth (SMAP vs ASCAT) | `studies/2026-10-16-storm-force-truth/` | - |
| 6 | Warning forecast experiment | `studies/2026-10-16-warning-forecast/` | - |
| 7 | Gale cores | `studies/2026-10-17-gale-core/` | - |
| 8 | Too shallow or too smooth (HF depth) | `studies/2026-10-18-hf-depth/` | - |
| 9 | Bias correction on the ensemble-lifted blend | `studies/2026-11-05-core-lift-bias/` | #70 |
| 10 | Strong-core lift | `studies/2026-11-06-strong-core-lift/` | #73 |
| 11 | Ramped lifts, HF ramp, warning contours | `studies/2026-11-06-gfe-wind-tool/` | #78, #84, #85, #87, #90, #91, #96 |
| 12 | 925 mb mix-down | `studies/2026-11-06-925-mixdown/` | #97 |
| 13 | The wind grid as a most-likely wind (gale threshold, deterministic-only scoring, HF amount over the whole winter) | `studies/2026-11-07-most-likely-wind/` | #98, #99, #100, #101 |

Every number comes from the findings file of its study; the "did not help" list draws also on the rows in `STUDIES.md`. The two new figures list their numbers and source in a CSV beside the image.
