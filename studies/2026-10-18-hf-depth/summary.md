# Too shallow or too smooth? Results

Cases: 258 (fix x lead), 86 fixes, 48 storms, 21 weeks, 234 Atlantic.

## Depth and wind gap by model and lead

Depth error = model low minus archive (hPa, + = too shallow); drop ratio = model / analysis pressure drop (500 km ring minus centre, 00/12 UTC only); gap = ASCAT peak minus model peak over the same seen cells (kt).

| Model | Lead | n | Matched | Depth err mean | median | vs analysis | Drop ratio | Gap seen | Gap all cells |
|---|---|---|---|---|---|---|---|---|---|
| gfs | 24 | 86 | 87% | -1.3 | -1.0 | -1.9 | 1.08 | 4.9 | 1.5 |
| gfs | 48 | 86 | 81% | -0.4 | -0.6 | -1.0 | 1.05 | 5.5 | 1.7 |
| gfs | 72 | 86 | 76% | +2.0 | +1.5 | +1.3 | 1.02 | 6.4 | 2.8 |
| gfs | all | 258 | 81% | +0.1 | -0.6 | -0.5 | 1.07 | 5.6 | 2.0 |
| ifs | 24 | 86 | 91% | +0.2 | +0.2 | -0.5 | 1.01 | 6.7 | 2.1 |
| ifs | 48 | 86 | 87% | +1.3 | +1.0 | +0.4 | 0.99 | 7.8 | 2.4 |
| ifs | 72 | 86 | 76% | +4.1 | +3.7 | +3.0 | 0.93 | 8.6 | 3.9 |
| ifs | all | 258 | 84% | +1.9 | +1.1 | +1.0 | 0.99 | 7.7 | 2.8 |
| aifs | 24 | 86 | 87% | +1.9 | +1.8 | +1.1 | 0.95 | 15.0 | 12.5 |
| aifs | 48 | 86 | 83% | +3.5 | +2.9 | +2.3 | 0.93 | 16.3 | 13.7 |
| aifs | 72 | 86 | 72% | +5.0 | +4.4 | +3.7 | 0.85 | 17.0 | 14.9 |
| aifs | all | 258 | 81% | +3.5 | +2.8 | +2.4 | 0.92 | 16.1 | 13.7 |

Analysis low minus archive: mean +0.8 hPa, median +0.7 (72 fixes at 00/12 UTC).

## Decision fit: gap = a + b x depth error (pooled leads; whole-week 95%)

| Model | Predictor | n | a (gap at zero error, kt) | b (kt per unit) | Mean gap | Gap where error within 3 hPa (n) |
|---|---|---|---|---|---|---|
| gfs | depth vs archive | 228 | 6.1 [4.7, 7.4] | +0.35 [+0.15, +0.52] | 6.2 | 5.6 (119) |
| gfs | depth vs analysis | 246 | 5.9 [4.5, 7.3] | +0.38 [+0.18, +0.56] | 5.7 | 5.8 (131) |
| gfs | drop ratio - 1 | 246 | 6.2 [4.7, 7.6] | -8.3 [-15.5, -2.7] | 5.7 | |
| ifs | depth vs archive | 228 | 7.3 [5.5, 9.0] | +0.44 [+0.01, +0.74] | 8.1 | 6.6 (131) |
| ifs | depth vs analysis | 246 | 7.2 [5.4, 9.2] | +0.55 [+0.05, +0.91] | 7.8 | 7.4 (176) |
| ifs | drop ratio - 1 | 246 | 7.4 [5.6, 9.3] | -16.2 [-26.4, -5.2] | 7.8 | |
| aifs | depth vs archive | 228 | 15.9 [14.2, 17.6] | +0.31 [+0.01, +0.55] | 17.0 | 16.8 (107) |
| aifs | depth vs analysis | 246 | 15.3 [13.3, 17.6] | +0.42 [+0.11, +0.65] | 16.3 | 15.7 (151) |
| aifs | drop ratio - 1 | 246 | 15.4 [13.5, 17.4] | -9.4 [-14.8, -4.6] | 16.3 | |
