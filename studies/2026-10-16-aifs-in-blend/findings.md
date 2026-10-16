# AIFS in the blend: findings

**Answer:** keep AIFS in the blend but at half weight. On the held-out weeks, half-weight AIFS (C) caught more gale and storm-force wind than the live three-model blend in both basins, with the gale gain outside week-to-week noise; Core Lifted held-out gale-tile CSI .618 -> .630 Atlantic, .602 -> .618 Pacific; storm-tile catch .594 -> .617 and .417 -> .500. Dropping AIFS entirely (B) catches the most but adds the most false alarms (gale FAR .125 -> .199 Atlantic, .145 -> .239 Pacific) and its Pacific gale gain is not distinguishable from zero, so it failed the preset line. Truth: ASCAT real 10 m wind; buoys for bias.

| Core Lifted, held-out, +24..+120 h | gale catch | gale FA | gale CSI | storm catch | gale area / ASCAT | buoy bias 34+ |
|---|---|---|---|---|---|---|
| Atlantic A live | 68% | 13% | .618 | 59% | 0.84 | -1.2 kt |
| Atlantic B no AIFS | 76% | 20% | .637 | 65% | 0.95 | +0.3 kt |
| Atlantic C AIFS x0.5 | 71% | 15% | .630 | 62% | 0.87 | -0.6 kt |
| Pacific A live | 67% | 14% | .602 | 42% | 0.89 | -1.3 kt |
| Pacific B no AIFS | 75% | 24% | .607 | 53% | 0.99 | +0.6 kt |
| Pacific C AIFS x0.5 | 71% | 17% | .618 | 50% | 0.92 | -0.5 kt |

Gale CSI difference from live (whole-week 95%): C +0.012 [+0.006, +0.019] Atlantic, +0.017 [+0.003, +0.033] Pacific; B +0.019 [+0.006, +0.030], +0.006 [-0.044, +0.056].

**Limits:** held-out = 70 cycles x 5 leads per basin in only 5 ISO weeks, so intervals are coarse; the tune weeks (232 cycles, nothing fitted) agree in direction for both B and C. Pacific scored at 00 UTC valid only (06/18 UTC steps not yet stored); 108 Pacific held-out storm tiles. Storm tiles here judge the forecast only at ASCAT-seen cells, so catches are not comparable with the verification page's 38%.

**Checked by:** a second agent recomputed every held-out number and the bootstrap from case_counts.csv without reading this write-up or verdict.md; all matched to the third decimal and it reached the same verdict.

Files: design.md (preset line), run.py, summarize.py, summary.csv, differences.csv, verdict.md. Case counts: RK_DATA/extra/aifs-in-blend/case_counts.csv.
