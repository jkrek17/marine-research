# Core-lift retrain: tune-week results (out of fold; held-out not yet scored)

All numbers: winter 2025-26 tune weeks, 00/12 UTC cycles, +24..+120 h, out-of-fold (5 folds by whole weeks), truth ASCAT real 10 m wind. Storm tiles = 5x5 deg tiles with 150+ ASCAT cells, judged at seen cells. Pacific at 00 UTC valid only.

1. **Retraining on both basins does not beat the live model.** Same +5 kt @ 35% rule: storm-tile CSI .436 vs live .435 (Atl), .209 vs .214 (Pac). Cell Brier skill: Pacific .275 [.158-.368] retrained vs .263 [.184-.340] live (live never saw the Pacific). Atlantic live .485 is in-sample (it was trained on this winter), retrained .446 out of fold. The retrained Pacific chances run high at 50-80% (says 55%, verifies 41%); the live model's Pacific chances are within 10 points from 20-80%. Store-only features (no 925/850 mb) lose ~0.01 BSS; basin flag adds nothing.
2. **The trained likelihood adds little over a plain member rule at +5 kt:** +5 where 10%+ of GEFS+ENS members have 48+ within ~100 km gives CSI .433 Atl / .203 Pac vs .435 / .214.
3. **Lift size is what moves storm catch.** Storm tiles, catch / false alarm / CSI / storm area vs ASCAT:

| rule | Atl catch | Atl FA | Atl CSI | Atl area | Pac catch | Pac FA | Pac CSI | Pac area |
|---|---|---|---|---|---|---|---|---|
| blend | 14% | 4% | .139 | 0.09 | 1% | 0% | .012 | 0.01 |
| live +5 @ 35% (today) | 47% | 13% | .435 | 0.53 | 23% | 18% | .214 | 0.27 |
| retrained +5 @ 35% | 47% | 13% | .436 | 0.53 | 22% | 22% | .209 | 0.27 |
| retrained +8 @ 35% | 68% | 27% | .542 | 1.18 | 43% | 36% | .347 | 0.95 |
| retrained +8 @ 50% | 63% | 23% | .528 | 1.03 | 35% | 31% | .300 | 0.72 |
| retrained + 10 x P | 56% | 19% | .494 | 0.85 | 29% | 28% | .264 | 0.50 |

Gale-tile CSI is unchanged by every rule (within 0.01). Against the preset win line (+5 pts catch at no more false alarms), nothing passes: every rule that catches more storm also adds false alarms. +8 kt keeps storm area under the 1.5x limit in both basins.
