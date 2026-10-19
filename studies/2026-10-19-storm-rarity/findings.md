# How rare is this storm: ERA5 and the archive agree on depth, so the badge needs no offset

*2026-10-19 · N Atlantic and N Pacific · OPC archive HF fixes 2004-2025 matched to ERA5 pipeline A tracks · truth: OPC archive pressure*

## The answer
ERA5 puts HF lows within about 1 hPa of the OPC archive (event medians: Atlantic +1.0 hPa, interquartile range -1.0 to +2.0; Pacific 0.0, -2.0 to +1.5). The archive records whole hPa, so this is at its resolution. A forecast low can be ranked against ERA5 lifetime minima without an adjustment.

## The evidence
| Basin | Matched fixes | Events | ERA5 minus archive, median of fixes | Median of event medians [IQR] |
|---|---|---|---|---|
| Atlantic | 2,314 | 730 | +1.0 hPa | +1.0 [-1.0, +2.0] |
| Pacific | 2,295 | 668 | 0.0 hPa | 0.0 [-2.0, +1.5] |

Examples from `rk.climo.rarity`: 950 hPa at 55N 30W in January is deeper than 93% of 512 nearby January lows; 958 hPa at 58N 150W in November, 96% of 537.

## What it does not show
- Only HF lows were matched; weaker lows may differ. ERA5 is a proxy and the matched set is HF-equivalent tracks only.
- The ranking is against lifetime minima, so a deepening low reads lower than it will end up.

## How it was done
- `offset_check.py` (writes `offset.csv`): each archive HF fix with a pressure, the nearest ERA5 HF-equivalent track fix at the same time within 300 km.
- Code: `rk/climo.py`, `tests/test_climo.py`.
- Checked by: no independent recompute yet (a descriptive check with no tuning).
