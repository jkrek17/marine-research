# Storm-force truth: ASCAT against SMAP, buoys and ships

*2026-10-16 · North Atlantic and North Pacific, 30-67N · winter 2025-26 (1 Nov - 31 Mar, 151 days) · truth: no single truth; two independent instruments (ASCAT, SMAP) and buoys/ships*

## The answer
At the storm-force line ASCAT holds up. Where both instruments see the same sea within 3 h, SMAP reads 0.4 kt above ASCAT at 48-56 kt (interval -0.4 to +1.2), inside the ±2 kt band set in advance, so ASCAT stays the storm-force referee unchanged and no adjustment goes into the kit. Above 56 kt the two part company, and at hurricane force there are too few pairs to say who is right. ASCAT's rain flag also hides at least 16% of the storm-force sea SMAP sees, so ASCAT-based scores undercount storm-force area.

## The evidence
SMAP minus ASCAT, equivalent-neutral kt. ASCAT is averaged to SMAP's ~40 km footprint first. Bands are on the mean of the two readings. Both basins pooled.

| Band (mean of pair) | Same-cell pairs within 3 h | Storm peaks, storms found in ASCAT | Storm peaks, storms found in SMAP |
|---|---|---|---|
| 48-56 kt | +0.4 [-0.4, +1.2], 14,236 cells | +1.5 [+0.3, +2.6], 55 pairs | +2.0 [+0.9, +3.4], 37 pairs |
| 56-64 kt | +2.4 [+1.0, +3.6], 2,266 cells | +6.1 [+3.8, +8.2], 48 pairs | -1.1 [-3.8, +2.2], 17 pairs |
| 64+ kt | +6.5 [-0.8, +12.2], 137 cells, 8 weeks | +10.3 [+4.6, +14.3], 14 pairs | 1 pair |
| All 25+ kt | +1.05 [+0.89, +1.20], 882,526 cells | | |

*Intervals: 95%, resampling whole weeks. All weeks; the held-out weeks agree in sign (storms found in ASCAT: +2.2 at 48-56, n=11; +4.6 at 56-64, n=12; +8.1 at 64+, n=6, intervals in `results/numbers.md`).*

- **Same-cell pairs are the fairest test**: no storm selection, same place, same footprint. They put the two instruments within half a knot at the storm-force line and about 1 kt apart overall.
- **Storm peaks depend on which instrument picks the storm.** Picked by ASCAT, SMAP's peak is higher; picked by SMAP, it is level or lower. Part of that is how the peaks were taken: the non-selecting instrument's peak is the maximum of ~400 cells in a 300 km disk, the selecting one's is the maximum inside the storm. The two directions agree only at 48-56 kt (+1.5 and +2.0).
- **Metop-B and Metop-C** (storms found in ASCAT): +4.7 [+3.2, +6.2] and +3.5 [+1.9, +4.8], after the kit's existing halfway intercalibration.
- **Rain**: of 18,870 SMAP storm-force cells that ASCAT also passed within 3 h, 15.8% [12.0, 19.3] were rain-flagged by ASCAT and so dropped from every ASCAT score: 13.6% in the Atlantic, 22.8% in the Pacific. ASCAT still read a median 51 kt there. This is a floor, since rain cells with no ASCAT wind at all cannot be counted.
- **Buoys and ships**: no pair at 48 kt or more for either instrument. ASCAT minus buoys at 25-34 kt: -1.7 [-2.0, -1.5] kt (151 pairs); at 34-48 kt ASCAT minus all obs: 0.0 [-2.1, +1.7] (32 pairs). SMAP had only 63 obs pairs, none at 34+, because it passes at about 06 and 18 local time.

![ASCAT and SMAP agree at the storm-force line; above 56 kt the answer depends on which instrument picks the storm](results/peaks.png)

## What it means for other numbers
- **The 48 kt line**: storm-force counts, chances and the core lift's out-of-sample storm catch (about 38% of ASCAT storm boxes) stand as scored; no offset to apply.
- **Storm-force area is undercounted** by ASCAT's rain flag, by at least 16% (23% in the Pacific). Detection scores against ASCAT cannot see storm force in heavy rain. A rain-aware truth (keep ASCAT's rain-flagged storm-force cells where SMAP confirms them) is the obvious follow-up; not done here.
- **Hurricane force is not settled.** Above 56 kt SMAP tends to read higher, which fits the known tendency of C-band scatterometers to read low at the top end, but storms picked by SMAP do not show it, and there are only 14 ASCAT-picked pairs at 64+ (the design asked for 30). Any HF verification against ASCAT should say this.

## What it does not show
- Which instrument is right above 56 kt. SMAP's own high-wind calibration (per RSS's published description) comes from tropical cyclones, not winter lows.
- Same-cell pairs are up to 3 h apart, so storm motion adds scatter, though not a sign.
- Only 2 storm pairs are within 90 min of each other; the time-gap split carries no information.
- Spring, autumn and summer; latitudes outside 30-67N.

## How it was done
- **Instruments**: ASCAT RSS v2.1 (`rk.truth.ascat_day`, rain dropped unless counted, Metop-B/C intercalibrated halfway) averaged to a ~40 km footprint (3 x 3 same-pass weighted mean); SMAP RSS v1.0 FINAL daily (`rk.truth.smap_day`, new in this study). Both equivalent-neutral 10 m wind.
- **Method 1**: storm objects (connected 40+ kt with a 48+ peak) in one instrument, the other's pass within 3 h, peaks within 300 km; both directions.
- **Method 2**: same 0.25 deg cell, both readings within 3 h (and within 90 min, high latitudes only: 9,152 cells, +2.2 [+1.7, +2.7] overall, too few above 48 kt).
- **Method 3**: GDAS marine buoys and ships (`rk.truth.obs`; Atlantic 12 UTC, Pacific 00 UTC cycles), within 30 min and 25 km.
- **Method 4**: SMAP 48+ cells against ASCAT's rain flag at the same cell within 3 h.
- **Decision rule set before running** (`design.md`): within ±2 kt at 48-64 kt, ASCAT stands. Met at 48-56 kt by every method; at 56-64 kt the same-cell offset is +2.4 [+1.0, +3.6], straddling the band, and the storm methods disagree, so no adjustment is fitted.
- **Code**: `compare.py`, `obs_fill.py`, `obs_pairs.py`, `summarize.py`; tables in `results/`. Data: the shared store (`truth/ascat`, `truth/smap`, `truth/obs`).
- **Checked by**: PENDING
