# Storm-core lift retrain: design card

*Status: approved 2026-10-16 08:05Z with the recommendations below; 08:06Z Jason: "pull the data we need to make the best determination".*

**Question** (Jason, 2026-10-16 07:55Z, "go both" on the coordinator's proposal): retrain the storm-core lift on both basins with held-out weeks, so the held-out score is the score we keep, and say whether the lift should stay at +5 kt or depend on the likelihood.

**What would change if the answer is yes:** the marine wind page's `core_model.json` (core likelihood), the Core Lifted layer (+5 kt where likelihood >= 35%) and the storm line. Page change goes through the Global view thread after Jason agrees; nothing in awips-tools from this study.

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat(real=True, intercal=True)`, rain dropped, floor(x+0.5) gridding). Target cell = 48+ kt within ~50 km, as the live model. The storm-force truth study kept ASCAT as referee with no adjustment. All ASCAT hours near the valid time: Atlantic 00Z and 12Z, Pacific 00Z, 06Z, 18Z (06/18Z when the store has the +30/+54/... steps).

**Baseline to beat:** the live model as it is (`core_model.json`, Atlantic winter trained) run on the same held-out cells: ~38% of ASCAT storm tiles caught out of sample (verification page). Also the plain blend and "lift where member share 48+ >= x" (no model), so we know what the trained model adds.

**Win means (decided now, held-out weeks only, both basins scored separately):**
1. Storm tiles (5x5 deg, any ASCAT 48+): catch at least 5 points more than the live model at no more tile false alarms, paired over whole held-out weeks with 95% intervals excluding zero (`rk.compare.paired`).
2. Storm area: forecast 48+ area / ASCAT 48+ area moves toward 1 (Pacific now 0.47) and stays under 1.5 in each basin (no massive over-warning).
3. Gale (34+) tile CSI and buoy bias at 34+ no worse than today by more than 0.01 / 0.5 kt.
4. Core likelihood is reliable as a chance on held-out weeks (reliability curve within 10 points in the 20-80% bins), so a likelihood-dependent lift is honest.

**Cases:** winter 2025-26 (1 Nov - 31 Mar), both basins, 00Z and 12Z cycles, +24 to +120 h (302 cycles per basin). Held-out weeks per `rk.cases.held_out`, scored once at the end; tuning by 5-fold whole-week CV on the rest.

**Data:** already in the store: GFS, GEFS stats both basins (299/302 cycles); IFS, AIFS, ENS, AIFS ENS filling in date order (27/302 now). Not in the store: the live model's lower-level fields (925/850 mb wind and temperature, 2 m and skin temperature, 3 models). Measured from the GFS index: 6.9 MB per model per step, so ~10 GB for GFS and ~30 GB for all three, cached under `extra/core-lift-retrain/`. ECMWF part waits until the ECMWF store fill ends (one heavy ECMWF pull at a time). The store keeps ensemble statistics, not members, so the live feature "90th percentile of members" becomes mean + 1.28 x SD here; the live page would compute the same new feature.

**Reused / new:** reused: `rk.cases`, `rk.store`, `rk.truth.ascat`, `rk.score.tile_peaks`, `rk.compare.paired`, `rk.style`; the feature definitions in awips-tools `marine_wind/pipeline/storm.py` (`core_features`) and the study code in `/mnt/project-files/wind-focus/core/code/` (lift.py, export_core.py). New in `rk/`: (a) `rk.truth.ascat_target(basin, valid)` - ASCAT 48+ within 50 km on the basin grid, all hours near valid (shared with Chance calibration if they need it); (b) `rk.features.core(...)` - the core feature grids from store data, one definition used by both studies and checked against `storm.core_features` (r >= 0.99). Study-only: training, lift rules, report.

**Methods tried, simplest first** (each must beat the one before it on CV to stay in):
1. Live model unchanged, scored both basins (baseline, gives the true held-out number).
2. No model: lift where combined member share 48+ (with neighbourhood) >= x.
3. Same features and settings as live, retrained on both basins' tuning weeks (basin as a feature).
4. Store-only features (10 m models + all ensembles), GEFS first, ECMWF features as they land.
5. Add the lower-level fields (925 mb wind, cold air over warm sea, cold advection) only if they still add on CV.
Lift rule, each on the best model: +5 kt at P >= 35% (today); +3/+5/+8 with threshold set from the hit-vs-area curve per basin; lift = k x P; lift toward the member 90th percentile where P is high.

**Known traps:** in-sample scores flattered the live model (49-51% vs 38%); synoptic clues add nothing (do not retry); whole-grid boosts win peaks and lose gales; Pacific dateline (lon 160-245); check the exported model against sklearn and the live port against the study at matched cells; sklearn fits then fork deadlock (use spawn); ASCAT 06/18Z near-empty in the Atlantic.

**Out of scope:** chances (Chance calibration thread), HF line, tracks and cone, any page edit.

## Questions for Jason
1. **Lower-level fields.** Pull the 925/850 mb and temperature fields (~10 GB GFS now, ~30 GB with IFS/AIFS after the ECMWF fill), or first see how far store-only features get and pull only if the CV says they matter? Recommended: store-only first.
2. **One model or two.** One model for both basins with basin as an input, or a separate model per basin? Recommended: one model (the Pacific has ~1/3 the ASCAT storm cells).
3. **Win line.** Is "+5 points of held-out storm-tile catch at no more false alarms, storm area under 1.5x ASCAT, gales no worse" the right bar?
4. **Lift size.** Keep a single +5 kt unless a likelihood-dependent lift wins on the same score, or are you open to a bigger lift (e.g. +8 kt) if it catches more at the false-alarm cost you accept?

## Jason's answers (2026-10-16 08:05-08:06Z)
1. Pull the lower-level fields ("pull the data we need to make the best determination"): GFS now (~10 GB streamed), IFS and AIFS after the ECMWF store fill ends. Method 5 is still kept only if it adds on CV.
2. One model, basin as an input.
3. Win line as written.
4. Keep +5 kt unless a likelihood-dependent lift wins on the same score.
ASCAT: every winter day is cached with all passes; the Pacific final score waits for the 06/18Z-valid steps in the store.
