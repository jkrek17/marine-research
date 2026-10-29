# Time-lagged runs in the GFE blend: design card

*Jason 2026-10-29 00:34Z: "should I use a time lagged ensemble at all? does that help if I dont have the members?"*

**Question:** in the GFE deterministic blend (PR #95 recipe, GFS + ECMWF as the AI-GFS study left it), do the 12 h and 24 h older runs earn their place, or does the GEFS storm lift cover what they give?

**What would change:** whether PR #95 keeps the lagged runs (support among 6 runs, spread of 6) or uses the latest two runs only. Only Jason can check a GFE change.

**Variants** (base wind GFS + ECMWF via `rk.features.det_blend`):
- latest runs only, no spread bump; latest + spread of the 2;
- lagged, no spread bump; lagged + spread of the 6 (PR #95);
- each again with the GEFS no-model storm lift (+5 kt where the GEFS 48 kt share within ~1 deg >= 25%, from the GEFS-only study).

**Reading line (set before the run; a description, nothing fitted):** lagging earns its place if lagged + spread beats latest + spread on storm catch with the whole-week 95% interval above zero, or on gale CSI in either basin, without pushing gale area past 1.3x ASCAT. Repeated with the GEFS lift on to see whether GEFS covers it.

**Truth and cases:** ASCAT real 10 m wind, 5x5 deg tiles, as in the AI-GFS study (its case list and scoring are imported). Held-out weeks only, 875 cases.

**Reused / new:** reused `rk.features.det_blend`, `rk.features.NB`/`NOMEM_K`, the AI-GFS study's `run.py` case list and tile scoring, the GEFS-only study's lift threshold. Nothing new in `rk/`. No new data.

**Note:** this card was written down when the study was committed; the reading line above is the one stated in the thread before the run.
