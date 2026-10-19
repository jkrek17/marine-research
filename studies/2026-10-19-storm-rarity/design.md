# How rare is this storm: design card

*Agreed with Jason in the project thread 2026-10-19 00:19Z ("follow your defaults"); the card is in the shared folder at `/mnt/project-files/wxmap/lab-design/cards.md` (card A).*

**Question** (Jason's words): "1": the "How rare is this storm?" badge for each forecast low on the lab map.

**What would change if the answer is yes:** a badge on each low on wxmap.pro/lab ("deeper than 96% of November lows near here since 1979"). Lab page only; nothing on the marine wind page.

**Truth:** none scored; the reference is the ERA5 pipeline A cyclone record in hf-low (a proxy), 1979-2025, lifetime lowest pressure.

**Baseline to beat:** not a skill question. The one check: does ERA5 put lows at the same depth as the analyses the forecasts are judged on? If not, apply the offset.

**Win means:** offset within 2 hPa at matched OPC archive HF fixes (forecast lows are within 1-2 hPa of the archive at day 1-2, `studies/2026-10-18-hf-depth`), else apply it.

**Cases:** all archive HF fixes with a pressure that have an ERA5 HF-equivalent track fix within 300 km at the same time.

**Data:** none pulled; two committed hf-low files over HTTPS (era5-peaks.js 3.5 MB, era5-tracks.js 1.4 MB).

**Reused / new:** `rk.truth.hf_archive`, `rk.score.km`. New `rk/climo.py` (with `tests/test_climo.py`) so the bomb watch and Storm Twins share the same bins.

**Methods:** 1,000 km radius, the low's month widened to +-2 months until 150 lows.

**Known traps:** ERA5 is a proxy; the peak position is where the gust peaked, not always where the pressure bottomed out; pressure only (gust index and sustained wind are different quantities).

**Out of scope:** wind percentiles; percentiles against the OPC archive alone.
