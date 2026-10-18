# Held-out weeks (scored once)

Method: boosted. Counts: {'cores': 147, 'hf': 39, 'weeks': 5, 'valid_times': 51, 'hf_valid_times': 11, 'natl': 115, 'npac': 32, 'npac_hf': 4, 'distinct_core_rows': 99}

| | ROC area |
|---|---|
| model | 0.905 |
| p_max | 0.888 |
| r10_max | 0.912 |

Model minus p_max: +0.017 [-0.112, +0.102]
Model minus r10_max: -0.007 [-0.080, +0.039]
Brier skill: 0.353

## Flagging at the tune-matched threshold (0.41)

| Basin | Lead | Cores | HF cores | Flagged | Hits | Hit rate | False-alarm ratio |
|---|---|---|---|---|---|---|---|
| all | all | 147 | 39 | 21 | 18 | 0.46 | 0.14 |
| all | 24 | 53 | 14 | 11 | 9 | 0.64 | 0.18 |
| all | 48 | 46 | 13 | 5 | 5 | 0.38 | 0.00 |
| all | 72 | 48 | 12 | 5 | 4 | 0.33 | 0.20 |
| natl | all | 115 | 35 | 19 | 17 | 0.49 | 0.11 |
| natl | 24 | 43 | 12 | 10 | 8 | 0.67 | 0.20 |
| natl | 48 | 36 | 12 | 5 | 5 | 0.42 | 0.00 |
| natl | 72 | 36 | 11 | 4 | 4 | 0.36 | 0.00 |
| npac | all | 32 | 4 | 2 | 1 | 0.25 | 0.50 |
| npac | 24 | 10 | 2 | 1 | 1 | 0.50 | 0.00 |
| npac | 48 | 10 | 1 | 0 | 0 | 0.00 | nan |
| npac | 72 | 12 | 1 | 1 | 0 | 0.00 | 1.00 |

Pass (ROC beats p_max with interval above 0, Brier skill > 0): False
