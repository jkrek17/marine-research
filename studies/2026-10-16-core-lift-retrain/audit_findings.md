# Adversarial audit 2026-10-17, holes 4 and 6: the core model and its referee

Asked by the audit hand-off (Jason, "address the lessons and anything else", 04:49Z 17 Oct).

## (b) Does core likelihood hold within the winter? (`season_split.py`, tune weeks)
| basin | half | BSS live (in-sample Atl) | BSS retrained, out of fold | storm-tile catch, Core Lifted |
|---|---|---|---|---|
| Atlantic | Nov-Dec | 0.469 [0.339, 0.525] | 0.438 | 0.458 |
| Atlantic | Jan-Mar | 0.492 [0.423, 0.548] | 0.455 | 0.468 |
| Pacific | Nov-Dec | 0.300 | 0.270 | 0.282 |
| Pacific | Jan-Mar | 0.241 | 0.253 | 0.179 |

Skill holds through both halves of the winter, and the live model scored in-sample beats the retrained model scored out of fold by only ~0.03 BSS. So the drop from ~49% catch in winter to ~38% outside it is mostly season (spring-autumn storms), not over-fit. As a chance, Atlantic core likelihood is close to honest and slightly low (35-55% stated verifies 41-56%); Pacific 65-85% runs high in Jan-Mar (57-70% observed, a few hundred cells). `season_reliability.csv`.

## (c) Rain-flagged ASCAT cells (`rain_test.py`, 3,720 cases: tune out of fold + held-out, both basins)
ASCAT drops rain-flagged cells. Truth three ways: dropped (all scores so far); strict (rain cells kept where ASCAT itself reads the threshold and SMAP within 3 h agrees); upper bound (any rain cell where SMAP within 5 h reads the threshold, at the larger of ASCAT and SMAP).

| | storm cells added | Core Lifted catches of the added | of all | storm-tile CSI dropped -> with rain |
|---|---|---|---|---|
| Atlantic strict | +2.6% | 75% | 41% | 0.458 -> 0.459 |
| Atlantic upper | +9.4% | 44% | 41% | 0.458 -> 0.445 |
| Pacific strict | +1.2% | 31% | 22% | 0.266 -> 0.265 |
| Pacific upper | +7.4% | 8% (1,298 cells) | 22% | 0.266 -> 0.256 |

Gale cores (galecore@0.6), Atlantic upper bound: +8.3% gale cells, 58% of them caught vs 76% overall; area 1.19 -> 1.14x, CSI 0.676 -> 0.668. Pacific: 53% vs 65%, CSI 0.571 either way.

Census, all 00/12Z valid times of the winter (`rk.truth.ascat` with `rain_keep_kt`): rain hides 1.9-8.7% of ASCAT 34+ cells and 2.7-10.6% of 48+ cells in the Atlantic, 0-8.9% / 0-4.8% in the Pacific (strict to upper). The audit's 16-23% was the share of SMAP storm cells that ASCAT flagged anywhere in the day; at the scored times it is far smaller because SMAP and ASCAT rarely pass within hours of each other.

**Verdict:** the rain blind spot moves every score by 0.015 CSI or less, and the Atlantic core model catches rainy storm cores as often as dry ones. No retrain. Two soft spots worth watching: Pacific rainy storm cores (8% caught, small sample) and rainy gale water under the gale-core lift (58% vs 76%). Both lean toward misses, not false alarms.
