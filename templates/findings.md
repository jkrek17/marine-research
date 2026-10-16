# <Study name>

*<date> · <basin(s), hour> · <period> · <N cases in M weeks> · truth: <...>*

## The answer
<Two or three sentences a forecaster can act on. What to do, or not do, and how big the difference is in knots or in storms caught.>

## The evidence
| Method | <score 1> | <score 2> | vs baseline |
|---|---|---|---|
| Baseline: ... | | | — |
| ... | | | +0.4 [+0.1, +0.7] |

*Intervals: 95%, resampling whole weeks. Held-out weeks only unless said.*

![<finding as caption>](fig1.png)

## What it does not show
- <untested area, season, lead; thin samples at storm/HF force>

## How it was done
- Truth: ...
- Baseline: ...
- Cases: ... held-out weeks: ...
- Code: `studies/<name>/` ; data: shared store (`rk.store`)
- Checked by: <independent recompute of the headline numbers: who, what matched>
