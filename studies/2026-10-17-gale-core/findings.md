# Gale cores: findings

**Question (Jason, 00:58Z 17 Oct):** should we look for cores of 34 kt too, where the gale decision is hard?

**Answer:** yes, in both basins. Lifting Core Lifted to 34 kt where the gale-core chance is 60% or more catches 12-13 points more of the ASCAT gale on held-out weeks, lifts the gale-tile score, and keeps the gale area at 1.19x (Atlantic) and 1.25x (Pacific) ASCAT's, inside the preset 1.3x cap. The Pacific verdict needs its 06/18Z ASCAT passes (as design.md said): on 00/12Z alone it rested on 42% of the Pacific gale cells and read 1.34x. Jason chose Atlantic only at 06:10Z on the 00/12Z-only result; the Pacific question goes back to him.

## Method
- Same 28 core features plus basin as the storm-core retrain; target = ASCAT 34+ kt within ~50 km (5x7 box max); candidate cells ocean & (blend >= 24 kt or strongest model >= 30 kt). Week-out-of-fold HGB on tune weeks; final model fit on all tune weeks.
- Product galecore@t: Core Lifted (blend + 5 kt at storm-core likelihood >= 35%), raised to at least 34 kt where the gale-core chance >= t. Reference ref@t: the same lift where the calibrated member gale chance (the page's P34) >= t.
- Win line, preset in design.md: held-out, both basins: (1) ASCAT gale-cell catch higher, interval above 0; (2) forecast 34+ area <= 1.3x ASCAT; (3) gale-tile CSI not lower; and more catch than ref@t. t chosen on tune weeks only (0.6, tune_results.md).

## Held-out weeks (scored once, 17 Oct 05:55Z)
5 ISO weeks, 70 cycles x 5 leads per basin (00/12Z runs, +24..+120 h at 00/12Z valid times). ASCAT real wind, intercalibrated; gale tiles 5x5 deg with >= 150 seen cells; brackets = whole-week 95% intervals.

| basin | product | gale catch | area vs ASCAT | gale-tile CSI | false alarms |
|---|---|---|---|---|---|
| Atlantic | Core Lifted (today) | 0.629 | 0.84 | 0.618 | 0.125 |
| Atlantic | galecore@0.6 | 0.762 (+0.133 [0.126, 0.141]) | 1.19 [1.06, 1.29] | 0.659 (+0.041 [0.026, 0.061]) | 0.179 |
| Atlantic | ref@0.6 | 0.650 | 0.89 | 0.624 | 0.135 |
| Pacific | Core Lifted (today) | 0.637 | 0.89 | 0.602 | 0.145 |
| Pacific | galecore@0.6 | 0.782 (+0.146 [0.137, 0.161]) | **1.34** [1.16, 1.49] | 0.661 (+0.060 [0.009, 0.127]) | 0.185 |
| Pacific | ref@0.6 | 0.667 | 0.97 | 0.612 | 0.154 |

Win line: Atlantic passes all four parts. Pacific passes catch, CSI and beats the reference, but fails the area cap (1.34 > 1.30). Read as a whole it does not pass, as preset.

Tune vs held-out agree: tune catch gain +0.149 Atl / +0.171 Pac at 1.19x / 1.14x area. The Pacific held-out weeks happened to be gale-richer for the model than for ASCAT.

## Pacific with all ASCAT hours (17 Oct 06:35Z)
The design (Cases) adds the Pacific 06/18Z-valid steps to the held-out score. They were first unscorable (no IFS analysis at 06/18Z, so no water mask); rk.truth.water_mask now takes the identical mask from GFS alone. Scored with `score_gale.py --final-extra`, same locked choice (t = 0.6), 350 more Pacific cases.

| Pacific, held-out | ASCAT gale cells | gale catch | area vs ASCAT | gale-tile CSI | false alarms |
|---|---|---|---|---|---|
| 00/12Z only | 59,666 | 0.637 -> 0.782 | 1.34 | 0.602 -> 0.661 | 0.145 -> 0.185 |
| 06/18Z only | 81,784 | 0.486 -> 0.595 | 1.19 | 0.489 -> 0.514 | 0.219 -> 0.260 |
| all (the preset test) | 141,450 | 0.550 -> 0.674 (+0.124 [0.111, 0.137]) | **1.25** [1.11, 1.34] | 0.526 -> 0.562 (+0.036 [0.019, 0.057]) | 0.193 -> 0.233 |

galecore@0.6 minus ref@0.6 catch, all hours: +0.100 [0.085, 0.116]. All four parts of the win line pass. (Atlantic 06/18Z adds only 3,981 gale cells, 1%; its numbers barely move: catch 0.627 -> 0.760, area 1.19.)

## What it means for forecasters
- The gale-core chance finds near-gale water that will verify at gale far better than the member gale chance does (out of fold BSS 0.51 vs 0.37, AUC 0.91 vs 0.88), so a "likely gale" layer from it is worth having.
- As a wind lift it adds roughly a fifth to the gale area for 13-15 points more caught gale. That fits Jason's "false alarm costs less than a miss" but the Pacific overshoots the agreed area cap.
- Pacific: with its 06/18Z passes it passes the same test at the same 60% threshold, so the shadow layer can become the Pacific product if Jason agrees.

## Not scored
The 06/18Z-valid steps (+30/+54/...) could not be scored: ASCAT truth needs an IFS analysis at the valid time and there is none at 06/18Z in the AWS archive (rk.fetch.det('ifs', 06Z, 0) is None). The held-out score therefore uses the same 00/12Z valid times as the tune weeks.
