# How much of the ocean the hazard focus covers (2026-11-05)

Question (Jason): with Core Lifted and model agreement, how much of the ocean is the desk effectively focusing on, versus worrying about all of it?

- Measure: share of open water (cos-latitude weighted, land and sea ice out) inside each layer the page already draws: gale / storm / HF warning areas (`warn` bits), core likelihood >= 35%, models split (`focus` >= 2; >= 3 for splits across 48/64), spread term >= 2 kt (`boost`), and their union.
- Reused: the page's own forecast records (`awips-tools/marine_wind/pipeline/record.py`, GitHub artifacts), `storm.warning_areas` for winter, the held-out Core Lifted grids (core-lift-retrain) and the warning-experiment cases with full members. Nothing new downloaded except one GFS land/ice field through `fetch.gfs_low`.
- New: three small scripts here (`share.py` recent records, `winter.py` held-out winter, `fig.py`).
- Samples: 27 live 00/12Z runs 23 Oct to 5 Nov 2026 (OPC boxes and 30-67N); 70 held-out 00/12Z runs per basin, winter 2025-26 (30-67N tested box). Winter gale, HF, split and spread layers only at +24/+48 (the only leads with full members saved).
