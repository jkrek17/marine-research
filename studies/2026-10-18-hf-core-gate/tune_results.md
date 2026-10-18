# Tune weeks

Counts: {'cores': 494, 'hf': 85, 'weeks': 18, 'valid_times': 166, 'hf_valid_times': 28, 'natl': 423, 'npac': 71, 'npac_hf': 3, 'distinct_core_rows': 350}

## Univariate ROC area (higher value -> HF)

| Predictor | ROC area | Mean in HF cores | Mean in other cores |
|---|---|---|---|
| p_max | 0.845 | 0.98 | 0.87 |
| p_mean | 0.799 | 0.75 | 0.62 |
| area | 0.797 | 1441.61 | 504.46 |
| r10_max | 0.869 | 53.58 | 46.87 |
| r10_p95 | 0.851 | 50.00 | 45.36 |
| mod_max | 0.849 | 61.35 | 52.37 |
| s925_max | 0.806 | 77.73 | 67.46 |
| p64_max | 0.877 | 0.12 | 0.02 |
| gefs_p64_max | 0.842 | 0.18 | 0.03 |
| ens_p64_max | 0.861 | 0.12 | 0.03 |
| msl_min | 0.253 | 963.34 | 975.17 |
| drop | 0.677 | 20.20 | 16.01 |
| ens_msl_min | 0.257 | 965.30 | 976.72 |
| ens_msl_sd | 0.634 | 4.72 | 3.84 |
| lat | 0.489 | 50.93 | 51.46 |
| step | 0.509 | 48.28 | 47.11 |

## Week-grouped 5-fold CV ROC area

| Method | CV ROC |
|---|---|
| logistic | 0.852 |
| boosted | 0.862 |
| p_max alone (no fit) | 0.845 |

## Logistic coefficients (standardised)

| Predictor | Coefficient |
|---|---|
| p_max | -0.268 |
| p_mean | +0.794 |
| area | +0.173 |
| r10_max | +0.496 |
| r10_p95 | +0.059 |
| mod_max | +0.254 |
| s925_max | +0.092 |
| p64_max | +0.416 |
| gefs_p64_max | -0.016 |
| ens_p64_max | +0.202 |
| msl_min | -0.025 |
| drop | -0.298 |
| ens_msl_min | -0.363 |
| ens_msl_sd | +0.494 |
| lat | -0.182 |
| step | +0.176 |

Chosen: **boosted**.
