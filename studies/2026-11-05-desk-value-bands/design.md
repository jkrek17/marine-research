# Desk value beyond storm and HF: design card

*2026-11-05. Jason: "can we show how much [human] forecasts add/subtract value over a model blend? clearly HF and storm is a given, but what about elsewhere". He left the choices below to the thread ("you choose").*

**Question:** below storm force, where does the desk's issued wind grid beat or lose to the page blend, by wind band, day, basin and situation?

**Choices (defaults put to Jason 5 Nov):**
- Period: 13 Jan - 31 Mar 2026 (desk grids cover OPC water only from 13 Jan; RSS ASCAT stopped 12 Oct 2026, so this winter cannot be scored yet). Apr-May dropped: the desk cache ends 1 Apr.
- Bands by the blend's value (what the forecaster starts from; LESSONS: condition on the forecast), under 20, 20-33, 34-47 kt; banding by the truth as a check. 48+ is computed but not the question.
- Situations from the analysis nearest the valid time: coastal (within 100 nm of land or ice) / open ocean; cold air (t2 - skin <= -2 K, behind fronts) / stable (t2 >= skin, warm sector); near a low under 1000 hPa (500 km) / away.
- Truth ASCAT at every synoptic hour (Pacific needs 06/18Z), analysis at 00/12Z beside it; 95% intervals from resampling ISO weeks.
- Gale areas: cell catch and area ratio at 34 kt, and the blend drawn at 26-34 kt for an equal-catch comparison.
- Issued HSF text left out (2 in 5 texts do not parse fully; gale lines showed no edge in the warning study).

**Reused:** `rk.desk` (grids; new `issue_settled`), `rk.features.blend` (live recipe, AIFS half weight), `rk.truth` (ascat, analysis, airsea, mask_time, ascat_to_grid), `rk.bomb.find_lows`, `rk.basins.opc_mask`, `rk.cases`, `rk.style`. Core Lifted from the held-out replay (`extra/core-lift-retrain/corelift-heldout`).
**New:** `rk.desk.issue_settled` (with a test); this study's scorer and summaries.
