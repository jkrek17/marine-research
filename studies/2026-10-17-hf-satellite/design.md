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

## Addendum, 2026-10-17 ~19Z: full archive (written before the full-archive features were computed)
Jason chose the full archive after the pilot ("Full archive", 14:39Z). Same features, same three methods, same win rule, nothing re-tuned on what the pilot showed.
- Cases: every HF and S fix in the basin boxes, seasons 2002-03 to 2025-26 (`features.py --seasons 2002-2025`, `features_full.csv`).
- Tune on the tuning weeks of all seasons. Primary score: the held-out weeks of seasons 2002-03 to 2023-24 (never looked at). The pilot's held-out weeks (2024-26) are reported beside it, not pooled into the verdict.
- ASCAT referee unchanged (winter 2025-26 only; the store's analyses start in 2025).
- Report a pre-2017 / 2017-on split (satellite generations) and a north/south of 55N split (view angle), as descriptions, not new tests.

## Addendum, 2026-10-17 ~19:30Z: air-mass RGB on the pilot winters (written before any air-mass feature was computed)
Jason: "What about RGB air mass. We use that heavily." He chose the pilot winters (18:49Z).
- Data: ABI bands 8 (6.2 um), 10 (7.3 um), 12 (9.6 um), 13 (10.3 um) from GOES-East (GOES-16 to 2025-04-07, then GOES-19) for the Atlantic and GOES-West (GOES-18) for the Pacific, `rk.satellite.airmass_box` (truth kind `airmass`), pixels beyond 80 deg view zenith left missing. No Meteosat or Himawari, so the eastern Atlantic and the western Pacific are seen at steep angles or not at all; limb cooling tints the RGB there.
- Cases: the pilot's HF and S fixes whose IR crop and air-mass crop are both at least 90% seen within 1000 km. Same storm split; same held-out weeks (their IR scores were seen once; air mass is new).
- Six air-mass measures from the motion-relative crop: 10th percentile of B12-B13 within 500 km (ozone, stratospheric air); mean B12-B13 in the rear half at 200-800 km; 90th percentile of B8 within 500 km (driest upper air near the centre); mean B8 right-rear at 200-800 km (dry slot); B8 90th minus 10th percentile within 800 km (moist cloud head vs dry intrusion); share within 500 km of the red-orange signature (B8-B10 > -10 K and B12-B13 < -22 K).
- Methods: base (pressure, latitude); ir (base + seven IR measures, as before); am (ir + six air-mass measures), logistic, refit on the tuning fixes of this subset.
- Win means: on held-out weeks, am beats ir by at least 0.03 in ROC area AND the paired Brier difference (am minus ir, whole weeks, 10,000 draws) has its 95% interval below 0. Reported also: am vs base, and the ASCAT rank correlation for winter 2025-26.
