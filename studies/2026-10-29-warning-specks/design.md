# Gale warning line without the specks

**Question (Jason, 2026-10-29):** the marine wind page looks messy, and much of it is the gale warning line breaking into small specks. Can the small pieces go without losing gale catch? ("sure", to re-score before shipping.)

**Rule tested.** The live gale warning area (strongest of GFS, ECMWF and AIFS >= 30 kt) with 8-connected pieces under N cells dropped, N = 4, 8, 16, 32, 64 (16 cells is about 1x1 deg), with and without filling enclosed gaps under N.

**Truth and scoring (reused).** The warning study's full-member winter cases (`RK_DATA/extra/warning-experiment/cases`, 604 per basin, +24/+48 h), `rk.truth.ascat_grid`, `rk.score.warning_events` (60 nm reach counted), OPC high seas areas on open water, `rk.cases.split` tune and held-out weeks. Same as `2026-10-16-warning-forecast/fair_lines.py`; nothing new in `rk/`.

**Preset (before running).** Ship the largest N whose held-out coverage of ASCAT gale cells and held-out events caught each drop by no more than 1 point, in both basins. Nothing is fitted, so held-out is the read.

**Limits.** Gale only (storm and HF pieces are few and not tested). ASCAT at 00/12Z, so the Pacific has 53 held-out events.
