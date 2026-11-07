---
title: "Drawing the most likely wind and the warning separately: how the Best Wind grid was built and tested"
subtitle: "A research report on open-ocean wind guidance for the OPC marine desk, winter 2025-26"
date: "7 November 2026"
author: "Marine research project (jkrek17/marine-research). Research directed by Jason; analysis and writing by Claude."
---

## Abstract

Weather models put ocean storms in about the right place, but their winds in the strongest part of a storm (the *core*) are too weak and too smooth. Averaging several models, which gives the best wind on an ordinary day, makes this worse, because each model's core sits in a slightly different spot and the average flattens all of them. We tested, on one winter of forecasts (November 2025 to March 2026) over the North Atlantic and North Pacific, how to build a wind grid that is right on average and still shows storm-force and hurricane-force cores. The referee was the ASCAT satellite wind. Every rule was chosen on four fifths of the weeks and scored once on the fifth that was held back.

The result, called **Best Wind**, is a blend of GFS, ECMWF and the ECMWF AI model, plus a small lean toward the ensemble spread, plus a lift of up to 10 kt that ramps in only where the stronger of GFS and ECMWF already shows 36 to 48 kt. On the held-back weeks it caught 74% of ASCAT storm-force areas in the Atlantic and 58% in the Pacific, against 28% and 12% for the plain blend, and over the whole winter it drew about as much storm-force water as ASCAT saw (0.94 and 0.87 times). The price is about 0.2 to 0.4 kt more average error and a field that runs 5 to 7 kt hot inside its own storm cores. No lift we tried put cores in a better place: at equal area every grid caught the same share. So the grid carries the *most likely* wind, and separate warning lines carry the *possible* wind. A version for AWIPS GFE, Make_BestWind, uses only GFS and ECMWF and scores about the same.

---

## 1. Introduction

The Ocean Prediction Center (OPC) marine desk issues wind grids, warning areas and the High Seas Forecast (HSF) text for the North Atlantic and North Pacific. The desk's job is hardest in the strongest storms. Gale (34 to 47 kt), storm (48 to 63 kt) and hurricane-force (64 kt and above) warnings depend on getting the core winds right, and a missed storm costs far more than a false alarm.

Earlier work in this project (Section 4.1) showed that an average of several models is the best starting wind for most of the ocean. The same average is a poor guide to storm cores. This report asks one question in two parts:

1. **What wind grid is closest to the truth and still shows the storm cores the desk must warn for?**
2. **If the grid cannot do both, which job belongs to the grid and which to the warning areas?**

The answer came out of about twenty linked studies run between 13 October and 7 November 2026. This report puts them in order, gives the number each step earned, and lists what was tried and dropped.

### Key terms

| Term | Meaning in this report |
|---|---|
| Gale / storm / HF | Sustained 10 m wind of 34-47 kt / 48-63 kt / 64 kt or more. HF = hurricane force. |
| Core | The small area of strongest wind near a low, usually in the cold sector or along a bent-back front. |
| ASCAT | A radar on the European Metop satellites that measures wind over the sea from the roughness of the surface. Our referee ("truth"). |
| Blend | A weighted average of the models' 10 m wind speeds at each grid cell. |
| Ensemble spread | How much the ensemble members disagree at a cell, as a standard deviation in knots. |
| Lift | Wind added to the blend in some cells, never taken away. |
| Ramp | A lift that grows smoothly with the model wind (for example from 0 kt at 36 kt to 6 kt at 40 kt), so the field has no jumps. |
| Tile | A 5 by 5 degree box. A storm tile is one where ASCAT saw at least one 48 kt cell. |
| Catch | The share of ASCAT storm (or HF) tiles where the forecast also had 48 (or 64) kt in the cells ASCAT saw. Also called probability of detection. |
| False tile | A tile where the forecast had storm force and ASCAT did not. |
| Area ratio | Forecast area at a threshold divided by ASCAT's area at the same threshold, over the cells ASCAT saw. 1.0 means the right amount. |
| Equal-area catch | Catch measured after every grid is set to draw exactly ASCAT's area. It tests *placement* with the amount taken out. |
| MAE | Mean absolute error: the average size of the miss in knots, ignoring sign. |
| Bias | Average forecast minus truth, in knots. Positive = forecast too strong. |
| CSI | Critical success index: hits divided by (hits + misses + false alarms). One number that punishes both misses and false alarms. |
| Held-out weeks | Weeks never used to choose a rule; scored once at the end (Section 3.1). |

---

## 2. Data

| Item | What was used |
|---|---|
| Period | Winter 2025-26 (November to March), plus earlier analysis-based tests in fall 2025 and spring 2026. |
| Area | The two OPC basins, 30-67N, open water only (the "tested area"). |
| Forecast runs | 00Z and 12Z cycles; forecast hours +24 to +126 every 24 h, with the 06/18Z valid times in between where ASCAT passes (most of the Pacific passes fall there). |
| Deterministic models | GFS, ECMWF (IFS) and the ECMWF AI model (AIFS), 0.25 degree, from the AWS open-data archive. For the GFE tests, GFS and ECMWF only (what AWIPS has). |
| Ensembles | GEFS (31 members), ECMWF ENS (51) and AIFS ENS: spread, chances of 34/48/64 kt, and the storm-core likelihood model. |
| Other fields | GFS 925 mb wind, GFS sea-surface (skin) and 2 m air temperature for the stability tests. |
| Truth | RSS ASCAT version 2.1 (Metop-B and -C), 0.25 degree, rain-flagged cells removed, within 90 minutes of the valid time. A buoy check gave ASCAT a bias of -0.3 kt and a scatter of 2.7 kt. Held-out sets hold 5.2 million (Atlantic) and 4.0 million (Pacific) ASCAT cells. |
| Earlier truth | The first blend tests (Section 4.1) used the GFS and ECMWF analyses and buoy and ship winds, before ASCAT was set up as referee. |

All model fields come from one shared store and are read through the project's code library (`rk/`), so every study scores the same cells the same way.

---

## 3. Methods

### 3.1 Held-out weeks

A rule tuned and scored on the same storms looks better than it is. So every study used one fixed split, set on 16 October 2026 and never changed: an ISO week is **held out** when (year x 53 + week number) is divisible by 5. That keeps about one week in five. For winter 2025-26 the held-out weeks were:

| ISO week | Dates |
|---|---|
| 2025 week 45 | 3-9 November 2025 |
| 2025 week 50 | 8-14 December 2025 |
| 2026 week 2 | 5-11 January 2026 |
| 2026 week 7 | 9-15 February 2026 |
| 2026 week 12 | 16-22 March 2026 |

The other weeks are **tune weeks**. Each study wrote its decision rule and its pick from the tune weeks into a file *before* the held-out weeks were scored, and the held-out weeks were scored once. Uncertainty ranges (in square brackets) come from resampling whole weeks, which respects the fact that cases in the same week share storms.

### 3.2 Scores

- **Catch and false tiles** (storm and HF) on 5 by 5 degree tiles. Tiles forgive a core that is off by a couple of hundred miles, which suits a warning but flatters a grid. So we also report:
- **Area ratio** at 34, 48 and 64 kt: is the grid drawing the right *amount*?
- **Equal-area catch**: is it drawing it in the right *place*?
- **MAE** over the cells where ASCAT or any candidate grid shows 30 kt or more (the same cells for every grid), and over all water.
- **Bias sorted by the grid's own value** (for example, "where the grid shows 48-63 kt, how strong was ASCAT?"). Sorting by ASCAT's value instead makes every grid look 11-13 kt too weak at storm force. That is a statistical trap (regression to the mean), not a real bias.

### 3.3 Checks

Each headline number was recomputed from the raw row files by a second, independent agent that did not read the write-up. Every value in the most-likely-wind study matched to 0.01 kt and 0.01 catch.

---

## 4. Results

The work ran as a chain. Each step below says what was tried, what it earned on held-out weeks, and what was kept.

### 4.1 Start with a blend, and lean toward the spread

The first experiment (13 October, 145 cases, analysis and buoy truth) asked what is the best way to combine GFS, ECMWF, AIFS and the ensembles. The 3-model mean was nearly unbiased in ordinary wind but drew only about 46% of the gale area in the first round of cases, because averaging flattens the peaks.

The fix was to add a fraction of the ensemble spread: **blend + min(0.25 x spread, 5 kt)** (0.15 on day 1). This is a deliberate lean to about the 60th percentile, not a bias correction.

| Change vs plain 3-model mean | Result |
|---|---|
| Gale-area bias | 0.71 to about 1.0 |
| Gale CSI (34 kt, analysis) | +0.026 |
| Buoy MAE in 25+ kt wind | -0.36 kt |
| Out of sample (40 new cycles) | Held: CSI34 +0.026, buoy MAE -0.36 kt |

Later tests tuned the blend:

| Test | Held-out result | Kept? |
|---|---|---|
| AIFS at half weight (vs full) | Gale CSI +0.012 Atl / +0.017 Pac; storm catch +2 / +8 pts | Yes |
| Older runs (12 h and 24 h) in the spread | About +2 pts storm catch, only together with the spread lean | Yes |
| Weighting models by recent skill | Skill does not persist; worse | No |
| Wind from the pressure gradient | MAE +1.1 kt, CSI34 -0.11 | No |

### 4.2 The models place the cores but make them too smooth

Before lifting anything we asked *why* the cores are weak.

- Near hurricane-force lows, GFS and ECMWF lows were within 1-2 hPa of the analysed depth on days 1-2, yet at zero depth error the core wind was still **6.1 / 7.3 / 15.9 kt below ASCAT** for GFS / ECMWF / AIFS. The lows are deep enough; the wind field is too smooth.
- On day 1 the desk caught 64% of ASCAT storm-force cells, GFS 26% and the plain blend 11%. Storm cores are where the forecaster adds the most value, and where a better first guess pays most.

So the target was clear: **lift the cores, not the whole field.** Whole-grid boosts were tested and never paid.

### 4.3 Core Lifted: an ensemble decides where to lift

The first core product (15 October) trained a model on ASCAT storm cores to give a **storm-core likelihood** at each cell, then added 5 kt where it was 35% or more. Storm-tile catch went from 15% to 49% at 15% false alarms. A **gale-core** version (17 October) raised the wind to 34 kt where a gale-core chance was 60% or more: gale catch +13 pts Atlantic and +12 Pacific, at 1.19 and 1.25 times ASCAT's gale area. Together these became **Core Lifted**, the page's main wind until 6 November.

| Follow-up test on Core Lifted | Held-out result | Verdict |
|---|---|---|
| Retrain the core model on both basins | Storm CSI .549 vs .547 Atl, .381 vs .381 Pac | No change |
| Bias correction, plain average | Storm catch -4 to -12 pts | Worse |
| +8 kt in cores instead of +5 | Atl storm catch 62 to 77%, area 0.72 to 1.25x; false tiles 78 to 190 | Candidate, superseded by ramps |

The bias-correction study made one thing plain: **Core Lifted was short of storm-force area** (0.72 times ASCAT's in the Atlantic, 0.51 in the Pacific).

### 4.4 Ramps on the stronger model

The GFE study (6 November) needed a lift that runs on AWIPS, which has deterministic GFS and ECMWF but no ECMWF members. The simplest signal turned out to be the best one: **lift where the stronger of GFS and ECMWF is already strong.** It went through four rounds, each chosen on tune weeks:

| GFE blend + lift (held-out, Atlantic) | Storm catch | Storm area | HF catch | HF area |
|---|---|---|---|---|
| GFE blend alone | 35% | 0.25x | 12% | 0.07x |
| +6 kt where stronger >= 42 | 74% | 1.02x | 26% | 0.35x |
| +6 at 42, then +6 more at 48 | 75% | 1.05x | 73% | 1.64x |
| +6 at 42, then +4 more at 48 | 75% | 1.04x | 60% | 0.93x |
| **Ramped: 0-6 kt over 38-42, 0-4 more over 48-52** | **75%** | **1.05x** | **59%** | **0.92x** |

The ramp scored the same as the steps with no jumps in the field, and became the tool's default (Figure 1). Pacific storm catch with the ramp was 64%.

![Figure 1. How much wind Best Wind adds, as a function of the stronger of GFS and ECMWF at that cell. The page ramps start 2 kt (first ramp) and 4 kt (second ramp) earlier because the page blend runs a little lower than the GFE blend. The dashed hurricane-force core applies only where its gate says so (Section 4.5).](fig_ramp.png)

Two tempting variants failed:

| Variant | Held-out result | Why it failed |
|---|---|---|
| Highest model everywhere + ramps | Atl storm catch 85% at 1.64x area; Pac 2.87x; false storm tiles 709 vs 296 | Draws far too much storm. It is a warning-area rule, not a grid. |
| Scale or gate the ramp by the ensemble core likelihood | Lost catch at every threshold tried; the tune pick was the threshold that turns it off (10%) | The stronger model already says where the core is. |

On the page blend (with the ensembles), the same ramps at 36-40 / 44-48 kt caught **75% Atl / 57% Pac** of storm tiles at 1.05x / 1.08x ASCAT's area, against Core Lifted's 62% / 41% at 0.71x / 0.51x.

### 4.5 A targeted hurricane-force core

Even with the ramps, the cores seldom reach 64 kt. A third ramp, **0-6 kt more as the stronger model goes 52-56 kt**, was tested with two gates so that it does not blanket every storm:

| HF core (held-out) | Atl HF catch | Atl HF area | Pac HF caught (of 15 tiles) |
|---|---|---|---|
| Page, no HF core | 34% | 0.65x | 2 |
| Page, gated where >= 30% of GEFS members have 48 kt nearby | **62%** | 1.33x | 6, with 0 false |
| GFE, no HF core | 59% | 0.92x | 3 |
| GFE, gated where GFS 925 mb wind x stability factor >= 55 kt | 70% | 1.67x | 6 |

The page took the GEFS gate. The GFE tool carries the 925 mb gate as an option.

**A correction from the whole winter.** On the held-out weeks alone the GFE HF core seemed to over-draw (1.67x), so it was first left Off. Scored over the whole winter (tune and held-out weeks together), the picture flips: the held-out weeks were stormier than average.

| Whole winter (tune + held-out), HF area / ASCAT HF area | Atlantic (10,203 ASCAT HF cells) | Pacific (228 cells) |
|---|---|---|
| Make_BestWind, HF core Off | 0.57 (too little) | 0.64 |
| Make_BestWind, HF core On | 1.13 (about right) | 1.18 |
| Page Best Wind (GEFS-gated HF core) | 0.86 | 0.46 |

So the HF core is needed to draw the right *amount* of hurricane force. It does not fix *where*: over the whole winter, at equal area, every grid covered about the same share of ASCAT's HF cells, 28-32% in the Atlantic (plain blend 32%, Make_BestWind 28% with or without the HF core, page Best Wind 31%) and 9-17% in the Pacific.

### 4.6 A better grid can be a worse warning line

Before the page switched from Core Lifted, the storm warning line and the HSF storm draft (both drawn where the field is 39 kt or more) were re-scored on the new field (held-out, covering ASCAT 48 kt cells with the 60 nm reach):

| Storm warning line | Atl covered | Atl area / ASCAT | Pac covered | Pac area / ASCAT |
|---|---|---|---|---|
| **Core Lifted >= 39 kt (kept)** | 83% | 2.07x | 67% | 3.4x |
| New field >= 39 kt | 86% | 3.35x | 80% | 10.2x |
| New field at the same coverage (Atl 41, Pac 43 kt) | 84% | 2.78x | 70% | 4.8x |

At the same coverage the new field's line is 1.35 times wider in the Atlantic and 1.4 times in the Pacific. The ramps lift broad near-storm areas, which is right for a grid and wrong for a line; the ensemble core likelihood is the better "where" for a warning. **Decision (Jason, 6 November): the new field becomes the drawn grid (Best Wind); the storm line and HSF stay on Core Lifted.**

![Figure 2. Best Wind as drawn on the marine wind page (Atlantic, 06Z 6 November run, +72 h, before the 80% gale floor). The fill is the most likely wind; the dashed outlines are the separate gale, storm and HF warning areas.](fig_page_map.jpg)

### 4.7 Scoring Best Wind as a most-likely wind

Jason then asked the central question directly (7 November): *"if the polygon goal is to catch possible, then the grid should try to get as close to truth as possible. what is the best strategy there."*

| Held-out grid | 30+ kt cells MAE, Atl / Pac (kt) | Bias where grid shows 48-63 kt | Storm tiles caught | HF tiles caught |
|---|---|---|---|---|
| GFS | 6.3 / 6.0 | +2.5 / +8.8 | 42% / 38% | 17% / 7% |
| ECMWF | 5.8 / 5.2 | -2.3 / +10.4 | 32% / 18% | 10% / 7% |
| AIFS | 5.4 / 5.0 | (few cells) | 8% / 1% | 0 / 0 |
| Blend (page, AIFS half) | 4.79 / 4.43 | -5.4 / -2.5 | 28% / 12% | 2% / 0 |
| Blend, AIFS full weight | **4.68 / 4.30** | -6.2 / -5.0 | 23% / 8% | 0 / 0 |
| Core Lifted | 4.68 / 4.46 | -0.1 / +2.3 | 62% / 40% | 16% / 7% |
| **Best Wind (live)** | 5.02 / 4.80 | +4.6 / +6.9 | **74% / 58%** | **61% / 40%** |
| Best Wind, ramps x0.5 | 4.79 / 4.57 | 0.0 / +2.3 | 55% / 36% | 22% / 7% |
| Best Wind, ramps x1.5 | 5.45 / 5.10 | +8.1 / +10.5 | 87% / 76% | 80% / 53% |

Three findings:

1. **Error and core catch are one trade.** On error alone the plain blend wins, but it catches a quarter or less of the storm tiles. Every lift moves the grid along one curve (Figure 4): each knot of added error buys storm catch. Best Wind sits where the catch gained per knot starts to flatten.
2. **No lift places cores better.** At equal area, storm catch was 0.60-0.62 (Atl) and 0.40-0.42 (Pac) for the blend, Core Lifted and every Best Wind variant. A lift changes how much is drawn, not where.
3. **Best Wind runs hot inside its own cores** (Figure 5): where it shows 48-63 kt, ASCAT averaged 4.6 kt (Atl) and 6.9 kt (Pac) less. Part of that is the referee (Section 5.3).

The rule set before the run was: lower error in both basins without losing more than 2 points of storm catch or any HF catch. **No variant passed**: AIFS at full weight cut error 0.15-0.16 kt but lost 2-4 pts storm and 7-13 pts HF catch; ramps 2 kt later cut 0.15-0.19 kt but lost 2-3 pts storm and 7-11 HF; ramps at half size cut 0.23 kt but lost 20-22 pts storm. **Best Wind was kept.**

![Figure 3. Held-out storm and hurricane-force catch for the four main grids. Pacific HF rests on 15 tiles.](fig_catch.png)

![Figure 4. Every grid on one trade-off: left is closer to ASCAT, up catches more storm tiles. Best Wind (orange) sits at the knee.](../../studies/2026-11-07-most-likely-wind/fig1_tradeoff.png)

![Figure 5. Bias sorted by the grid's own value. Where Best Wind draws storm force, ASCAT averages 5-7 kt less; the plain blend runs low there.](../../studies/2026-11-07-most-likely-wind/fig2_own_band.png)

### 4.8 Drawing the right amount of gale

Over the whole winter Best Wind drew the right storm area (0.94 Atl / 0.87 Pac) but 1.26 / 1.30 times ASCAT's gale area. All of the excess came from the gale-core floor (blend alone 0.85 / 0.81). Raising the floor's trigger from a 60% to an 80% gale-core chance fixed it:

| Gale floor (held-out) | Gale area Atl / Pac | Gale cells caught | False gale tiles | 30+ kt MAE change |
|---|---|---|---|---|
| Chance >= 60% (old) | 1.27 / 1.38 | 78% / 69% | 835 / 504 | - |
| **Chance >= 80% (live since 7 Nov)** | **1.05 / 1.13** | 71% / 63% | 670 / 448 | -0.02 / -0.04 kt |
| Floor off | 0.95 / 1.04 | 65% / 58% | 632 / 436 | |

Storm and HF are untouched. The gale warning line (strongest model at 30 kt) still carries the possible gales. Core Lifted, the storm line and the HSF keep 60%.

### 4.9 The GFE version: Make_BestWind

Make_BestWind (awips-tools) blends GFS and ECMWF over the latest three runs (agreement-weighted, + 0.3 x run spread, capped at 5 kt), then applies the ramps of Figure 1. It has no gale floor because that needs members. Scored on the same held-out cells as the page:

| Held-out, Atl / Pac | Area vs ASCAT at 34 / 48 / 64 kt | Storm tiles | HF tiles | 30+ kt MAE |
|---|---|---|---|---|
| GFE blend alone | 0.93 / 0.25 / 0.07, 1.02 / 0.17 / 0.00 | 35% / 20% | 12% / 0 | 5.37 / 4.93 |
| **Make_BestWind, defaults** | **0.95 / 1.06 / 0.93, 1.06 / 1.21 / 0.73** | **75% / 63%** | **57% / 20%** | 5.48 / 5.16 |
| + HF core option | same / same / 1.68, same / 1.22 / 1.30 | 75% / 63% | 69% / 40% | 5.50 / 5.16 |
| Page Best Wind (80% floor) | 1.05 / 1.05 / 1.35, 1.12 / 1.06 / 0.51 | 74% / 58% | 62% / 40% | 5.18 / 4.89 |

Make_BestWind draws close to ASCAT's area at every threshold and runs about 0.2-0.3 kt worse than the page grid, the cost of having no ensemble weights and no AIFS. With the whole-winter result in Section 4.5 (marine-research #101), the HF core option is recommended On by default; that change waits on a check on AWIPS.

### 4.10 What was tried and dropped

| Idea | Result | Study |
|---|---|---|
| 30 m winds or a stability switch | Lost to the 10 m blend everywhere | Stability and 30 m winds |
| Mix the 925 mb wind down in unstable air | GFS 10 m already carries 0.81 of the 925 mb wind there and is unbiased (+0.3 kt). Lifted gap cells verified at gale 10% (Atl) / 3% (Pac) | 925 mb mix-down |
| 925 mb wind x stability as a gridded lift | Ranks HF cores no better than the core likelihood (0.801 vs 0.805) and runs 10-13 kt hot outside storms | HF mixing; strong-core lift |
| Deepening-rate lift | No gain | Warning forecast |
| Satellite (IR, air mass) clues for HF | ROC +0.06, Brier no better; not passed | HF satellite |
| Core model retrain | No change | Core lift retrain |
| Average bias correction | -4 to -12 pts storm catch | Core lift bias |
| Ensemble core likelihood on the ramp | Only lost catch | GFE wind tool |
| Highest model + ramps as the grid | 1.6-2.9x storm area | GFE wind tool |
| AIFS at full weight; smaller or later ramps | Less error, but failed the catch rule | Most-likely wind |
| Machine-learned blend (gradient boosting) | Did not beat the recipe | Wind blend experiment |

---

## 5. Discussion

### 5.1 Two products, two jobs

The clearest result is that one field cannot be both the most likely wind and the warning. A grid built to be right on average must miss most cores, because models put them a little off and a smooth field cannot reach them. A grid that reaches them is hot where it draws them. The project therefore splits the work:

| Product | Job | Built from | Judged by |
|---|---|---|---|
| **Wind grid (Best Wind / Make_BestWind)** | Most likely wind, with cores drawn at about ASCAT's amount | Blend + spread + ramps + HF core | Area ratio near 1.0 at 34/48/64 kt; error; catch |
| **Gale warning line** | Possible gale | Strongest model >= 30 kt | Coverage of ASCAT gale (about 97%) |
| **Storm warning line, HSF storm** | Possible storm | Core Lifted >= 39 kt | 93% coverage at 2.1x area |
| **HF warning line** | Possible HF | Strongest model >= 44 kt with >= 1% of members at 64 kt | 81% of HF lows within 150 km |

This matches how the desk already thinks: the grid is the forecast, the warning is the hazard. A forecaster can accept a core drawn in slightly the wrong spot in the grid, because the warning area around it is wider on purpose.

### 5.2 Why lifting cannot fix placement

Every lift changes a cell's wind using only what the models already show there. If no model has the core in the right cell, no lift can put it there. That is why equal-area catch was the same for every grid (0.60-0.62 for storm tiles, 28-32% of HF cells in the Atlantic). Better placement will come only from better models or shorter lead times. What a lift *can* fix is the amount, and Best Wind now draws close to the right amount of gale, storm and (Atlantic) hurricane force.

### 5.3 The referee runs low in the strongest cores

ASCAT measures roughness and loses sensitivity at high winds; its 0.25 degree cells also smooth small cores. Where SMAP (a second satellite) and ASCAT saw the same 48-56 kt cells, SMAP read 0.4-2.0 kt higher, and above 56 kt the truth is unsettled. So part of Best Wind's +4.6 / +6.9 kt "heat" in its own storm band is the referee. A forecaster reading the grid should treat its storm cores as a slight over-statement, not a large one.

### 5.4 What a forecaster should take from this

- Read the grid as the most likely wind. Read the lines for what is possible.
- Where Best Wind shows storm force, expect a few knots less from ASCAT; where it shows HF, the core is about the right size but may be 50-100 nm off.
- In strongly unstable air, trust GFS 10 m over ECMWF (ECMWF runs about 4 kt low there); do not mix down the 925 mb wind by rule.
- Spend desk time on storm cores, days 1-2, above all in the Pacific.

---

## 6. Limitations

- **One winter.** All tuning and testing used November 2025 to March 2026. Warm-season behaviour is untested, and the core likelihood is weaker March to October.
- **Five held-out weeks.** The ranges resample those weeks, so they are tighter than another winter would allow. One mid-December week holds 37% of the Atlantic storm events.
- **Pacific hurricane force is thin**: 15 held-out tiles and a few hundred ASCAT cells all winter. Pacific HF numbers are a rough guide.
- **ASCAT** reads low in the strongest cores, is blind within 25-30 km of ice and steep coasts (where Greenland barrier jets peak), and has had an outage at RSS since 12 October 2026.
- **The GFE tool** has not yet been run on Jason's AWIPS; its grid names for 925 mb wind and temperatures are guesses.
- **Untested**: subtropics, tropical cyclones, fast bombs with a 12-18 h timing split between model families (the blend averages two lows), CMC and UKMET.

---

## 7. Conclusion

A plain model blend is the best wind on an ordinary day and the worst guide to a storm core. Adding a quarter of the ensemble spread restores the gale area; ramping in up to 10 kt where the stronger of GFS and ECMWF already shows 36-48 kt restores the storm-force area; and a gated 6 kt hurricane-force ramp restores most of the HF area. The result, Best Wind on the page and Make_BestWind in GFE, catches about three quarters of ASCAT storm tiles in the Atlantic and about six in ten in the Pacific while drawing close to ASCAT's area at gale, storm and hurricane force. It costs a few tenths of a knot of average error and runs a few knots hot in its own cores. No lift improves *where* cores are drawn, so the wider "possible" belongs in the warning lines, which stay on their own tested rules. The test of all of this is next winter: does the desk warn more accurately, over smaller areas, in less time.

---

## References (studies in jkrek17/marine-research unless noted)

| # | Study | Location | Pull requests |
|---|---|---|---|
| 1 | Wind blend experiment (13 Oct) | `/mnt/project-files/wind-focus/experiment/` | - |
| 2 | Pressure to wind; recent MSLP skill (13 Oct) | `/mnt/project-files/wind-focus/pressure-wind/`, `mslp-skill/` | - |
| 3 | ASCAT as referee (15 Oct) | `/mnt/project-files/wind-focus/ascat/` | - |
| 4 | Stability and 30 m winds (15 Oct) | `/mnt/project-files/wind-focus/stability30m/` | - |
| 5 | Storm-force cores, Core Lifted (15 Oct) | `/mnt/project-files/wind-focus/core/` | - |
| 6 | AIFS in the blend | `studies/2026-10-16-aifs-in-blend/` | - |
| 7 | Storm-core lift retrain | `studies/2026-10-16-core-lift-retrain/` | - |
| 8 | Desk added value | `studies/2026-10-16-desk-value/` | - |
| 9 | Storm-force truth (SMAP vs ASCAT) | `studies/2026-10-16-storm-force-truth/` | - |
| 10 | Warning forecast experiment | `studies/2026-10-16-warning-forecast/` | - |
| 11 | Chance calibration | `studies/2026-10-16-chance-calibration/` | - |
| 12 | Gale cores | `studies/2026-10-17-gale-core/` | - |
| 13 | Core wind ceiling at HF lows | `studies/2026-10-17-core-ceiling/` | - |
| 14 | HF satellite pilot | `studies/2026-10-17-hf-satellite/` | - |
| 15 | Too shallow or too smooth (HF depth) | `studies/2026-10-18-hf-depth/` | - |
| 16 | Which HF winds aloft reach the surface | `studies/2026-10-18-hf-mixing/` | - |
| 17 | Time-lagged runs in the GFE blend | `studies/2026-10-29-lagged-runs/` | - |
| 18 | Bias correction on Core Lifted | `studies/2026-11-05-core-lift-bias/` | #70 |
| 19 | Strong-core lift | `studies/2026-11-06-strong-core-lift/` | #73 |
| 20 | Best GFE grid wind tool (ramps, HF core, page ramps, warning lines) | `studies/2026-11-06-gfe-wind-tool/` | #78, #84, #85, #87, #90, #91, #96 |
| 21 | 925 mb mix-down | `studies/2026-11-06-925-mixdown/` | #97 |
| 22 | The wind grid as a most-likely wind (incl. gale floor, GFE scoring, "HF amount over the whole winter") | `studies/2026-11-07-most-likely-wind/` | #98, #99, #100, #101 |
| 23 | Make_BestWind, Best Wind page layer, gale floor 80% | jkrek17/awips-tools | #157, #158, #162 |
| 24 | The forecast recipe page | awips-tools `marine_wind/page/recipe/` | - |

Every number in this report is taken from the findings file of the study named beside it in the text; the two new figures list their numbers and source in a CSV beside the image (`fig_ramp.csv`, `fig_catch.csv`).

## Appendix: the recipe as of 7 November 2026

| Step | Page (Best Wind) | GFE (Make_BestWind) |
|---|---|---|
| Blend | GFS, ECMWF, AIFS (half weight), ensemble-support weights, latest three runs | GFS, ECMWF, latest three runs (lags 12, 24 h), agreement weights |
| Spread lean | + 0.25 x member spread (0.15 at +24 h), cap 5 kt | + 0.3 x run spread, cap 5 kt |
| Storm ramps | 0-6 kt over 36-40 kt, 0-4 more over 44-48, of the stronger of GFS/ECMWF | Same, over 38-42 and 48-52 |
| HF core | 0-6 kt over 52-56 where >= 30% of GEFS members have 48 kt within ~100 km | Option: 0-6 kt over 52-56 where GFS 925 mb wind x stability >= 55 kt (recommended On) |
| Gale floor | 34 kt where gale-core chance >= 80% | None |
| Warning lines | Gale: strongest model >= 30; storm: Core Lifted >= 39; HF: strongest >= 44 with >= 1% members at 64 | Gale, storm, HF warning tools (separate) |
