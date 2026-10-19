# Bomb watch, day 5-7: design card

*Agreed with Jason in the project thread 2026-10-19 00:19Z ("follow your defaults"); card C of `/mnt/project-files/wxmap/lab-design/cards.md`. Rules fixed before scoring: `preregistration.md`.*

**Question** (Jason's words): "Id also be interested in the bomb watch, but for day 5-7".

**What would change if the answer is yes:** a "chance of a bomb" layer on wxmap.pro/lab for the 24 h ending at day 5, 6 and 7. Lab page only.

**Truth:** anl (GFS+IFS 12 UTC analysis mean). A bomb is an analysed low that deepened at least 1 Bergeron over the 24 h ending at the valid time: (p(t-24) - p(t)) x sin 60 / sin(mean latitude) >= 24 hPa (Sanders and Gyakum 1980).

**Baseline to beat:** climatology (the share of training weeks with an analysed bomb within 500 km, by basin, cell and season half) and each deterministic model's yes/no (GFS, IFS, AIFS).

**Win means** (held-out weeks, each lead +120/+144/+168): Brier skill above zero against climatology with the lower bound of the 95% whole-week interval above zero, a better Brier than every deterministic model's yes/no, and a reliability slope of 0.8-1.25.

**Cases:** 12 UTC runs 1 Mar 2025 to 8 Oct 2026, both basins (30-67N), the same as the day 5-7 pressure study. Held-out weeks per `rk.cases.held_out`, scored once.

**Data:** the stored member MSLP lows (`mslpd57_*`) at +120/+144/+168, and +96 h pulled now (`fetch96.py`, same downloader; about 3 MB stored per run, about 2 GB in all, well under the 50 GB line). The analyses are already in the store.

**Reused / new:** the day 5-7 study's downloader and store layout, `rk.cases`, `rk.calibrate`, `rk.compare`, `rk.score.km`. New: a 24 h low-tracking and deepening rule (`bomb.py`) applied the same way to members, models and analyses. It moves into `rk/` once it passes.

**Methods tried, simplest first:**
1. Each deterministic model's yes/no (a bomb ending within 500 km).
2. Raw member share: the fraction of the 133 members (31 GEFS, 51 ENS, 51 AIFS ENS) with a bomb ending within 500 km.
3. The same share with each ensemble weighted equally.
4. The best of 2 and 3, calibrated on training weeks (`rk.calibrate.fit_logistic`).

**Known traps:** flat-bottomed lows and twin minima fake fast deepening, so the tracking uses one rule everywhere and ignores minima within 6 cells of the box edge. Lows forming inside 24 h borrow an older low's pressure. Ensembles under-deepen at day 5-7. Neighbouring cells and lows within a week are not independent, so the intervals resample whole weeks.

**Out of scope:** days 1-4 (hf-low `bomb_env` covers 24 h on ERA5), 00 UTC runs, wind.
