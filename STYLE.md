# House style

Figures and write-ups are read by forecasters between shifts. Every rule here serves one thing: the answer is visible in a few seconds, and the same thing looks the same in every study.

## Figures (matplotlib, light background)
Call `rk.style.use()` before plotting and `rk.style.save(fig, path)` to write PNG + SVG.

**Titles say the finding.** "The blend catches 15% of storm tiles; the core lift catches 49%", not "CSI by method". Beneath it, in smaller grey text: case count, period, basin and hour, truth. Use `rk.style.title(ax, finding, detail)`.

**One colour per method, forever** (`rk.style.METHOD_COLORS`). These are the hues the models have on the web pages, stepped for white.

| Method | Colour | | Method | Colour |
|---|---|---|---|---|
| ECMWF (IFS) | blue `#2a78d6` | | Core Lifted (the live page layer: blend + 5 kt where storm-core chance is 35%+) | green `#008300` |
| GFS | orange `#eb6834` | | 3-model mean | grey `#7a7974` |
| AIFS | violet `#6250d6` | | Desk (issued) | near-black `#1f1f1d` |
| Blend | aqua `#1baf7a` | | ASCAT / buoys | red `#e34948` / amber `#eda100` |
| Member vote (day 5-7 lows: lows kept where enough members carry one) | sienna `#a0522d` | | | |

Ensemble means take their parent's colour, dashed (GEFS = GFS, ENS = ECMWF, AIFS ENS = AIFS). A method that is not in the table gets added here before it is plotted.

**Wind maps use the page's knot breaks** (0, 10, 15, 20, 25, 30, 34, 41, 48, 56, 64, 80). Below gale, light blues that recede on white; from 34 kt up, exactly the page's colours (violet above 80 kt), so a figure and the page agree at a glance. Gale, storm and HF outlines use `rk.style.HAZARD_COLORS` (the page's line hues, darkened for white).

**Errors** (forecast minus truth) use the blue-grey-red diverging map, centred on zero, symmetric limits, blue = forecast too low.

**Marks.** 2 px lines, markers 6-8 px, light grid behind data, no top or right spines, legend without a frame. Label lines directly when there are five or fewer (`rk.style.method_line`); the blend's aqua is below 3:1 contrast on white, so it is always labelled. Never two y-axes; make two panels. Leads on the x-axis in hours (+24, +48, ...).

**Every chart can be checked.** The numbers behind it go in a CSV next to the PNG with the same name.

## Write-ups (`templates/findings.md`)
1. **The answer**, in two or three sentences a forecaster can act on. Lead with what to do or not do.
2. **The evidence**: one table and at most three figures. Numbers carry their sample (cases, weeks) and their interval.
3. **What it does not show**: untested areas, seasons, leads; thin samples.
4. **How it was done**: truth, baseline, held-out weeks, code path. Last, because it matters least to the reader.

Words: knots, gale/storm/hurricane force, "caught" and "false alarms" before POD and FAR (give both the plain words and the score once). Say which truth a number came from. Call the 30-67N boxes the tested area and anything outside it untested.

## Review pages (Artifacts)
Start from `templates/review_page.html`. Light page by default with a dark mode, the system font stack the site uses, one column, the answer at the top, figures with their finding as the caption. The live site pages (globe kit, `/ndfd/` look) stay dark; review pages are documents, not the site.
