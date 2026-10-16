# Desk added value: interim findings

*2026-10-16 · both basins, OPC High Seas Forecast areas only · desk grids 14 Jan - 31 May 2026 (276 model cycles, 21 weeks) · truth: ASCAT (real 10 m, Metop B/C met halfway) · INTERIM: winter (Jan-Mar) has no ECMWF columns and no routine/attention split yet; those fields land in the store late on 16 Oct.*

## The answer so far
- **Each shift makes the grid better than the one it started from**, at every lead in both basins: 0.2 kt better at day 1 rising to 0.5-0.75 kt by day 5 (wind error at 25 kt and up against ASCAT), every interval clear of zero in the winter weeks.
- **On wind speed alone the models beat the desk early.** GFS is 0.4-0.8 kt closer to ASCAT on days 1-2. In April-May the 3-model mean (GFS, ECMWF, AIFS) is 0.65-1.1 kt closer than the desk on every day in the Atlantic. The desk passes GFS from day 4 (clear of zero in the Atlantic in April-May only).
- **At storm force the desk catches far more.** Atlantic, April-May: the desk catches 29% of ASCAT 48+ kt cells against 9% for GFS and 2% for the 3-model mean, and with fewer false alarms than GFS (58% of its storm-force cells vs 73%). The desk reads 2-3 kt above ASCAT in its strong-wind areas on days 1-2; that is the desk lifting the cores the models smooth, the same thing Core Lifted does.
- **Against an automatic update** (the previous grid moved by the change in the models, April-May) the desk is no better at days 1-2 and 0.2-0.4 kt better at days 3-5 in the Atlantic; the Pacific is mixed.
- **Edits are slightly better than a coin flip.** About a fifth of the water is edited by more than 2 kt each shift at day 1, rising to over half by day 6. Of the edited cells ASCAT saw, 51-57% moved toward ASCAT and 37-46% away (the rest no closer either way).
- **Routine vs attention (April-May only, a quiet season):** 96% of the water is ride (all three models under 30 kt), and 94% of the desk's edits fall there. A third of ride water is edited each shift; 56% of those edits move toward ASCAT. In focus and high-impact water, edits move toward ASCAT 48% of the time, no better than chance. On these numbers most desk time goes into routine water, where the gain is small, and the edits where the models disagree do not beat the models yet. Winter is the real test of this and waits on the ECMWF fields.

## The evidence
Wind error at 25 kt and up against ASCAT (kt; cells where forecast or ASCAT reach 25 kt), desk minus each baseline, the same cells and valid times, 95% intervals from resampling whole weeks. Negative = desk better.

| Desk minus | Basin | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 |
|---|---|---|---|---|---|---|
| Previous grid, Jan-Mar | Atlantic | -0.23 [-0.31,-0.15] | -0.37 [-0.50,-0.26] | -0.56 [-0.68,-0.45] | -0.60 [-0.78,-0.41] | -0.75 [-1.08,-0.47] |
| Previous grid, Jan-Mar | Pacific | -0.21 [-0.36,-0.07] | -0.31 [-0.50,-0.16] | -0.42 [-0.58,-0.29] | -0.52 [-0.71,-0.32] | -0.49 [-0.61,-0.34] |
| GFS, Jan-Mar | Atlantic | +0.44 [0.23,0.66] | +0.25 [0.02,0.51] | +0.06 [-0.16,0.33] | -0.20 [-0.46,0.08] | +0.09 [-0.41,0.57] |
| GFS, Jan-Mar | Pacific | +0.64 [0.07,1.16] | +0.79 [0.17,1.38] | +0.17 [-0.47,0.76] | -0.33 [-0.93,0.22] | -1.40 [-2.49,-0.26] |
| Automatic update, Apr-May | Atlantic | -0.00 [-0.11,0.11] | -0.12 [-0.27,0.01] | -0.17 [-0.29,-0.04] | -0.26 [-0.40,-0.10] | -0.40 [-0.60,-0.21] |
| 3-model mean, Apr-May | Atlantic | +0.99 [0.66,1.32] | +1.01 [0.70,1.27] | +0.85 [0.63,1.07] | +0.65 [0.37,0.96] | +0.77 [0.36,1.14] |
| 3-model mean, Apr-May | Pacific | +1.03 [0.49,1.71] | +1.17 [0.65,1.74] | +0.97 [-0.23,2.09] | +1.14 [-0.33,2.50] | +0.39 [-1.06,1.87] |

Storm force (48 kt), April-May, all leads, same cells: Atlantic desk / GFS / 3-model mean catch 29% / 9% / 2% of ASCAT 48+ kt cells (CSI .20 / .07 / .02); Pacific 43% / 32% / 7% (CSI .30 / .28 / .06). The 3-model mean almost never reaches 48 kt, so its low false-alarm rate is not skill.

## What it does not show
- **No winter class split and no winter ECMWF column yet.** The routine/attention numbers are April-May, when ride water is 96% of the area and high-impact water is 0.02%.
- **OPC water is in the archived desk grids only from 13 Jan 2026**; before that the oceanic grid covers 14% of the Atlantic area and 25% of the Pacific. One winter half is all there is.
- **The Pacific model comparison is thin**: models are stored at 00/12Z valid, and Pacific ASCAT is mostly 06/18Z, so 26-56 cycles per day; storm force in the Pacific rests on few cells.
- Wind error at 25 kt and up selects different cells for a method that runs high; on cells where ASCAT itself is 25+ kt the ordering is the same but the desk's high reading turns into a low reading from day 3 (cores still too weak at long range, as for every model).
- No blend or Core Lifted column yet (needs ensembles); no situations table yet.

## How it was done
- Desk grid: NDFD oceanic wind speed (YCYZ98 days 1-3, YCYZ97 days 4-7), averaged onto 0.25 deg. The Atlantic's update after the 00Z/12Z runs lands in the ~10Z/22Z snapshots, the Pacific's in the ~13Z/01Z snapshots (measured on 5 days; `rk.desk.issue_for`). Previous grid = the previous update; automatic update = previous grid + (3-model mean now minus 3-model mean 12 h earlier) at the same valid time.
- Truth: ASCAT (`rk.truth.ascat`, real 10 m wind, rain dropped), OPC High Seas Forecast areas only (`rk.basins.opc_mask`). Classes: the marine wind page rule (`rk.classes`, identical to the page's `focus_grid`).
- Code: `studies/2026-10-16-desk-value/score.py`, `summarize.py`; tables in `results/`; row tables in the shared folder `research-data/extra/desk-value/`.
- Checked by: a second agent recomputed every number above from the row tables without reading the summary code or this write-up; all paired differences matched to 0.01 kt. It caught that the summary had the Atlantic 3-model-mean range as +0.85 to +1.14 (it is +0.65 to +1.14, corrected here) and that the `toward`/`away` columns count all ASCAT cells, not only edited ones (the shares above use the edited-cell columns).
