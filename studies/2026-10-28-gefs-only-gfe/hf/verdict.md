# HF line gated on GEFS only: verdict (2026-10-28)

**Verdict: the preset rule (strongest of GFS/IFS + 20 kt, kept where >= 1 GEFS member reaches 64 kt within ~1 deg) meets the win line on Atlantic held-out weeks at both 0.25 and 0.5 deg.** 86.2% of archive HF lows within 150 km (25 of 29; live pooled gate 86.2%) and HF area 0.90x the pooled gate's. No escalation to 2 or 3 members was needed. Caveat: on tune weeks the same rule catches only 71.1% (69 of 97, below 75%) at 0.85x area, so the held-out pass is a good-sample result; 2 and 3 members are worse on tune (57%, 41%) and are not chosen.

Inputs are the stored GFS/IFS 10 m and the GEFS p64 share (n = 31) from the store. Truth is the hf-low archive lows within 150 km (the warning study's `rk.score.warning_points`). HF area is warned area inside the OPC area over water (`area_nm2`; `reach` adds the ~60 nm ring). Cases are the warning study's: 00/12 UTC runs, +24 and +48 h, every hour with an issued HSF text, winter 2025-26.

## Reproduction check (live pooled gate, held-out)
Recomputed from the case files with `W.products` and the `hf_gated.py` gate (strongest of GFS/IFS/AIFS + 20, >= 1% of the 132 pooled members at 64 within 9x9 cells): both basins 26 of 32 lows = 81.25%, 8,578 nm2 (reach 24,264). The warning study reported 81% and 8,578. Exact match (tune also: 78.7%, 8,862). Atlantic alone 25 of 29 = 86.2%, 14,137 nm2.

## Held-out, rule k = 1 member (the preset rule), against the pooled gate on the same cases
| basin | res | lows | caught within 150 km | HF area nm2 | ratio to pooled | HF areas | areas with no low within 150 km |
|---|---|---|---|---|---|---|---|
| Atlantic | pooled gate | 29 | 25 (86.2%) | 14,137 | 1.00 | 102 | 74 (73%) |
| Atlantic | 0.25 deg | 29 | 25 (86.2%) | 12,683 | 0.90 | 80 | 50 (62%) |
| Atlantic | 0.5 deg | 29 | 25 (86.2%) | 12,787 | 0.90 | 80 | 50 (62%) |
| Pacific | pooled gate | 3 | 1 | 3,019 | 1.00 | 36 | 35 |
| Pacific | 0.25 deg | 3 | 1 | 2,436 | 0.81 | 21 | 20 |
| Pacific | 0.5 deg | 3 | 1 | 2,283 | 0.76 | 18 | 17 |
| Both | pooled gate | 32 | 26 (81.2%) | 8,578 | 1.00 | 138 | 109 (79%) |
| Both | 0.25 deg | 32 | 26 (81.2%) | 7,559 | 0.88 | 101 | 70 (69%) |
| Both | 0.5 deg | 32 | 26 (81.2%) | 7,535 | 0.88 | 98 | 67 (68%) |

Pacific: 3 held-out lows (11 on tune), untestable. Ungated GFS/IFS + 20 kt for reference: same 25 of 29 catch but 1.8x the pooled area (2.1x both basins), 89% of its areas without a low, so the GEFS gate cuts area without losing a low. Dropping AIFS from the live gate (pooled members kept) changes nothing: 25 of 29, 0.99x area.

Sensitivity, 0.5 deg with the literal "p64_nb > 0" (bilinear fractions count): Atlantic 86.2%, 12,874 nm2 (0.91x); same.

## Tune-week gate choice and sensitivity (Atlantic)
| members needed | tune catch (0.25 / 0.5) | tune area ratio | held-out catch (0.25 / 0.5) | held-out area ratio (0.25 / 0.5) |
|---|---|---|---|---|
| 1 | 71.1% / 71.1% | 0.85 | 86.2% / 86.2% | 0.90 / 0.90 |
| 2 | 56.7% / 53.6% | 0.51 / 0.48 | 75.9% / 75.9% | 0.59 / 0.56 |
| 3 | 41.2% / 38.1% | 0.33 / 0.30 | 62.1% / 51.7% | 0.39 / 0.36 |

Held-out was scored for the preset rule; the 2 and 3 rows are printed for sensitivity and were not used to choose. If the tune miss (71%) is read as a failure of the preset rule, no stricter gate passes on tune either, so 1 member stays the best available.

## Uncertain
- The tune/held-out gap (71% vs 86% on 97 and 29 lows) is within what 29 lows give by chance; a 75% line on 29 lows is a coarse test. Week-resampled intervals were not computed.
- "k members" for k >= 2 uses the maximum over the 9x9 neighbourhood of the stored GEFS share (k members at one cell). The live gate counts members that reach 64 anywhere in the neighbourhood, so for k >= 2 the GEFS gate is stricter than the live one. For k = 1 the two are identical.
- Both gates still draw about 2 in 3 HF areas with no archived low within 150 km (storm cores warned one category high, tip-jet water; see the warning study).
- 0.5 deg is the 0.25 deg share grid subsampled and bilinear back (`rk.features.half_deg`), as the card assumed, not NCEP's own 0.5 deg probabilities.

Code: `run_hf.py` (per-case rows, reuses the warning study's code), `summarize_hf.py`; table `results_hf.csv`; per-case rows in `RK_DATA/extra/gefs-only-gfe/hf/rows_hf.csv`.
