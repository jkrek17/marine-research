# GFE without ECMWF ensembles: GEFS chances, core lift and HF gate: design card

*Jason 2026-10-28: "what if I only have deterministic global models", then "what about GEFS 34 kt, 48 kt, 64 kt wind probs?", "probably 0.5 degree", and 06:15Z card "GEFS pieces only". Win lines preset here before any run.*

**Question:** Jason's AWIPS has GFS, ECMWF, AI-GFS, CMC and UKMET deterministic runs and the GEFS 34/48/64 kt probability grids (probably 0.5 deg). It has no ECMWF ENS or AIFS ENS. How much of the page's chances, Core Lifted and HF line can the GFE build from that?

**What would change:** the GFE procedure (after the deterministic Wind blend of PR #95, which the AI-GFS study left on GFS + ECMWF):
- calibrated gale/storm chance grids from GEFS;
- a core lift on the deterministic blend;
- an HF warning line gated on GEFS.
Nothing changes on the page. Only Jason can check a GFE change.

**Inputs allowed (the GFE's):**
- deterministic GFS and IFS 10 m, current and 12/24 h older runs. AI-GFS is left out because the AI-GFS study found it does not earn its place; CMC and UKMET are out of scope.
- GEFS member shares p34/p48/p64, member mean and SD as stored.
- GFS (and IFS where stored) low-level fields.

No ECMWF ENS and no AIFS ENS anywhere. The base wind is `rk.features.det_blend(models=("gfs","ifs"))`, called "N" below.

**0.5 deg:** every GEFS input is also built the way AWIPS would hold it: the 0.25 deg share grids subsampled to the 0.5 deg points (every other row and column, which is what the NCEP 0.5 deg grids are), then bilinear back to 0.25 deg for scoring. Each test is reported at both; the 0.5 deg result decides. Assumed, not confirmed: AWIPS GEFS probabilities are the share of members with sustained 10 m wind at or above 34/48/64 kt.

**Truth:** ASCAT real 10 m wind (intercal), passes within 90 min. Chances are scored on the ~75 km box mean (`rk.truth.ascat_box`, Jason's 10-16 choice). Cores are scored on `ascat_target` (48+ within ~50 km; gale core 34+). HF uses the hf-low archive lows within 150 km, as in the warning study.

**Cases:** winter 2025-26, 00/12 UTC cycles, +24..+120 h, both basins; the Pacific also uses the 06/18 UTC valid steps. Tune weeks fit; held-out weeks (`rk.cases.held_out`) are scored once at the end.

**1. Chances (GEFS only)**
- Fit: gale and storm curves on tune weeks with `rk.calibrate` (same method and lead groups as the 10-16 study), per basin.
- Win line: on held-out weeks, in both basins and at each lead group, the remapped chance must
  - have a lower reliability error than raw GEFS, and
  - have a Brier skill not lower than raw by more than 0.01.
- HF: GEFS 64 kt stays raw and labelled "not calibrated" (64 kt events are too few, as found before).
- Reported beside it, without deciding: the page's pooled chances on the same cells, to show what the missing ensembles cost.

**2. Core lift on the deterministic blend**
- Retrain the storm-core model with the 10-16 retrain's final method (same target and learner, basin as a feature, 5-fold whole-week CV on tune weeks).
- Features: only the allowed inputs, i.e. the live 28 minus AIFS, ENS and AIFS ENS features, with GEFS-only ensemble stats.
- Lift: N + 5 kt where P >= t. t is set on tune weeks so that the storm 48+ area / ASCAT matches what live Core Lifted gives on the same tune cells (no tuning on held-out).
- Gale-core piece: retrain the 10-17 gale-core model the same way and lift to max(wind, 34) where its chance >= t34 (t34 on tune, 0.3-0.7).
- Win line (held-out, both basins, +24..+120, against N):
  1. storm tiles (48+): catch up at least 5 points, whole-week 95% interval above zero;
  2. storm area forecast/ASCAT at most 1.5;
  3. gale tile CSI not lower than N by more than 0.01.
  The gale-core piece must also raise ASCAT gale cells caught, with its interval above zero, at gale area at most 1.3.
- Reported beside it: live Core Lifted on the page blend (with all ensembles), and the no-model reference (lift where GEFS p48 >= x).

**3. HF line gated on GEFS**
- Rule: the strongest of GFS/IFS + 20 kt at 64+, kept where at least 1 GEFS member (3%) reaches 64 kt within ~1 deg. This is the live gate (>= 1% of the pooled members) with the pooled ensemble swapped for GEFS.
- Win line (Atlantic held-out; the Pacific is untestable with ~14 lows):
  - catches at least 75% of archive HF lows within 150 km (live pooled gate 81%), and
  - HF area is no more than 1.2x the pooled gate's on the same cases.
- If it fails, try 2 members (6%) and then 3 (10%), picked on tune weeks only.

**Data:** all in the store: GEFS stats, GFS/IFS det with lag steps, GFS low-level fields, ASCAT and analyses, the hf-low archive. The held-out weeks were filled for the AI-GFS study; tune weeks are in the store at 00/12 UTC +24..+144 (the 06/18 UTC lag steps 42..150 are stored only for held-out weeks, so fitting and tuning use 00/12 UTC valid times; the held-out score adds the Pacific 06/18 UTC). No new pull.

**Reused / new:**
- Reused: `rk.features.core` (with `ens=("gefs",)`, `models=("gfs","ifs")`), `rk.features.det_blend`, `rk.calibrate`, `rk.truth.ascat_box`/`ascat_target`, `rk.score.tile_hits`, `rk.compare.paired_counts`, the retrain's `train.py`/`score.py`, gale-core `score_gale.py`, the warning study's `gated_lines.py`.
- New in rk: a `coarsen_half_deg(grid)` helper (subsample + bilinear back) with a test.

**Known traps:** GEFS alone runs high at gale and low at storm (10-16 first look), so do not reuse the pooled curves; in-sample scores flatter core models; whole-grid boosts win peaks and lose gales; the Pacific has few storm and HF events; `held_out` marks cycles, so lagged runs from a tune week are fine as inputs.

**Out of scope:** CMC, UKMET, AI-GFS ensemble, the page, HSF text.
