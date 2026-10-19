# Storm Twins: findings

**Answer: passes the design card's rule.** Twins found from a GFS f024 patch give a share of hurricane-force twins that beats climatology and is reliable enough to show, though it reads a little low.

Cases: hf-low's 18,167 matched GFS lead 24 h fixes, 2,122 cycles (00Z and 12Z, 2021-10-01 to 2026-04-30), 836 of them reached hurricane force (ERA5 pipeline A gust class 3 over hours 24-48, a proxy). Twins come only from other seasons of the 32,288-fix ERA5 library (Oct-Apr 2014-15..2021-22).

| | Value | Rule |
|---|---|---|
| Brier skill vs basin-month climatology | +0.088 | > 0: pass |
| by season 2021-22 / 22-23 / 23-24 / 24-25 / 25-26 | +0.076 / +0.065 / +0.102 / +0.110 / +0.086 | all positive |
| ROC area | 0.803 | |
| Reliability slope | 1.23 | 0.8-1.25: pass |

Reliability (`results/gfs_check_reliability.csv`):

| Share of twins at HF | Fixes | Mean share | Observed HF |
|---|---|---|---|
| 0-10% | 15,370 | 1.6% | 2.3% |
| 10-20% | 2,203 | 12.2% | 13.6% |
| 20-30% | 495 | 22.4% | 27.5% |
| 30-40% | 86 | 32.2% | 50.0% |
| 40-50% | 13 | 41.5% | 69.2% |

The observed rate is above the share in every bin, and the gap widens above 30% (99 fixes, so loose). No fix had more than 14 of 30 twins at HF. For the lab card: show "x of 30 twins reached hurricane force", and say that a share above 30% has verified about half the time or more.

Compared with the ERA5-in test in hf-low (Brier skill +0.107, slope 1.12), feeding GFS patches costs about a fifth of the skill.

Verified: an independent recompute from `results/gfs_check.csv.gz` matched every number (Brier skill 0.0877, ROC 0.8027, slope 1.226, the counts and the bins), with no NaNs or duplicate (cycle, track) pairs.

Rerun: `HF_RESEARCH=<hf-low research checkout> python3 build_library.py`, then `gfs_check.py pull 8` (about 6.4 GB streamed) and `gfs_check.py score`.
