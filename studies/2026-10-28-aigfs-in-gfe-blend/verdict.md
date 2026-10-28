# AI-GFS in the GFE blend: verdict

Cases scored (basin: cycle x lead; every case has all four blends and all four single models): held-out {'natl': 165, 'npac': 670}; tune {}. Truth ASCAT real 10 m wind; tiles 5x5 deg with >= 150 seen cells; area ratio = forecast / ASCAT seen cells at 34+ and 48+; buoy bias = forecast - buoy (kt) where either is >= 34 kt. Pooled over all scored leads (Pacific: +24..+120 and +30..+126).

## Verdict (held-out weeks, both basins)

**GFE runs GFS + ECMWF (N).** neither G1 nor Gh passes all three tests in both basins (failed: G1 natl 1; G1 natl 2; G1 npac 1; G1 npac 2; G1 npac 3; Gh natl 1; Gh natl 2; Gh npac 1; Gh npac 2; Gh npac 3).

### Win-line checks, held-out

| variant | basin | rule | value | passed |
|---|---|---|---|---|
| G1 | natl | 1 gale CSI higher than N, interval above 0 | -0.007 [-0.019, +0.008] | False |
| G1 | natl | 2 storm POD not lower by > 2 pts | -0.048 | False |
| G1 | natl | 3 gale area ratio not further from 1 | 0.959 vs N 0.946 | True |
| G1 | npac | 1 gale CSI higher than N, interval above 0 | -0.003 [-0.033, +0.017] | False |
| G1 | npac | 2 storm POD not lower by > 2 pts | -0.043 | False |
| G1 | npac | 3 gale area ratio not further from 1 | 0.954 vs N 1.023 | False |
| Gh | natl | 1 gale CSI higher than N, interval above 0 | -0.005 [-0.015, +0.004] | False |
| Gh | natl | 2 storm POD not lower by > 2 pts | -0.034 | False |
| Gh | natl | 3 gale area ratio not further from 1 | 0.948 vs N 0.946 | True |
| Gh | npac | 1 gale CSI higher than N, interval above 0 | -0.004 [-0.024, +0.006] | False |
| Gh | npac | 2 storm POD not lower by > 2 pts | -0.024 | False |
| Gh | npac | 3 gale area ratio not further from 1 | 0.964 vs N 1.023 | False |

## Held-out weeks (primary)

| basin | variant | n_cases | tiles34 | pod34 | far34 | csi34 | tiles48 | pod48 | far48 | csi48 | area34 | area48 | buoy_n | buoy_bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| natl | A  +AIFS x0.5 | 165 | 1805 | 0.688 | 0.166 | 0.605 | 352 | 0.273 | 0.040 | 0.270 | 0.837 | 0.161 | 312 | -1.809 |
| natl | G1  +AI-GFS x1 | 165 | 1805 | 0.712 | 0.196 | 0.607 | 352 | 0.324 | 0.095 | 0.313 | 0.959 | 0.242 | 363 | 0.054 |
| natl | Gh  +AI-GFS x0.5 | 165 | 1805 | 0.719 | 0.201 | 0.609 | 352 | 0.338 | 0.092 | 0.327 | 0.948 | 0.238 | 355 | -0.170 |
| natl | N  GFS+ECMWF | 165 | 1805 | 0.751 | 0.230 | 0.614 | 352 | 0.372 | 0.109 | 0.356 | 0.946 | 0.251 | 347 | -0.241 |
| npac | A  +AIFS x0.5 | 670 | 1734 | 0.642 | 0.209 | 0.549 | 208 | 0.120 | 0.107 | 0.118 | 0.844 | 0.090 | 1093 | -0.992 |
| npac | G1  +AI-GFS x1 | 670 | 1734 | 0.662 | 0.249 | 0.543 | 208 | 0.173 | 0.077 | 0.171 | 0.954 | 0.122 | 1244 | 0.998 |
| npac | Gh  +AI-GFS x0.5 | 670 | 1734 | 0.677 | 0.270 | 0.542 | 208 | 0.192 | 0.091 | 0.189 | 0.964 | 0.124 | 1242 | 0.818 |
| npac | N  GFS+ECMWF | 670 | 1734 | 0.728 | 0.314 | 0.546 | 208 | 0.216 | 0.262 | 0.201 | 1.023 | 0.159 | 1248 | 0.647 |

Differences (whole-week 95% intervals):

| basin | pair | buoy_bias | csi34 | csi48 | pod48 |
|---|---|---|---|---|---|
| natl | A - N | -1.568 [-2.019, -0.915] | -0.008 [-0.023, +0.010] | -0.086 [-0.134, -0.043] | -0.099 [-0.141, -0.054] |
| natl | G1 - A | +1.862 [+1.190, +2.285] | +0.002 [-0.010, +0.011] | +0.044 [+0.005, +0.112] | +0.051 [+0.013, +0.119] |
| natl | G1 - N | +0.295 [-0.174, +0.950] | -0.007 [-0.019, +0.008] | -0.043 [-0.061, -0.007] | -0.048 [-0.071, -0.004] |
| natl | Gh - A | +1.638 [+0.899, +2.109] | +0.003 [-0.009, +0.016] | +0.057 [+0.020, +0.116] | +0.065 [+0.031, +0.123] |
| natl | Gh - N | +0.071 [-0.365, +0.655] | -0.005 [-0.015, +0.004] | -0.029 [-0.055, -0.001] | -0.034 [-0.055, +0.000] |
| npac | A - N | -1.639 [-2.521, -1.255] | +0.003 [-0.024, +0.019] | -0.082 [-0.121, -0.061] | -0.096 [-0.139, -0.069] |
| npac | G1 - A | +1.990 [+0.293, +2.567] | -0.006 [-0.013, +0.003] | +0.052 [+0.042, +0.067] | +0.053 [+0.042, +0.067] |
| npac | G1 - N | +0.351 [-1.875, +1.224] | -0.003 [-0.033, +0.017] | -0.030 [-0.056, -0.013] | -0.043 [-0.078, -0.020] |
| npac | Gh - A | +1.811 [+0.734, +2.217] | -0.008 [-0.014, +0.004] | +0.070 [+0.038, +0.112] | +0.072 [+0.039, +0.116] |
| npac | Gh - N | +0.172 [-1.334, +0.861] | -0.004 [-0.024, +0.006] | -0.012 [-0.047, +0.024] | -0.024 [-0.058, +0.005] |

Gale-tile CSI by lead:

| basin | lead | N | A | G1 | Gh |
|---|---|---|---|---|---|
| natl | 24 | 0.735 | 0.735 | 0.749 | 0.740 |
| natl | 48 | 0.673 | 0.680 | 0.666 | 0.665 |
| natl | 72 | 0.657 | 0.623 | 0.649 | 0.651 |
| natl | 96 | 0.539 | 0.530 | 0.529 | 0.532 |
| natl | 120 | 0.473 | 0.462 | 0.453 | 0.462 |
| npac | 24 | 0.765 | 0.729 | 0.758 | 0.750 |
| npac | 30 | 0.619 | 0.663 | 0.614 | 0.613 |
| npac | 48 | 0.699 | 0.674 | 0.682 | 0.709 |
| npac | 54 | 0.601 | 0.596 | 0.598 | 0.602 |
| npac | 72 | 0.646 | 0.654 | 0.637 | 0.657 |
| npac | 78 | 0.520 | 0.506 | 0.485 | 0.473 |
| npac | 96 | 0.510 | 0.575 | 0.564 | 0.528 |
| npac | 102 | 0.479 | 0.458 | 0.459 | 0.472 |
| npac | 120 | 0.447 | 0.443 | 0.488 | 0.466 |
| npac | 126 | 0.364 | 0.347 | 0.340 | 0.347 |

Single models: mean error (kt, forecast - ASCAT) at ASCAT >= 34, all / cold air (GFS t2 - skt < -3 K) / not cold; storm-tile POD:

| basin | days | model | n_all | bias_all | n_cold | bias_cold | n_notcold | bias_notcold | tiles48 | pod48 |
|---|---|---|---|---|---|---|---|---|---|---|
| natl | all | AI-GFS | 187985 | -6.043 | 86713 | -5.613 | 101272 | -6.410 | 352 | 0.315 |
| natl | all | AIFS | 187985 | -7.443 | 86713 | -7.186 | 101272 | -7.664 | 352 | 0.071 |
| natl | all | ECMWF | 187985 | -6.790 | 86713 | -6.625 | 101272 | -6.931 | 352 | 0.361 |
| natl | all | GFS | 187985 | -6.207 | 86713 | -5.612 | 101272 | -6.716 | 352 | 0.406 |
| natl | day 1-2 | AI-GFS | 74282 | -4.128 | 35022 | -4.432 | 39260 | -3.858 | 148 | 0.351 |
| natl | day 1-2 | AIFS | 74282 | -6.326 | 35022 | -6.856 | 39260 | -5.853 | 148 | 0.054 |
| natl | day 1-2 | ECMWF | 74282 | -5.147 | 35022 | -5.689 | 39260 | -4.663 | 148 | 0.399 |
| natl | day 1-2 | GFS | 74282 | -3.672 | 35022 | -3.875 | 39260 | -3.492 | 148 | 0.453 |
| natl | day 3-5 | AI-GFS | 113703 | -7.293 | 51691 | -6.413 | 62012 | -8.027 | 204 | 0.289 |
| natl | day 3-5 | AIFS | 113703 | -8.173 | 51691 | -7.409 | 62012 | -8.811 | 204 | 0.083 |
| natl | day 3-5 | ECMWF | 113703 | -7.864 | 51691 | -7.259 | 62012 | -8.368 | 204 | 0.333 |
| natl | day 3-5 | GFS | 113703 | -7.863 | 51691 | -6.789 | 62012 | -8.757 | 204 | 0.373 |
| npac | all | AI-GFS | 138907 | -5.410 | 39241 | -5.243 | 99666 | -5.476 | 208 | 0.207 |
| npac | all | AIFS | 138907 | -7.278 | 39241 | -7.045 | 99666 | -7.369 | 208 | 0.010 |
| npac | all | ECMWF | 138907 | -6.411 | 39241 | -6.236 | 99666 | -6.480 | 208 | 0.197 |
| npac | all | GFS | 138907 | -4.934 | 39241 | -4.540 | 99666 | -5.089 | 208 | 0.370 |
| npac | day 1-2 | AI-GFS | 46295 | -3.170 | 13763 | -2.909 | 32532 | -3.280 | 68 | 0.176 |
| npac | day 1-2 | AIFS | 46295 | -4.921 | 13763 | -5.146 | 32532 | -4.826 | 68 | 0.015 |
| npac | day 1-2 | ECMWF | 46295 | -4.223 | 13763 | -4.338 | 32532 | -4.174 | 68 | 0.221 |
| npac | day 1-2 | GFS | 46295 | -2.900 | 13763 | -2.526 | 32532 | -3.059 | 68 | 0.368 |
| npac | day 3-5 | AI-GFS | 92612 | -6.530 | 25478 | -6.504 | 67134 | -6.540 | 140 | 0.221 |
| npac | day 3-5 | AIFS | 92612 | -8.456 | 25478 | -8.070 | 67134 | -8.602 | 140 | 0.007 |
| npac | day 3-5 | ECMWF | 92612 | -7.505 | 25478 | -7.261 | 67134 | -7.597 | 140 | 0.186 |
| npac | day 3-5 | GFS | 92612 | -5.951 | 25478 | -5.628 | 67134 | -6.073 | 140 | 0.371 |

## Tune weeks (second look; nothing is fitted)

No cases in this split.

