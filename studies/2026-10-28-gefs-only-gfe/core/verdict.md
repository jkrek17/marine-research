# GEFS only: core lift on the deterministic GFE blend, verdict

**Verdict (0.5 deg decides): storm lift PASSES; gale-core piece FAILS.** At 0.25 deg: storm lift passes, gale-core fails.

Held-out weeks, scored once. Base wind N = GFS + IFS deterministic blend (rk.features.det_blend). Storm lift = N + 5 kt where the GEFS-only storm-core chance >= t; gale-core = lift, then at least 34 kt where the gale-core chance >= t34. Truth ASCAT real 10 m wind (intercal); tiles 5x5 deg with >= 150 seen cells; area = forecast cells / ASCAT cells at seen cells. Pooled over all scored leads (Atlantic +24..+120 at 00/12 UTC valid; Pacific also +30..+126 at 06/18 UTC); brackets are whole-week 95% intervals. 0.25 = GEFS inputs as stored; 0.5 = GEFS inputs subsampled to the 0.5 deg points and interpolated back (the 0.5 result decides).

Choices made on tune weeks: 0.25: t = 0.67, x = 0.25, t34 = 0.6; 0.5: t = 0.67, x = 0.25, t34 = 0.6

Cases scored (basin, variant: cases): natl h: 350, npac h: 700, natl q: 350, npac q: 700

## 0.25 deg GEFS inputs

| basin | product | storm catch | d catch vs N | storm FAR | storm area | gale CSI | d gale CSI vs N | gale cells caught | gale area |
|---|---|---|---|---|---|---|---|---|---|
| natl | N (GFS+IFS blend) | 0.355 | - | 0.100 | 0.25 [0.17, 0.30] | 0.630 | - | 0.630 | 0.93 |
| natl | N + 5 at storm-core | 0.583 | +0.228 [+0.186, +0.257] | 0.177 | 0.64 [0.47, 0.73] | 0.630 | +0.000 [+0.000, +0.000] | 0.630 | 0.93 |
| natl | + gale-core to 34 | 0.583 | +0.228 [+0.186, +0.257] | 0.177 | 0.64 [0.47, 0.73] | 0.646 | +0.017 [+0.007, +0.029] | 0.733 | 1.21 |
| natl | live Core Lifted (ref) | 0.595 | +0.240 [+0.165, +0.286] | 0.124 | 0.67 [0.50, 0.77] | 0.620 | -0.010 [-0.020, +0.002] | 0.630 | 0.84 |
| natl | no-model lift (ref) | 0.581 | +0.226 [+0.183, +0.252] | 0.193 | 0.67 [0.50, 0.77] | 0.630 | +0.000 [-0.001, +0.001] | 0.635 | 0.94 |
| npac | N (GFS+IFS blend) | 0.216 | - | 0.286 | 0.16 [0.05, 0.25] | 0.547 | - | 0.565 | 1.03 |
| npac | N + 5 at storm-core | 0.365 | +0.149 [+0.111, +0.180] | 0.269 | 0.45 [0.25, 0.55] | 0.547 | +0.000 [+0.000, +0.000] | 0.565 | 1.03 |
| npac | + gale-core to 34 | 0.365 | +0.149 [+0.111, +0.180] | 0.269 | 0.45 [0.25, 0.55] | 0.555 | +0.008 [-0.004, +0.023] | 0.676 | 1.38 |
| npac | live Core Lifted (ref) | 0.361 | +0.144 [+0.090, +0.181] | 0.227 | 0.47 [0.19, 0.61] | 0.526 | -0.020 [-0.056, -0.002] | 0.551 | 0.85 |
| npac | no-model lift (ref) | 0.394 | +0.178 [+0.104, +0.245] | 0.299 | 0.53 [0.32, 0.64] | 0.548 | +0.001 [+0.000, +0.002] | 0.571 | 1.04 |

Win line, storm lift against N (0.25 deg):

| basin | rule | value | pass |
|---|---|---|---|
| natl | 1 storm catch up >= 5 pts, interval above 0 | +0.228 [+0.186, +0.257] | yes |
| natl | 2 storm area <= 1.5 | 0.64 | yes |
| natl | 3 gale CSI not lower than N by > 0.01 | +0.000 [+0.000, +0.000] | yes |
| npac | 1 storm catch up >= 5 pts, interval above 0 | +0.149 [+0.111, +0.180] | yes |
| npac | 2 storm area <= 1.5 | 0.45 | yes |
| npac | 3 gale CSI not lower than N by > 0.01 | +0.000 [+0.000, +0.000] | yes |

Gale-core piece (0.25 deg):

| basin | rule | value | pass |
|---|---|---|---|
| natl | G1 gale cells caught up vs lift, interval above 0 | +0.103 [+0.091, +0.114] | yes |
| natl | G2 gale area <= 1.3 | 1.21 | yes |
| npac | G1 gale cells caught up vs lift, interval above 0 | +0.111 [+0.095, +0.121] | yes |
| npac | G2 gale area <= 1.3 | 1.38 | NO |

## 0.5 deg GEFS inputs

| basin | product | storm catch | d catch vs N | storm FAR | storm area | gale CSI | d gale CSI vs N | gale cells caught | gale area |
|---|---|---|---|---|---|---|---|---|---|
| natl | N (GFS+IFS blend) | 0.355 | - | 0.100 | 0.25 [0.17, 0.30] | 0.630 | - | 0.630 | 0.93 |
| natl | N + 5 at storm-core | 0.587 | +0.232 [+0.186, +0.257] | 0.175 | 0.63 [0.46, 0.73] | 0.630 | +0.000 [+0.000, +0.000] | 0.630 | 0.93 |
| natl | + gale-core to 34 | 0.587 | +0.232 [+0.186, +0.257] | 0.175 | 0.63 [0.46, 0.73] | 0.647 | +0.018 [+0.009, +0.029] | 0.733 | 1.21 |
| natl | live Core Lifted (ref) | 0.595 | +0.240 [+0.165, +0.286] | 0.124 | 0.67 [0.50, 0.77] | 0.620 | -0.010 [-0.020, +0.002] | 0.630 | 0.84 |
| natl | no-model lift (ref) | 0.570 | +0.216 [+0.173, +0.241] | 0.188 | 0.66 [0.48, 0.76] | 0.630 | +0.000 [-0.001, +0.001] | 0.634 | 0.94 |
| npac | N (GFS+IFS blend) | 0.216 | - | 0.286 | 0.16 [0.05, 0.25] | 0.547 | - | 0.565 | 1.03 |
| npac | N + 5 at storm-core | 0.361 | +0.144 [+0.110, +0.175] | 0.279 | 0.43 [0.24, 0.54] | 0.547 | +0.000 [+0.000, +0.000] | 0.565 | 1.03 |
| npac | + gale-core to 34 | 0.361 | +0.144 [+0.110, +0.175] | 0.279 | 0.43 [0.24, 0.54] | 0.554 | +0.007 [-0.005, +0.020] | 0.674 | 1.37 |
| npac | live Core Lifted (ref) | 0.361 | +0.144 [+0.090, +0.181] | 0.227 | 0.47 [0.19, 0.61] | 0.526 | -0.020 [-0.056, -0.002] | 0.551 | 0.85 |
| npac | no-model lift (ref) | 0.375 | +0.159 [+0.091, +0.210] | 0.297 | 0.51 [0.30, 0.62] | 0.547 | +0.000 [+0.000, +0.001] | 0.570 | 1.04 |

Win line, storm lift against N (0.5 deg):

| basin | rule | value | pass |
|---|---|---|---|
| natl | 1 storm catch up >= 5 pts, interval above 0 | +0.232 [+0.186, +0.257] | yes |
| natl | 2 storm area <= 1.5 | 0.63 | yes |
| natl | 3 gale CSI not lower than N by > 0.01 | +0.000 [+0.000, +0.000] | yes |
| npac | 1 storm catch up >= 5 pts, interval above 0 | +0.144 [+0.110, +0.175] | yes |
| npac | 2 storm area <= 1.5 | 0.43 | yes |
| npac | 3 gale CSI not lower than N by > 0.01 | +0.000 [+0.000, +0.000] | yes |

Gale-core piece (0.5 deg):

| basin | rule | value | pass |
|---|---|---|---|
| natl | G1 gale cells caught up vs lift, interval above 0 | +0.103 [+0.091, +0.113] | yes |
| natl | G2 gale area <= 1.3 | 1.21 | yes |
| npac | G1 gale cells caught up vs lift, interval above 0 | +0.109 [+0.095, +0.119] | yes |
| npac | G2 gale area <= 1.3 | 1.37 | NO |

## Notes

- Low-level features use the GFS fields only (low_models = gfs): IFS low-level files are missing for 5% of Atlantic and 17% of Pacific tune cycles (and 20% of Pacific held-out 00 UTC runs at 00/12 UTC valid), and one definition had to serve every case. A GFS-only mean is not the live feature.
- The training tables sample every second row and column, which are exactly the 0.5 deg points, so the 0.5 deg model is trained on uninterpolated values (only the neighbourhood-max features differ from 0.25); scoring uses the interpolated grids at every cell.
- 0.5 deg inputs: the stored GEFS shares, mean and SD are subsampled and interpolated back before the features (r10, boost, m90, the neighbourhood maxima) are built, so every GEFS-derived feature is 0.5 deg.
- Tune cases with all references: 1944 of 2320 (live Core Lifted needs the AIFS and IFS low files, missing for 260; 116 more lack the lag runs of the GFS+IFS blend). t = 0.67 and x = 0.25 are pooled over both basins; the tune area ratio match is in tune_storm_area.csv.
- Gale-core and lift are scored on the same cases as N. 00/12 UTC valid only: final_summary_0012only.csv.

