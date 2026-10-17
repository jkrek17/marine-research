# Storm-core lift retrain: held-out result

Scored once on 17 Oct 05:50Z with the choice locked beforehand (FINAL_CHOICE.json: retrained live28+basin model, +5 kt at 35%, Jason 23:01Z 16 Oct). 5 ISO weeks, 70 cycles x 5 leads per basin, 00/12Z valid times; storm tiles 5x5 deg with >= 150 ASCAT-seen cells.

| basin | product | storm catch | storm false alarms | storm-tile CSI | storm area vs ASCAT | gale CSI |
|---|---|---|---|---|---|---|
| Atlantic | live Core Lifted | 0.594 | 0.125 | 0.547 | 0.67 | 0.618 |
| Atlantic | retrained, +5 at 35% | 0.600 | 0.134 | 0.549 (+0.002 [-0.007, +0.009]) | 0.67 | 0.617 |
| Pacific | live Core Lifted | 0.417 | 0.182 | 0.381 | 0.53 | 0.602 |
| Pacific | retrained, +5 at 35% | 0.417 | 0.182 | 0.381 (+0.000) | 0.55 | 0.600 |

Verdict: the retrained model is indistinguishable from the live one on held-out weeks, as on tune weeks. Keep the live core model and +5 kt; no page change. Reliability of both models is the same (Pacific: 5 of 6 bins within 10 points; the member p48 share is not reliable without calibration).
With the Pacific 06/18Z-valid steps added (`score.py --final-extra`, rk.truth.water_mask): Pacific storm tiles 208 (from 108), catch 0.361 live vs 0.365 retrained, CSI 0.328 vs 0.333. Still no difference.
