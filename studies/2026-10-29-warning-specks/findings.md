# Findings

**Answer: drop gale warning pieces under 32 cells (about 2 square degrees).** That's the largest size that passes the preset in both basins. Held-out weeks, from `results.md`:

| | events caught | covered (ASCAT 34 kt cells inside) | false cells | pieces per map | reach (60 nm ring) |
|---|---|---|---|---|---|
| North Atlantic raw | 99.9% | 98.2% | 22.0% | 16.0 | 764,785 nm2 |
| North Atlantic, under 32 dropped | 98.9% | 98.2% | 21.0% | 3.6 | 687,805 nm2 (-10%) |
| North Pacific raw | 100% | 98.6% | 19.8% | 27.4 | 985,786 nm2 |
| North Pacific, under 32 dropped | 100% | 98.5% | 19.0% | 4.3 | 853,648 nm2 (-13%) |

- 732 held-out Atlantic events, 53 Pacific. At 64 cells the Atlantic loses 1.9 points of events caught, which fails the preset.
- The specks are not empty. Even 4-cell pieces sit next to small ASCAT gale pockets, but the pockets they catch are a few cells each and the share of gale water covered does not move.
- Filling enclosed gaps changes nothing measurable (+0.1 point covered, same reach), so it is left out.
- Live run 18Z 28 Oct, all steps: 2.5% of gale warning cells are removed.

Rows: `RK_DATA/extra/warning-experiment/results/rows_specks.csv` (13,288 rows).

**Shipped:** awips-tools `marine_wind/pipeline/storm.py` (`WARN_GALE_MIN = 32`, `drop_small`, joined across the date line). The page, the forecast records and the nightly verification all carry the same line.

**Not done:** the Pacific line's edge is still ragged on big areas (the edge itself, not specks); a smoothed outline would be drawing only, and has not been tried.
