# Time-lagged runs in the GFE blend: findings

*Jason 2026-10-29 00:34Z: "should I use a time lagged ensemble at all? does that help if I dont have the members?"*

**Answer:** yes, keep it, but it earns only a little. Almost all of the gain comes from the spread bump; the lagged runs make that bump a bit better.
- Without the spread bump, lagging adds nothing. The lagged support weighting alone smooths the peaks: storm-force catch falls 2-3 points against the latest runs only.
- The spread bump is what matters. With the bump, using the 12 h and 24 h older runs (6 runs) instead of the latest two:
  - adds about 2 points of storm-force catch in both basins;
  - adds +.012 gale CSI in the Pacific (Atlantic no change);
  - brings gale area closer to ASCAT's (Atlantic 0.87 -> 0.94, Pacific 0.94 -> 1.02).
- With the GEFS storm lift on top, lagging still adds the Pacific gale gain (+.012 CSI). Its storm gain shrinks to 1 point, inside the noise. So GEFS covers most of what lagging does at storm force, but not the Pacific gale gain.

Held-out weeks (5), ASCAT tiles. Atlantic: 175 cases (12 UTC cycles, +24..+120). Pacific: 700 cases (00/12 UTC cycles, +24..+120 and +30..+126). Base wind from GFS + ECMWF. "+GEFS" = +5 kt where the GEFS 48 kt share nearby >= 25% (the GEFS-only study's no-model lift).

| basin | blend | gale CSI | gale false share | gale area | storm catch | storm false share | storm area |
|---|---|---|---|---|---|---|---|
| Atl | latest runs only | .590 | .18 | 0.75 | .30 | .09 | 0.17 |
| Atl | latest + spread of 2 | .609 | .22 | 0.87 | .35 | .12 | 0.22 |
| Atl | lagged, no spread | .580 | .17 | 0.73 | .27 | .06 | 0.15 |
| Atl | lagged + spread (PR #95) | .608 | .23 | 0.94 | .36 | .11 | 0.25 |
| Atl | latest + spread + GEFS | .609 | .22 | 0.89 | .57 | .17 | 0.64 |
| Atl | lagged + spread + GEFS | .608 | .24 | 0.95 | .58 | .20 | 0.70 |
| Pac | latest runs only | .531 | .24 | 0.76 | .14 | .20 | 0.09 |
| Pac | latest + spread of 2 | .534 | .30 | 0.94 | .20 | .28 | 0.14 |
| Pac | lagged, no spread | .532 | .22 | 0.74 | .13 | .16 | 0.08 |
| Pac | lagged + spread (PR #95) | .546 | .31 | 1.02 | .22 | .26 | 0.16 |
| Pac | latest + spread + GEFS | .535 | .30 | 0.95 | .38 | .28 | 0.50 |
| Pac | lagged + spread + GEFS | .547 | .31 | 1.03 | .39 | .29 | 0.53 |

These are differences against lagged + spread, with whole-week 95% intervals. The intervals are coarse with 5 weeks.

| difference | gale CSI, Atlantic | gale CSI, Pacific | storm catch, Atlantic | storm catch, Pacific |
|---|---|---|---|---|
| latest + spread of 2 | +.001 [-.010, +.012] | -.012 [-.015, -.009] | -1.9 pts [-2.8, -0.4] | -1.9 [-5.1, -0.4] |
| latest only | -.018 [-.031, -.003] | -.015 [-.027, -.007] | -6.7 [-9.5, -3.7] | -8.2 [-12.1, -5.2] |
| with GEFS: latest + spread of 2 | +.001 [-.010, +.013] | -.012 [-.015, -.009] | -1.3 [-2.4, +0.3] | -1.4 [-3.3, +0.5] |

Nothing was fitted; the GEFS threshold came from the GEFS-only study's tune weeks. Code: `run.py` (imports the AI-GFS study's case list and scoring). Per-case counts: `RK_DATA/extra/lagged-runs/case_counts.csv`. Not independently rechecked; the PR #95 row repeats the AI-GFS study's N row (Pacific .546 / .216 there too).
