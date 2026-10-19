# Storm Twins: design card

*Agreed with Jason in the project thread 2026-10-19 00:19Z ("follow your defaults"): card B of `/mnt/project-files/wxmap/lab-design/cards.md`. Defaults are day 1-3 GFS lows and the existing 8-season library.*

**Question** (Jason's words): "we can do the analogs too".

**What would change if the answer is yes:** clicking a low on wxmap.pro/lab opens a "Storm Twins" card with its five closest past storms and "x of 30 twins reached hurricane force in the next 24 h". Lab page only.

**Truth:** the ERA5 pipeline A gust class over the next 24 h (hf-low `storm_patch_analogs`, a proxy), which is what the twins carry.

**Baseline to beat:** the basin-month climatology of that class. The hf-low ERA5 test already gives the k = 30 analog chance of HF a Brier skill of +0.107, with calibration slope 1.12 (ERA5 patches in). Untested: twins found from a GFS forecast patch.

**Win means:** GFS f024 patches matched against the library (twins from other seasons only) give a k = 30 HF share with Brier skill > 0 against climatology and a reliability slope of 0.8-1.25, over the 5 GFS seasons hf-low already matched (`gfs/results/gfs_fixes_lead24.csv.gz`). If it fails, the card shows the twins but no share.

**Cases:** the 18,167 matched GFS lead 24 h fixes, 2021-22 to 2025-26. Only 2021-22 overlaps the library seasons, and same-season twins are excluded.

**Data:** the library is rebuilt from WeatherBench2 (24.8 GB streamed plus 1.2 GB of climatology, done 2026-10-19, stored at `/mnt/project-files/storm-patches/`, 0.7 GB). GFS f024 patches for the check come from the existing extractor (about 6.4 GB streamed, under the 50 GB line).

**Reused / new:** hf-low's patch recipe, frozen 15-component PCA (`gfs/results/frozen_pca_full.npz`), fixes and outcomes (`results/oof_hf_prob.csv.gz`). New: `rk/twins.py` (patch from any 0.25 degree global field, frozen PCs, k-nearest twins, with a test) so the live lab job and later studies share it, plus the library table.

**Methods:** k = 30 nearest in the frozen 15-PC space; share of twins reaching HF (gust class 3). Five closest twins are shown.

**Known traps:** ERA5 is a proxy; neighbouring fixes of one storm are near-duplicates (twins come from other seasons, and the five shown come from different storms); GFS anomalies carry a small offset against the ERA5 climatology (-2.5 m Z500).

**Out of scope:** day 5-7 vote lows; extending the library beyond 2014-22 (WeatherBench2 ERA5 ends January 2023).
