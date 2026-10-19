# Bomb watch, day 5-7: rules fixed before any score (2026-10-19)

## Tracking and the bomb rule (same code for members, models and analyses)
- Lows: local minima of MSLP at 0.25 deg, 13-cell window, below 1012 hPa, more than 6 cells from the box edge (the stored member lows; the same finder on deterministic and analysis grids), then deduplicated within 150 km keeping the deepest.
- 24 h track: each low at t takes the nearest low of the same member at t-24 within 1,200 km. No match means no bomb.
- Bomb: (p(t-24) - p(t)) x sin 60 / sin(mean of the two latitudes) >= 24 hPa, and the end latitude is at least 30N.

## Forecast and truth on a grid
- A 2 deg grid over each basin box. A cell has an event when an analysed bomb ends within 500 km of its centre. The forecast is the share of members (or a model's yes/no) with a bomb ending within 500 km.
- Leads: +120 (window +96 to +120), +144, +168. Valid times are 12 UTC.

## Scores
- Brier score and Brier skill against climatology. Climatology is the event frequency for the cell over training weeks in the same half-year (Nov-Mar, Apr-Oct), basin-pooled if fewer than 20 training cases. ROC area, reliability (10 bins) and slope.
- Intervals: 95%, 2,000 resamples of whole ISO weeks (`rk.compare`).
- Calibration (method 4): `rk.calibrate.fit_logistic` per lead, fitted on training weeks only.

## Decision
The layer passes when, at all three leads on held-out weeks, the chosen method has BSS > 0 against climatology with a lower bound > 0, a Brier score below each deterministic model's, and a reliability slope of 0.8-1.25. If it passes at +120 and +144 but not +168, the page shows day 5-6 only.

## Prior (written before scoring)
The ensemble shares will be skilful against climatology at day 5 and weaker by day 7, with BSS of roughly +0.05 to +0.15. The raw shares will read low, which calibration fixes. The deterministic yes/no will have a worse Brier than the calibrated share at every lead.
