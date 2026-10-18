# Tune weeks

Counts: {'cells': 19052, 'cells64': 2776, 'weeks': 15, 'storms': 35, 'storms64': 15}

## Univariate ROC area (higher value -> hurricane force at the surface)

| Predictor | ROC area |
|---|---|
| s925 | 0.774 |
| s925_minus_r10 | 0.610 |
| sst_t850 | 0.603 |
| sst_t925 | 0.572 |
| dT | 0.422 |
| tadv850 | 0.418 |
| tadv925 | 0.374 |
| gradT850 | 0.501 |
| dist_km | 0.488 |
| sin_b | 0.378 |
| cos_b | 0.356 |
| r10 | 0.795 |
| P | 0.829 |

## 5-fold week-grouped CV ROC area

| Method | CV ROC area |
|---|---|
| logistic | 0.747 |
| boosted | 0.722 |

## Logistic coefficients (standardised; + means more hurricane force)

| Predictor | Coefficient |
|---|---|
| s925 | +0.511 |
| s925_minus_r10 | +0.130 |
| sst_t850 | +3.429 |
| sst_t925 | -2.503 |
| dT | +0.375 |
| tadv850 | +0.589 |
| tadv925 | -0.541 |
| gradT850 | +0.223 |
| dist_km | -0.083 |
| sin_b | -0.284 |
| cos_b | -0.263 |
| r10 | +0.526 |

Chosen for the held-out score: **logistic** (higher CV ROC area).
