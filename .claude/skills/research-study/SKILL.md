---
name: research-study
description: Use when starting, running or writing up any marine forecast research study (wind, pressure, warnings, storm cores, HSF) so it reuses the shared cases, data store, truth, scores and house style in jkrek17/marine-research.
---

# Run a research study

Every study since 10-13 had the same shape. This is that shape, with the parts that were rebuilt each time now shared.

## 0. Before anything
- Read `STUDIES.md` (has someone answered this already, or part of it?) and `LESSONS.md` (traps).
- Check what the shared store already holds: `python3 tools/fill_store.py --start ... --end ... --dry-run`.

## 1. Design card → Jason's yes
Copy `templates/design_card.md` to `studies/<yyyy-mm-dd>-<short-name>/design.md`. Fill it: his question in his words, truth, baseline, what counts as a win (decided now), cases and held-out weeks, data cost, methods simplest first. Post it and wait for his yes. Add a row to `STUDIES.md` marked Running.

## 2. Data
- Cases: `rk.cases.cycles(basin, start, end)`; the Atlantic runs at 12 UTC and the Pacific at 00 UTC by default (ASCAT coverage). Winter = Nov-Mar.
- Fields: `rk.store.load_det / load_ens`; anything missing: `tools/fill_store.py` in the background (it waits out the marine wind build windows by itself). Big pulls (more than ~50 GB streamed): say the estimate first.
- Truth: `rk.truth.analysis` (where), `rk.truth.ascat` (how strong, real 10 m), `rk.truth.obs` (buoys, ships).
- Fields the store does not carry (925 mb, temperatures, full members): fetch with `rk.fetch` and cache under `rk.paths.data("extra", "<study>")`, not in a session folder.

## 3. Run
- Code lives in `studies/<name>/`; it imports `rk` and finds the repo from its own path.
- Tune on `rk.cases.split(dt) == "tune"`; score held-out weeks once, at the end.
- Compare with `rk.compare.paired` (whole-week resampling). Score peaks with `rk.score.tile_peaks` as well as cell scores.
- Write result tables as CSV in the study folder (small); never commit fields or anything over 10 MB.

## 4. Check
Before telling Jason, have a second agent recompute the headline numbers from the saved CSVs without reading your write-up, and read the draft for claims the numbers don't support (oversold labels, one metric standing for several, truth not named). Record who checked and what matched in the write-up.

## 5. Write-up
Copy `templates/findings.md` to the study folder. Answer first in forecaster language; one table, at most three figures made with `rk.style` (titles say the finding). Update the `STUDIES.md` row with the one-line answer. Long or visual results: a review page from `templates/review_page.html` published as an Artifact, linked in the thread.

## 6. Lessons
Anything that made you change a finished result goes in `LESSONS.md` as one line, and into `rk/` or `tests/` as a check where it can.

## Rules that don't bend
- No awips-tools, hf-low or public page change from research until Jason agrees.
- Never commit data, tokens or files over 10 MB; stage files by name.
- Name methods for what they do. Say which truth every number came from.
