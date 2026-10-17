# HF satellite pilot: design card

*Written 2026-10-17 before any imagery was pulled. Jason chose the pilot on the decision card (09:20Z) after the feasibility note in the thread "satellite presentation for HF lows".*

**Question** (Jason's words): "given that we have a HF archive. how feasible would it be to start some kind of optical training on satellite presentation for HF lows. we could gather the satellite at HF"

**Pilot question:** On two winters, does the infrared presentation of a low tell hurricane force from storm force better than its central pressure and latitude alone?

**What would change if the answer is yes:** the full 2002-2026 pull (about 60 GB streamed, needs Jason's go) and a predictor of HF 12-24 h ahead from imagery; later an experimental layer on wxmap.pro/lab. Nothing on a page or in GFE from this pilot.

**Truth:** the hf-low archive's category at each fix (HF vs S), as analysed by OPC. The analysts used ASCAT and imagery to set it, so the label is partly circular; ASCAT referees on the winter it covers in the store (2025-26): the largest real 10 m ASCAT wind within 500 km of the fix (`rk.truth.ascat`), reported beside the label test, not used to tune.

**Baseline to beat:** a logistic model on the archive's central pressure and latitude (what an analyst knows without imagery).

**Win means** (decided now): on held-out weeks, adding the imagery features raises the ROC area by at least 0.05 over the baseline, AND the paired Brier score difference (imagery minus baseline, whole-week resampling, `rk.compare.paired`) has its 95% interval below 0. Anything less: "no clear signal in IR alone at this sample size", and the full pull is not proposed on the strength of this test.

**Cases:** both basins, seasons 2024-25 and 2025-26 (1 June to 31 May), every archive fix in the basin box with category HF (positive) or S (negative). DHF/DS fixes are kept for the composites only. About 193 events, 555 HF and 197 S fixes. An event goes to the held-out set when its first fix falls in a held-out week (`rk.cases.held_out`), so no storm is split between tuning and scoring; held-out fixes are scored once, at the end. The independent sample is storms and weeks, not fixes.

**Data:** GridSat-B1 v02r01 (NOAA CDR, AWS `noaa-cdr-gridsat-b1-pds`), 11 um IR window brightness temperature `irwin_cdr` (limb corrected), 0.07 deg, 3-hourly, 70S-70N, all geostationary satellites merged (GOES, Himawari, Meteosat). Its water-vapour channel is empty in 2025, so the pilot is IR only. Only the IR chunk (about 9 MB of a 30-55 MB file) is read with byte ranges: about 840 valid times, about 8 GB streamed, about 1 GB stored as truth files (basin box with margins, int16). Pull kept clear of the marine wind build windows by `rk.fetch.get`.

**Reused / new:** reused: `rk.truth.hf_archive`, `rk.truth.ascat`, `rk.cases.held_out`, `rk.compare.paired`, `rk.score.auc`, `rk.store` truth files and `tools/publish_store.py`, `rk.style`. New in `rk/` (with `tests/test_satellite.py`): `rk/satellite.py`, the GridSat IR box as truth kind `gridsat` (per basin, 00/06/12/18 UTC) and a storm-centred, motion-relative crop (azimuthal equidistant, 10 km pixels, 1200 km half-width), so the full pull, the predictor and any other storm study reuse them.

**Methods tried, simplest first:** each must beat the one before it to stay in.
1. Baseline: logistic regression on central pressure and latitude.
2. Plus seven hand-built IR features from the motion-relative crop: cold-cloud (< 233 K) share within 500 km and within 1000 km; 5th-percentile Tb within 500 km; centre (< 150 km) minus ring (150-500 km) mean Tb (warm seclusion or wrapped dry air); warm (> 260 K) share in the right-rear quadrant at 200-800 km (dry slot); cold share in the left half at 200-800 km (cloud head); spread of the 12 sector means at 300-700 km (comma or spiral asymmetry). Logistic regression.
3. Gradient boosting on the same features, only if 2 passes.
Composites: mean motion-relative IR at HF fixes, at S fixes, and their difference, per basin.

**Known traps for this question:** the sample is storms and weeks (resample whole weeks); hold out before looking; geostationary views are slanted north of about 60N (keep a high-latitude split and the GridSat satellite id); labels are partly made from imagery; the archive has typo dates (dropped by `hf_archive`); name the method for what it does ("IR features", not "satellite AI").

**Out of scope:** water vapour and visible imagery, a deep network, predicting HF ahead of time, storms that never reached HF, anything on a page.
